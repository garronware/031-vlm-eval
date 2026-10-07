"""Builds the work list for the inch-value review page, one screen per drawing.

Each screen shows one drawing and every value on it that needs an answer, so a
drawing is opened once rather than once per dimension.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass

from vlm_eval import paths

CONFIRMATIONS_CSV = paths.DATA / "inch-confirmations.csv"

# Inch grids drafters actually use, coarsest first. A guess is only offered when a
# grid value converts back to the recorded mm display, so a wrong guess cannot be
# silently accepted by looking plausible.
GRIDS = (1.0, 0.5, 0.25, 0.125, 0.0625, 0.03125, 0.1, 0.05, 0.025, 0.01, 0.005, 0.001)

REASONS = {
    "needs_confirmation": "No readable text on this drawing",
    "spot_check": "Spot-check of an automatic pair",
    "chain": "Chain dimension - confirm each piece",
}


def _decimals(value: str) -> int:
    return len(value.split(".")[-1]) if "." in value else 0


def _format_inch(value: float, decimals: int) -> str:
    """Format the way drawings print inches: .750 rather than 0.750."""
    text = f"{value:.{decimals}f}"
    return text[1:] if text.startswith("0.") else text


def guess_inch(mm_text: str) -> str:
    """Best guess at the printed inch for a recorded mm value, or '' if none fits.

    Tries each grid coarsest-first and keeps the first whose value, converted back
    to millimetres, still rounds to the recorded mm display.
    """
    try:
        mm = float(mm_text)
    except ValueError:
        return ""
    half = 0.5 * 10 ** -_decimals(mm_text)
    raw = mm / 25.4
    for grid in GRIDS:
        snapped = round(raw / grid) * grid
        if snapped <= 0:
            continue
        # 1e-9 keeps a value sitting exactly on the rounding boundary (69.9 vs 2.75 in)
        # from being rejected by floating-point drift.
        if abs(snapped * 25.4 - mm) <= half + 1e-9:
            return _format_inch(snapped, max(_decimals(f"{grid:g}"), 2))
    return ""


@dataclass
class ReviewValue:
    label: str
    axis: str
    recorded_mm: str
    mm_segments: list[str]
    found_inch: str
    inch_segments: list[str]
    guess: str
    segment_guesses: list[str]
    kind: str  # needs_confirmation | spot_check | chain


@dataclass
class ReviewScreen:
    file: str
    part_no: str
    shape: str
    render: str
    values: list[ReviewValue]

    @property
    def kinds(self) -> list[str]:
        return sorted({v.kind for v in self.values})


def _partner_rows() -> list[dict]:
    with paths.INCH_PARTNERS_CSV.open(newline="") as fh:
        return list(csv.DictReader(fh))


def _shapes() -> dict[str, str]:
    with paths.GROUND_TRUTH_CSV.open(newline="") as fh:
        return {r["file"]: r["shape"] for r in csv.DictReader(fh)}


def build_screens() -> list[ReviewScreen]:
    shapes = _shapes()
    screens: dict[str, ReviewScreen] = {}
    for row in _partner_rows():
        if row["is_chain"] == "true":
            kind = "chain"
        elif row["status"] == "needs_confirmation":
            kind = "needs_confirmation"
        elif row["spot_check"] == "true":
            kind = "spot_check"
        else:
            continue

        mm_segments = row["mm_segments"].split("|") if row["mm_segments"] else []
        inch_segments = row["inch_segments"].split("|") if row["inch_segments"] else []
        value = ReviewValue(
            label=row["label"],
            axis=row["axis"],
            recorded_mm=row["recorded_mm"],
            mm_segments=mm_segments,
            found_inch=row["inch_partner"],
            inch_segments=inch_segments,
            guess=row["inch_partner"] or guess_inch(row["recorded_mm"]),
            segment_guesses=[
                inch_segments[i] if i < len(inch_segments) else guess_inch(seg)
                for i, seg in enumerate(mm_segments)
            ],
            kind=kind,
        )
        screen = screens.setdefault(
            row["file"],
            ReviewScreen(
                file=row["file"],
                part_no=row["part_no"],
                shape=shapes.get(row["file"], ""),
                render=row["file"][:-4] + ".png",
                values=[],
            ),
        )
        screen.values.append(value)

    order = {"Dia": 0, "Thk": 1, "W": 2, "L": 3}
    for screen in screens.values():
        screen.values.sort(key=lambda v: order.get(v.label, 9))
    return [screens[f] for f in sorted(screens)]


def as_json() -> list[dict]:
    out = []
    for s in build_screens():
        d = asdict(s)
        d["kinds"] = s.kinds
        out.append(d)
    return out


def load_confirmations() -> dict[str, dict]:
    """Answers saved so far, keyed by 'file|label'."""
    if not CONFIRMATIONS_CSV.exists():
        return {}
    with CONFIRMATIONS_CSV.open(newline="") as fh:
        return {f"{r['file']}|{r['label']}": r for r in csv.DictReader(fh)}


CONFIRMATION_FIELDS = [
    "file",
    "label",
    "axis",
    "recorded_mm",
    "confirmed_inch",
    "confirmed_segments",
    "verdict",
    "note",
    "saved_at",
]


def save_confirmation(entry: dict) -> None:
    """Write one answer, replacing any earlier answer for the same value."""
    existing = load_confirmations()
    existing[f"{entry['file']}|{entry['label']}"] = entry
    paths.DATA.mkdir(exist_ok=True)
    with CONFIRMATIONS_CSV.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CONFIRMATION_FIELDS)
        writer.writeheader()
        for key in sorted(existing):
            row = existing[key]
            writer.writerow({k: row.get(k, "") for k in CONFIRMATION_FIELDS})
