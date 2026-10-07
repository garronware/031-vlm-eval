"""Run plans: what a run sends, what it should cost, and what Garron approved (SPEC 2.7, 2.8).

A plan names the models (each with its thinking level), the drawings, and the runs
per model. It is saved as one JSON file under runs/plans/ and never sends
anything itself; `runner.py` does the sending, and only after an approval is saved.

Calls land where they would for any plan with the same models, so results add up
across plans and days: real runs share `runs/calls/main/`, and a 60-drawing plan
after a 30-drawing plan sends only the 30 new drawings. Test runs (fewer than 30
drawings) go to `runs/calls/test/` and are marked as test runs, so they can never be
published (SPEC 2.11).
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from vlm_eval import extraction, paths
from vlm_eval.calls import PROMPTS, call_path, cost_usd, is_done, load_call, model_folder
from vlm_eval.models_config import MAKER_DEFAULT, Model, load_extractor, load_models

MAIN_FOLDER = "main"  # real runs, 30 drawings or more
TEST_FOLDER = "test"  # test runs, kept out of published results
DEFAULT_PROMPT_ID = "stock-shape"  # what new runs use; see calls.PROMPTS
SMALLEST_REAL_RUN = 30
PAUSE_OVER_ESTIMATE = Decimal("1.25")
MAKERS_WITH_CONNECTIONS = ("anthropic", "openai", "google")

# The default test run: 5 drawings from the 30-set that cover the mix of shape,
# print type, PDF type, and one chain.
TEST_DRAWINGS = (
    "201533-020.pdf",  # CUBE, dual, text
    "201548-030.pdf",  # CYL, dual, text
    "201258-012.pdf",  # CYL, dual, image-only
    "202985-001.pdf",  # CUBE, inch-only, image-only
    "90-100012-B.pdf",  # CYL, inch-only, text, chain
)

# A rough guess per call for a model with no saved calls yet (Chunk 4's guess, which
# came out about 5x too high, so it errs on the safe side).
FALLBACK_INPUT_TOKENS = 5_000
FALLBACK_OUTPUT_TOKENS = 8_000
FALLBACK_REPLY_CHARS = 3_000  # for estimating extraction before a reply exists

# Statuses a plan moves through.
PLANNED, RUNNING, STOPPED, PAUSED, DONE = (
    "planned",
    "running",
    "stopped",
    "paused over estimate",
    "done",
)


class PlanError(ValueError):
    """A plan that can't be made or run as asked. Shown to Garron as-is."""


@dataclass
class RunPlan:
    name: str
    created: str
    test_run: bool
    calls_folder: str  # main | test
    drawing_choice: str  # 30 | 60 | 141 | test
    drawings: list[str]
    models: list[dict[str, str]]  # [{"id": ..., "thinking": ...}]
    runs: int
    estimate_usd: str  # at planning time, for everything not yet saved
    prompt_id: str = "bare"  # which of calls.PROMPTS was asked
    prompt: str = ""  # the exact words, kept with the plan for the record
    approvals: list[dict[str, str]] = field(default_factory=list)
    status: str = PLANNED
    note: str = ""  # why it stopped, in plain words

    @property
    def approved_usd(self) -> Decimal | None:
        return Decimal(self.approvals[-1]["approved_usd"]) if self.approvals else None

    @property
    def limit_usd(self) -> Decimal | None:
        """Spending that pauses the run: the latest approval plus 25%."""
        approved = self.approved_usd
        return None if approved is None else approved * PAUSE_OVER_ESTIMATE


def plan_path(name: str) -> Path:
    return paths.PLANS / f"{name}.json"


def save(plan: RunPlan) -> None:
    paths.PLANS.mkdir(parents=True, exist_ok=True)
    plan_path(plan.name).write_text(json.dumps(dataclasses.asdict(plan), indent=2) + "\n")


def load(name: str) -> RunPlan:
    path = plan_path(name)
    if not path.exists():
        raise PlanError(f"No run plan named {name!r}. See: uv run vlm-eval list-runs")
    return RunPlan(**json.loads(path.read_text()))


def all_plans() -> list[RunPlan]:
    return [load(p.stem) for p in sorted(paths.PLANS.glob("*.json"))]


# --- what a plan sends ------------------------------------------------------------


def _set_rows() -> list[dict[str, str]]:
    with paths.DRAWING_SETS_CSV.open(newline="") as fh:
        return list(csv.DictReader(fh))


def drawings_for(choice: str, test_count: int = len(TEST_DRAWINGS)) -> list[str]:
    """The drawings in a set, always in the same order."""
    rows = _set_rows()
    if choice == "141":
        return [r["file"] for r in rows]
    if choice in ("30", "60"):
        return [r["file"] for r in rows if r[f"in_set_{choice}"] == "true"]
    if choice == "test":
        if not 1 <= test_count < SMALLEST_REAL_RUN:
            raise PlanError(f"A test run has 1 to {SMALLEST_REAL_RUN - 1} drawings.")
        rest = [f for f in drawings_for("30") if f not in TEST_DRAWINGS]
        return (list(TEST_DRAWINGS) + rest)[:test_count]
    raise PlanError(f"Drawings must be 30, 60, 141 or test, not {choice!r}.")


def _model(model_id: str, thinking: str) -> Model:
    models = {m.id: m for m in load_models()}
    if model_id not in models:
        raise PlanError(f"{model_id!r} is not in config/models.yaml.")
    model = models[model_id]
    if model.maker not in MAKERS_WITH_CONNECTIONS:
        raise PlanError(
            f"{model.name} can't be run: no connection is built for {model.maker}. "
            "See config/models.yaml for why."
        )
    if thinking != MAKER_DEFAULT and thinking not in model.levels:
        raise PlanError(
            f"{model.name} thinking must be the maker default or one of {', '.join(model.levels)}."
        )
    return dataclasses.replace(model, thinking=thinking)


def plan_models(plan: RunPlan) -> list[Model]:
    return [_model(m["id"], m["thinking"]) for m in plan.models]


def call_file(plan: RunPlan, model: Model, drawing: str, run_number: int) -> Path:
    return call_path(plan.calls_folder, model_folder(model), drawing, run_number)


def every_call(plan: RunPlan) -> list[tuple[Model, str, int]]:
    """Every (model, drawing, run number) the plan covers, in a fixed order."""
    return [
        (model, drawing, n)
        for model in plan_models(plan)
        for drawing in plan.drawings
        for n in range(1, plan.runs + 1)
    ]


@dataclass(frozen=True)
class Todo:
    model: Model
    drawing: str
    run_number: int
    needs_call: bool  # False when the reply is saved and only extraction is left


def todo(plan: RunPlan) -> list[Todo]:
    """What is still left: calls with no saved reply, and replies not yet extracted."""
    left = []
    for model, drawing, n in every_call(plan):
        path = call_file(plan, model, drawing, n)
        if not is_done(path):
            left.append(Todo(model, drawing, n, needs_call=True))
        elif not extraction.is_current(path):
            left.append(Todo(model, drawing, n, needs_call=False))
    return left


# --- money ---------------------------------------------------------------------------


def _average_cost(files: list[Path]) -> Decimal | None:
    costs = [Decimal(r["cost_usd"]) for r in map(load_call, files) if r.get("cost_usd")]
    return sum(costs, Decimal(0)) / len(costs) if costs else None


def per_call_estimate(model: Model, prompt: str = "") -> tuple[Decimal, str]:
    """What one call to this model should cost, and what that figure is based on.

    A longer prompt makes models think longer, so calls asked the same way are used
    when there are any; otherwise every saved call for the model is averaged.
    """
    saved = [
        f
        for f in paths.CALLS.glob(f"*/{model_folder(model)}/*.json")
        if load_call(f).get("cost_usd")
    ]
    same_prompt = [f for f in saved if load_call(f).get("prompt") == prompt] if prompt else []
    average = _average_cost(same_prompt or saved)
    if average is not None:
        count = len(same_prompt or saved)
        asked = " asked the same way" if same_prompt else ""
        return average, f"average of {count} saved call{'s' if count != 1 else ''}{asked}"
    guess = cost_usd(model, FALLBACK_INPUT_TOKENS, FALLBACK_OUTPUT_TOKENS)
    return guess, "rough guess, no saved calls yet"


def per_extraction_estimate() -> Decimal:
    average = _average_cost(sorted(paths.EXTRACTIONS.glob("**/*.json")))
    if average is not None:
        return average
    chars = len(extraction.INSTRUCTIONS) + FALLBACK_REPLY_CHARS
    return cost_usd(
        load_extractor(),
        chars // extraction.CHARS_PER_TOKEN,
        extraction.ESTIMATED_OUTPUT_TOKENS,
    )


@dataclass(frozen=True)
class ModelEstimate:
    model: Model
    calls: int  # calls still to send
    extractions: int  # replies still to extract (includes the new calls)
    per_call: Decimal
    basis: str
    per_extraction: Decimal

    @property
    def total(self) -> Decimal:
        return self.calls * self.per_call + self.extractions * self.per_extraction


def estimate(plan: RunPlan) -> list[ModelEstimate]:
    """The cost of everything the plan still has to do, per model."""
    left = todo(plan)
    per_extraction = per_extraction_estimate()
    out = []
    for model in plan_models(plan):
        mine = [t for t in left if t.model == model]
        per_call, basis = per_call_estimate(model, plan.prompt)
        calls = sum(t.needs_call for t in mine)
        out.append(ModelEstimate(model, calls, len(mine), per_call, basis, per_extraction))
    return out


def spent(plan: RunPlan) -> Decimal:
    """What this plan has actually spent: its own calls and extractions, nothing else."""
    total = Decimal(0)
    for model, drawing, n in every_call(plan):
        path = call_file(plan, model, drawing, n)
        for f in (path, extraction.extraction_path(path)):
            if f.exists():
                record = load_call(f)
                if record.get("plan_name") == plan.name and record.get("cost_usd"):
                    total += Decimal(record["cost_usd"])
    return total


# --- making and approving plans --------------------------------------------------------


def _parse_thinking(text: str) -> dict[str, str]:
    """`claude-opus-5=low,gpt-5.6-sol=high` -> {"claude-opus-5": "low", ...}."""
    out = {}
    for part in filter(None, (p.strip() for p in text.split(","))):
        model_id, _, level = part.partition("=")
        if not level:
            raise PlanError(f"Thinking must look like model-id=level, not {part!r}.")
        out[model_id.strip()] = level.strip()
    return out


def _new_name(label: str) -> str:
    base = f"{date.today().isoformat()}-{label}"
    name, n = base, 2
    while plan_path(name).exists():
        name, n = f"{base}-{n}", n + 1
    return name


def calls_folder(test_run: bool, prompt_id: str) -> str:
    """Where a plan's calls go. Each prompt has its own folder, so answers never mix."""
    base = TEST_FOLDER if test_run else MAIN_FOLDER
    return base if prompt_id == "bare" else f"{base}-{prompt_id}"


def make_plan(
    model_ids: list[str],
    drawings: str,
    runs: int,
    thinking: dict[str, str] | None = None,
    test_count: int = len(TEST_DRAWINGS),
    prompt_id: str = DEFAULT_PROMPT_ID,
) -> RunPlan:
    """Build and save a plan. Sends nothing."""
    if not model_ids:
        raise PlanError("Pick at least one model.")
    if prompt_id not in PROMPTS:
        raise PlanError(f"Prompt must be one of {', '.join(PROMPTS)}, not {prompt_id!r}.")
    if not 1 <= runs <= 5:
        raise PlanError("Runs per model must be 1 to 5.")
    thinking = thinking or {}
    unknown = set(thinking) - set(model_ids)
    if unknown:
        raise PlanError(f"Thinking given for models not in the run: {', '.join(sorted(unknown))}")
    models = [_model(m, thinking.get(m, MAKER_DEFAULT)) for m in model_ids]
    files = drawings_for(drawings, test_count)
    test_run = len(files) < SMALLEST_REAL_RUN
    label = f"test-{len(files)}" if test_run else f"set-{drawings}"
    if prompt_id != "bare":
        label += f"-{prompt_id}"
    plan = RunPlan(
        name=_new_name(label),
        created=datetime.now(UTC).isoformat(timespec="seconds"),
        test_run=test_run,
        calls_folder=calls_folder(test_run, prompt_id),
        prompt_id=prompt_id,
        prompt=PROMPTS[prompt_id],
        drawing_choice=drawings,
        drawings=files,
        models=[{"id": m.id, "thinking": m.thinking} for m in models],
        runs=runs,
        estimate_usd="0",
    )
    plan.estimate_usd = str(sum((e.total for e in estimate(plan)), Decimal(0)))
    save(plan)
    return plan


def approve(name: str) -> RunPlan:
    """Record Garron's approval: what's spent so far plus the estimate for what's left."""
    plan = load(name)
    remaining = sum((e.total for e in estimate(plan)), Decimal(0))
    so_far = spent(plan)
    plan.approvals.append(
        {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "spent_before_usd": str(so_far),
            "estimate_usd": str(remaining),
            "approved_usd": str(so_far + remaining),
        }
    )
    save(plan)
    return plan


# --- what Garron sees ------------------------------------------------------------------


def _money(x: Decimal) -> str:
    return f"${x:.2f}" if x >= 1 else f"${x:.4f}"


def describe(plan: RunPlan) -> str:
    """The plan in plain words: what runs, what's left, what it should cost."""
    estimates = estimate(plan)
    remaining = sum((e.total for e in estimates), Decimal(0))
    so_far = spent(plan)
    kind = "TEST RUN (kept out of published results)" if plan.test_run else "Real run"
    lines = [
        f"Run plan {plan.name}: {kind}",
        f'  Prompt ({plan.prompt_id}): "{plan.prompt or PROMPTS["bare"]}"',
        f"  Calls saved under: runs/calls/{plan.calls_folder}/",
        f"  Drawings: {len(plan.drawings)}"
        + (f" (the fixed {plan.drawing_choice}-set)" if not plan.test_run else ""),
        f"  Runs per model: {plan.runs}",
        f"  Status: {plan.status}" + (f" ({plan.note})" if plan.note else ""),
        "",
        "  Still to do, per model:",
    ]
    for e in estimates:
        thinking = e.model.thinking
        if thinking == MAKER_DEFAULT:
            thinking = f"maker default: {e.model.maker_default}"
        lines.append(f"    {e.model.name} (thinking {thinking})")
        lines.append(
            f"      {e.calls} calls x about {_money(e.per_call)} ({e.basis}), "
            f"{e.extractions} extractions x about {_money(e.per_extraction)} = {_money(e.total)}"
        )
    lines += [
        "",
        f"  Estimated cost of what's left: about {_money(remaining)}",
        f"  Already spent by this plan: {_money(so_far)}",
    ]
    if plan.approvals:
        lines.append(
            f"  Approved: {_money(plan.approved_usd)}; pauses if spending passes "
            f"{_money(plan.limit_usd)} (+25%)"
        )
    else:
        limit = (so_far + remaining) * PAUSE_OVER_ESTIMATE
        lines.append(f"  If approved, pauses if spending passes {_money(limit)} (+25%)")
    return "\n".join(lines)


def list_runs() -> str:
    plans = all_plans()
    if not plans:
        return "No run plans yet. Make one with /run-eval."
    lines = []
    for plan in plans:
        left = len(todo(plan))
        lines.append(
            f"{plan.name}: {plan.status}, {left} of {len(every_call(plan))} left"
            + (", TEST RUN" if plan.test_run else "")
        )
    return "\n".join(lines)


# --- commands ------------------------------------------------------------------------


def cli_plan(args: list[str]) -> None:
    """`vlm-eval plan-run --models a,b --drawings 30 --runs 3 [--thinking a=low]`. Free."""
    parser = argparse.ArgumentParser(prog="vlm-eval plan-run")
    parser.add_argument("--models", required=True, help="comma-separated model ids")
    parser.add_argument("--drawings", required=True, choices=["30", "60", "141", "test"])
    parser.add_argument("--test-count", type=int, default=len(TEST_DRAWINGS))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--thinking", default="", help="model-id=level,...")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT_ID, choices=sorted(PROMPTS))
    opts = parser.parse_args(args)
    try:
        plan = make_plan(
            [m.strip() for m in opts.models.split(",") if m.strip()],
            opts.drawings,
            opts.runs,
            _parse_thinking(opts.thinking),
            opts.test_count,
            opts.prompt,
        )
    except PlanError as exc:
        print(f"Can't make that plan: {exc}")
        return
    print(describe(plan))
    print(f"\nNothing was sent. To approve: uv run vlm-eval approve-run {plan.name}")


def cli_approve(args: list[str]) -> None:
    if not args:
        print("usage: vlm-eval approve-run <plan name>")
        return
    try:
        plan = approve(args[0])
    except PlanError as exc:
        print(exc)
        return
    print(describe(plan))
    print(f"\nApproved. To start: uv run vlm-eval run-eval {plan.name}")


def cli_list(args: list[str]) -> None:
    print(list_runs())
