"""`vlm-eval test-connections`: prove each switched-on model can be reached and read a PDF.

Without --send it is free: it checks that each maker's key is in .env, asks each
maker's free model list whether the configured model names exist, and prints the
plan and the estimated cost. With --send it sends one drawing once to each
model, saves every call under runs/calls/, and opens a page with the replies.
"""

from __future__ import annotations

import html
import os
import webbrowser
from datetime import date
from decimal import Decimal

from dotenv import load_dotenv

from vlm_eval import paths
from vlm_eval.calls import (
    PROMPT,
    call_path,
    cost_usd,
    is_done,
    load_call,
    model_folder,
    send_drawing,
)
from vlm_eval.connections import connection_for
from vlm_eval.models_config import Model, enabled_models

TEST_DRAWING = "201533-020.pdf"

# A rough guess per call until real calls measure it: a one-page PDF read as an
# image plus text, and a reply that is mostly thinking.
ESTIMATED_INPUT_TOKENS = 5_000
ESTIMATED_OUTPUT_TOKENS = 8_000
PAUSE_OVER_ESTIMATE = Decimal("1.25")


def estimate(model: Model) -> Decimal:
    return cost_usd(model, ESTIMATED_INPUT_TOKENS, ESTIMATED_OUTPUT_TOKENS)


def check(models: list[Model]) -> bool:
    """Free checks. Prints one line per model; True when every model is ready."""
    load_dotenv(paths.ENV_FILE)
    ready = True
    live: dict[str, set[str] | str] = {}
    for model in models:
        key = os.environ.get(model.key, "").strip()
        if not key:
            problem = f"no key: add {model.key} to .env"
        else:
            if model.maker not in live:
                try:
                    live[model.maker] = connection_for(model.maker).list_model_ids(key)
                except Exception as exc:  # noqa: BLE001 - shown to Garron as a problem line
                    live[model.maker] = f"couldn't reach {model.maker}: {type(exc).__name__}"
            found = live[model.maker]
            if isinstance(found, str):
                problem = found
            elif model.id not in found:
                problem = f"{model.id} is not in {model.maker}'s list of live models"
            else:
                problem = ""
        ready = ready and not problem
        status = "ready" if not problem else f"PROBLEM: {problem}"
        print(f"  {model.name:<28} {model.id:<26} {status}")
    return ready


def run(send: bool = False) -> None:
    models = enabled_models()
    run_name = f"connection-test-{date.today().isoformat()}"
    print(f"Models switched on in config/models.yaml ({len(models)}):")
    if not check(models):
        print("\nFix the problems above, then run this again. Nothing was sent.")
        return

    total = sum((estimate(m) for m in models), Decimal(0))
    print(f"\nPlan: send {TEST_DRAWING} once to each model above, with the prompt")
    print(f'  "{PROMPT}"')
    for m in models:
        print(f"  {m.name:<28} about ${estimate(m):.2f}")
    print(f"  {'Total':<28} about ${total:.2f}")
    print(f"  Stops early if spending passes ${total * PAUSE_OVER_ESTIMATE:.2f} (+25%).")
    if not send:
        print("\nNothing was sent. To send, run: uv run vlm-eval test-connections --send")
        return

    spent = Decimal(0)
    for model in models:
        path = call_path(run_name, model_folder(model), TEST_DRAWING, 1)
        if is_done(path):
            print(f"  {model.name}: already done today, not sent again")
            record = load_call(path)
        elif spent > total * PAUSE_OVER_ESTIMATE:
            print(f"  Stopped before {model.name}: spent ${spent:.2f}, over the +25% limit.")
            break
        else:
            print(f"  {model.name}: sending...", flush=True)
            record = send_drawing(model, TEST_DRAWING, run_name, 1)
        spent += Decimal(record.get("cost_usd") or 0)
        print(f"    {_one_line(record)}")

    write_page(run_name, models, total)
    print(f"\nSpent ${spent:.4f} against an estimate of ${total:.2f}.")
    print(f"Opened {paths.CONNECTION_TEST_PAGE.relative_to(paths.ROOT)}")
    webbrowser.open(paths.CONNECTION_TEST_PAGE.as_uri())


def _one_line(record: dict) -> str:
    if record["error"]:
        return f"FAILED after {record['attempts']} attempt(s): {record['error']}"
    return (
        f"{record['model_version']}, {record['seconds']}s, "
        f"{record['input_tokens']:,} in / {record['output_tokens']:,} out, "
        f"${Decimal(record['cost_usd']):.4f}"
    )


def write_page(run_name: str, models: list[Model], estimated_total: Decimal) -> None:
    cards, spent = [], Decimal(0)
    for model in models:
        path = call_path(run_name, model_folder(model), TEST_DRAWING, 1)
        if not path.exists():
            continue
        r = load_call(path)
        spent += Decimal(r.get("cost_usd") or 0)
        if r["error"]:
            body = f"<p class=bad>No reply after {r['attempts']} attempt(s).</p>"
            body += f"<pre>{html.escape(r['error'])}</pre>"
        else:
            thinking = r["thinking_tokens"]
            facts = [
                ("Model version", r["model_version"]),
                ("Stop reason", r["stop_reason"]),
                ("Tokens in", f"{r['input_tokens']:,}"),
                (
                    "Tokens out",
                    f"{r['output_tokens']:,}"
                    + (f" ({thinking:,} thinking)" if thinking is not None else ""),
                ),
                ("Time", f"{r['seconds']} s"),
                ("Cost", f"${Decimal(r['cost_usd']):.4f}"),
                ("Thinking", f"{r['thinking']} ({r['maker_default_thinking']})"),
            ]
            rows = "".join(f"<tr><th>{k}</th><td>{html.escape(str(v))}</td></tr>" for k, v in facts)
            body = f"<table>{rows}</table><h3>Reply, exactly as sent back</h3>"
            body += f"<pre>{html.escape(r['reply_text'])}</pre>"
        saved = path.relative_to(paths.ROOT)
        cards.append(
            f"<section><h2>{html.escape(model.name)}</h2>{body}"
            f"<p class=file>Saved call: {saved}</p></section>"
        )

    paths.CONNECTION_TEST_PAGE.write_text(
        f"""<!doctype html>
<html lang=en><head><meta charset=utf-8><title>Connection test</title>
<style>
body {{ font: 16px/1.5 -apple-system, system-ui, sans-serif; max-width: 60rem;
  margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; background: #fafaf8; }}
section {{ background: #fff; border: 1px solid #ddd; border-radius: 8px;
  padding: 1rem 1.5rem; margin: 1.5rem 0; }}
table {{ border-collapse: collapse; }} th {{ text-align: left; padding-right: 1.5rem;
  font-weight: 600; color: #555; }}
pre {{ white-space: pre-wrap; background: #f3f3f0; padding: 1rem; border-radius: 6px; }}
.bad {{ color: #b00020; font-weight: 600; }} .file {{ color: #777; font-size: 13px; }}
</style></head><body>
<h1>Connection test: {TEST_DRAWING}</h1>
<p>Each model got the PDF as-is and the prompt <b>{html.escape(PROMPT)}</b>, once.
Nothing here is scored yet.</p>
<p><b>Cost:</b> ${spent:.4f} spent, against an estimate of ${estimated_total:.2f}.</p>
{"".join(cards)}
</body></html>
"""
    )
