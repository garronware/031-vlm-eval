"""`vlm-eval build-report`: the results folder for one run (SPEC 2.10, Chunk 10).

Everything is read from saved files, so building the folder spends $0 and can be
repeated whenever more replies arrive. The folder goes public: it never holds costs,
keys, or paths into the private `runs/` folder, and a test run is refused.

Headline tables count each drawing once, from run 1. Later runs feed only the two
consistency tables; `every-run.csv` holds every reply. Only Garron's labels are
published: a failure he hasn't ruled on says so.

The tables are built here from the scored replies. `recompute_check` rebuilds them a
second way, from `every-run.csv` alone, and they must agree.
"""

from __future__ import annotations

import csv
import json
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from vlm_eval import (
    casebook,
    diagnosis,
    paths,
    replay,
    report_charts,
    report_page,
    run_plan,
    scoring,
)
from vlm_eval.extraction import form_envelopes, units_written

RESULTS = paths.ROOT / "results"
README = paths.ROOT / "README.md"
DEFAULT_FOLDER = diagnosis.DEFAULT_FOLDER  # the stock-shape prompt, in use since 2026-09-20
MIN_DRAWINGS = 30  # fewer is a test run, never published (SPEC 2.7)
SMALL_GROUP = 5  # a split with fewer drawings shows counts only, never a rate (SPEC 2.10)
HEADLINE_RUN = "1"
ALL_MODELS = "All three models"

PASS, FAIL = "PASS", "FAIL"
NOT_GRADED = "NOT GRADED"
NO_REPLY = "NO REPLY"
NOT_DIAGNOSED = "Not diagnosed yet"
NOT_REVIEWED = "Not reviewed by the evaluator yet"

# The published folder never names the person who ran the evaluation (Garron, 2026-10-01):
# it says "the evaluator", so the page reads the same for anyone who runs the pipeline.
# The agent's notes name him, so his name is swapped out of them on the way out.
EVALUATOR_NAME = re.compile(r"\bGarron(?: Ware)?\b")

EVERY_RUN_COLUMNS = (
    "drawing",
    "model",
    "model_version",
    "run",
    "values_returned",
    "result",
    "correct",
    "total_criteria",
    "missed",
    "label",
    "evidence",
    "shape",
    "print_type",
    "pdf_type",
    "dimension_origin",
    "converted_readings_used",
)

# Each split table: its file name, the ground-truth tag it splits on, and a heading.
SPLITS = (
    ("by-dimension-origin", "dimension_origin"),
    ("by-shape", "shape"),
    ("by-pdf-type", "pdf_type"),
    ("by-print-type", "print_type"),
)


class ReportError(ValueError):
    """A run that can't be published. Never swallowed."""


# --- one record per reply ------------------------------------------------------------


@dataclass(frozen=True)
class Reply:
    """One reply, scored, with Garron's labels and the drawing's tags."""

    row: replay.Row
    model: str
    drawing: str  # file name without .pdf
    run: str
    tags: dict[str, str]  # shape, print_type, pdf_type, dimension_origin
    labels: tuple[tuple[str, str, str], ...]  # (missed size, label, evidence)

    @property
    def verdict(self) -> scoring.Verdict | None:
        return self.row.verdict

    @property
    def graded(self) -> bool:
        return bool(self.verdict and self.verdict.scored)

    @property
    def passed(self) -> bool:
        return bool(self.verdict and self.verdict.strict_pass)

    @property
    def result(self) -> str:
        if self.row.status == replay.NO_REPLY:
            return NO_REPLY
        if not self.graded:
            return NOT_GRADED
        return PASS if self.passed else FAIL


def _tags() -> dict[str, dict[str, str]]:
    with paths.GROUND_TRUTH_CSV.open(newline="") as fh:
        return {
            r["file"]: {
                "shape": r["shape"],
                "print_type": r["print_type"],
                "pdf_type": r["pdf_text_type"],
                "dimension_origin": r["dimension_origin"],
            }
            for r in csv.DictReader(fh)
        }


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def unnamed(text: str) -> str:
    """The text with the evaluator's name replaced by "the evaluator"."""
    text = EVALUATOR_NAME.sub("the evaluator", text)
    return re.sub(r"(^|[.!?]\s+)the evaluator", r"\1The evaluator", text)


def _evidence(entry: dict) -> str:
    """The agent's note where Garron's label matches the agent's; his own reason where not.

    A note written for a label he overruled argues for the wrong label, so it is never
    published beside his. Labels are compared rather than the verdict, because a merged
    label (2026-10-10) can make an old change agree with the agent.
    """
    if entry["garron_label"] != entry["agent_label"]:
        return str(entry["reason"]).strip()
    original = diagnosis._original(entry) or {}
    return str(original.get("note", "")).strip() or str(entry.get("reason", "")).strip()


def _labels(folder: str) -> dict[Path, tuple[tuple[str, str, str], ...]]:
    """call file -> (missed size, Garron's label, evidence) for every failed reply."""
    groups, _ = diagnosis.failure_groups(folder)
    out = {}
    for group in groups:
        saved = _read_json(diagnosis.diagnosis_path(folder, group))
        found = {}
        for e in (saved or {}).get("diagnoses") or []:
            entry = casebook.confirmed(group.drawing, e["missed"], str(e.get("wrong_value", "")))
            if entry:
                found[e["missed"]] = (entry["garron_label"], _evidence(entry))
        missing = (NOT_REVIEWED if saved else NOT_DIAGNOSED, "")
        labels = tuple((m, *found.get(m, missing)) for m in group.missed)
        for reply in group.replies:
            out[reply.call_file] = labels
    return out


def replies(folder: str = DEFAULT_FOLDER) -> list[Reply]:
    """Every reply saved in a calls folder, scored for $0, with labels and tags."""
    tags = _tags()
    labels = _labels(folder)
    out = []
    for row in replay.replay(folder):
        if not row.call:
            continue
        model, drawing, run = replay.parts(row)
        out.append(
            Reply(
                row, model, drawing, run, tags[row.call["drawing"]], labels.get(row.call_file, ())
            )
        )
    return sorted(out, key=lambda r: (r.drawing, r.model, int(r.run)))


def headline(all_replies: list[Reply]) -> list[Reply]:
    """Run 1 of every drawing: each drawing counted once per model."""
    return [r for r in all_replies if r.run == HEADLINE_RUN]


# --- every-run.csv -------------------------------------------------------------------


def _values_returned(reply: Reply) -> str:
    extraction = reply.row.extraction
    if not extraction:
        return ""
    written = units_written(reply.row.call.get("reply_text", ""))

    def value(v: dict) -> str:
        unit = v["unit"] if v["unit"] in written else ""
        text = " ".join(p for p in (v["label"], v["number"], unit) if p)
        if v["number_in_other_unit"]:
            text += f" ({v['number_in_other_unit']})"
        return text

    envelopes = [e for e in form_envelopes(extraction.get("form") or {}) if e["values"]]
    return " | ".join("; ".join(value(v) for v in e["values"]) for e in envelopes)


def _described(m: scoring.Match) -> str:
    return f"{m.label} ({m.axis})" if m.axis else m.label


def _converted(reply: Reply) -> str:
    """For the tolerance audit: the values a pass needed a converted reading for."""
    v = reply.verdict
    if not (v and v.relied_on_conversion):
        return ""
    return "; ".join(
        f"{_described(m)}: {m.answer_number} {m.answer_unit} matched the {m.reading}"
        for m in v.matches
        if m.converted
    )


def every_run_row(reply: Reply) -> dict[str, str]:
    v = reply.verdict
    counted = reply.result in (PASS, FAIL)
    return {
        "drawing": reply.drawing,
        "model": reply.model,
        "model_version": reply.row.call.get("model_version")
        or reply.row.call.get("model_requested", ""),
        "run": reply.run,
        "values_returned": _values_returned(reply),
        "result": reply.result,
        "correct": str(v.criteria_correct) if v and counted else "",
        "total_criteria": str(v.criteria_total) if v else "",
        "missed": "; ".join(v.dims_missed) if v and counted else "",
        "label": "; ".join(f"{m}: {label}" for m, label, _ in reply.labels),
        "evidence": unnamed(" || ".join(f"{m}: {ev}" for m, _, ev in reply.labels if ev)),
        **reply.tags,
        "converted_readings_used": _converted(reply),
    }


# --- the tables ----------------------------------------------------------------------


def _percent(k: int, n: int) -> str:
    return f"{100 * k / n:.0f}" if n else ""


def rate_cells(passed: int, graded: int, drawings: int, with_range: bool = True) -> dict:
    """Pass rate and its exact 95% range; blank for a group too small to give a rate.

    The range is left blank when `with_range` is off: a pooled range would treat three
    models on the same drawings as independent tries.
    """
    small = drawings < SMALL_GROUP or not graded
    low, high = casebook.exact_range(passed, graded) if not small else (0, 0)
    show_range = with_range and not small
    return {
        "pass_rate_percent": "" if small else _percent(passed, graded),
        "range_low_percent": f"{100 * low:.0f}" if show_range else "",
        "range_high_percent": f"{100 * high:.0f}" if show_range else "",
    }


def _models(rs: list[Reply]) -> list[str]:
    return sorted({r.model for r in rs})


def pass_rate_by_model(rs: list[Reply]) -> list[dict]:
    rows = []
    for model in [*_models(rs), ALL_MODELS]:
        mine = [r for r in rs if model in (ALL_MODELS, r.model)]
        graded = [r for r in mine if r.graded]
        passed = sum(r.passed for r in graded)
        drawings = len({r.drawing for r in graded})
        rows.append(
            {
                "model": model,
                "drawings": str(drawings),
                "replies_graded": str(len(graded)),
                "passed": str(passed),
                **rate_cells(passed, len(graded), drawings, with_range=model != ALL_MODELS),
                "criteria_correct": str(sum(r.verdict.criteria_correct for r in graded)),
                "criteria_total": str(sum(r.verdict.criteria_total for r in graded)),
                "not_graded": str(sum(r.result == NOT_GRADED for r in mine)),
                "no_reply": str(sum(r.result == NO_REPLY for r in mine)),
            }
        )
    return rows


def split_table(rs: list[Reply], tag: str) -> list[dict]:
    rows = []
    for group in sorted({r.tags[tag] for r in rs}):
        for model in [*_models(rs), ALL_MODELS]:
            graded = [
                r
                for r in rs
                if r.graded and r.tags[tag] == group and model in (ALL_MODELS, r.model)
            ]
            passed = sum(r.passed for r in graded)
            drawings = len({r.drawing for r in graded})
            rows.append(
                {
                    tag: group,
                    "model": model,
                    "drawings": str(drawings),
                    "replies_graded": str(len(graded)),
                    "passed": str(passed),
                    **rate_cells(passed, len(graded), drawings, with_range=model != ALL_MODELS),
                }
            )
    return rows


def runs_passed_per_drawing(all_rs: list[Reply]) -> list[dict]:
    models = _models(all_rs)
    per: dict[str, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    for r in all_rs:
        if r.result == NO_REPLY:
            continue
        per[r.drawing]  # every answered drawing gets a row, even with nothing graded
        if r.result in (PASS, FAIL):  # a reply that couldn't be graded is neither
            per[r.drawing][r.model].append(r.passed)
    return [
        {
            "drawing": drawing,
            **{
                m: f"{sum(per[drawing][m])} of {len(per[drawing][m])}" if per[drawing][m] else ""
                for m in models
            },
        }
        for drawing in sorted(per)
    ]


def consistency_by_model(all_rs: list[Reply]) -> list[dict]:
    """Drawings graded 2 or more times: did the model give the same verdict every time?

    A reply that couldn't be graded is neither a pass nor a fail, so it is left out.
    """
    per: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for r in all_rs:
        if r.result in (PASS, FAIL):
            per[(r.model, r.drawing)].append(r.passed)
    rows = []
    for model in _models(all_rs):
        runs = [v for (m, _), v in per.items() if m == model and len(v) >= 2]
        always_pass = sum(all(v) for v in runs)
        always_fail = sum(not any(v) for v in runs)
        rows.append(
            {
                "model": model,
                "drawings_run_more_than_once": str(len(runs)),
                "always_passed": str(always_pass),
                "always_failed": str(always_fail),
                "mixed": str(len(runs) - always_pass - always_fail),
                "same_answer_every_run_percent": _percent(always_pass + always_fail, len(runs)),
            }
        )
    return rows


def _missed_sizes(rs: list[Reply]) -> list[tuple[str, str, str]]:
    """(model, missed size, label) for every size missed by a failed reply."""
    out = []
    for r in rs:
        if r.result != FAIL:
            continue
        labels = {m: label for m, label, _ in r.labels}
        for missed in r.verdict.dims_missed:
            out.append((r.model, missed, labels.get(missed, NOT_DIAGNOSED)))
    return out


def _axis(missed: str) -> str:
    """ "L (Y)" -> "Y"; a diameter has no axis."""
    return missed.partition("(")[2].rstrip(")") or "none (diameter)"


def failures_table(rs: list[Reply], column: str, key) -> list[dict]:
    models = _models(rs)
    counts: dict[str, Counter] = defaultdict(Counter)
    for model, missed, label in _missed_sizes(rs):
        counts[key(missed, label)][model] += 1
    return [
        {column: k, **{m: str(counts[k][m]) for m in models}, "total": str(sum(counts[k].values()))}
        for k in sorted(counts)
    ]


def tolerance_audit(rs: list[Reply]) -> list[dict]:
    return [
        {
            "drawing": r.drawing,
            "model": r.model,
            "run": r.run,
            "converted_readings_used": _converted(r),
        }
        for r in rs
        if _converted(r)
    ]


def tables(all_rs: list[Reply]) -> dict[str, list[dict]]:
    """Every table in SPEC 2.10, by file name. Run 1 only, except the consistency pair."""
    rs = headline(all_rs)
    out = {
        "pass-rate-by-model": pass_rate_by_model(rs),
        "runs-passed-per-drawing": runs_passed_per_drawing(all_rs),
        "consistency-by-model": consistency_by_model(all_rs),
    }
    for name, tag in SPLITS:
        out[name] = split_table(rs, tag)
    out["failures-by-label"] = failures_table(rs, "label", lambda missed, label: label)
    out["failures-by-axis"] = failures_table(rs, "axis", lambda missed, label: _axis(missed))
    out["failures-by-dimension"] = failures_table(
        rs, "dimension", lambda missed, label: missed.split(" ")[0]
    )
    out["tolerance-audit"] = tolerance_audit(rs)
    return out


LABEL_REVIEW = "label-review"  # the one table built from the casebook, not every-run.csv


def folder_groups(folder: str, every_run: list[dict]) -> set[str]:
    """The failure groups with a reply in this results folder's every-run.csv."""
    published = {(r["drawing"], r["model"], r["run"]) for r in every_run}
    groups, _ = diagnosis.failure_groups(folder)
    return {
        g.name
        for g in groups
        if any(
            (g.drawing.removesuffix(".pdf"), r.model, r.run_number) in published for r in g.replies
        )
    }


def folder_agreement(folder: str, every_run: list[dict]) -> casebook.Agreement:
    """Garron's rulings on the labels in this folder only, so one folder's review can't
    change another folder's figure."""
    return casebook.agreement(folder, folder_groups(folder, every_run))


def label_review(agreement: casebook.Agreement) -> list[dict]:
    """How often Garron kept the agent's own labels (SPEC 2.6). Reused labels don't count."""
    low, high = agreement.range
    reviewed = agreement.reviewed
    return [
        {
            "agent_labels_evaluator_reviewed": str(reviewed),
            "evaluator_kept_agent_label": str(agreement.agreed),
            "evaluator_changed_agent_label": str(reviewed - agreement.agreed),
            "kept_percent": _percent(agreement.agreed, reviewed),
            "range_low_percent": f"{100 * low:.0f}" if reviewed else "",
            "range_high_percent": f"{100 * high:.0f}" if reviewed else "",
        }
    ]


# --- writing the folder --------------------------------------------------------------

TABLE_COLUMNS = {
    "tolerance-audit": ["drawing", "model", "run", "converted_readings_used"],
}


def _write_csv(path: Path, rows: list[dict], columns: list[str] | None = None) -> None:
    columns = columns or (list(rows[0]) if rows else TABLE_COLUMNS.get(path.stem, []))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def _run_settings(all_rs: list[Reply], folder: str) -> dict:
    calls = [r.row.call for r in all_rs]
    extractors = sorted(
        {r.row.extraction.get("model_version", "") for r in all_rs if r.row.extraction}
    )
    models = {}
    for c in calls:
        m = models.setdefault(
            c["model_requested"],
            {
                "name": c["model_name"],
                "maker": c["maker"],
                "versions": set(),
                "thinking": c["thinking"],
                "what_the_maker_default_means": c.get("maker_default_thinking", ""),
            },
        )
        if c.get("model_version"):
            m["versions"].add(c["model_version"])
    for m in models.values():
        m["versions"] = sorted(m["versions"])
    dates = sorted(c["started_at"][:10] for c in calls)
    return {
        "calls_folder": folder,
        "prompt": sorted({c["prompt"] for c in calls}),
        "models": models,
        "drawings": len({r.drawing for r in all_rs}),
        "most_runs_per_drawing": max(int(r.run) for r in all_rs),
        "replies": len(all_rs),
        "dates": {"first": dates[0], "last": dates[-1]},
        "extraction_model": extractors,
        "headline_tables_use": f"run {HEADLINE_RUN} of every drawing",
        "scoring_rules": "docs/scoring-rules.md",
    }


LICENSE_NOTICE = """# License notice

The replies, tables and evidence in this folder are derived from the engineering
drawings in `drawings/`. They fall under the drawings' license,
[`DRAWINGS-LICENSE`](../../DRAWINGS-LICENSE), not the code's MIT license.
"""


def folder_name(folder: str, drawings: int, when: date) -> str:
    """Dated by the run's last reply, so a rebuild on another day replaces the folder."""
    prompt = "stock-shape" if folder == DEFAULT_FOLDER else folder
    return f"{when.isoformat()}-{prompt}-{drawings}-drawings"


def _last_reply(all_rs: list[Reply]) -> date:
    return max(date.fromisoformat(r.row.call["started_at"][:10]) for r in all_rs)


def _page(every_run, tables_, settings, review) -> str:
    charts = {name for name, rows in _charts(tables_).items() if rows}
    return report_page.page(
        every_run,
        tables_,
        settings,
        review,
        charts,
        pooled=ALL_MODELS,
        headline_run=HEADLINE_RUN,
        small_group=SMALL_GROUP,
    )


def _charts(tables_: dict[str, list[dict]]) -> dict[str, list[dict]]:
    return report_charts.chart_data(tables_, pooled=ALL_MODELS)


def build(folder: str = DEFAULT_FOLDER, results: Path = RESULTS) -> Path:
    """Write the results folder for one calls folder. Spends $0."""
    if folder == run_plan.TEST_FOLDER:
        raise ReportError("Test runs are kept out of published results.")
    return write_folder(replies(folder), folder, results)


def write_folder(
    all_rs: list[Reply],
    folder: str,
    results: Path = RESULTS,
    agreement: casebook.Agreement | None = None,
) -> Path:
    """The results folder for these replies. Refuses anything not fit to publish."""
    waiting = [r for r in all_rs if r.row.status == replay.NOT_EXTRACTED]
    if waiting:
        raise ReportError(
            f"{len(waiting)} replies haven't had their numbers pulled out yet: "
            f"run uv run vlm-eval extract {folder}"
        )
    drawings = len({r.drawing for r in headline(all_rs)})
    if drawings < MIN_DRAWINGS:
        raise ReportError(
            f"{folder} has {drawings} drawings; under {MIN_DRAWINGS} is a test run, "
            "never published."
        )
    out = results / folder_name(folder, drawings, _last_reply(all_rs))
    if out.exists():
        shutil.rmtree(out)  # a rebuild replaces the folder entirely
    out.mkdir(parents=True)
    every_run = [every_run_row(r) for r in all_rs]
    _write_csv(out / "every-run.csv", every_run, list(EVERY_RUN_COLUMNS))
    all_tables = tables(all_rs)
    for name, rows in all_tables.items():
        _write_csv(out / "tables" / f"{name}.csv", rows)
    review = label_review(agreement or folder_agreement(folder, every_run))
    _write_csv(out / "tables" / f"{LABEL_REVIEW}.csv", review)
    report_charts.write(out, _charts(all_tables))
    settings = _run_settings(all_rs, folder)
    for r in all_rs:
        if r.result != NO_REPLY:
            model_id = r.row.call["model_requested"]
            path = out / "raw-replies" / model_id / f"{r.drawing}-run{r.run}.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(r.row.call["reply_text"])
    (out / "run-settings.json").write_text(json.dumps(settings, indent=2) + "\n")
    (out / "LICENSE-NOTICE.md").write_text(LICENSE_NOTICE)
    (out / "README.md").write_text(_page(every_run, all_tables, settings, review))
    return out


def published_folders(results: Path = RESULTS) -> list[Path]:
    """Every results folder, the one with fewest drawings first."""
    found = [p for p in results.iterdir() if (p / "every-run.csv").exists()]
    return sorted(found, key=lambda p: (len(_drawings(p)), p.name))


def _drawings(out: Path) -> set[str]:
    return {r["drawing"] for r in _read_csv(out / "every-run.csv")}


def update_readme(readme: Path = README, results: Path = RESULTS) -> None:
    """The main README's results section, listing every results folder."""
    readme.write_text(
        report_page.replace_section(readme.read_text(), _readme_section(readme, results))
    )


def _readme_section(readme: Path, results: Path) -> str:
    evaluations = []
    for out in published_folders(results):
        every_run = _read_csv(out / "every-run.csv")
        evaluations.append(
            report_page.Evaluation(
                link=out.relative_to(readme.parent).as_posix() + "/",
                tables=recompute(every_run),
                settings=json.loads((out / "run-settings.json").read_text()),
                first_answers={
                    (r["drawing"], r["model"]) for r in every_run if r["run"] == HEADLINE_RUN
                },
            )
        )
    return report_page.readme_section(evaluations, ALL_MODELS, HEADLINE_RUN)


def readme_check(readme: Path = README, results: Path = RESULTS) -> list[str]:
    """The main README's results section, rebuilt from every results folder."""
    text = readme.read_text()
    if report_page.START not in text:
        return ["README.md has no results section"]
    section = text.partition(report_page.START)[2].partition(report_page.END)[0]
    if report_page.START + section + report_page.END != _readme_section(readme, results):
        return ["README.md's results section disagrees with the results folders"]
    return []


def waiting_for_garron(all_rs: list[Reply]) -> int:
    """Missed sizes whose label isn't Garron's yet: not diagnosed, or not reviewed."""
    return sum(label in (NOT_DIAGNOSED, NOT_REVIEWED) for r in all_rs for _, label, _ in r.labels)


# --- the checks ----------------------------------------------------------------------


def recompute(every_run: list[dict]) -> dict[str, list[dict]]:
    """Every table again, from every-run.csv's text alone. Shares no counting code."""
    first = [r for r in every_run if r["run"] == HEADLINE_RUN]
    models = sorted({r["model"] for r in every_run})
    graded = [r for r in first if r["result"] in (PASS, FAIL)]

    def rate_rows(rows, extra):
        out = []
        for model in [*models, ALL_MODELS]:
            mine = [r for r in rows if model in (ALL_MODELS, r["model"])]
            passed = sum(r["result"] == PASS for r in mine)
            row = {
                **extra,
                "model": model,
                "drawings": str(len({r["drawing"] for r in mine})),
                "replies_graded": str(len(mine)),
                "passed": str(passed),
                **rate_cells(
                    passed,
                    len(mine),
                    len({r["drawing"] for r in mine}),
                    with_range=model != ALL_MODELS,
                ),
            }
            out.append(row)
        return out

    by_model = []
    for row in rate_rows(graded, {}):
        model = row["model"]
        mine = [r for r in first if model in (ALL_MODELS, r["model"])]
        ok = [r for r in mine if r["result"] in (PASS, FAIL)]
        row["criteria_correct"] = str(sum(int(r["correct"]) for r in ok))
        row["criteria_total"] = str(sum(int(r["total_criteria"]) for r in ok))
        row["not_graded"] = str(sum(r["result"] == NOT_GRADED for r in mine))
        row["no_reply"] = str(sum(r["result"] == NO_REPLY for r in mine))
        by_model.append(row)
    out = {"pass-rate-by-model": by_model}

    answered = [r for r in every_run if r["result"] != NO_REPLY]
    per: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for r in answered:
        if r["result"] in (PASS, FAIL):
            per[(r["drawing"], r["model"])].append(r["result"] == PASS)
    out["runs-passed-per-drawing"] = [
        {
            "drawing": d,
            **{
                m: f"{sum(per[(d, m)])} of {len(per[(d, m)])}" if (d, m) in per else ""
                for m in models
            },
        }
        for d in sorted({r["drawing"] for r in answered})
    ]
    consistency = []
    for m in models:
        runs = [v for (_, mm), v in per.items() if mm == m and len(v) >= 2]
        agree = [v for v in runs if len(set(v)) == 1]
        passes = sum(v[0] for v in agree)
        consistency.append(
            {
                "model": m,
                "drawings_run_more_than_once": str(len(runs)),
                "always_passed": str(passes),
                "always_failed": str(len(agree) - passes),
                "mixed": str(len(runs) - len(agree)),
                "same_answer_every_run_percent": _percent(len(agree), len(runs)),
            }
        )
    out["consistency-by-model"] = consistency

    for name, tag in SPLITS:
        out[name] = [
            row
            for group in sorted({r[tag] for r in graded})
            for row in rate_rows([r for r in graded if r[tag] == group], {tag: group})
        ]

    missed = []  # (model, missed size, label)
    for r in first:
        if r["result"] != FAIL:
            continue
        labels = dict(part.split(": ", 1) for part in r["label"].split("; ") if part)
        for size in r["missed"].split("; "):
            missed.append((r["model"], size, labels.get(size, NOT_DIAGNOSED)))

    def counted(column, key):
        tally: dict[str, Counter] = defaultdict(Counter)
        for model, size, label in missed:
            tally[key(size, label)][model] += 1
        return [
            {
                column: k,
                **{m: str(tally[k][m]) for m in models},
                "total": str(sum(tally[k].values())),
            }
            for k in sorted(tally)
        ]

    out["failures-by-label"] = counted("label", lambda size, label: label)
    out["failures-by-axis"] = counted(
        "axis",
        lambda size, label: size[size.find("(") + 1 : -1] if "(" in size else "none (diameter)",
    )
    out["failures-by-dimension"] = counted("dimension", lambda size, label: size.split(" ")[0])
    out["tolerance-audit"] = [
        {k: r[k] for k in ("drawing", "model", "run", "converted_readings_used")}
        for r in first
        if r["converted_readings_used"]
    ]
    return out


def recompute_check(out: Path) -> list[str]:
    """Every table file against the same table rebuilt from every-run.csv. [] if all agree."""
    every_run = _read_csv(out / "every-run.csv")
    again = recompute(every_run)
    problems = []
    written = {p.stem: p for p in (out / "tables").glob("*.csv") if p.stem != LABEL_REVIEW}
    for name in sorted(set(again) | set(written)):
        if name not in written:
            problems.append(f"tables/{name}.csv is missing")
        elif name not in again:
            problems.append(f"tables/{name}.csv is not recomputed by the check")
        elif _read_csv(written[name]) != again[name]:
            problems.append(f"tables/{name}.csv disagrees with every-run.csv")

    settings = json.loads((out / "run-settings.json").read_text())
    review_path = out / "tables" / f"{LABEL_REVIEW}.csv"
    review = _read_csv(review_path) if review_path.exists() else []
    if review != label_review(folder_agreement(settings["calls_folder"], every_run)):
        problems.append(f"tables/{LABEL_REVIEW}.csv disagrees with Garron's casebook")

    for name, rows in _charts(again).items():
        path = out / "charts" / f"{name}.csv"
        if rows and not (path.exists() and (out / "charts" / f"{name}.png").exists()):
            problems.append(f"charts/{name} is missing")
        elif rows and _read_csv(path) != rows:
            problems.append(f"charts/{name}.csv disagrees with every-run.csv")
        elif not rows and path.exists():
            problems.append(f"charts/{name}.csv should not exist: it has nothing to draw")

    page_path = out / "README.md"
    if not page_path.exists():
        problems.append("README.md is missing")
    elif page_path.read_text() != _page(every_run, again, settings, review):
        problems.append("README.md disagrees with every-run.csv")
    return problems


# Private things that must never reach the public folder.
FORBIDDEN = {
    "a dollar amount": re.compile(r"\$\s?\d"),
    "a cost field": re.compile(r"cost_usd|price_per_million", re.I),
    "an API key": re.compile(r"api[_ ]key|\bsk-[a-z0-9_-]{12,}|\bAIza[0-9A-Za-z_-]{20,}", re.I),
    "a path into runs/": re.compile(r"(?<![\w-])runs/"),
    "a request ID": re.compile(r"request_id|\breq_[0-9a-f]{16,}|\bmsg_[0-9A-Za-z]{16,}"),
    "the evaluator's name": EVALUATOR_NAME,
}


def publish_check(out: Path) -> list[str]:
    """Nothing private in the folder: no costs, keys, or paths into runs/.

    Raw replies are skipped: they are the models' own words, published as they are.
    """
    problems = []
    for path in sorted(out.rglob("*")):
        if not path.is_file() or "raw-replies" in path.relative_to(out).parts:
            continue
        if path.suffix == ".png":
            continue  # a picture, drawn from a CSV that is checked
        text = path.read_text(errors="ignore")
        for what, pattern in FORBIDDEN.items():
            if pattern.search(text):
                problems.append(f"{path.relative_to(out)} contains {what}")
    return problems


# --- the Cowork message (private) ---------------------------------------------------

COWORK_NOTES = paths.RUNS / "cowork-notes.md"  # Garron's answers, asked once (SPEC 2.10)

COWORK_RULES = """\
- Take every number from the attached files. Don't recompute a number a table already gives.
- Pass rates count each drawing once per model, using its first answer (run 1). The later
  runs measure only whether a model gives the same verdict every time. Keep the two apart.
- Give each pass rate with its 95% range. Call one model better than another only where
  their ranges don't overlap; the results page says whether they do.
- A group of fewer than {small} drawings gets counts, never a rate.
- Use only the failure labels above, with their definitions. A note that
  says "Watch list:" marks a possible new kind of failure filed as Unclassified: mention it
  as a candidate, never as a label.
- The failure counts are small, so whenever a share of failures appears as a percentage,
  give the count beside it ("n of N missed sizes").
- Say who labelled the failures: Claude, an Anthropic model, proposed each label, and I
  reviewed every one. `tables/label-review.csv` shows how often I kept Claude's label. Say
  this plainly, because Claude labelled failures by Anthropic's own model.
- Quote the question the models received word for word, and say that each model received
  each drawing as a PDF with no other instructions.
"""


def _cowork_files(out: Path) -> list[tuple[Path, str]]:
    files = [
        (out / "README.md", "the results page. Start here: it explains the evaluation, gives "
         "every key number with its source table, and lists the limits"),
        (out / "tables", "every table on the results page, as CSV"),
        (out / "charts", "the charts as PNG, each beside the CSV of the numbers it draws"),
        (out / "every-run.csv", "one row per model reply, with the failure label and evidence "
         "for each missed size"),
        (out / "run-settings.json", "the models, versions, thinking settings, dates and the "
         "exact question"),
        (paths.ROOT / "docs" / "scoring-rules.md", "how code grades a reply"),
    ]  # fmt: skip
    return [(path, what) for path, what in files if path.exists()]


PLAYBOOK = paths.ROOT / "docs" / "diagnosis-playbook.md"


def failure_labels(playbook: Path = PLAYBOOK) -> list[tuple[str, str]]:
    """(label, definition) from the playbook's label table.

    Only the table goes to Cowork: the playbook's worked examples are working notes for the
    agent, not results.
    """
    text = playbook.read_text().partition("## The labels")[2]
    rows = []
    for line in text.splitlines()[1:]:
        if rows and not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) == 2 and cells[0] not in ("Label", "---"):
            rows.append((re.sub(r"\s*\(research example [^)]*\)", "", cells[0]), cells[1]))
    return rows


def cowork_message(out: Path, notes: Path = COWORK_NOTES) -> str | None:
    """The message Garron pastes into Cowork, or None until his notes exist."""
    if not notes.exists():
        return None
    text = notes.read_text()
    background = text[text.index("\n## ") + 1 :] if "\n## " in text else text
    background = re.sub(r"(?m)^## ", "### ", background).strip()
    files = "\n".join(f"- `{path}`: {what}" for path, what in _cowork_files(out))
    return (
        "\n\n".join(
            [
                f"# Message for Cowork: {out.name}",
                "Paste everything below the line into Cowork, and attach the files it lists.",
                "---",
                "Please draft a research paper from the results of an evaluation I ran. I'm the "
                "author, Garron Ware. I'll design the layout myself, so give me the text and the "
                "tables, and say which chart goes where.",
                "## Background, in my words",
                background,
                "## Files to attach",
                files,
                "## The failure labels",
                "Each missed size has exactly one label. Datum reconstruction wins over Chain "
                "aggregation; when any other two labels fit equally well, the label is "
                "Unclassified.",
                "\n".join(f"- **{label}:** {definition}" for label, definition in failure_labels()),
                "## Rules for the paper",
                COWORK_RULES.format(small=SMALL_GROUP).strip(),
            ]
        )
        + "\n"
    )


def write_cowork_message(out: Path, notes: Path = COWORK_NOTES, runs: Path = paths.RUNS):
    """runs/cowork-message-<folder>.md; None, with nothing written, until the notes exist."""
    message = cowork_message(out, notes)
    if message is None:
        return None
    path = runs / f"cowork-message-{out.name}.md"
    path.write_text(message)
    return path


def only_drawing_set(all_rs: list[Reply], choice: str) -> list[Reply]:
    """The replies for one fixed drawing set (30, 60 or 141), e.g. to rebuild an earlier folder."""
    wanted = set(run_plan.drawings_for(choice))
    return [r for r in all_rs if r.row.call["drawing"] in wanted]


def runs_every_drawing_has(all_rs: list[Reply]) -> list[Reply]:
    """Only the runs every drawing in the folder has, so a folder is one evaluation.

    The 30-drawing set ran 3 times and the other 111 drawings once, so the full set's
    folder holds run 1 only, and the extra runs stay with the 30-drawing folder.
    """
    runs: dict[str, set[str]] = defaultdict(set)
    for r in all_rs:
        runs[r.drawing].add(r.run)
    common = set.intersection(*runs.values()) if runs else set()
    return [r for r in all_rs if r.run in common]


def cli(args: list[str]) -> None:
    """`vlm-eval build-report [run] [--drawings 30|60]`. Spends $0.

    With --drawings, the folder covers only that fixed set. A folder holds only the runs
    every one of its drawings has. Every build rewrites the main README's results section
    to list every results folder.
    """
    names = [a for a in args if not a.startswith("--")]
    choice = args[args.index("--drawings") + 1] if "--drawings" in args else ""
    names = [n for n in names if n != choice]
    folder = names[0] if names else DEFAULT_FOLDER
    if folder == run_plan.TEST_FOLDER:
        raise ReportError("Test runs are kept out of published results.")
    all_rs = replies(folder)
    if choice:
        all_rs = only_drawing_set(all_rs, choice)
    all_rs = runs_every_drawing_has(all_rs)
    out = write_folder(all_rs, folder)
    update_readme()
    rel = out.relative_to(paths.ROOT)
    checks = (
        ("recompute", recompute_check),
        ("publish", publish_check),
        ("main README", lambda _: readme_check()),
    )
    for name, check in checks:
        problems = check(out)
        if problems:
            print(f"{name} check found problems:")
            print("\n".join(f"  - {p}" for p in problems))
        else:
            print(f"{name} check passed")
    if waiting := waiting_for_garron(all_rs):
        print(f"{waiting} missed sizes don't have Garron's label yet; they say so in the folder")
    print(f"Wrote {rel}/ (spent $0: nothing was sent)")
    message = write_cowork_message(out)
    if message:
        print(f"Cowork message: {message.relative_to(paths.ROOT)}")
    else:
        print("No Cowork message yet: ask Garron the Cowork questions (SPEC 2.10) first")
