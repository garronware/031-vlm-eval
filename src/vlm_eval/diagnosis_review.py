"""The diagnosis review page: Garron accepts or changes each label (SPEC 2.6, Chunk 9).

One card per failure group shows his ground-truth sizes beside what each model gave,
the drawing, the agent's note and evidence, and the reply. For each missed size he
accepts the agent's label or changes it with a one-line reason. Every answer goes to
the casebook (data/casebook.jsonl) the moment he clicks, so he can stop and come back.

The browser only says which missed size and what Garron chose. Everything else in the
casebook entry (drawing, wrong number, agent's label, reused) is read from the
diagnosis on disk, so the page can't put a wrong fact in the book.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path

from vlm_eval import casebook, crops, diagnosis, grading_examples, paths, replay, scoring
from vlm_eval.answers import UnreadableNumber, parse_number
from vlm_eval.review_server import BaseHandler, serve

SUGGESTIONS_FILE = "garron-chunk-8-read.json"  # Garron's earlier read, if there was one
SECOND_READ_FOLDER = "main-stock-shape"  # he already read these labels on 2026-09-24


@dataclass(frozen=True)
class Item:
    """One missed size to review: the agent's diagnosis for it."""

    group: str
    drawing: str
    missed: str
    wrong_value: str
    agent_label: str
    axis: str  # the part axis the wrong number runs along on the drawing
    note: str
    reused: bool

    @property
    def key(self) -> str:
        return f"{self.group}|{self.missed}"


def _checks(folder: str) -> list[diagnosis.Check]:
    groups, _ = diagnosis.failure_groups(folder)
    return [diagnosis.check(folder, g) for g in groups]


def _items(result: diagnosis.Check) -> list[Item]:
    data = result.diagnosis or {}
    entries = {e.get("missed"): e for e in data.get("diagnoses") or []}
    items = []
    for missed in result.group.missed:
        e = entries.get(missed)
        if not e or e.get("label") not in diagnosis.LABELS:
            continue  # not diagnosed, or not on the label list: nothing to rule on
        items.append(
            Item(
                group=result.group.name,
                drawing=result.group.drawing,
                missed=missed,
                wrong_value=str(e.get("wrong_value", "")),
                agent_label=e["label"],
                axis=str(e.get("wrong_value_axis", "")),
                note=str(e.get("note", "")),
                reused=bool(data.get("reused") or e.get("reused")),
            )
        )
    return items


def items(folder: str) -> list[Item]:
    """Every missed size in this run that has a diagnosis to review."""
    return [i for result in _checks(folder) for i in _items(result)]


def suggestions(folder: str) -> tuple[str, dict[str, dict]]:
    """Garron's earlier read for this run: (its date, "<group>|<missed>" -> reason/note)."""
    path = paths.DIAGNOSES / folder / SUGGESTIONS_FILE
    if not path.exists():
        return "", {}
    data = json.loads(path.read_text())
    date = re.search(r"\d{4}-\d{2}-\d{2}", data.get("source", ""))
    return (date.group(0) if date else ""), data.get("suggestions") or {}


def saved_answers(folder: str) -> dict[str, dict]:
    """ "<group>|<missed>" -> Garron's latest casebook answer, for this run only."""
    return {
        f"{group}|{missed}": entry
        for (run_folder, group, missed), entry in casebook.load().items()
        if run_folder == folder
    }


def state(folder: str) -> dict:
    """What the page shows live: saved answers, how many are done, and the agreement."""
    keys = {i.key for i in items(folder)}
    answers = {k: v for k, v in saved_answers(folder).items() if k in keys}
    return {
        "answers": answers,
        "reviewed": len(answers),
        "total": len(keys),
        "agreement": casebook.agreement(folder).text(),
    }


def answer(folder: str, body: dict) -> dict:
    """Save one answer from the page. Raises ValueError, in plain words, if it can't."""
    match = [
        i for i in items(folder) if i.group == body.get("group") and i.missed == body.get("missed")
    ]
    if not match:
        raise ValueError("That missed size isn't on this page any more. Reload the page.")
    item = match[0]
    verdict = body.get("verdict")
    reason = str(body.get("reason", "")).strip()
    if verdict == casebook.ACCEPT:
        label = item.agent_label
    elif verdict == casebook.CHANGE:
        label = body.get("garron_label", "")
        if label not in diagnosis.LABELS:
            raise ValueError("Pick one of your seven labels from the list.")
        if label == item.agent_label:
            raise ValueError(
                "That is the agent's own label. Press Accept to keep it, or pick a different label."
            )
        if not reason:
            raise ValueError("Write a one-line reason for the change, then press Save change.")
    else:
        raise ValueError("Press Accept or Save change.")
    return casebook.save(
        {
            "run_folder": folder,
            "group": item.group,
            "drawing": item.drawing,
            "missed": item.missed,
            "wrong_value": item.wrong_value,
            "agent_label": item.agent_label,
            "garron_label": label,
            "verdict": verdict,
            "reason": reason,
            "note": str(body.get("note", "")).strip(),
            "reused": item.reused,
        }
    )


# --- the page -----------------------------------------------------------------------


def _esc(text) -> str:
    return html.escape(str(text))


def _same_number(a: str, b: str) -> bool:
    try:
        return parse_number(a) == parse_number(b)
    except UnreadableNumber:
        return a == b


def _described(label: str, axis: str) -> str:
    return f"{label} ({axis})" if axis else label


def _runs_url(path: Path) -> str:
    """A picture's address on the page: its path inside runs/."""
    return path.resolve().relative_to(paths.RUNS.resolve()).as_posix()


def _your_size(key: scoring.DrawingKey, dim: scoring.DimensionKey, inch: dict) -> str:
    """One ground-truth size as grading_examples.your_numbers shows it."""
    text = f"<b>{_esc(dim.label)}</b> {_esc(dim.printed)}"
    if key.print_type == "dual" and (key.file, dim.label) in inch:
        text += f' <span class="soft">[{_esc(inch[(key.file, dim.label)])} in]</span>'
    return text


def _gave(reply: diagnosis.Reply, wrong_value: str | None) -> str:
    """The number this reply gave for a missed size, as the reply wrote it."""
    if wrong_value is None:  # no diagnosis to pair the number with the size
        given = ", ".join(f"{u.number} {u.unit}" for u in reply.wrong_values)
        return f"missed — gave one of: {given}" if given else "missed"
    if wrong_value == diagnosis.NO_WRONG_VALUE:
        return "missed — gave no number for it"
    for u in reply.wrong_values:
        if _same_number(u.number, wrong_value):
            return f"missed — gave {u.number} {u.unit}"
    return f"missed — gave {wrong_value}"


def _cell(verdict: scoring.Verdict | None, dim, reply, wrong: dict[str, str]) -> str:
    if verdict is None:
        return '<td class="soft">no score</td>'
    for m in verdict.matches:
        if m.label == dim.label and _described(m.label, m.axis) == dim.described:
            return f'<td class="ok">✓ {_esc(m.answer_number)} {_esc(m.answer_unit)}</td>'
    for m in verdict.matches:  # a round part answered as its box names Dia twice
        if m.label == dim.label:
            return f'<td class="ok">✓ {_esc(m.answer_number)} {_esc(m.answer_unit)}</td>'
    return f'<td class="bad">✗ {_esc(_gave(reply, wrong.get(dim.described)))}</td>'


def _sizes_table(result: diagnosis.Check, verdicts: dict, key, inch) -> str:
    g = result.group
    wrong = {
        e.get("missed"): str(e.get("wrong_value", ""))
        for e in (result.diagnosis or {}).get("diagnoses") or []
    }
    head = "".join(f"<th>{_esc(r.model)} run {_esc(r.run_number)}</th>" for r in g.replies)
    rows = []
    for dim in key.dimensions:
        cells = "".join(_cell(verdicts.get(r.call_file), dim, r, wrong) for r in g.replies)
        rows.append(f"<tr><td>{_your_size(key, dim, inch)}</td>{cells}</tr>")
    unit = "mm [in]" if key.print_type == "dual" else "in"
    return (
        f'<div class="scroll"><table><thead><tr><th>Your size ({unit})</th>{head}</tr>'
        f"</thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _controls(item: Item, saved: dict | None, suggestion: dict | None, date: str) -> str:
    reason = note = hint = status = ""
    chosen = item.agent_label
    if saved:
        reason, note, chosen = saved.get("reason", ""), saved.get("note", ""), saved["garron_label"]
        status = (
            f"Saved ✓ (Accepted: {saved['garron_label']})"
            if saved["verdict"] == casebook.ACCEPT
            else f"Saved ✓ (Changed to {saved['garron_label']})"
        )
    elif suggestion:
        reason, note = suggestion.get("reason", ""), suggestion.get("note", "")
        when = f"your {date} read" if date else "your earlier read"
        hint = f'<p class="hint">From {_esc(when)} — keep or edit. Not saved until you click.</p>'
    options = "".join(
        f"<option{' selected' if label == chosen else ''}>{_esc(label)}</option>"
        for label in diagnosis.LABELS
    )
    return f"""<div class="controls">
{hint}
<label>Reason (one line; needed if you change the label)
<input class="reason" type="text" value="{_esc(reason)}"></label>
<label>Note (optional)
<textarea class="note-box" rows="2">{_esc(note)}</textarea></label>
<div class="actions">
<button type="button" class="accept" data-action="accept">Accept: {_esc(item.agent_label)}</button>
<span class="or">or change it to</span>
<select class="label-choice" aria-label="Change label to">{options}</select>
<button type="button" data-action="change">Save change</button>
</div>
<p class="status{" saved" if saved else ""}" role="status">{_esc(status)}</p>
</div>"""


def _review_block(item: Item, cited: dict, saved: dict, suggested: dict, date: str) -> str:
    return f"""<div class="review" data-group="{_esc(item.group)}"
 data-missed="{_esc(item.missed)}" data-agent="{_esc(item.agent_label)}">
<h3>{_esc(item.missed)} · gave {_esc(item.wrong_value)}</h3>
<p><span class="badge label">{_esc(item.agent_label)}</span></p>
<p class="soft">{
        _esc(diagnosis.direction_sentence(item.drawing, item.missed, item.wrong_value, item.axis))
    }</p>
<p>{_esc(item.note)}</p>
{diagnosis._evidence(cited.get(item.missed, ()))}
{_controls(item, saved.get(item.key), suggested.get(item.key), date)}
</div>"""


def _card(result: diagnosis.Check, verdicts, keys, inch, saved, suggested, date):
    g = result.group
    who = ", ".join(f"{r.model} run {r.run_number}" for r in g.replies)
    card_items = _items(result)
    reused = (
        '<span class="badge reused">Reused label: copied from your earlier answer '
        "on the same failure</span>"
        if any(i.reused for i in card_items)
        else ""
    )
    sheet = _runs_url(crops.sheet_view(g.drawing))
    replies = "".join(
        f"<details><summary>Reply from {_esc(r.model)} run {_esc(r.run_number)} "
        f'<span class="soft">({_esc(r.model_version)})</span></summary>'
        f"<pre>{_esc(r.reply_text.strip())}</pre></details>"
        for r in g.replies
    )
    problems = "".join(f'<div class="flag">{_esc(p)}</div>' for p in result.problems)
    cited = dict(result.citations)
    blocks = "".join(_review_block(i, cited, saved, suggested, date) for i in card_items)
    if not card_items:
        blocks = '<p class="flag">No diagnosis to review for this group yet.</p>'
    return f"""<section>
<div class="head"><h2>{_esc(g.drawing.removesuffix(".pdf"))}</h2>
<span class="soft">{_esc(who)}</span>{reused}</div>
{_sizes_table(result, verdicts, keys[g.drawing], inch)}
<a class="sheet" href="{_esc(sheet)}" target="_blank" rel="noopener">
<img src="{_esc(sheet)}" alt="The whole drawing"></a>
<p class="soft small">The whole sheet, with a grid. Click it to open full size.</p>
{replies}
{problems}
{blocks}
</section>"""


_CSS = """
:root { --ink:#1d2330; --soft:#5d6778; --line:#e3e6ec; --bg:#f7f8fa; --card:#fff;
  --pass:#1f7a3f; --pass-bg:#e3f4e8; --fail:#b3261e; --flag:#8a5a00; --flag-bg:#fdf1d6;
  --label:#e7ecfb; }
* { box-sizing:border-box }
body { margin:0; background:var(--bg); color:var(--ink);
  font:16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
main { max-width:960px; margin:0 auto; padding:32px 16px 48px; }
h1 { font-size:28px; margin:0 0 12px; } h2 { font-size:20px; margin:0; }
h3 { font-size:15px; margin:18px 0 4px; }
.intro { max-width:720px; color:var(--soft); } .intro b { color:var(--ink); }
.live { background:var(--card); border:1px solid var(--line); border-radius:10px;
  padding:12px 16px; position:sticky; top:0; z-index:1; }
.live p { margin:2px 0; }
section { background:var(--card); border:1px solid var(--line); border-radius:10px;
  padding:18px 20px; margin:20px 0; }
.head { display:flex; flex-wrap:wrap; gap:4px 16px; align-items:baseline; margin-bottom:10px; }
.soft { color:var(--soft); } .small { font-size:13px; margin-top:4px; }
.ok { color:var(--pass); } .bad { color:var(--fail); font-weight:600; }
.badge { display:inline-block; padding:4px 10px; border-radius:6px; font-weight:700;
  font-size:14px; }
.label { background:var(--label); } .reused { background:var(--flag-bg); color:var(--flag); }
.scroll { overflow-x:auto; }
table { border-collapse:collapse; width:100%; margin:4px 0 14px; }
th { text-align:left; font-size:13px; color:var(--soft); background:#fbfbfc; }
th, td { padding:8px 10px; border:1px solid var(--line); vertical-align:top; }
.sheet img { display:block; max-width:100%; border:1px solid var(--line); border-radius:6px; }
details { margin:8px 0; } summary { cursor:pointer; font-weight:600; }
pre { white-space:pre-wrap; word-break:break-word; background:#fbfbfc;
  border:1px solid var(--line); border-radius:6px; padding:10px; font-size:13px; }
.evidence { padding-left:18px; } .evidence li { margin:8px 0; }
.evidence img { display:block; max-width:100%; max-height:320px; margin-top:6px;
  border:1px solid var(--line); border-radius:6px; }
.flag, .hint { font-size:14px; margin:6px 0; padding:6px 8px; border-radius:6px;
  background:var(--flag-bg); color:var(--flag); }
.review { border-top:1px solid var(--line); margin-top:16px; }
.controls { background:#fbfbfc; border:1px solid var(--line); border-radius:8px;
  padding:12px; margin-top:10px; }
.controls label { display:block; font-size:14px; color:var(--soft); margin-bottom:8px; }
input, textarea, select, button { font:inherit; }
input, textarea { display:block; width:100%; margin-top:2px; padding:8px;
  border:1px solid var(--line); border-radius:6px; color:var(--ink); }
.actions { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
select { padding:8px; border:1px solid var(--line); border-radius:6px; max-width:100%; }
button { font-weight:600; padding:8px 14px; border:1px solid var(--ink); border-radius:6px;
  background:#fff; cursor:pointer; }
button.accept { background:var(--pass); border-color:var(--pass); color:#fff; }
.or { color:var(--soft); font-size:14px; }
.status { margin:8px 0 0; font-weight:600; min-height:1.5em; }
.status.saved { color:var(--pass); } .status.error { color:var(--fail); }
"""

_SCRIPT = """
function statusText(a) {
  return a.verdict === "accept" ? `Saved ✓ (Accepted: ${a.garron_label})`
                                : `Saved ✓ (Changed to ${a.garron_label})`;
}
function showLive(s) {
  document.getElementById("count").textContent =
    `${s.reviewed} of ${s.total} labels reviewed.`;
  document.getElementById("agreement").textContent = s.agreement;
}
function say(box, text, kind) {
  const p = box.querySelector(".status");
  p.textContent = text;
  p.className = "status " + (kind || "");
}
async function load() {
  try {
    const s = await (await fetch("/api/state")).json();
    showLive(s);
    document.querySelectorAll(".review").forEach(box => {
      const a = s.answers[box.dataset.group + "|" + box.dataset.missed];
      if (a) say(box, statusText(a), "saved");
    });
  } catch (e) { /* the page still works; counts update on the next save */ }
}
document.addEventListener("click", async (e) => {
  const button = e.target.closest("button[data-action]");
  if (!button) return;
  const box = button.closest(".review");
  const reason = box.querySelector(".reason").value.trim();
  const note = box.querySelector(".note-box").value.trim();
  let verdict = "accept", label = box.dataset.agent;
  if (button.dataset.action === "change") {
    verdict = "change";
    label = box.querySelector(".label-choice").value;
    if (label === box.dataset.agent)
      return say(box, "That is the agent's own label. Press Accept to keep it, " +
                      "or pick a different label.", "error");
    if (!reason)
      return say(box, "Write a one-line reason for the change, then press Save change.",
                 "error");
  }
  say(box, "Saving…");
  try {
    const r = await fetch("/api/answer", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({group: box.dataset.group, missed: box.dataset.missed,
                            verdict, garron_label: label, reason, note})});
    const d = await r.json();
    if (!r.ok || !d.ok) return say(box, "Not saved: " + (d.error || "unknown problem"), "error");
    say(box, statusText(d.saved), "saved");
    const hint = box.querySelector(".hint");
    if (hint) hint.remove();
    showLive(d);
  } catch (err) {
    say(box, "Not saved: the page can't reach the review program. " +
             "Is it still running in the terminal?", "error");
  }
});
load();
"""


def build(folder: str = diagnosis.DEFAULT_FOLDER) -> str:
    """The whole review page for one run, with any saved answers already filled in."""
    checks = _checks(folder)
    verdicts = {row.call_file: row.verdict for row in replay.replay(folder)}
    keys = scoring.load_answer_key()
    inch = grading_examples.inch_values()
    saved = saved_answers(folder)
    date, suggested = suggestions(folder)
    s = state(folder)
    cards = "\n".join(_card(c, verdicts, keys, inch, saved, suggested, date) for c in checks)
    second_read = (
        "<p>This is a second read of labels you already saw on 2026-09-24, not a blind test.</p>"
        if folder == SECOND_READ_FOLDER
        else ""
    )
    not_diagnosed = [c.group.name for c in checks if not _items(c)]
    waiting = (
        f'<p class="flag">Not diagnosed yet, so not on this page to review: '
        f"{_esc(', '.join(not_diagnosed))}. Run /diagnose-failures first.</p>"
        if not_diagnosed
        else ""
    )
    if not checks:
        cards = f"<p>No failures found in {_esc(folder)}, so there is nothing to review.</p>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Review Diagnoses</title>
<style>{_CSS}</style></head><body><main>
<h1>Review diagnoses: {_esc(folder)}</h1>
<p class="intro">Each card is one failure: your sizes beside what the model gave, the
drawing, and the agent's note. For <b>each missed size</b>, press <b>Accept</b> if the
agent's label is right, or pick a different label, write a one-line reason, and press
<b>Save change</b>. Answers save as you click, so you can stop and come back; saving
again replaces your earlier answer. Your labels, reasons and notes are saved in
data/casebook.jsonl, which will be published with the results.</p>
<div class="live">
<p><b id="count">{s["reviewed"]} of {s["total"]} labels reviewed.</b></p>
<p id="agreement">{_esc(s["agreement"])}</p>
{second_read}
</div>
{waiting}
{cards}
</main>
<script>{_SCRIPT}</script>
</body></html>
"""


# --- serving it ---------------------------------------------------------------------


def handler_for(folder: str) -> type[BaseHandler]:
    """A request handler serving the review page for one run."""

    class DiagnosisHandler(BaseHandler):
        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                self._send(200, build(folder).encode(), "text/html; charset=utf-8")
            elif self.path == "/api/state":
                self._send_json(200, state(folder))
            else:
                self._send_run_picture()

        def do_POST(self) -> None:
            if self.path != "/api/answer":
                self._send(404, b"not found", "text/plain")
                return
            try:
                saved = answer(folder, self._read_json())
            except ValueError as exc:
                self._send_json(400, {"ok": False, "error": str(exc)})
                return
            self._send_json(200, {"ok": True, "saved": saved, **state(folder)})

    return DiagnosisHandler


def stopped_message(folder: str) -> str:
    where = casebook.CASEBOOK
    if where.is_relative_to(paths.ROOT):
        where = where.relative_to(paths.ROOT)
    return f"Your answers are saved in {where}.\n{casebook.agreement(folder).text()}"


def cli(args: list[str]) -> None:
    """`vlm-eval review-diagnoses [folder] [--no-open]`: serve the review page."""
    names = [a for a in args if not a.startswith("--")]
    folder = names[0] if names else diagnosis.DEFAULT_FOLDER
    if not (paths.DIAGNOSES / folder).is_dir():
        raise SystemExit(f"No diagnoses for {folder} yet. Run /diagnose-failures first.")
    serve(
        handler_for(folder),
        open_browser="--no-open" not in args,
        stopped=lambda: stopped_message(folder),
    )
