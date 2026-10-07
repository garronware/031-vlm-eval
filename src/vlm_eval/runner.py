"""`vlm-eval run-eval <plan>`: sends an approved plan's drawings, extracts each reply, keeps count.

Each model runs in its own thread, one call at a time, so makers are asked in
parallel but never flooded. After each reply, extraction runs straight away and
its cost counts toward the plan's spending.

Before every new call the runner checks three things:
- a stop request (`vlm-eval stop-run`, or Ctrl+C): stop cleanly;
- spending past the latest approval plus 25%: pause and wait for a new approval;
- nothing else left: done.

A call already under way always finishes and is saved, so nothing paid for is
lost. Running the same plan again picks up where it stopped: saved replies and
extractions are never redone.
"""

from __future__ import annotations

import os
import signal
import threading
import time
from decimal import Decimal
from typing import Any

from dotenv import load_dotenv

from vlm_eval import extraction, paths, replay
from vlm_eval.calls import PROMPT, send_drawing
from vlm_eval.models_config import load_extractor
from vlm_eval.run_plan import (
    DONE,
    PAUSED,
    RUNNING,
    STOPPED,
    PlanError,
    Todo,
    call_file,
    describe,
    load,
    save,
    spent,
    todo,
)


def request_stop() -> None:
    """Ask any running run to stop after the calls under way."""
    paths.STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
    paths.STOP_FILE.write_text("stop\n")


def _missing_keys(models) -> list[str]:
    load_dotenv(paths.ENV_FILE)
    keys = {m.key for m in models} | {load_extractor().key}
    return sorted(k for k in keys if not os.environ.get(k, "").strip())


class _Run:
    """Shared state for one run's threads."""

    def __init__(self, plan, limit: Decimal, spent_so_far: Decimal):
        self.plan = plan
        self.limit = limit
        self.spent = spent_so_far
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.reason = ""  # STOPPED or PAUSED once a thread has stopped for it
        self.failed: list[str] = []

    def may_start(self) -> bool:
        """Checked before every new call."""
        with self.lock:
            if self.reason:
                return False
            if self.stop.is_set() or paths.STOP_FILE.exists():
                self.reason = STOPPED
            elif self.spent > self.limit:
                self.reason = PAUSED
            return not self.reason

    def add(self, cost: Decimal, line: str) -> None:
        with self.lock:
            self.spent += cost
            print(f"  {line} (spent so far ${self.spent:.4f})", flush=True)


def _cost(record: dict[str, Any]) -> Decimal:
    return Decimal(record.get("cost_usd") or 0)


def _work(run: _Run, items: list[Todo], connections, extract_connection, sleep) -> None:
    plan = run.plan
    for item in items:
        if not run.may_start():
            return
        name = f"{item.model.name}, {item.drawing}, run {item.run_number}"
        path = call_file(plan, item.model, item.drawing, item.run_number)
        cost = Decimal(0)
        if item.needs_call:
            record = send_drawing(
                item.model,
                item.drawing,
                plan.calls_folder,
                item.run_number,
                connection=(connections or {}).get(item.model.maker),
                sleep=sleep,
                plan_name=plan.name,
                prompt=plan.prompt or PROMPT,
            )
            cost += _cost(record)
            if record["error"]:
                run.failed.append(f"{name}: {record['error']}")
                run.add(cost, f"{name}: NO REPLY after {record['attempts']} attempt(s)")
                continue
        extracted = extraction.extract(
            path, connection=extract_connection, sleep=sleep, plan_name=plan.name
        )
        if extracted.get("error"):
            run.failed.append(f"{name}: extraction got no reply: {extracted['error']}")
        else:
            cost += _cost(extracted)
        run.add(cost, f"{name}: done")


def run(
    name: str,
    *,
    connections: dict[str, Any] | None = None,
    extract_connection: Any = None,
    sleep=time.sleep,
    open_page: bool = False,
) -> str:
    """Run an approved plan until it's done, stopped, or over its limit. Returns the status."""
    plan = load(name)
    if not plan.approvals:
        print(f"{name} isn't approved yet, so nothing was sent.")
        print(f"To see the estimate and approve: uv run vlm-eval approve-run {name}")
        return plan.status
    left = todo(plan)
    models = {t.model for t in left}
    missing = _missing_keys(models) if connections is None else []
    if missing:
        print(f"No key in .env for {', '.join(missing)}. Nothing was sent.")
        return plan.status

    paths.STOP_FILE.unlink(missing_ok=True)  # starting again means go
    run_state = _Run(plan, plan.limit_usd, spent(plan))
    plan.status, plan.note = RUNNING, ""
    save(plan)
    print(f"Running {name}: {len(left)} to do. Stop any time with: uv run vlm-eval stop-run")

    previous = None
    if threading.current_thread() is threading.main_thread():
        previous = signal.signal(signal.SIGINT, lambda *_: run_state.stop.set())
    try:
        threads = [
            threading.Thread(
                target=_work,
                args=(
                    run_state,
                    [t for t in left if t.model == model],
                    connections,
                    extract_connection,
                    sleep,
                ),
                daemon=True,
            )
            for model in sorted(models, key=lambda m: m.id)
        ]
        for t in threads:
            t.start()
        while any(t.is_alive() for t in threads):
            for t in threads:
                t.join(timeout=0.5)
    finally:
        if previous is not None:
            signal.signal(signal.SIGINT, previous)
        paths.STOP_FILE.unlink(missing_ok=True)

    plan = load(name)
    still_left = todo(plan)
    so_far = spent(plan)
    if not still_left:
        plan.status, plan.note = DONE, ""
    elif run_state.reason == PAUSED:
        plan.status = PAUSED
        plan.note = (
            f"spent ${so_far:.4f}, past ${run_state.limit:.4f} "
            f"(approved ${plan.approved_usd:.4f} + 25%)"
        )
    else:
        plan.status = STOPPED
        plan.note = (
            f"{len(run_state.failed)} got no reply; run again to retry"
            if run_state.failed and run_state.reason != STOPPED
            else "stopped on request"
        )
    save(plan)

    print()
    for line in run_state.failed:
        print(f"  NO REPLY: {line}")
    print(describe(plan))
    print(f"\n  Estimated: ${plan.approved_usd:.4f}   Actual so far: ${so_far:.4f}")
    if plan.status == PAUSED:
        print(f"\nPaused. To continue, approve again: uv run vlm-eval approve-run {name}")
    elif plan.status == STOPPED:
        print(f"\nStopped. To resume: uv run vlm-eval run-eval {name}")
    replay.run(plan.name, open_page=open_page)
    return plan.status


def cli_run(args: list[str]) -> None:
    names = [a for a in args if not a.startswith("--")]
    if not names:
        print("usage: vlm-eval run-eval <plan name>")
        return
    try:
        run(names[0], open_page="--open" in args)
    except PlanError as exc:
        print(exc)


def cli_stop(args: list[str]) -> None:
    request_stop()
    print("Stop requested: the run stops after the calls under way finish and are saved.")
