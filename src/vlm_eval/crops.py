"""Cuts zoomed crops of a drawing around a dimension callout.

On drawings with a text layer the callout's position is known exactly, so the
crop is cut from the PDF coordinates. On image-only drawings there is nothing to
locate, so the region has to be supplied.
"""

from __future__ import annotations

import csv
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from vlm_eval import paths

RENDER_DPI = 200
POINTS_PER_INCH = 72
SCALE = RENDER_DPI / POINTS_PER_INCH

RENDERS = paths.ROOT / "runs" / "renders"
CROPS = paths.ROOT / "runs" / "crops"

_WORD = re.compile(
    r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]+)</word>'
)
_NUMBER = re.compile(r"^[Ø⌀R]?(\d*\.?\d+)$")


@dataclass(frozen=True)
class Word:
    value: float
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


def words(pdf_name: str) -> list[Word]:
    out = subprocess.run(
        ["pdftotext", "-bbox", str(paths.DRAWINGS / pdf_name), "-"],
        capture_output=True,
        text=True,
    ).stdout
    found = []
    for m in _WORD.finditer(out):
        text = m.group(5).strip().strip("[]()")
        number = _NUMBER.match(text)
        if number:
            found.append(
                Word(float(number.group(1)), text, *(float(m.group(i)) for i in range(1, 5)))
            )
    return found


def render(pdf_name: str) -> Path:
    RENDERS.mkdir(parents=True, exist_ok=True)
    dest = RENDERS / (pdf_name[:-4] + ".png")
    if not dest.exists():
        subprocess.run(
            [
                "pdftoppm",
                "-r",
                str(RENDER_DPI),
                "-png",
                "-singlefile",
                str(paths.DRAWINGS / pdf_name),
                str(dest)[:-4],
            ],
            check=True,
        )
    return dest


def crop_box(
    pdf_name: str, box: tuple[float, float, float, float], name: str, min_width: int = 900
) -> Path:
    """Cut a crop in PIXEL coordinates, widened to min_width so it reads clearly."""
    CROPS.mkdir(parents=True, exist_ok=True)
    image = Image.open(render(pdf_name))
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    half_w = max((x1 - x0) / 2, min_width / 2)
    half_h = max((y1 - y0) / 2, min_width / 4)
    box = (
        max(0, int(cx - half_w)),
        max(0, int(cy - half_h)),
        min(image.width, int(cx + half_w)),
        min(image.height, int(cy + half_h)),
    )
    dest = CROPS / f"{name}.png"
    image.crop(box).save(dest)
    return dest


def where_on_sheet(x: float, y: float, width: int, height: int) -> str:
    """Plain description of a point's position, so a crop can be placed on the sheet."""
    down = "top" if y < height / 3 else "middle" if y < height * 2 / 3 else "bottom"
    across = "left" if x < width / 3 else "centre" if x < width * 2 / 3 else "right"
    return f"{down} {across}"


def crops_around_value(
    pdf_name: str, mm_value: float, name: str, pad_points: float = 60, limit: int = 4
) -> list[tuple[Path, str]]:
    """Crop around EVERY place this number is printed, not just the first.

    The same number often appears in several views and only one of them is the
    envelope dimension. Guessing which would show the wrong view, so all of them
    are offered and the person reviewing picks.
    """
    anchors = [w for w in words(pdf_name) if abs(w.value - mm_value) < 1e-9]
    anchors.sort(key=lambda w: (w.cy, w.cx))
    image = Image.open(render(pdf_name))
    out = []
    for i, a in enumerate(anchors[:limit]):
        box = (
            (a.x0 - pad_points) * SCALE,
            (a.y0 - pad_points * 0.6) * SCALE,
            (a.x1 + pad_points) * SCALE,
            (a.y1 + pad_points * 0.6) * SCALE,
        )
        where = where_on_sheet(a.cx * SCALE, a.cy * SCALE, image.width, image.height)
        out.append((crop_box(pdf_name, box, f"{name}-{i}"), where))
    return out


# --- the diagnosis agent's two drawing tools (SPEC 2.6) ------------------------------
#
# Positions are given as fractions of the sheet (0 = left/top, 1 = right/bottom), so
# the same numbers work on text drawings, where Poppler knows where each number is, and
# on picture-only drawings, where the agent reads positions off the gridded sheet view.

VIEWS = paths.DIAGNOSES / "views"
SHEET_VIEW_LONG_SIDE = 2400  # pixels; enough to read the layout, small enough to open
VIEW_MAX_LONG_SIDE = 2400  # a zoomed view never exceeds this; zoom by asking for less sheet
DEFAULT_VIEW_DPI = 400

_PAGE_SIZE = re.compile(r"Page size:\s+([\d.]+) x ([\d.]+) pts")


def sheet_size(pdf_name: str) -> tuple[float, float]:
    """The sheet's width and height in points. Every drawing is a single page."""
    out = subprocess.run(
        ["pdfinfo", str(paths.DRAWINGS / pdf_name)], capture_output=True, text=True, check=True
    ).stdout
    m = _PAGE_SIZE.search(out)
    if not m:
        raise ValueError(f"pdfinfo gave no page size for {pdf_name}")
    return float(m.group(1)), float(m.group(2))


@dataclass(frozen=True)
class PrintedNumber:
    """A number printed in the drawing's text layer, and where it sits."""

    text: str  # as printed, brackets removed, e.g. "78.00", "3.071", "Ø9.53"
    number: str  # the number alone, e.g. "9.53"
    across: float  # centre, as a fraction of the sheet width
    down: float  # centre, as a fraction of the sheet height

    @property
    def where(self) -> str:
        return where_on_sheet(self.across, self.down, 1, 1)


def printed_numbers(pdf_name: str) -> list[PrintedNumber]:
    """Every number in the text layer, top to bottom. Empty for a picture-only drawing."""
    width, height = sheet_size(pdf_name)
    found = [
        PrintedNumber(w.text, _NUMBER.match(w.text).group(1), w.cx / width, w.cy / height)
        for w in words(pdf_name)
    ]
    return sorted(found, key=lambda p: (round(p.down, 2), p.across))


def _fraction_label(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".") if value else "0"


def sheet_view(pdf_name: str) -> Path:
    """The whole sheet with a labelled grid every tenth, for picking regions to zoom."""
    from PIL import ImageDraw, ImageFont

    VIEWS.mkdir(parents=True, exist_ok=True)
    dest = VIEWS / f"{pdf_name[:-4]}-sheet.png"
    if dest.exists():
        return dest
    width, height = sheet_size(pdf_name)
    dpi = SHEET_VIEW_LONG_SIDE * POINTS_PER_INCH / max(width, height)
    raw = VIEWS / f"{pdf_name[:-4]}-sheet-raw.png"
    subprocess.run(
        ["pdftoppm", "-r", f"{dpi:.2f}", "-png", "-singlefile", str(paths.DRAWINGS / pdf_name)]
        + [str(raw)[:-4]],
        check=True,
    )
    image = Image.open(raw).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=max(18, image.width // 90))
    for i in range(1, 10):
        x, y = image.width * i / 10, image.height * i / 10
        draw.line([(x, 0), (x, image.height)], fill=(80, 160, 255), width=1)
        draw.line([(0, y), (image.width, y)], fill=(80, 160, 255), width=1)
        draw.text((x + 4, 4), f"{i / 10:.1f}", fill=(0, 90, 220), font=font)
        draw.text((4, y + 4), f"{i / 10:.1f}", fill=(0, 90, 220), font=font)
    image.save(dest)
    raw.unlink()
    return dest


def zoomed_view(
    pdf_name: str, box: tuple[float, float, float, float], dpi: int = DEFAULT_VIEW_DPI
) -> tuple[Path, int]:
    """A sharp render of one region of the sheet, given as fractions (x0, y0, x1, y1).

    Poppler renders only the region, so large sheets never have to fit in memory. The
    resolution drops if the region would exceed VIEW_MAX_LONG_SIDE; the DPI used is
    returned. To see more detail, ask for a smaller region.
    """
    x0, y0, x1, y1 = box
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise ValueError("A region is x0 y0 x1 y1, each between 0 and 1, with x0 < x1 and y0 < y1")
    width, height = sheet_size(pdf_name)
    long_side_points = max((x1 - x0) * width, (y1 - y0) * height)
    dpi = int(min(dpi, VIEW_MAX_LONG_SIDE * POINTS_PER_INCH / long_side_points))
    scale = dpi / POINTS_PER_INCH
    VIEWS.mkdir(parents=True, exist_ok=True)
    name = "-".join([pdf_name[:-4], *(_fraction_label(v) for v in box), f"{dpi}dpi"])
    dest = VIEWS / f"{name}.png"
    if not dest.exists():
        subprocess.run(
            ["pdftoppm", "-r", str(dpi), "-png", "-singlefile"]
            + ["-x", str(int(x0 * width * scale)), "-y", str(int(y0 * height * scale))]
            + [
                "-W",
                str(int((x1 - x0) * width * scale)),
                "-H",
                str(int((y1 - y0) * height * scale)),
            ]
            + [str(paths.DRAWINGS / pdf_name), str(dest)[:-4]],
            check=True,
        )
    return dest, dpi


def _drawing_file(name: str) -> str:
    """Accepts `201513`, `201513.pdf` or `drawings/201513.pdf`."""
    name = Path(name).name
    name = name if name.endswith(".pdf") else f"{name}.pdf"
    if not (paths.DRAWINGS / name).exists():
        raise SystemExit(f"No drawing called {name} in drawings/")
    return name


def is_picture_only(pdf_name: str) -> bool:
    """True for the 42 drawings whose text layer doesn't hold the drawing's numbers.

    Some of them still carry a few title-block numbers, so an empty text layer is not
    the test; the tag recorded in data/ground-truth.csv is.
    """
    with paths.GROUND_TRUTH_CSV.open(newline="") as f:
        tags = {row["file"]: row["pdf_text_type"] for row in csv.DictReader(f)}
    return tags.get(pdf_name) == "image_only"


def cli_numbers(args: list[str]) -> None:
    """`vlm-eval drawing-numbers <drawing>`: printed numbers with their positions."""
    if not args:
        raise SystemExit("usage: vlm-eval drawing-numbers <drawing>")
    pdf = _drawing_file(args[0])
    if is_picture_only(pdf):
        print(f"{pdf} is a picture-only drawing: its dimensions are not in the text layer.")
        print(f"Read them from the pictures: uv run vlm-eval drawing-view {pdf[:-4]}")
        return
    found = printed_numbers(pdf)
    print(f"{len(found)} numbers printed on {pdf}. Position = fraction of sheet across, down.")
    for p in found:
        print(f"{p.text:>12}   across {p.across:.3f}  down {p.down:.3f}   {p.where}")


def cli_view(args: list[str]) -> None:
    """`vlm-eval drawing-view <drawing> [x0 y0 x1 y1] [--dpi N]`: a picture to Read."""
    usage = "usage: vlm-eval drawing-view <drawing> [x0 y0 x1 y1] [--dpi N]"
    dpi = DEFAULT_VIEW_DPI
    if "--dpi" in args:
        i = args.index("--dpi")
        dpi = int(args[i + 1])
        args = args[:i] + args[i + 2 :]
    if len(args) not in (1, 5):
        raise SystemExit(usage)
    pdf = _drawing_file(args[0])
    if len(args) == 1:
        print(f"Whole sheet with a grid every 0.1: {sheet_view(pdf).relative_to(paths.ROOT)}")
        return
    box = tuple(float(a) for a in args[1:])
    dest, used = zoomed_view(pdf, box, dpi)
    print(f"Region {' '.join(args[1:])} at {used} dpi: {dest.relative_to(paths.ROOT)}")
