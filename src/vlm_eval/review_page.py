"""Builds a local page of zoomed dimension crops for Garron to read and confirm.

Each item shows one dimension, cropped tight on its callout, with the recorded
millimetre value and the inch value the software believes is printed beside it.
Garron reads down the page and says the inch values aloud; nothing is typed here.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass

from vlm_eval import crops, paths

PAGE = paths.ROOT / "runs" / "review.html"

KINDS = {
    "spot-check": "checking the software",
    "confirm": "needs your answer",
    "chain": "chain - two pieces",
}
LOCATIONS = paths.DATA / "callout-locations.json"


@dataclass
class Item:
    number: int
    file: str
    label: str
    axis: str
    recorded_mm: str
    inch_shown: str
    source: str  # text layer | read from sheet | not located
    kind: str
    crops: list[str]
    places: list[str]
    note: str = ""


def _partner_rows() -> list[dict]:
    with paths.INCH_PARTNERS_CSV.open(newline="") as fh:
        return list(csv.DictReader(fh))


def _locations() -> dict:
    return json.loads(LOCATIONS.read_text()) if LOCATIONS.exists() else {}


def build_items() -> list[Item]:
    located = _locations()
    items: list[Item] = []
    n = 0
    for row in sorted(_partner_rows(), key=lambda r: (r["file"], r["label"])):
        if row["is_chain"] == "true":
            kind = "chain"
        elif row["status"] == "needs_confirmation":
            kind = "confirm"
        elif row["spot_check"] == "true":
            kind = "spot-check"
        else:
            continue
        n += 1

        crop_name = f"{row['file'][:-4]}-{row['label']}"
        crop_path, places, source, inch, note = None, [], "not located", "", ""

        if row["status"] == "auto":
            # Text layer: the callout's position is known exactly.
            mm_values = (
                [float(x) for x in row["mm_segments"].split("|")]
                if row["mm_segments"]
                else [float(row["recorded_mm"])]
            )
            cut = []
            for i, mm in enumerate(mm_values):
                cut += crops.crops_around_value(row["file"], mm, f"{crop_name}-{i}")
            if cut:
                crop_path = [c for c, _ in cut]
                places = [w for _, w in cut]
                source = "text layer"
            inch = (
                " + ".join(row["inch_segments"].split("|"))
                if row["inch_segments"]
                else row["inch_partner"]
            )
        else:
            found = located.get(row["file"], {}).get(row["label"])
            if found and found.get("x") is not None:
                box = (found["x"] - 1, found["y"] - 1, found["x"] + 1, found["y"] + 1)
                crop_path = [crops.crop_box(row["file"], box, crop_name, min_width=1100)]
                places = [""]
                source = "read from sheet"
                inch = found.get("inch_seen") or ""
                note = found.get("note") or ""
            else:
                note = (found or {}).get("note", "") or "callout not located yet"

        items.append(
            Item(
                number=n,
                file=row["file"],
                label=row["label"],
                axis=row["axis"],
                recorded_mm=row["recorded_mm"],
                inch_shown=inch,
                source=source,
                kind=kind,
                crops=[str(c.relative_to(paths.ROOT / "runs")) for c in (crop_path or [])],
                places=places,
                note=note,
            )
        )
    return items


_CSS = """
:root{color-scheme:light;--line:#d8d4cd;--ink:#1a1a1a;--dim:#6b6660;--accent:#8a5a00;
      --ok:#2d6a3f;--no:#9c3428}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;font:15px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:#f2efea;color:var(--ink);display:flex;flex-direction:column}
header{background:#fff;border-bottom:1px solid var(--line);padding:10px 20px;
       display:flex;gap:14px;align-items:center;flex-wrap:wrap}
.pos{font-weight:700;white-space:nowrap}
.file{font-family:ui-monospace,Menlo,monospace;font-weight:600}
.tag{font-size:11px;text-transform:uppercase;letter-spacing:.07em;padding:3px 9px;
     border-radius:99px;background:#efece7;color:var(--dim);white-space:nowrap}
.tag.chain{background:#fdf0d5;color:var(--accent)}
.tag.confirm{background:#e6f0e9;color:var(--ok)}
.done{margin-left:auto;font-size:13px;color:var(--dim);white-space:nowrap}
.bar{height:4px;background:#e2ded7;width:100%;border-radius:99px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--accent);transition:width .15s}
.ask{background:#fff;border-bottom:1px solid var(--line);padding:14px 20px;font-size:17px}
.ask b{font-weight:700}
.inch{color:var(--accent);font-weight:700;font-size:20px}
.saved{display:inline-block;margin-left:10px;font-size:13px;font-weight:700;padding:2px 10px;
       border-radius:99px}
.saved.yes{background:#e6f0e9;color:var(--ok)}
.saved.no{background:#fbeae8;color:var(--no)}
.saved.unsure{background:#efece7;color:var(--dim)}
main{flex:1;overflow:auto;padding:16px 20px;display:flex;flex-direction:column;gap:12px;
     align-items:center}
main img{max-width:100%;background:#fff;border:1px solid var(--line);border-radius:6px}
.pieces{font-size:13px;color:var(--dim)}
.miss{color:var(--dim);font-style:italic;padding:40px;text-align:center}
footer{background:#fff;border-top:1px solid var(--line);padding:12px 20px;display:flex;
       gap:10px;align-items:center;flex-wrap:wrap}
button{font:inherit;font-weight:600;padding:10px 20px;border:1px solid var(--ink);
       border-radius:6px;background:#fff;cursor:pointer}
button:hover{filter:brightness(.97)}
button.yes{background:var(--ok);color:#fff;border-color:var(--ok)}
button.no{background:#fff;color:var(--no);border-color:var(--no)}
button.ghost{border-color:var(--line);color:var(--dim)}
button.warn{background:#fff;color:var(--accent);border-color:var(--accent)}
.saved.wrong_dimension{background:#fdf0d5;color:var(--accent)}
#notetext{width:230px}
#notewrap{display:flex;gap:8px;align-items:center}
.nav{display:flex;gap:6px;margin-left:auto}
.nav button{padding:10px 14px}
input{font:inherit;padding:10px;border:1px solid var(--line);border-radius:6px}
#fix{width:130px}
#fixwrap{display:flex;gap:8px;align-items:center}
.hint{width:100%;color:var(--dim);font-size:13px}
kbd{font:inherit;font-size:12px;background:#efece7;border-radius:4px;padding:1px 6px}
"""


def render_page(items: list[Item]) -> str:
    """One item on screen at a time, answered with buttons. Numbers never change."""
    payload = [
        {
            "n": i.number,
            "file": i.file,
            "label": i.label,
            "axis": i.axis,
            "mm": i.recorded_mm,
            "inch": i.inch_shown,
            "kind": i.kind,
            "kindText": KINDS[i.kind],
            "crops": i.crops,
            "places": i.places,
            "note": i.note,
        }
        for i in sorted(items, key=lambda x: (not x.crops, x.number))
    ]
    ready = sum(1 for i in items if i.crops)

    return f"""<!doctype html><meta charset="utf-8">
<title>Inch values to confirm</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{_CSS}</style>
<header>
  <span class="pos" id="pos"></span>
  <span class="file" id="file"></span>
  <span class="tag" id="kind"></span>
  <span class="tag" id="dim"></span>
  <span class="done" id="done"></span>
  <span class="bar"><i id="bar"></i></span>
</header>
<div class="ask" id="ask"></div>
<main id="main"></main>
<footer>
  <button class="yes" id="yes">Yes &mdash; that's right</button>
  <button class="no" id="no">No &mdash; it's different</button>
  <span id="notewrap" hidden>
    <input id="notetext" placeholder="where is it? e.g. bottom section view">
    <button class="main" id="savenote">Save</button>
  </span>
  <span id="fixwrap" hidden>
    <input id="fix" placeholder="e.g. 1.375" inputmode="decimal">
    <button class="main" id="savefix">Save</button>
  </span>
  <button class="warn" id="wrongdim"
          title="Use when the right callout is not shown at all">Wrong dimension</button>
  <button class="ghost" id="unsure">Not sure</button>
  <button class="ghost" id="sheet">Whole sheet</button>
  <span class="nav">
    <button id="prev">&larr;</button>
    <button id="next">&rarr;</button>
  </span>
  <span class="hint"><kbd>Y</kbd> yes &middot; <kbd>N</kbd> wrong number &middot;
    <kbd>W</kbd> wrong dimension &middot; <kbd>S</kbd> not sure &middot;
    <kbd>F</kbd> whole sheet &middot; <kbd>&larr;</kbd><kbd>&rarr;</kbd> move
    &middot; answers save as you go &middot; {ready} of {len(items)} have a crop</span>
</footer>
<script>
const ITEMS = {json.dumps(payload)};
let answers = {{}};
let at = 0;

async function load() {{
  try {{ answers = await (await fetch("/api/state")).json(); }} catch (e) {{ answers = {{}}; }}
  const firstUnanswered = ITEMS.findIndex(x => x.crops.length && !answers[x.n]);
  at = firstUnanswered >= 0 ? firstUnanswered : 0;
  show();
}}

function show() {{
  const it = ITEMS[at], a = answers[it.n];
  document.getElementById("pos").textContent = `Item ${{it.n}}`;
  document.getElementById("file").textContent = it.file;
  const kind = document.getElementById("kind");
  kind.textContent = it.kindText; kind.className = "tag " + it.kind;
  document.getElementById("dim").textContent = it.label + (it.axis ? " / " + it.axis : "");
  const n = Object.keys(answers).length;
  document.getElementById("done").textContent = `${{n}} of ${{ITEMS.length}} answered`;
  document.getElementById("bar").style.width = (n / ITEMS.length * 100) + "%";

  let q;
  if (!it.inch) q = "What inch value does the sheet print beside it?";
  else if (it.inch.includes(" + "))
    q = `Do the two pieces print <span class="inch">[${{it.inch}}]</span>?`;
  else q = `Does the sheet print <span class="inch">[${{it.inch}}]</span> beside it?`;
  let badge = "";
  if (a) {{
    const t = a.verdict === "yes" ? "confirmed " + a.confirmed_inch
            : a.verdict === "no" ? "corrected to " + a.confirmed_inch
            : a.verdict === "wrong_dimension" ? "wrong callout - flagged" : "not sure";
    badge = `<span class="saved ${{a.verdict}}">${{t}}</span>`;
  }}
  document.getElementById("ask").innerHTML =
    `You recorded <b>${{it.mm}} mm</b>. ${{q}}${{badge}}`;

  const main = document.getElementById("main");
  main.innerHTML = !it.crops.length
    ? `<div class="miss">No crop yet &mdash; ${{it.note || "being located"}}</div>`
    : (it.crops.length > 1
        ? `<div class="pieces">${{it.mm.includes("+")
            ? "Two separate callouts, one per piece"
            : "This number is printed in " + it.crops.length
              + " places - the envelope dimension is one of them"}}</div>` : '')
      + it.crops.map((c, i) => (it.places[i]
          ? `<div class="pieces">${{it.places[i]}} of the sheet</div>` : "")
          + `<img src="/${{c}}" alt="crop">`).join("");
  main.scrollTop = 0;
  main.dataset.full = "";
  document.getElementById("fixwrap").hidden = true;
  document.getElementById("notewrap").hidden = true;
  document.getElementById("yes").disabled = !it.inch;
}}

async function answer(verdict, inch, note) {{
  const it = ITEMS[at];
  const body = {{ n: it.n, file: it.file, label: it.label, axis: it.axis,
                 recorded_mm: it.mm, verdict, confirmed_inch: inch || "",
                 note: note || "" }};
  answers[it.n] = body;
  try {{ await fetch("/api/answer", {{ method: "POST", body: JSON.stringify(body) }}); }}
  catch (e) {{ alert("Could not save - is the server still running?"); }}
  const nxt = ITEMS.findIndex((x, i) => i > at && x.crops.length && !answers[x.n]);
  at = nxt >= 0 ? nxt : Math.min(ITEMS.length - 1, at + 1);
  show();
}}

document.getElementById("yes").onclick = () => answer("yes", ITEMS[at].inch);
document.getElementById("unsure").onclick = () => answer("unsure", "");
document.getElementById("no").onclick = () => {{
  const w = document.getElementById("fixwrap");
  w.hidden = false; document.getElementById("fix").focus();
}};
document.getElementById("savefix").onclick = () => {{
  const v = document.getElementById("fix").value.trim();
  if (v) {{ document.getElementById("fix").value = ""; answer("no", v); }}
}};
document.getElementById("fix").onkeydown = (e) => {{
  if (e.key === "Enter") document.getElementById("savefix").click();
}};
const nextBtn = document.getElementById("next");
nextBtn.onclick = () => {{ at = Math.min(ITEMS.length - 1, at + 1); show(); }};
document.getElementById("prev").onclick = () => {{ at = Math.max(0, at - 1); show(); }};
addEventListener("keydown", (e) => {{
  if (e.target.tagName === "INPUT") return;
  const k = e.key.toLowerCase();
  if (k === "y") document.getElementById("yes").click();
  if (k === "n") document.getElementById("no").click();
  if (k === "s") document.getElementById("unsure").click();
  if (k === "w") document.getElementById("wrongdim").click();
  if (k === "f") document.getElementById("sheet").click();
  if (e.key === "ArrowRight") {{ e.preventDefault(); document.getElementById("next").click(); }}
  if (e.key === "ArrowLeft") {{ e.preventDefault(); document.getElementById("prev").click(); }}
}});
load();
</script>
"""


def build() -> str:
    return render_page(build_items())
