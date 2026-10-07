"""Writes data/grading-examples.html: pretend replies to real drawings, graded by the scorer.

The replies are made up to show the grading rules that matter most. The result
and the count on each row come from `scoring.score`. Each example also states
the result it is meant to show; if the scorer ever disagrees, building the page
fails instead of showing a wrong explanation.
"""

from __future__ import annotations

import csv
import html
import webbrowser
from dataclasses import dataclass

from vlm_eval import paths, scoring
from vlm_eval.answers import Answer, Envelope
from vlm_eval.answers import AnswerValue as V
from vlm_eval.ground_truth import Drawing, read_ground_truth

PASS, FAIL, NOT_GRADED = "PASS", "FAIL", "NOT GRADED"


@dataclass(frozen=True)
class Example:
    file: str
    reply: str  # how the pretend reply reads
    answer: Answer  # the same reply as the scorer receives it
    expected: str  # PASS | FAIL | NOT GRADED
    why: str  # one plain sentence


EXAMPLES = [
    Example(
        "201551-016.pdf",
        "63.5 × 19.1 × 25.4 mm",
        Answer((V("63.5", "mm"), V("19.1", "mm"), V("25.4", "mm"))),
        PASS,
        "All three sizes are right. For a CUBE the order doesn't matter, the same "
        "way flat stock is ordered.",
    ),
    Example(
        "201551-016.pdf",
        "2.50 × .75 × 1.00 in",
        Answer((V("2.50", "in"), V(".75", "in"), V("1.00", "in"))),
        PASS,
        "The same sizes in inches. Either unit is fine.",
    ),
    Example(
        "201551-016.pdf",
        "63.5 × 25.4 mm",
        Answer((V("63.5", "mm"), V("25.4", "mm"))),
        FAIL,
        "Only two sizes given. The 19.1 is missing.",
    ),
    Example(
        "201551-016.pdf",
        "63.5 × 19.0 × 25.4 mm",
        Answer((V("63.5", "mm"), V("19.0", "mm"), V("25.4", "mm"))),
        FAIL,
        "19.0 is a different number printed on the same sheet, not the 19.1.",
    ),
    Example(
        "201011.pdf",
        "Ø8.000 × 90.0 mm long",
        Answer((V("8.000", "mm", "Ø"), V("90.0", "mm", "length"))),
        PASS,
        "Diameter and length both right.",
    ),
    Example(
        "201011.pdf",
        "Diameter 90.0 mm, length 8.000 mm",
        Answer((V("90.0", "mm", "diameter"), V("8.000", "mm", "length"))),
        FAIL,
        "Diameter and length are swapped. On a cylinder they are not interchangeable.",
    ),
    Example(
        "201011.pdf",
        "8.000 × 90.0 mm",
        Answer((V("8.000", "mm"), V("90.0", "mm"))),
        NOT_GRADED,
        "The reply doesn't say which number is the diameter, so it's flagged for you "
        "to look at instead of guessed.",
    ),
    Example(
        "201011.pdf",
        "Bounding box 8.000 × 8.000 × 90.0 mm. Cylindrical envelope Ø8.000 × 90.0 mm long.",
        Answer(
            (V("8.000", "mm", "width"), V("8.000", "mm", "height"), V("90.0", "mm", "length")),
            "CUBE",
            other_envelopes=(Envelope((V("8.000", "mm", "Ø"), V("90.0", "mm", "long")), "CYL"),),
        ),
        PASS,
        "The reply gives the same envelope twice, as a box and as a cylinder. Both are "
        "right, so it passes; the extra wording isn't counted against it.",
    ),
    Example(
        "201011.pdf",
        "Bounding box 8.000 × 8.000 × 90.0 mm.",
        Answer(
            (V("8.000", "mm", "width"), V("8.000", "mm", "height"), V("90.0", "mm", "length")),
            "CUBE",
        ),
        PASS,
        "A box for a round part. The prompt never asked for a shape, and this is the box "
        "that Ø8.000 × 90.0 fills, so it describes the same envelope.",
    ),
    Example(
        "201011.pdf",
        "Bounding box 6.000 × 8.000 × 90.0 mm.",
        Answer(
            (V("6.000", "mm", "width"), V("8.000", "mm", "height"), V("90.0", "mm", "length")),
            "CUBE",
        ),
        FAIL,
        "A box 6.000 wide could not hold a Ø8.000 part. A smaller number from a feature "
        "is not a bounding dimension.",
    ),
    Example(
        "200951.pdf",
        "40.64 × 91.0 × 72.91 mm",
        Answer((V("40.64", "mm"), V("91.0", "mm"), V("72.91", "mm"))),
        PASS,
        "The model added up the chain 34.29 + 6.35 = 40.64 itself.",
    ),
    Example(
        "200951.pdf",
        "34.29 × 91.0 × 72.91 mm",
        Answer((V("34.29", "mm"), V("91.0", "mm"), V("72.91", "mm"))),
        FAIL,
        "The model gave one part of the chain instead of adding both. The result "
        "notes that, so you can see it at a glance.",
    ),
]


def inch_values() -> dict[tuple[str, str], str]:
    with paths.INCH_PARTNERS_CSV.open(newline="") as fh:
        return {(r["file"], r["label"]): r["final_inch"] for r in csv.DictReader(fh)}


def your_numbers(drawing: Drawing, inch: dict[tuple[str, str], str]) -> str:
    """The ground truth as recorded, with the printed inch value beside each mm value."""
    unit = "mm" if drawing.print_type == "dual" else "in"
    lines = []
    for d in drawing.dimensions:
        text = f"<b>{d.label}</b> {html.escape(d.printed)}"
        if drawing.print_type == "dual":
            text += f' <span class="inch">[{html.escape(inch[(drawing.file, d.label)])} in]</span>'
        lines.append(text)
    return "<br>".join(lines) + f'<div class="unit">{unit}</div>'


def result_label(verdict: scoring.Verdict) -> str:
    if not verdict.scored:
        return NOT_GRADED
    return PASS if verdict.strict_pass else FAIL


def found_text(verdict: scoring.Verdict) -> str:
    if not verdict.scored:
        return ""
    found = f"{verdict.dims_correct} of {verdict.dims_total} sizes found"
    if verdict.dims_missed:
        found += f"; missed {', '.join(verdict.dims_missed)}"
    notes = "".join(f'<div class="note">{html.escape(n)}</div>' for n in verdict.chain_parts_given)
    return f'<div class="found">{html.escape(found)}</div>{notes}'


def _rows() -> str:
    drawings = {d.file: d for d in read_ground_truth(classify_pdfs=False)}
    inch = inch_values()
    rows = []
    for ex in EXAMPLES:
        verdict = scoring.score(ex.file, ex.answer)
        result = result_label(verdict)
        if result != ex.expected:
            raise AssertionError(
                f"{ex.file} '{ex.reply}': scorer says {result}, example expects {ex.expected}"
            )
        badge = result.lower().replace(" ", "-")
        rows.append(
            "<tr>"
            f'<td class="drawing">{html.escape(ex.file.removesuffix(".pdf"))}<div class="shape">'
            f"{'CUBE' if drawings[ex.file].shape == 'CUBE' else 'cylinder'}</div></td>"
            f"<td>{your_numbers(drawings[ex.file], inch)}</td>"
            f'<td class="reply">“{html.escape(ex.reply)}”</td>'
            f'<td><span class="badge {badge}">{result}</span></td>'
            f"<td>{html.escape(ex.why)}{found_text(verdict)}</td>"
            "</tr>"
        )
    return "\n".join(rows)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Grading Examples</title>
<style>
:root {{ --ink:#1d2330; --soft:#5d6778; --line:#e3e6ec; --bg:#f7f8fa; --card:#fff;
  --pass:#1f7a3f; --pass-bg:#e3f4e8; --fail:#b3261e; --fail-bg:#fbe5e3;
  --flag:#8a5a00; --flag-bg:#fdf1d6; }}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font:16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
main {{ max-width:1100px; margin:0 auto; padding:32px 16px 48px; }}
h1 {{ font-size:28px; margin:0 0 12px; }}
.intro {{ max-width:720px; color:var(--soft); margin:0 0 24px; }}
.intro b {{ color:var(--ink); }}
table {{ width:100%; border-collapse:collapse; background:var(--card);
  border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
th {{ text-align:left; font-size:13px; text-transform:uppercase; letter-spacing:.04em;
  color:var(--soft); background:#fbfbfc; }}
th, td {{ padding:14px 16px; border-bottom:1px solid var(--line); vertical-align:top; }}
tr:last-child td {{ border-bottom:0; }}
.drawing {{ font-weight:600; white-space:nowrap; }}
.shape, .unit {{ font-weight:400; color:var(--soft); font-size:13px; }}
.inch {{ color:var(--soft); }}
.reply {{ font-size:17px; }}
.badge {{ display:inline-block; padding:4px 10px; border-radius:6px; font-weight:700;
  font-size:14px; white-space:nowrap; }}
.pass {{ color:var(--pass); background:var(--pass-bg); }}
.fail {{ color:var(--fail); background:var(--fail-bg); }}
.not-graded {{ color:var(--flag); background:var(--flag-bg); }}
.found {{ color:var(--soft); font-size:14px; margin-top:6px; }}
.note {{ font-size:14px; margin-top:6px; padding:6px 8px; border-radius:6px;
  background:var(--flag-bg); color:var(--flag); }}
footer {{ color:var(--soft); font-size:14px; margin-top:16px; }}
@media (max-width:760px) {{
  table, tbody, tr, td {{ display:block; width:100%; }}
  thead {{ display:none; }}
  tr {{ border-bottom:1px solid var(--line); padding:8px 0; }}
  td {{ border:0; padding:6px 16px; }}
}}
</style>
</head>
<body>
<main>
<h1>How replies will be graded</h1>
<p class="intro">These are <b>pretend model replies</b> to real drawings from your set.
The right answer is always <b>your own number</b> from ground-truth.md, shown in the
“Your numbers” column. For each row, ask one question: <b>if a model replied this,
would I grade it the same way?</b> If any row is wrong, tell Claude which one.</p>
<table>
<thead><tr><th>Drawing</th><th>Your numbers</th><th>Pretend reply</th><th>Result</th>
<th>Why</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
<footer>Each result and count on this page comes from the scorer itself, not typed in
by hand.</footer>
</main>
</body>
</html>
"""


def write() -> str:
    """Build the page and return its path."""
    paths.GRADING_EXAMPLES.write_text(PAGE.format(rows=_rows()))
    return str(paths.GRADING_EXAMPLES)


def write_and_open() -> None:
    path = write()
    print(f"Wrote {path}")
    webbrowser.open(paths.GRADING_EXAMPLES.as_uri())
