"""Picks the fixed, nested 30- and 60-drawing sets used by smaller runs.

The sets are chosen once and written to data/drawing-sets.csv. They never change
from run to run: the same 30 sit inside the same 60, which sit inside the 141, so
a run today can be compared with a run next month. Picking at random each time
would make those comparisons meaningless, and a random 30 would usually miss the
4 chain drawings entirely.
"""

from __future__ import annotations

import csv
import random
from collections import defaultdict

from vlm_eval import paths
from vlm_eval.ground_truth import Drawing, read_ground_truth

SEED = 20260917

SET_SIZES = (30, 60)

# Drawings every small set must contain: the 4 chain drawings (too rare to leave
# to chance) and the 2 failures worked through on the research page.
REQUIRED = (
    "90-100012-B.pdf",
    "90-100013-A.pdf",
    "200951.pdf",
    "201516.pdf",
    "201533-020.pdf",
    "201548-013.pdf",
)

FIELDNAMES = [
    "file",
    "shape",
    "print_type",
    "pdf_text_type",
    "stratum",
    "dimension_origin",
    "required",
    "in_set_30",
    "in_set_60",
]


class DrawingSetError(ValueError):
    """A set could not be built to spec. Never swallowed."""


def stratum_of(d: Drawing) -> str:
    """The balance bucket a drawing belongs to."""
    return f"{d.shape}|{d.print_type}|{d.pdf_text_type}"


def _proportional_shares(sizes: dict[str, int], total: int, n: int) -> dict[str, float]:
    return {s: count * n / total for s, count in sizes.items()}


def _largest_remainder(sizes: dict[str, int], total: int, n: int) -> dict[str, int]:
    """Split n across the strata in proportion to their size, summing to exactly n."""
    shares = _proportional_shares(sizes, total, n)
    targets = {s: int(share) for s, share in shares.items()}
    leftover = n - sum(targets.values())
    # Strata whose share lost the most to rounding down get the leftover slots.
    # The stratum name breaks exact ties so the result never depends on dict order.
    ranked = sorted(shares, key=lambda s: (-(shares[s] - int(shares[s])), s))
    for s in ranked[:leftover]:
        targets[s] += 1
    return targets


def _apply_floors(
    targets: dict[str, int], floors: dict[str, int], shares: dict[str, float], n: int
) -> dict[str, int]:
    """Raise any target that sits below its floor, then trim back to exactly n.

    Each slot taken back comes from whichever stratum currently sits furthest
    above its proportional share, and no stratum is trimmed below its floor.
    """
    targets = {s: max(t, floors.get(s, 0)) for s, t in targets.items()}
    while sum(targets.values()) > n:
        # Most over-represented first; the stratum name breaks exact ties.
        ranked = sorted(targets, key=lambda s: (-(targets[s] - shares[s]), s))
        trimmable = next((s for s in ranked if targets[s] > max(floors.get(s, 0), 0)), None)
        if trimmable is None:
            raise DrawingSetError(f"cannot trim the set back to {n}: every stratum is at its floor")
        targets[trimmable] -= 1
    if sum(targets.values()) != n:
        raise DrawingSetError(f"targets sum to {sum(targets.values())}, expected {n}")
    return targets


def _select(
    by_stratum: dict[str, list[str]],
    total: int,
    n: int,
    keep: dict[str, list[str]],
    rng: random.Random,
) -> set[str]:
    """Choose n files, keeping everything in `keep` and topping each stratum up."""
    sizes = {s: len(files) for s, files in by_stratum.items()}
    shares = _proportional_shares(sizes, total, n)
    floors = {s: len(files) for s, files in keep.items()}
    targets = _apply_floors(_largest_remainder(sizes, total, n), floors, shares, n)

    chosen: set[str] = set()
    for stratum in sorted(by_stratum):
        kept = sorted(keep.get(stratum, []))
        chosen.update(kept)
        wanted = targets[stratum] - len(kept)
        if wanted <= 0:
            continue
        pool = sorted(f for f in by_stratum[stratum] if f not in kept)
        if wanted > len(pool):
            raise DrawingSetError(f"{stratum}: needs {wanted} more drawings, only {len(pool)} left")
        chosen.update(rng.sample(pool, wanted))
    return chosen


def build_sets(drawings: list[Drawing]) -> dict[int, set[str]]:
    """Build the 30 first, then grow it into the 60 so the sets stay nested."""
    rng = random.Random(SEED)
    total = len(drawings)
    by_stratum: dict[str, list[str]] = defaultdict(list)
    for d in drawings:
        by_stratum[stratum_of(d)].append(d.file)

    stratum_by_file = {d.file: stratum_of(d) for d in drawings}
    keep: dict[str, list[str]] = defaultdict(list)
    for f in sorted(REQUIRED):
        if f not in stratum_by_file:
            raise DrawingSetError(f"required drawing {f} is not in the ground truth")
        keep[stratum_by_file[f]].append(f)

    sets: dict[int, set[str]] = {}
    for n in SET_SIZES:
        sets[n] = _select(dict(by_stratum), total, n, dict(keep), rng)
        # The next, larger set keeps everything this one holds.
        keep = defaultdict(list)
        for f in sorted(sets[n]):
            keep[stratum_by_file[f]].append(f)
    return sets


def _check(drawings: list[Drawing], sets: dict[int, set[str]]) -> None:
    files = [d.file for d in drawings]
    if len(files) != len(set(files)):
        raise DrawingSetError("the same drawing appears more than once")
    for f in files:
        if not (paths.DRAWINGS / f).is_file():
            raise DrawingSetError(f"{f} has no PDF in drawings/")
    for n in SET_SIZES:
        if len(sets[n]) != n:
            raise DrawingSetError(f"the {n}-set holds {len(sets[n])} drawings, expected {n}")
    if not sets[30] <= sets[60]:
        raise DrawingSetError(
            f"the 60-set is missing {sorted(sets[30] - sets[60])} from the 30-set"
        )
    missing = sorted(f for f in REQUIRED if f not in sets[30])
    if missing:
        raise DrawingSetError(f"the 30-set is missing required drawings: {missing}")


def write_csv(drawings: list[Drawing], sets: dict[int, set[str]]) -> None:
    paths.DATA.mkdir(exist_ok=True)
    with paths.DRAWING_SETS_CSV.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        for d in sorted(drawings, key=lambda x: x.file):
            writer.writerow(
                {
                    "file": d.file,
                    "shape": d.shape,
                    "print_type": d.print_type,
                    "pdf_text_type": d.pdf_text_type,
                    "stratum": stratum_of(d),
                    "dimension_origin": d.dimension_origin,
                    "required": "true" if d.file in REQUIRED else "false",
                    "in_set_30": "true" if d.file in sets[30] else "false",
                    "in_set_60": "true" if d.file in sets[60] else "false",
                }
            )


def build(drawings: list[Drawing] | None = None) -> dict[int, set[str]]:
    """Build both sets, check them, and write data/drawing-sets.csv."""
    drawings = drawings if drawings is not None else read_ground_truth()
    sets = build_sets(drawings)
    _check(drawings, sets)
    write_csv(drawings, sets)
    return sets
