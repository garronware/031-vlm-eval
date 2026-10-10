"""Tolerances printed on envelope sizes (SPEC 2.5, Garron 2026-10-10).

A size printed with a tolerance, e.g. `Ø83.570 ±0.025 [Ø3.2902 ±.0010]`, can be as large
as its upper limit, so the scorer also accepts that limit as a bounding dimension. This
module finds each such tolerance in the drawing's text layer and writes
data/envelope-tolerances.csv. Picture-only drawings have no text layer, so none are found
there. Only symmetric (±) tolerances are read; chains are skipped.
"""

from __future__ import annotations

import csv
import re
import subprocess
from decimal import Decimal

from vlm_eval import paths
from vlm_eval.ground_truth import Drawing, read_ground_truth

# Some fonts on these sheets put a backtick in the text layer where the sheet shows ±.
_PLUS_MINUS = r"\s*(?:±|`|\+/-)\s*"
_TOLERANCE = r"(\d*\.?\d+)"

FIELDNAMES = ["file", "label", "printed", "printed_tolerance", "inch", "inch_tolerance"]


def _text(drawing: Drawing) -> str:
    return subprocess.run(
        ["pdftotext", "-layout", str(paths.DRAWINGS / drawing.file), "-"],
        capture_output=True,
        text=True,
    ).stdout


def _spellings(number: str) -> set[str]:
    """`0.750` is printed as `.750` on some sheets."""
    return {number, number[1:]} if number.startswith("0.") else {number}


def tolerance_of(number: str, text: str) -> str:
    """The ± tolerance printed right after this number, or "" if none."""
    for spelling in _spellings(number):
        pattern = r"(?<![\d.])" + re.escape(spelling) + _PLUS_MINUS + _TOLERANCE
        found = {m.group(1) for m in re.finditer(pattern, text)}
        if len(found) == 1:
            return found.pop()
    return ""


def find(drawings: list[Drawing], inch_values: dict[tuple[str, str], str]) -> list[dict]:
    rows = []
    for drawing in drawings:
        dims = [d for d in drawing.dimensions if not d.is_chain]
        if not dims:
            continue
        text = _text(drawing)
        if not text.strip():
            continue
        for d in dims:
            inch = (
                d.printed if drawing.units == "IN" else inch_values.get((drawing.file, d.label), "")
            )
            printed_tol = "" if drawing.units == "IN" else tolerance_of(d.printed, text)
            inch_tol = tolerance_of(inch, text) if inch else ""
            if printed_tol or inch_tol:
                rows.append(
                    {
                        "file": drawing.file,
                        "label": d.label,
                        "printed": "" if drawing.units == "IN" else d.printed,
                        "printed_tolerance": printed_tol,
                        "inch": inch,
                        "inch_tolerance": inch_tol,
                    }
                )
    return rows


def build() -> list[dict]:
    """Find every printed envelope tolerance and write data/envelope-tolerances.csv."""
    with paths.INCH_PARTNERS_CSV.open(newline="") as fh:
        inch_values = {(r["file"], r["label"]): r["final_inch"] for r in csv.DictReader(fh)}
    rows = find(read_ground_truth(classify_pdfs=False), inch_values)
    with paths.ENVELOPE_TOLERANCES_CSV.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def load() -> dict[tuple[str, str], tuple[Decimal | None, Decimal | None]]:
    """(file, label) -> (tolerance on the printed mm, tolerance on the inch value)."""
    if not paths.ENVELOPE_TOLERANCES_CSV.exists():
        return {}
    with paths.ENVELOPE_TOLERANCES_CSV.open(newline="") as fh:
        return {
            (r["file"], r["label"]): (
                Decimal(r["printed_tolerance"]) if r["printed_tolerance"] else None,
                Decimal(r["inch_tolerance"]) if r["inch_tolerance"] else None,
            )
            for r in csv.DictReader(fh)
        }
