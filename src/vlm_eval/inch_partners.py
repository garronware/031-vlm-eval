"""Finds the printed inch number that sits beside each recorded mm value.

Most drawings are dual-dimensioned: the sheet prints `69.9 [2.75]`, but the
ground truth recorded only the mm display. Scoring has to accept either printed
number, so this module reads the PDF text layer and pairs each ground-truth mm
value with the inch number printed next to it. Whatever cannot be paired
automatically is marked `needs_confirmation` and goes to Garron's review page.
"""

from __future__ import annotations

import csv
import math
import random
import re
import subprocess
from dataclasses import dataclass

from vlm_eval import paths
from vlm_eval.ground_truth import Dimension, Drawing, read_ground_truth

MM_PER_INCH = 25.4

# An inch display printed to `dec` decimals can sit half a unit of its own last
# place away from the true size, and the mm display rounds independently: 0.13 mm
# is exactly 0.005 in, the allowance for an inch printed to two decimals. Both
# halves are needed; neither alone pairs the corpus cleanly.
INCH_ROUNDING_MM = 0.13

# A dual callout prints its inch value inside or just under the mm value's
# bracket, so the partner is always within a few character heights of the anchor.
NEIGHBOUR_RADIUS_IN_TOKEN_SIZES = 3

SPOT_CHECK_COUNT = 20
SPOT_CHECK_SEED = 20260917

LABEL_ORDER = ("Dia", "Thk", "W", "L")

_NUMBER = re.compile(r"^[Ø⌀R]?(\d*\.?\d+)$")
_WORD = re.compile(r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]+)<')


@dataclass(frozen=True)
class Token:
    """One number printed on the sheet, with where it sits."""

    value: float
    text: str  # as printed, e.g. ".750" rather than 0.75
    x: float
    y: float
    size: float  # the larger of width and height, a stand-in for character height


@dataclass(frozen=True)
class ValuePartner:
    """The inch partner for one ground-truth mm value."""

    drawing: Drawing
    dimension: Dimension
    mm_segments: tuple[str, ...]  # the mm numbers looked up: the chain's segments, or the value
    inch_segments: tuple[str, ...]  # empty unless every mm number paired

    @property
    def paired(self) -> bool:
        return bool(self.inch_segments)

    @property
    def status(self) -> str:
        return "auto" if self.paired else "needs_confirmation"

    @property
    def inch_partner(self) -> str:
        """A chain's partner is the sum of its segments' printed inch values."""
        if not self.paired:
            return ""
        if len(self.inch_segments) == 1:
            return self.inch_segments[0]
        decimals = max(_decimals(s) for s in self.inch_segments)
        return f"{sum(float(s) for s in self.inch_segments):.{decimals}f}"


def _decimals(number: str) -> int:
    return len(number.split(".")[1]) if "." in number else 0


def read_tokens(pdf_path) -> list[Token]:
    """Every number in the PDF text layer, with its centre and size."""
    text = subprocess.run(
        ["pdftotext", "-bbox", str(pdf_path), "-"], capture_output=True, text=True
    ).stdout
    tokens = []
    for x_min, y_min, x_max, y_max, word in _WORD.findall(text):
        match = _NUMBER.match(word.strip().strip("[]()"))
        if not match:
            continue
        x0, y0, x1, y1 = float(x_min), float(y_min), float(x_max), float(y_max)
        tokens.append(
            Token(
                float(match.group(1)),
                match.group(1),
                (x0 + x1) / 2,
                (y0 + y1) / 2,
                max(x1 - x0, y1 - y0),
            )
        )
    return tokens


def find_inch_partner(mm: str, tokens: list[Token]) -> str | None:
    """The printed inch number beside `mm`, or None if nothing qualifies."""
    allowance = 0.5 * 10 ** -_decimals(mm) + INCH_ROUNDING_MM
    target = float(mm)
    best: tuple[float, str] | None = None

    # A sheet can print the same size twice with different trailing zeros - 4.060 on
    # one side of a min/max master and 4.06 on the other - and those carry DIFFERENT
    # inch displays. Comparing as numbers cannot tell them apart, so prefer a token
    # written exactly as the ground truth wrote it, and fall back to numeric matching.
    anchors = [t for t in tokens if abs(t.value - target) < 1e-9]
    anchors = [t for t in anchors if t.text == mm] or anchors

    for anchor in anchors:
        for other in tokens:
            if other is anchor or other.value <= 0:
                continue
            if abs(other.value * MM_PER_INCH - target) > allowance:
                continue
            distance = math.hypot(other.x - anchor.x, other.y - anchor.y)
            if distance >= NEIGHBOUR_RADIUS_IN_TOKEN_SIZES * anchor.size:
                continue
            if best is None or distance < best[0]:
                best = (distance, other.text)
    return best[1] if best else None


def _mm_lookups(dimension: Dimension) -> tuple[str, ...]:
    """The mm numbers to look for on the sheet, as strings so decimals survive.

    A chain's total is never printed anywhere, so only its segments can be found.
    """
    if dimension.is_chain:
        parts = dimension.printed.split("=")[0]
        return tuple(p.strip() for p in parts.split("+"))
    return (dimension.printed.strip(),)


def pair_drawing(drawing: Drawing) -> list[ValuePartner]:
    """Pair every mm value on one drawing. Image-only sheets have no text to read."""
    tokens = (
        [] if drawing.pdf_text_type == "image_only" else read_tokens(paths.DRAWINGS / drawing.file)
    )
    partners = []
    for dimension in drawing.dimensions:
        mm_values = _mm_lookups(dimension)
        found = [find_inch_partner(mm, tokens) for mm in mm_values] if tokens else []
        inches = tuple(f for f in found if f is not None)
        partners.append(
            ValuePartner(
                drawing, dimension, mm_values, inches if len(inches) == len(mm_values) else ()
            )
        )
    return partners


def pair_all(drawings: list[Drawing] | None = None) -> list[ValuePartner]:
    """Every ground-truth mm value across the dual-dimensioned drawings, sorted for output."""
    drawings = drawings if drawings is not None else read_ground_truth()
    partners = []
    for drawing in sorted((d for d in drawings if d.units == "MM"), key=lambda d: d.file):
        partners.extend(pair_drawing(drawing))
    return sorted(partners, key=lambda p: (p.drawing.file, LABEL_ORDER.index(p.dimension.label)))


def choose_spot_checks(partners: list[ValuePartner]) -> set[int]:
    """Indices of the 20 automatic pairs Garron spot-checks, one per drawing.

    Chains are excluded because he reviews all four chain drawings in full anyway.
    """
    by_file: dict[str, list[int]] = {}
    for i, p in enumerate(partners):
        if p.paired and not p.dimension.is_chain:
            by_file.setdefault(p.drawing.file, []).append(i)
    rng = random.Random(SPOT_CHECK_SEED)
    files = rng.sample(sorted(by_file), SPOT_CHECK_COUNT)
    return {rng.choice(by_file[f]) for f in files}


FIELDNAMES = [
    "file",
    "part_no",
    "label",
    "axis",
    "recorded_mm",
    "is_chain",
    "mm_segments",
    "inch_partner",
    "inch_segments",
    "status",
    "pdf_text_type",
    "spot_check",
    "final_inch",
    "final_source",
]


def _confirmations() -> dict[str, dict]:
    """Garron's answers from the review page, keyed by file and label."""
    from vlm_eval import review_items

    return {f"{r['file']}|{r['label']}": r for r in review_items.load_confirmations().values()}


def write_csv(partners: list[ValuePartner]) -> None:
    spot_checks = choose_spot_checks(partners)
    confirmed = _confirmations()
    paths.DATA.mkdir(exist_ok=True)
    with paths.INCH_PARTNERS_CSV.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        for i, p in enumerate(partners):
            chain = p.dimension.is_chain
            writer.writerow(
                {
                    "file": p.drawing.file,
                    "part_no": p.drawing.part_no,
                    "label": p.dimension.label,
                    "axis": p.dimension.axis,
                    "recorded_mm": p.dimension.printed,
                    "is_chain": "true" if chain else "false",
                    "mm_segments": "|".join(p.mm_segments) if chain else "",
                    "inch_partner": p.inch_partner,
                    "inch_segments": "|".join(p.inch_segments) if chain else "",
                    "status": p.status,
                    "pdf_text_type": p.drawing.pdf_text_type,
                    "spot_check": "true" if i in spot_checks else "false",
                    **_final(p, confirmed.get(f"{p.drawing.file}|{p.dimension.label}")),
                }
            )


def _final(p: ValuePartner, answer: dict | None) -> dict[str, str]:
    """The inch value to score against, and where it came from.

    Garron's answer always wins: he is the only authority on what the sheet prints.
    """
    if answer and answer.get("verdict") == "yes":
        return {"final_inch": answer["confirmed_inch"], "final_source": "confirmed"}
    if answer and answer.get("verdict") == "no":
        return {"final_inch": answer["confirmed_inch"], "final_source": "corrected"}
    if answer and answer.get("verdict") in ("unsure", "wrong_dimension"):
        return {"final_inch": "", "final_source": answer["verdict"]}
    if p.status == "auto":
        return {"final_inch": p.inch_partner, "final_source": "found_not_reviewed"}
    return {"final_inch": "", "final_source": "unconfirmed"}


def build() -> list[ValuePartner]:
    """Pair every mm value and write data/inch-partners.csv."""
    partners = pair_all()
    write_csv(partners)
    return partners
