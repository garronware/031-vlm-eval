"""Groups failed replies and checks the diagnoses written for them (SPEC 2.6).

Code finds the failures and checks the evidence; the failure-diagnostician agent
(`.claude/agents/`) explains them. Identical failures (same drawing, same missed
dimensions, same wrong numbers) are one group and get one diagnosis, whichever model
or run made them.

Each group has a folder under runs/diagnoses/<calls folder>/<group>/ holding
`brief.md` (everything the agent needs) and, once diagnosed, `diagnosis.json`.

Garron's confirmed labels (the casebook, `casebook.py`) feed back in two ways: every
brief lists them as precedent, and a group whose every missed size he has already
labelled on the same drawing with the same wrong number gets his label copied on,
marked "reused", with no agent run.
"""

from __future__ import annotations

import csv
import html
import json
import webbrowser
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from vlm_eval import casebook, crops, paths, replay, scoring
from vlm_eval.answers import UnreadableNumber, parse_number
from vlm_eval.scoring import UnmatchedValue

DEFAULT_FOLDER = "main-stock-shape"  # the prompt in use from 2026-09-20 on (SPEC 2.1)

# Garron's labels, word for word (SPEC 2.6). Never add or rename one without his approval.
LABELS = (
    "Proximity association",
    "Axis mapping",
    "Section-view selection",
    "Chain aggregation",
    "Datum reconstruction",
    "Feature substitution",
    "Unclassified",
)
WRONG_VALUE_AXES = ("X", "Y", "Z", "none", "unclear")
NO_WRONG_VALUE = "none"  # the reply gave no number for this dimension at all

PLAYBOOK = paths.ROOT / "docs" / "diagnosis-playbook.md"


@dataclass(frozen=True)
class Reply:
    """One failed reply in a group."""

    model: str
    run_number: str
    call_file: Path
    reply_text: str
    model_version: str
    wrong_values: tuple[UnmatchedValue, ...]  # as this reply wrote them


@dataclass
class Group:
    name: str
    drawing: str  # PDF file name
    missed: tuple[str, ...]  # e.g. ("L (Y)",), as the scorer reports it
    wrong_numbers: tuple[str, ...]  # normalised, e.g. ("78",)
    chain_parts_given: tuple[str, ...]
    replies: list[Reply] = field(default_factory=list)

    @property
    def models(self) -> list[str]:
        return sorted({r.model for r in self.replies})


def _normalised(number: str) -> str:
    """`78.0` and `78.00` are the same printed size."""
    try:
        value = parse_number(number)
    except UnreadableNumber:
        return number
    return format(value.normalize(), "f")


def _label(missed: str) -> str:
    return missed.split(" ")[0]  # "L (Y)" -> "L"


def failure_groups(folder: str = DEFAULT_FOLDER) -> tuple[list[Group], list[replay.Row]]:
    """Every graded failure in a calls folder, grouped; plus replies that weren't graded.

    Ungraded replies are listed so nothing disappears quietly, but they are never
    diagnosed: there is no score for a diagnosis to explain.
    """
    groups: dict[tuple, Group] = {}
    ungraded = []
    for row in replay.replay(folder):
        v = row.verdict
        if v is None or not v.scored:
            ungraded.append(row)
            continue
        if v.strict_pass:
            continue
        model, drawing, run_number = replay.parts(row)
        wrong = tuple(sorted((_normalised(u.number), u.unit) for u in v.unmatched_values))
        key = (row.call["drawing"], v.dims_missed, wrong)
        if key not in groups:
            name = "-".join(
                [drawing, *(_label(m) for m in v.dims_missed), *(n for n, _ in wrong)]
            ).replace("/", "_")
            groups[key] = Group(
                name,
                row.call["drawing"],
                v.dims_missed,
                tuple(n for n, _ in wrong),
                v.chain_parts_given,
            )
        groups[key].replies.append(
            Reply(
                model,
                run_number,
                row.call_file,
                row.call.get("reply_text", ""),
                row.call.get("model_version") or row.call.get("model_requested", ""),
                v.unmatched_values,
            )
        )
    return sorted(groups.values(), key=lambda g: g.name), ungraded


# --- briefs ------------------------------------------------------------------------


def group_folder(folder: str, group: Group) -> Path:
    return paths.DIAGNOSES / folder / group.name


def diagnosis_path(folder: str, group: Group) -> Path:
    return group_folder(folder, group) / "diagnosis.json"


def _ground_truth_rows() -> dict[str, dict[str, str]]:
    with paths.GROUND_TRUTH_CSV.open(newline="") as f:
        return {row["file"]: row for row in csv.DictReader(f)}


def _shown(path: Path) -> str:
    """A path as the brief shows it: from the project folder when it is inside it."""
    try:
        return path.relative_to(paths.ROOT).as_posix()
    except ValueError:
        return str(path)


def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


CASEBOOK_RULE = (
    "These are Garron's rulings. They outrank the playbook's general wording. If this "
    "group is on the same drawing with the same wrong number, use his label. Otherwise "
    "follow his reasons as precedent, and if your case goes against one of them, say so "
    "in the note."
)


def casebook_section(folder: str, group: Group, trial: bool = False) -> list[str]:
    """Garron's confirmed labels as Markdown lines, this drawing's first.

    In a trial the group's own rulings are left out, so a test of the agent can't copy
    the answer it is being tested on.
    """
    book = casebook.entries()
    if trial:
        book = [e for e in book if (e["run_folder"], e["group"]) != (folder, group.name)]
    lines = ["## Garron's casebook (his confirmed labels — precedent)", ""]
    if not book:
        return lines + ["No confirmed labels yet."]
    book.sort(key=lambda e: e["drawing"] != group.drawing)  # stable: oldest first within
    lines += [
        "| Drawing | Missed size | Wrong number | Garron's label | His reason |",
        "|---|---|---|---|---|",
    ]
    for e in book:
        label = e["garron_label"]
        if e["garron_label"] != e["agent_label"]:
            label += f" (changed from {e['agent_label']})"
        reason = str(e.get("reason", "")).strip() or "Agreed with the agent's label."
        if str(e.get("note", "")).strip():
            reason += f" Note: {e['note'].strip()}"
        lines.append(
            f"| {_cell(e['drawing'][:-4])} | {_cell(e['missed'])} | {_cell(e['wrong_value'])} "
            f"| {_cell(label)} | {_cell(reason)} |"
        )
    return lines + ["", CASEBOOK_RULE]


def brief(folder: str, group: Group, trial: bool = False, output: Path | None = None) -> str:
    """Everything the agent needs about one group, in plain Markdown.

    `trial` leaves the group's own casebook rulings out; `output` sends the diagnosis
    somewhere other than the real diagnosis.json (both for testing the agent).
    """
    row = _ground_truth_rows()[group.drawing]
    key = scoring.load_answer_key()[group.drawing]
    picture_only = row["pdf_text_type"] == "image_only"
    lines = [
        f"# Failure group {group.name}",
        "",
        f"- Drawing: `drawings/{group.drawing}`",
        f"- Drawing type: {'picture-only (no usable text layer)' if picture_only else 'text'}",
        f"- Shape: {row['shape']} · Units: {row['units']} "
        f"({'dual mm [in]' if row['units'] == 'MM' else 'inch only'}) · "
        f"Projection: {row['projection'] or 'not recorded'}",
        f"- How the envelope is dimensioned: {row['dimension_origin']}"
        + (f" · Measured From: {row['measured_from']}" if row["measured_from"] else ""),
    ]
    if row["notes"]:
        lines.append(f"- Garron's note on this drawing: {row['notes']}")
    lines += ["", "## Garron's ground truth (correct, never question it)", ""]
    lines += ["| Dimension | Axis | Printed value |", "|---|---|---|"]
    for d in key.dimensions:
        lines.append(f"| {d.label} | {d.axis or '-'} | {d.printed} |")
    lines += ["", "## What went wrong", ""]
    lines.append(f"- Missed: {', '.join(group.missed)}")
    lines.append(
        f"- Wrong numbers the reply gave instead: {', '.join(group.wrong_numbers) or 'none'}"
    )
    for note in group.chain_parts_given:
        lines.append(f"- {note}")
    lines.append(
        f"- Made by {len(group.replies)} "
        f"{'reply' if len(group.replies) == 1 else 'replies'}: "
        + ", ".join(f"{r.model} run {r.run_number}" for r in group.replies)
    )
    for r in group.replies:
        values = ", ".join(
            f'{u.number} {u.unit} (called "{u.label or "no label"}")' for u in r.wrong_values
        )
        lines += [
            "",
            f"## Reply from {r.model} ({r.model_version}), run {r.run_number}",
            "",
            f"Wrong numbers in this reply: {values}",
            "",
            "```text",
            r.reply_text.strip(),
            "```",
        ]
    lines += ["", *casebook_section(folder, group, trial)]
    check_command = f"uv run vlm-eval check-diagnoses {folder} {group.name}"
    if output is not None:
        check_command += f" --file {_shown(output)}"
    lines += [
        "",
        "## Your output",
        "",
        f"Write `{_shown(output or diagnosis_path(folder, group))}` as described in",
        "`docs/diagnosis-playbook.md`, then check it with",
        f"`{check_command}`.",
    ]
    return "\n".join(lines) + "\n"


def write_trial_brief(folder: str, group: Group | str, dest: Path) -> Path:
    """Write a brief for testing the agent: its own rulings hidden, output beside `dest`.

    The agent is told to write `diagnosis.json` in `dest`'s folder, never the real one.
    """
    if isinstance(group, str):
        match = [g for g in failure_groups(folder)[0] if g.name == group]
        if not match:
            raise ValueError(f"No failure group called {group} in {folder}")
        group = match[0]
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(brief(folder, group, trial=True, output=dest.parent / "diagnosis.json"))
    return dest


# --- reusing Garron's confirmed labels ----------------------------------------------


def _pairing(group: Group) -> list[tuple[str, str, dict]] | None:
    """Pair every missed size with a wrong number Garron has already ruled on.

    Returns (missed size, wrong number, his casebook entry) for each missed size, or
    None if any size is left without one. Each wrong number serves one size only, so on
    a reply that missed two sizes neither of his labels can land on the other size.
    """
    numbers = list(group.wrong_numbers) or [NO_WRONG_VALUE]
    options = [
        [
            (i, n, entry)
            for i, n in enumerate(numbers)
            if (entry := casebook.confirmed(group.drawing, missed, n)) is not None
        ]
        for missed in group.missed
    ]

    def assign(k: int, used: frozenset[int]) -> list[tuple[str, str, dict]] | None:
        if k == len(group.missed):
            return []
        for i, n, entry in options[k]:
            if i in used and n != NO_WRONG_VALUE:
                continue
            rest = assign(k + 1, used | {i})
            if rest is not None:
                return [(group.missed[k], n, entry), *rest]
        return None

    return assign(0, frozenset())


def _original(entry: dict) -> dict | None:
    """The diagnosis entry Garron ruled on, from its own group's diagnosis.json."""
    path = paths.DIAGNOSES / entry["run_folder"] / entry["group"] / "diagnosis.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    found = [e for e in data.get("diagnoses") or [] if e.get("missed") == entry["missed"]]
    return found[0] if len(found) == 1 else None


def reuse_for(group: Group) -> dict | None:
    """A diagnosis.json built from Garron's earlier labels, or None to diagnose as usual.

    It applies only when every missed size has his confirmed label on the same drawing
    with the same wrong number (SPEC 2.6), and the diagnosis he ruled on is still saved,
    since its evidence is copied across.
    """
    pairs = _pairing(group)
    if pairs is None:
        return None
    diagnoses, sources = [], []
    for missed, number, entry in pairs:
        original = _original(entry)
        if original is None or not original.get("evidence"):
            return None
        source = f"{entry['run_folder']}/{entry['group']}"
        reason = str(entry.get("reason", "")).strip().rstrip(".")
        when = str(entry["saved_at"])[:10]
        prefix = f"Reused: Garron's label from {source} ({when})"
        prefix += f": {reason}. " if reason else ". "
        diagnoses.append(
            {
                "missed": missed,
                "wrong_value": number,
                "label": entry["garron_label"],
                "wrong_value_axis": original.get("wrong_value_axis", "unclear"),
                "note": prefix + str(original.get("note", "")).strip(),
                "evidence": original["evidence"],
            }
        )
        sources.append(source)
    return {"group": group.name, "reused": True, "reused_from": sources, "diagnoses": diagnoses}


TO_DIAGNOSE = "to diagnose"
DIAGNOSED = "diagnosed"
REUSED = "reused from Garron's label"
CONFIRMED = "confirmed by Garron"


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def state(folder: str, group: Group, book: dict | None = None) -> str:
    """Where a group stands: to diagnose, diagnosed, reused, or confirmed by Garron."""
    path = diagnosis_path(folder, group)
    if not path.exists():
        return TO_DIAGNOSE
    book = casebook.load() if book is None else book
    if all((folder, group.name, m) in book for m in group.missed):
        return CONFIRMED
    if (_read(path) or {}).get("reused"):
        return REUSED
    return DIAGNOSED


def write_briefs(folder: str = DEFAULT_FOLDER) -> tuple[list[Group], list[replay.Row]]:
    """Write every group's brief, and his label onto groups Garron has already ruled on.

    An existing diagnosis.json is never overwritten.
    """
    groups, ungraded = failure_groups(folder)
    for group in groups:
        dest = group_folder(folder, group)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "brief.md").write_text(brief(folder, group))
        path = diagnosis_path(folder, group)
        if not path.exists() and (reused := reuse_for(group)) is not None:
            path.write_text(json.dumps(reused, indent=2) + "\n")
    return groups, ungraded


# --- checking a diagnosis -----------------------------------------------------------


@dataclass(frozen=True)
class Citation:
    number: str
    where: str
    view: str
    printed: bool | None  # None: can't check, the drawing is picture-only


@dataclass(frozen=True)
class Check:
    group: Group
    diagnosis: dict | None
    problems: tuple[str, ...]
    citations: tuple[tuple[str, tuple[Citation, ...]], ...]  # per missed dimension

    @property
    def done(self) -> bool:
        return self.diagnosis is not None and not self.problems


def _same_number(a: str, b: str) -> bool:
    try:
        return parse_number(a) == parse_number(b)
    except UnreadableNumber:
        return False


def _printed(pdf: str) -> list[Decimal]:
    return [parse_number(p.number) for p in crops.printed_numbers(pdf)]


def check(folder: str, group: Group, path: Path | None = None) -> Check:
    """Is the diagnosis complete, on Garron's label list, and is its evidence printed?

    The cited-number check confirms each number the note relies on is really on the
    drawing. It never argues with the label. On a picture-only drawing there is no text
    layer to check against, so its citations are marked can't-check, never passed.
    """
    path = path or diagnosis_path(folder, group)
    if not path.exists():
        return Check(group, None, ("Not diagnosed yet",), ())
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return Check(group, None, (f"diagnosis.json is not valid JSON: {exc}",), ())

    problems = []
    entries = data.get("diagnoses") or []
    covered = [e.get("missed") for e in entries]
    for missed in group.missed:
        if covered.count(missed) != 1:
            problems.append(
                f"Needs exactly one diagnosis for {missed}, found {covered.count(missed)}"
            )
    for extra in set(covered) - set(group.missed):
        problems.append(f"Diagnoses {extra!r}, which this reply did not miss")

    picture_only = crops.is_picture_only(group.drawing)
    printed = [] if picture_only else _printed(group.drawing)
    citations = []
    for e in entries:
        where = e.get("missed", "?")
        if e.get("label") not in LABELS:
            problems.append(f"{where}: {e.get('label')!r} is not one of Garron's labels")
        wrong = str(e.get("wrong_value", ""))
        if wrong != NO_WRONG_VALUE and not any(_same_number(wrong, n) for n in group.wrong_numbers):
            problems.append(f"{where}: wrong_value {wrong!r} is not a number the reply gave")
        if e.get("wrong_value_axis") not in WRONG_VALUE_AXES:
            problems.append(
                f"{where}: wrong_value_axis must be one of {', '.join(WRONG_VALUE_AXES)}"
            )
        if not str(e.get("note", "")).strip():
            problems.append(f"{where}: the note is empty")
        cited = []
        for c in e.get("evidence") or []:
            number = str(c.get("number", ""))
            try:
                value = parse_number(number)
            except UnreadableNumber:
                problems.append(f"{where}: cited {number!r} is not a number")
                continue
            found = None if picture_only else value in printed
            if found is False:
                problems.append(f"{where}: cited {number} is not printed on the drawing")
            view = str(c.get("view", ""))
            if view and not (paths.ROOT / view).exists():
                problems.append(f"{where}: view {view} does not exist")
            cited.append(Citation(number, str(c.get("where", "")), view, found))
        if not cited:
            problems.append(f"{where}: no evidence cited")
        citations.append((where, tuple(cited)))
    return Check(group, data, tuple(problems), tuple(citations))


def direction_sentence(drawing: str, missed: str, wrong_value: str, wrong_axis: str) -> str:
    """The missed size and the direction the wrong number runs on the drawing, in words.

    e.g. "Missed: Dia, 76.2 (across the part). The model gave 82.6, which on the drawing
    runs in the X direction (the direction of L, 120.7)."
    """
    dims = scoring.load_answer_key()[drawing].dimensions
    label = _label(missed)
    own = next((d for d in dims if d.label == label), None)
    size = f", {own.printed}" if own else ""
    where = f"the {own.axis} direction" if own and own.axis else "across the part"
    first = f"Missed: {label}{size} ({where})."
    if wrong_value == NO_WRONG_VALUE:
        return f"{first} The model gave no number for it."
    gave = f"The model gave {wrong_value}, which on the drawing"
    if wrong_axis in ("X", "Y", "Z"):
        if own and own.axis == wrong_axis:
            return f"{first} {gave} runs the same way ({wrong_axis} direction)."
        other = next((d for d in dims if d.axis == wrong_axis), None)
        of = f" (the direction of {other.label}, {other.printed})" if other else ""
        return f"{first} {gave} runs in the {wrong_axis} direction{of}."
    if wrong_axis == "none":
        return f"{first} {gave} isn't a length along the part (e.g. a hole size), or isn't printed."
    return f"{first} {gave} runs in a direction the diagnosis couldn't settle."


# --- the list page ------------------------------------------------------------------


def _evidence(citations: tuple[Citation, ...]) -> str:
    items = []
    for c in citations:
        mark = {
            True: '<span class="ok">printed on the drawing ✓</span>',
            False: '<span class="bad">not found on the drawing</span>',
            None: '<span class="soft">can\'t check: picture-only drawing</span>',
        }[c.printed]
        image = (
            f'<a href="{html.escape(Path(c.view).relative_to("runs").as_posix())}">'
            f'<img src="{html.escape(Path(c.view).relative_to("runs").as_posix())}" alt=""></a>'
            if c.view.startswith("runs/")
            else ""
        )
        items.append(
            f"<li><b>{html.escape(c.number)}</b> · {html.escape(c.where)} · {mark}{image}</li>"
        )
    return f"<ul class=evidence>{''.join(items)}</ul>"


def _garron_badges(folder: str, group: Group, entry: dict, reused: bool, book: dict) -> str:
    """Garron's own answer for this missed size, and whether the label was reused."""
    badges = ""
    ruling = book.get((folder, group.name, entry.get("missed", "")))
    if ruling:
        changed = ruling["garron_label"] != ruling["agent_label"]
        badges += (
            f' <span class="badge garron">Garron: {html.escape(ruling["garron_label"])}'
            + (f" · changed from {html.escape(ruling['agent_label'])}" if changed else "")
            + "</span>"
        )
    if reused:
        badges += ' <span class="badge reused">Reused</span>'
    return badges


def _card(result: Check, folder: str = DEFAULT_FOLDER, book: dict | None = None) -> str:
    g = result.group
    book = casebook.load() if book is None else book
    who = ", ".join(f"{r.model} run {r.run_number}" for r in g.replies)
    body = ""
    if result.diagnosis:
        cited = dict(result.citations)
        reused = bool(result.diagnosis.get("reused"))
        for e in result.diagnosis.get("diagnoses") or []:
            missed = e.get("missed", "?")
            body += (
                f"<h3>{html.escape(missed)} · gave {html.escape(str(e.get('wrong_value', '')))}"
                f'</h3><p><span class="badge label">{html.escape(str(e.get("label", "")))}</span>'
                f"{_garron_badges(folder, g, e, reused, book)}"
                "</p><p class=soft>"
                + html.escape(
                    direction_sentence(
                        g.drawing,
                        missed,
                        str(e.get("wrong_value", "")),
                        str(e.get("wrong_value_axis", "")),
                    )
                )
                + "</p>"
                f"<p>{html.escape(str(e.get('note', '')))}</p>"
                f"{_evidence(cited.get(missed, ()))}"
            )
    if result.problems:
        body += "".join(f'<div class="note">{html.escape(p)}</div>' for p in result.problems)
    return f"""<section>
<div class=head><h2>{html.escape(g.drawing[:-4])}</h2>
<span class=soft>{html.escape(who)}</span></div>
<p class=soft>Missed {html.escape(", ".join(g.missed))}
· gave {html.escape(", ".join(g.wrong_numbers))}</p>
{body}
</section>"""


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Failure Diagnoses</title>
<style>
:root {{ --ink:#1d2330; --soft:#5d6778; --line:#e3e6ec; --bg:#f7f8fa; --card:#fff;
  --pass:#1f7a3f; --fail:#b3261e; --flag:#8a5a00; --flag-bg:#fdf1d6; --label:#e7ecfb;
  --garron-bg:#e3f3e8; }}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font:16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
main {{ max-width:960px; margin:0 auto; padding:32px 16px 48px; }}
h1 {{ font-size:28px; margin:0 0 12px; }} h2 {{ font-size:20px; margin:0; }}
h3 {{ font-size:15px; margin:18px 0 4px; }}
.intro {{ max-width:720px; color:var(--soft); }} .intro b {{ color:var(--ink); }}
section {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
  padding:18px 20px; margin:20px 0; }}
.head {{ display:flex; flex-wrap:wrap; gap:4px 16px; align-items:baseline; }}
.soft {{ color:var(--soft); }} .ok {{ color:var(--pass); }}
.bad {{ color:var(--fail); font-weight:600; }}
.badge {{ display:inline-block; padding:4px 10px; border-radius:6px; font-weight:700;
  font-size:14px; }}
.label {{ background:var(--label); }}
.garron {{ background:var(--garron-bg); color:var(--pass); }}
.reused {{ background:var(--flag-bg); color:var(--flag); }}
.evidence {{ padding-left:18px; }} .evidence li {{ margin:8px 0; }}
.evidence img {{ display:block; max-width:100%; max-height:320px; margin-top:6px;
  border:1px solid var(--line); border-radius:6px; }}
.note {{ font-size:14px; margin-top:6px; padding:6px 8px; border-radius:6px;
  background:var(--flag-bg); color:var(--flag); }}
</style></head><body><main>
<h1>Failure diagnoses: {folder}</h1>
<p class="intro"><b>{groups} failure groups</b> covering {replies} failed replies.
Identical failures are grouped, so each group is explained once. Each missed size has
one label from your list, a short note, and the numbers the note relies on. Numbers on
text drawings were checked against the drawing's text layer by code. A green
<b>Garron</b> badge is your own confirmed label; <b>Reused</b> means your earlier label
was copied onto the same wrong number on the same drawing, with no new diagnosis.</p>
{ungraded}
{cards}
</main></body></html>
"""


def write_page(folder: str, results: list[Check], ungraded: list[replay.Row]) -> Path:
    skipped = ""
    if ungraded:
        names = ", ".join(f"{replay.parts(r)[1]} ({replay.parts(r)[0]})" for r in ungraded)
        skipped = f'<p class="intro">Not graded, so not diagnosed: {html.escape(names)}</p>'
    book = casebook.load()
    paths.DIAGNOSES_PAGE.write_text(
        PAGE.format(
            folder=html.escape(folder),
            groups=len(results),
            replies=sum(len(r.group.replies) for r in results),
            ungraded=skipped,
            cards="\n".join(_card(r, folder, book) for r in results),
        )
    )
    return paths.DIAGNOSES_PAGE


# --- commands -----------------------------------------------------------------------


def _folder(args: list[str]) -> str:
    names = [a for a in args if not a.startswith("--")]
    return names[0] if names else DEFAULT_FOLDER


def cli_groups(args: list[str]) -> None:
    """`vlm-eval failure-groups [folder]`: group failures and write each group's brief."""
    folder = _folder(args)
    groups, ungraded = write_briefs(folder)
    book = casebook.load()
    states = {g.name: state(folder, g, book) for g in groups}
    replies = sum(len(g.replies) for g in groups)
    counted = list(states.values())
    print(
        f"{folder}: {replies} failed replies in {len(groups)} groups, "
        f"{counted.count(TO_DIAGNOSE)} not diagnosed yet, "
        f"{counted.count(REUSED)} reused from Garron's labels, "
        f"{counted.count(CONFIRMED)} confirmed by Garron."
    )
    for g in groups:
        print(f"  {g.name:<32} {', '.join(g.models):<48} {states[g.name]}")
        if states[g.name] == TO_DIAGNOSE:
            print(f"      brief: {_shown(group_folder(folder, g) / 'brief.md')}")
    for r in ungraded:
        model, drawing, _ = replay.parts(r)
        print(f"  not graded, not diagnosed: {drawing} ({model})")


def cli_check(args: list[str]) -> None:
    """`vlm-eval check-diagnoses [folder] [group] [--file path]`: check, write the page.

    `--file` checks a diagnosis saved somewhere else (the agent's own test runs), so
    trials never mix with the real diagnoses.
    """
    other_file = None
    if "--file" in args:
        i = args.index("--file")
        other_file = Path(args[i + 1]).resolve()
        args = args[:i] + args[i + 2 :]
    names = [a for a in args if not a.startswith("--")]
    folder = names[0] if names else DEFAULT_FOLDER
    groups, ungraded = failure_groups(folder)
    if len(names) > 1:  # one group, as the agent checks its own work
        match = [g for g in groups if g.name == names[1]]
        if not match:
            raise SystemExit(f"No failure group called {names[1]} in {folder}")
        result = check(folder, match[0], other_file)
        print("All checks passed." if result.done else "\n".join(result.problems))
        return
    results = [check(folder, g) for g in groups]
    bad = [r for r in results if not r.done]
    if bad:
        print(f"{len(bad)} of {len(results)} groups need attention:")
        for r in bad:
            for p in r.problems:
                print(f"  {r.group.name}: {p}")
    else:
        print(f"All {len(results)} diagnoses passed their checks.")
    page = write_page(folder, results, ungraded)
    print(f"Wrote {page.relative_to(paths.ROOT)}")
    if "--no-open" not in args:
        webbrowser.open(page.as_uri())
