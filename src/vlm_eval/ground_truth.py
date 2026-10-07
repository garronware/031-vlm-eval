"""Reads drawings/ground-truth.md, the only hand-edited source of truth.

Everything this module produces is generated. Nothing here writes back to the
markdown table.
"""

from __future__ import annotations

import csv
import re
import subprocess
from dataclasses import dataclass, field

from vlm_eval import paths

# Image-only PDFs carry between 0 and 141 characters of extractable text; PDFs
# with a real text layer carry 658 or more. Nothing in the corpus falls between,
# so any cutoff inside that gap splits the 141 drawings the same way. Picking the
# middle keeps the split stable if a future drawing lands near an edge.
TEXT_LAYER_MIN_CHARS = 300

CUBE_LABELS = ("Thk", "W", "L")
CYL_LABELS = ("Dia", "L")

_CHAIN = re.compile(r"^(?P<parts>[\d.]+(?:\s*\+\s*[\d.]+)+)\s*=\s*(?P<total>[\d.]+)$")


class GroundTruthError(ValueError):
    """A row in ground-truth.md could not be read. Never swallowed."""


@dataclass(frozen=True)
class Dimension:
    """One bounding dimension as Garron recorded it."""

    label: str  # Dia | Thk | W | L
    axis: str  # X | Y | Z, blank for Dia
    printed: str  # the cell exactly as written
    total: float
    segments: tuple[float, ...] = ()

    @property
    def is_chain(self) -> bool:
        return bool(self.segments)


@dataclass(frozen=True)
class Drawing:
    """One row of ground-truth.md, plus what code works out from it."""

    file: str
    part_no: str
    shape: str  # CUBE | CYL
    units: str  # MM | IN
    material: str
    projection: str
    notes: str
    measured_from: str  # Part Edge | In-Between Edges | ""
    dimensions: tuple[Dimension, ...] = field(default_factory=tuple)
    pdf_text_type: str = ""  # text | image_only

    @property
    def print_type(self) -> str:
        """Dual-dimensioned `mm [in]` prints vs inch-only prints."""
        return "dual" if self.units == "MM" else "inch_only"

    @property
    def dimension_origin(self) -> str:
        """Worked out from the `+` in Garron's formulas, never recorded separately."""
        return (
            "calculated_chain"
            if any(d.is_chain for d in self.dimensions)
            else "explicitly_dimensioned"
        )

    @property
    def datum_referenced(self) -> bool:
        """True when the chain's zero sits between the part's edges."""
        return self.measured_from == "In-Between Edges"

    def dimension(self, label: str) -> Dimension | None:
        return next((d for d in self.dimensions if d.label == label), None)


def _parse_value(label: str, axis: str, cell: str) -> Dimension:
    cell = cell.strip()
    chain = _CHAIN.match(cell)
    if chain:
        segments = tuple(float(p) for p in re.split(r"\s*\+\s*", chain.group("parts")))
        return Dimension(label, axis, cell, float(chain.group("total")), segments)
    try:
        return Dimension(label, axis, cell, float(cell))
    except ValueError as exc:
        raise GroundTruthError(f"{label} value {cell!r} is not a number or a chain") from exc


def _classify_pdf(pdf_path) -> str:
    text = subprocess.run(["pdftotext", str(pdf_path), "-"], capture_output=True, text=True).stdout
    return "text" if len("".join(text.split())) >= TEXT_LAYER_MIN_CHARS else "image_only"


def read_ground_truth(classify_pdfs: bool = True) -> list[Drawing]:
    """Read every row. Raises on the first row that does not read cleanly."""
    drawings: list[Drawing] = []
    for line in paths.GROUND_TRUTH_MD.read_text().splitlines():
        if not line.startswith("| ") or ".pdf" not in line.split("|")[1]:
            continue
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) < 15:
            raise GroundTruthError(f"{c[0]}: expected 15 columns, found {len(c)}")
        (
            fname,
            part_no,
            shape,
            units,
            dia,
            thk,
            thk_axis,
            w,
            w_axis,
            length,
            l_axis,
            material,
            projection,
            notes,
            measured_from,
        ) = c[:15]

        if shape not in ("CUBE", "CYL"):
            raise GroundTruthError(f"{fname}: shape {shape!r} is not CUBE or CYL")
        if units not in ("MM", "IN"):
            raise GroundTruthError(f"{fname}: units {units!r} is not MM or IN")

        cells = {"Dia": (dia, ""), "Thk": (thk, thk_axis), "W": (w, w_axis), "L": (length, l_axis)}
        expected = CUBE_LABELS if shape == "CUBE" else CYL_LABELS
        for label, (value, _) in cells.items():
            if label in expected and not value:
                raise GroundTruthError(f"{fname}: {shape} is missing {label}")
            if label not in expected and value:
                raise GroundTruthError(f"{fname}: {shape} should not have {label}, found {value!r}")

        dims = tuple(_parse_value(label, cells[label][1], cells[label][0]) for label in expected)
        for d in dims:
            if d.label != "Dia" and d.axis not in ("X", "Y", "Z"):
                raise GroundTruthError(f"{fname}: {d.label} axis {d.axis!r} is not X, Y or Z")
        if measured_from and measured_from not in ("Part Edge", "In-Between Edges"):
            raise GroundTruthError(f"{fname}: Measured From {measured_from!r} is not a known value")

        pdf_type = _classify_pdf(paths.DRAWINGS / fname) if classify_pdfs else ""
        drawings.append(
            Drawing(
                fname,
                part_no,
                shape,
                units,
                material,
                projection,
                notes,
                measured_from,
                dims,
                pdf_type,
            )
        )

    if not drawings:
        raise GroundTruthError("no rows found in ground-truth.md")
    return drawings


FIELDNAMES = [
    "file",
    "part_no",
    "shape",
    "units",
    "print_type",
    "pdf_text_type",
    "dimension_origin",
    "datum_referenced",
    "measured_from",
    "dia",
    "dia_segments",
    "thk",
    "thk_axis",
    "thk_segments",
    "w",
    "w_axis",
    "w_segments",
    "l",
    "l_axis",
    "l_segments",
    "material",
    "projection",
    "notes",
]


def _cols(d: Drawing, label: str) -> dict[str, str]:
    dim = d.dimension(label)
    key = label.lower()
    if dim is None:
        out = {key: "", f"{key}_segments": ""}
    else:
        out = {key: dim.printed, f"{key}_segments": "|".join(str(s) for s in dim.segments)}
    if label != "Dia":
        out[f"{key}_axis"] = dim.axis if dim else ""
    return out


def write_csv(drawings: list[Drawing]) -> None:
    paths.DATA.mkdir(exist_ok=True)
    with paths.GROUND_TRUTH_CSV.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        for d in sorted(drawings, key=lambda x: x.file):
            row = {
                "file": d.file,
                "part_no": d.part_no,
                "shape": d.shape,
                "units": d.units,
                "print_type": d.print_type,
                "pdf_text_type": d.pdf_text_type,
                "dimension_origin": d.dimension_origin,
                "datum_referenced": "true" if d.datum_referenced else "false",
                "measured_from": d.measured_from,
                "material": d.material,
                "projection": d.projection,
                "notes": d.notes,
            }
            for label in ("Dia", "Thk", "W", "L"):
                row.update(_cols(d, label))
            writer.writerow(row)
