"""`vlm-eval replay`: re-score every saved reply from saved files, with zero API spend.

Replay reads only what is already on disk: the saved calls in runs/calls/ and the
saved extractions in runs/extractions/. It never sends anything to any model. A
reply with no saved extraction is shown as waiting for `vlm-eval extract`, not
extracted here. Scoring the same saved files twice gives the same page.
"""

from __future__ import annotations

import html
import webbrowser
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from vlm_eval import paths, run_plan, scoring
from vlm_eval.calls import load_call
from vlm_eval.extraction import (
    answer_from_record,
    extraction_path,
    form_envelopes,
    numbers_in,
    saved_calls,
    units_written,
)
from vlm_eval.grading_examples import found_text, inch_values, result_label, your_numbers
from vlm_eval.ground_truth import read_ground_truth

NO_REPLY = "No reply came back"
NOT_EXTRACTED = "Not extracted yet: run uv run vlm-eval extract"
NOT_SENT = "Not sent yet"


@dataclass(frozen=True)
class Row:
    call_file: Path
    call: dict[str, Any]
    extraction: dict[str, Any] | None
    verdict: scoring.Verdict | None
    status: str  # "" when scored; otherwise why it wasn't


def _row(call_file: Path, keys) -> Row:
    if not call_file.exists():
        return Row(call_file, {}, None, None, NOT_SENT)
    call = load_call(call_file)
    if call.get("error"):
        return Row(call_file, call, None, None, NO_REPLY)
    saved = extraction_path(call_file)
    if not saved.exists():
        return Row(call_file, call, None, None, NOT_EXTRACTED)
    extraction = load_call(saved)
    verdict = scoring.score(
        call["drawing"],
        answer_from_record(extraction, call["reply_text"]),
        keys[call["drawing"]],
    )
    return Row(call_file, call, extraction, verdict, "")


def _plan(name: str | None) -> run_plan.RunPlan | None:
    """The run plan with this name, if `name` is a plan rather than a calls folder."""
    return run_plan.load(name) if name and run_plan.plan_path(name).exists() else None


def replay(name: str | None = None) -> list[Row]:
    """Score saved replies from saved files. Never calls a model.

    `name` is a run plan (every call it covers, sent or not), a folder under
    runs/calls/, or nothing for every saved call.
    """
    keys = scoring.load_answer_key()
    plan = _plan(name)
    if plan:
        files = [run_plan.call_file(plan, m, d, n) for m, d, n in run_plan.every_call(plan)]
    else:
        files = saved_calls(name)
    return [_row(f, keys) for f in files]


# --- adding the results up (SPEC 2.10) --------------------------------------------


def parts(row: Row) -> tuple[str, str, str]:
    """The model, drawing and run number a row belongs to."""
    drawing, _, run_number = Path(row.call_file.name).stem.rpartition("-run")
    model = row.call.get("model_name") or row.call_file.parent.name
    return model, drawing, run_number


@dataclass(frozen=True)
class ModelTally:
    """One model's results over every reply in the run."""

    model: str
    replies: int  # calls that came back and were graded
    passed: int
    not_graded: int  # flagged by extraction, or a cylinder that named neither size
    no_reply: int
    not_sent: int
    sizes_found: int
    sizes_total: int

    @property
    def calls(self) -> int:
        return self.replies + self.not_graded + self.no_reply + self.not_sent

    @property
    def pass_rate(self) -> str:
        return f"{100 * self.passed / self.replies:.0f}%" if self.replies else "-"

    @property
    def sizes(self) -> str:
        """Sizes found out of the sizes asked for, over every graded reply."""
        if not self.sizes_total:
            return "-"
        share = 100 * self.sizes_found / self.sizes_total
        return f"{self.sizes_found} of {self.sizes_total} ({share:.0f}%)"


def by_model(rows: list[Row]) -> list[ModelTally]:
    tallies: dict[str, dict[str, int]] = {}
    for row in rows:
        model, _, _ = parts(row)
        t = tallies.setdefault(
            model,
            dict(replies=0, passed=0, not_graded=0, no_reply=0, not_sent=0, found=0, total=0),
        )
        if row.status == NO_REPLY:
            t["no_reply"] += 1
        elif row.verdict is None:
            t["not_sent" if row.status == NOT_SENT else "not_graded"] += 1
        elif not row.verdict.scored:
            t["not_graded"] += 1
        else:
            t["replies"] += 1
            t["passed"] += row.verdict.strict_pass
            t["found"] += row.verdict.dims_correct
            t["total"] += row.verdict.dims_total
    return [
        ModelTally(
            model,
            t["replies"],
            t["passed"],
            t["not_graded"],
            t["no_reply"],
            t["not_sent"],
            t["found"],
            t["total"],
        )
        for model, t in sorted(tallies.items())
    ]


def by_drawing(rows: list[Row]) -> dict[str, dict[str, tuple[int, int]]]:
    """drawing -> model -> (runs that passed, runs in the run). Never guesses a missing run."""
    out: dict[str, dict[str, tuple[int, int]]] = {}
    for row in rows:
        if row.status == NOT_SENT:
            continue
        model, drawing, _ = parts(row)
        passed, runs = out.setdefault(drawing, {}).get(model, (0, 0))
        won = bool(row.verdict and row.verdict.strict_pass)
        out[drawing][model] = (passed + won, runs + 1)
    return out


@dataclass(frozen=True)
class Consistency:
    """How often a model gave the same verdict on a drawing every time (SPEC 2.10)."""

    model: str
    all_pass: int
    all_fail: int
    mixed: int

    @property
    def drawings(self) -> int:
        return self.all_pass + self.all_fail + self.mixed

    @property
    def rate(self) -> str:
        if not self.drawings:
            return "-"
        agreed = self.all_pass + self.all_fail
        return f"{100 * agreed / self.drawings:.0f}%"


def consistency(rows: list[Row]) -> list[Consistency]:
    counts: dict[str, dict[str, int]] = {}
    for models in by_drawing(rows).values():
        for model, (passed, runs) in models.items():
            c = counts.setdefault(model, dict(all_pass=0, all_fail=0, mixed=0))
            c["all_pass" if passed == runs else "all_fail" if passed == 0 else "mixed"] += 1
    return [
        Consistency(model, c["all_pass"], c["all_fail"], c["mixed"])
        for model, c in sorted(counts.items())
    ]


def runs_per_drawing(rows: list[Row]) -> int:
    """The most runs any one model did on any one drawing."""
    return max(
        (runs for models in by_drawing(rows).values() for _, runs in models.values()),
        default=0,
    )


def tables(rows: list[Row]) -> str:
    """The two summaries in plain text, for the terminal."""
    lines = ["By model:"]
    for t in by_model(rows):
        extra = [
            f"{t.not_graded} not graded" if t.not_graded else "",
            f"{t.no_reply} no reply" if t.no_reply else "",
            f"{t.not_sent} not sent yet" if t.not_sent else "",
        ]
        lines.append(
            f"  {t.model}: {t.passed} of {t.replies} replies passed ({t.pass_rate}); "
            f"sizes found {t.sizes}" + "".join(f"; {e}" for e in extra if e)
        )
    if runs_per_drawing(rows) > 1:
        lines.append("Same answer every run (consistency):")
        for c in consistency(rows):
            lines.append(
                f"  {c.model}: {c.rate} of {c.drawings} drawings "
                f"({c.all_pass} always passed, {c.all_fail} always failed, {c.mixed} mixed)"
            )
    return "\n".join(lines)


def summary(rows: list[Row]) -> str:
    """One plain line per reply, for the terminal and for comparing two replays."""
    lines = []
    for r in rows:
        name = r.call_file.relative_to(paths.CALLS)
        if r.verdict is None:
            lines.append(f"{name}: {r.status}")
        else:
            v = r.verdict
            lines.append(
                f"{name}: {result_label(v)}, {v.dims_correct} of {v.dims_total}"
                + (f", missed {', '.join(v.dims_missed)}" if v.dims_missed else "")
                + (f", {', '.join(v.problems)}" if v.problems else "")
                + (f" ({v.note})" if v.note else "")
            )
    return "\n".join(lines)


# --- the page ------------------------------------------------------------------


def _values_table(extraction: dict[str, Any], reply_text: str) -> str:
    envelopes = [e for e in form_envelopes(extraction.get("form") or {}) if e["values"]]
    if not envelopes:
        return "<p class=soft>No sizes found in the reply.</p>"
    found = numbers_in(reply_text)
    written = units_written(reply_text)

    def unit(u: str) -> str:
        if not u:
            return "<span class=soft>not stated</span>"
        if u not in written:
            return (
                f"<span class=soft>not stated (extractor guessed {html.escape(u)}; not used)</span>"
            )
        return html.escape(u)

    def number(n: str) -> str:
        if not n:
            return ""
        mark = "✓" if " ".join(n.split()) in found else "✗ not in reply"
        cls = "ok" if mark == "✓" else "bad"
        return f"{html.escape(n)} <span class={cls}>{mark}</span>"

    def group(entry: dict[str, Any], n: int) -> str:
        shape = entry["shape"] or "shape not stated"
        head = (
            f"<tr><th colspan=4 class=envelope>Envelope {n}: {html.escape(shape)}</th></tr>"
            if len(envelopes) > 1
            else ""
        )
        return head + "".join(
            "<tr>"
            f"<td>{html.escape(v['label']) or '<span class=soft>none</span>'}</td>"
            f"<td>{number(v['number'])}</td>"
            f"<td>{unit(v['unit'])}</td>"
            f"<td>{number(v['number_in_other_unit'])}</td>"
            "</tr>"
            for v in entry["values"]
        )

    body = "".join(group(e, i) for i, e in enumerate(envelopes, 1))
    return (
        "<table class=values><thead><tr><th>Reply's label</th><th>Number</th><th>Unit</th>"
        f"<th>Same size, other unit</th></tr></thead><tbody>{body}</tbody></table>"
    )


def _verdict(row: Row) -> str:
    if row.verdict is None:
        return f'<span class="badge not-graded">{html.escape(row.status)}</span>'
    v = row.verdict
    label = result_label(v)
    badge = f'<span class="badge {label.lower().replace(" ", "-")}">{label}</span>'
    details = found_text(v)
    for ignored in v.ignored_envelopes:
        details += f'<div class="found">{html.escape(ignored)}</div>'
    if v.problems:
        details += f'<div class="found">{html.escape(", ".join(v.problems))}</div>'
    if v.note:
        details += f'<div class="note">{html.escape(v.note)}</div>'
    return badge + details


def _card(row: Row, drawings, inch) -> str:
    c = row.call
    drawing = drawings[c["drawing"]]
    extracted = ""
    if row.extraction:
        extracted = "<h3>Numbers pulled from the reply</h3>" + _values_table(
            row.extraction, c["reply_text"]
        )
    reply = (
        f"<h3>Reply, exactly as sent back</h3><pre>{html.escape(c['reply_text'])}</pre>"
        if not c.get("error")
        else ""
    )
    return f"""<section>
<div class=head><h2>{html.escape(drawing.part_no)} · {html.escape(c["model_name"])}</h2>
<span class=soft>{html.escape(c.get("model_version") or c["model_requested"])},
run {c["run_number"]} · {html.escape(c["run_name"])}</span></div>
<div class=grid>
<div><h3>Your numbers</h3>{your_numbers(drawing, inch)}</div>
<div><h3>Score</h3>{_verdict(row)}</div>
</div>
{extracted}
{reply}
</section>"""


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Replay Results</title>
<style>
:root {{ --ink:#1d2330; --soft:#5d6778; --line:#e3e6ec; --bg:#f7f8fa; --card:#fff;
  --pass:#1f7a3f; --pass-bg:#e3f4e8; --fail:#b3261e; --fail-bg:#fbe5e3;
  --flag:#8a5a00; --flag-bg:#fdf1d6; }}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font:16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
main {{ max-width:960px; margin:0 auto; padding:32px 16px 48px; }}
h1 {{ font-size:28px; margin:0 0 12px; }} h2 {{ font-size:20px; margin:0; }}
h3 {{ font-size:13px; text-transform:uppercase; letter-spacing:.04em; color:var(--soft);
  margin:18px 0 6px; }}
.intro {{ max-width:720px; color:var(--soft); }} .intro b {{ color:var(--ink); }}
section {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
  padding:18px 20px; margin:20px 0; }}
.head {{ display:flex; flex-wrap:wrap; gap:4px 16px; align-items:baseline; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:0 24px; }}
.soft, .unit, .inch {{ color:var(--soft); }} .unit {{ font-size:13px; }}
table.values {{ border-collapse:collapse; width:100%; }}
table.values th {{ text-align:left; font-size:13px; color:var(--soft); font-weight:600; }}
table.values th, table.values td {{ padding:6px 10px 6px 0; border-bottom:1px solid var(--line); }}
.envelope {{ color:var(--soft); font-size:13px; padding-top:10px; }}
.ok {{ color:var(--pass); }} .bad {{ color:var(--fail); font-weight:600; }}
pre {{ white-space:pre-wrap; background:#f3f3f0; padding:12px; border-radius:6px;
  font-size:14px; margin:0; }}
.badge {{ display:inline-block; padding:4px 10px; border-radius:6px; font-weight:700;
  font-size:14px; }}
.pass {{ color:var(--pass); background:var(--pass-bg); }}
.fail {{ color:var(--fail); background:var(--fail-bg); }}
.not-graded {{ color:var(--flag); background:var(--flag-bg); }}
.found {{ color:var(--soft); font-size:14px; margin-top:6px; }}
.note {{ font-size:14px; margin-top:6px; padding:6px 8px; border-radius:6px;
  background:var(--flag-bg); color:var(--flag); }}
table.results {{ border-collapse:collapse; width:100%; margin-top:12px; font-size:14px; }}
table.results th {{ text-align:left; color:var(--soft); font-weight:600; }}
table.results th, table.results td {{ padding:6px 10px 6px 0;
  border-bottom:1px solid var(--line); }}
@media (max-width:640px) {{ .grid {{ grid-template-columns:1fr; }} }}
</style></head><body><main>
<h1>Replay: saved replies, extracted and scored</h1>
<p class="intro"><b>This replay spent $0.</b> It read saved files only and sent nothing
to any model. {extraction_cost}</p>
<p class="intro">For each reply, check two things: are the <b>numbers pulled from the
reply</b> the sizes a person reading it would take as its answer, and would you
<b>score</b> it the same way against your numbers?</p>
{cards}
</main></body></html>
"""


def _extraction_cost(rows: list[Row]) -> str:
    done = [r.extraction for r in rows if r.extraction]
    if not done:
        return "Nothing has been extracted yet."
    cost = sum((Decimal(e["cost_usd"]) for e in done), Decimal(0))
    dates = sorted({e["started_at"][:10] for e in done})
    when = dates[0] if len(dates) == 1 else f"{dates[0]} to {dates[-1]}"
    return (
        f"The one-time extraction of these {len(done)} replies cost ${cost:.4f} "
        f"({when}), and is reused every time."
    )


def _model_table(rows: list[Row]) -> str:
    """Each model's pass rate, sizes found, and how often it answered the same way."""
    show_consistency = runs_per_drawing(rows) > 1
    agreed = {c.model: c for c in consistency(rows)}
    head = (
        "<tr><th>Model</th><th>Replies passed</th><th>Pass rate</th><th>Sizes found</th>"
        + ("<th>Same answer every run</th>" if show_consistency else "")
        + "<th>Not graded</th><th>No reply</th></tr>"
    )
    body = []
    for t in by_model(rows):
        c = agreed.get(t.model)
        same = (
            f"<td>{c.rate} of {c.drawings} drawings<div class=soft>{c.all_pass} always passed, "
            f"{c.all_fail} always failed, {c.mixed} mixed</div></td>"
            if show_consistency and c
            else ""
        )
        body.append(
            f"<tr><td>{html.escape(t.model)}</td><td>{t.passed} of {t.replies}</td>"
            f"<td><b>{t.pass_rate}</b></td><td>{t.sizes}</td>{same}"
            f"<td>{t.not_graded or ''}</td><td>{t.no_reply or ''}</td></tr>"
        )
    return (
        f"<h3>By model</h3><table class=results><thead>{head}</thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


def _consistency_table(rows: list[Row]) -> str:
    """One line per drawing: how many runs each model passed."""
    if runs_per_drawing(rows) <= 1:
        return ""
    per_drawing = by_drawing(rows)
    models = sorted({m for models in per_drawing.values() for m in models})
    head = "".join(f"<th>{html.escape(m)}</th>" for m in models)
    body = []
    for drawing, results in sorted(per_drawing.items()):
        cells = []
        for model in models:
            passed, runs = results.get(model, (0, 0))
            if not runs:
                cells.append("<td class=soft>-</td>")
                continue
            cls = "ok" if passed == runs else "bad" if passed == 0 else ""
            cells.append(f'<td class="{cls}">{passed} of {runs}</td>')
        body.append(f"<tr><td>{html.escape(drawing)}</td>{''.join(cells)}</tr>")
    return (
        "<h3>Runs passed, per drawing</h3>"
        f"<table class=results><thead><tr><th>Drawing</th>{head}</tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


def _results_table(rows: list[Row], drawings) -> str:
    """One line per call: drawing, model, run, result, sizes found."""
    lines = []
    for r in rows:
        model, drawing, run_no = parts(r)
        if r.verdict is None:
            result = f'<span class="badge not-graded">{html.escape(r.status)}</span>'
            found = missed = ""
        else:
            v = r.verdict
            label = result_label(v)
            result = f'<span class="badge {label.lower().replace(" ", "-")}">{label}</span>'
            found = f"{v.dims_correct} of {v.dims_total}" if v.scored else ""
            missed = html.escape(", ".join(v.dims_missed)) if v.scored else html.escape(v.note)
        lines.append(
            f"<tr><td>{html.escape(drawing)}</td><td>{html.escape(model)}</td>"
            f"<td>{html.escape(run_no)}</td><td>{result}</td><td>{found}</td>"
            f"<td>{missed}</td></tr>"
        )
    return (
        "<h3>Every reply</h3>"
        "<table class=results><thead><tr><th>Drawing</th><th>Model</th><th>Run</th>"
        "<th>Result</th><th>Sizes found</th><th>Missed</th></tr></thead>"
        f"<tbody>{''.join(lines)}</tbody></table>"
    )


def _summary_section(rows: list[Row], plan: run_plan.RunPlan | None, drawings) -> str:
    """The run added up: cost, each model's results, consistency, then every reply."""
    title, cost = "Results", ""
    if plan:
        estimated = (
            plan.approved_usd if plan.approved_usd is not None else Decimal(plan.estimate_usd)
        )
        test = ' <span class="badge not-graded">TEST RUN</span>' if plan.test_run else ""
        title = f"Run plan {html.escape(plan.name)}{test}"
        note = f" ({html.escape(plan.note)})" if plan.note else ""
        cost = (
            f"<p><b>Estimated ${estimated:.4f} · Actual ${run_plan.spent(plan):.4f}</b>"
            f" · status: {html.escape(plan.status)}{note}"
            f" · {len(rows)} calls in the plan</p>"
        )
    return (
        f"<section><h2>{title}</h2>{cost}"
        f"{_model_table(rows)}{_consistency_table(rows)}{_results_table(rows, drawings)}"
        "</section>"
    )


def write_page(rows: list[Row], plan: run_plan.RunPlan | None = None) -> None:
    drawings = {d.file: d for d in read_ground_truth(classify_pdfs=False)}
    inch = inch_values()
    header = _summary_section(rows, plan, drawings)
    cards = "\n".join(_card(r, drawings, inch) for r in rows if r.call)
    paths.REPLAY_PAGE.write_text(
        PAGE.format(extraction_cost=html.escape(_extraction_cost(rows)), cards=header + cards)
    )


def run(run_name: str | None = None, open_page: bool = True) -> None:
    rows = replay(run_name)
    if not rows:
        print("No saved replies found in runs/calls/.")
        return
    plan = _plan(run_name)
    print(tables(rows))
    if len(rows) <= 20:  # a short run reads better call by call
        print(summary(rows))
    write_page(rows, plan)
    print(f"\nSpent $0: nothing was sent. Wrote {paths.REPLAY_PAGE.relative_to(paths.ROOT)}")
    if open_page:
        webbrowser.open(paths.REPLAY_PAGE.as_uri())
