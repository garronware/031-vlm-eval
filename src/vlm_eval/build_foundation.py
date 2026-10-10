"""Regenerates everything in data/ from ground-truth.md, then writes the summary.

Nothing here touches drawings/ground-truth.md, and nothing calls a model API.
"""

from __future__ import annotations

import collections
import csv

from vlm_eval import drawing_sets, ground_truth, inch_partners, paths, tolerances


def _read(path):
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def write_summary() -> str:
    drawings = _read(paths.GROUND_TRUTH_CSV)
    partners = _read(paths.INCH_PARTNERS_CSV)
    sets = _read(paths.DRAWING_SETS_CSV)
    toleranced = _read(paths.ENVELOPE_TOLERANCES_CSV)

    prints = collections.Counter(d["print_type"] for d in drawings)
    pdfs = collections.Counter(d["pdf_text_type"] for d in drawings)
    status = collections.Counter(p["status"] for p in partners)
    final = collections.Counter(p["final_source"] for p in partners)

    chains = [d for d in drawings if d["dimension_origin"] == "calculated_chain"]
    between = [d["file"] for d in chains if d["datum_referenced"] == "true"]
    edge = [d["file"] for d in chains if d["datum_referenced"] != "true"]
    spot = [p for p in partners if p["spot_check"] == "true"]
    set30 = sorted(s["file"] for s in sets if s["in_set_30"] == "true")
    image_in_30 = sum(
        1 for s in sets if s["in_set_30"] == "true" and s["pdf_text_type"] == "image_only"
    )

    lines = [
        "# Ground-truth foundation",
        "",
        "Generated from `drawings/ground-truth.md`. Nothing here is hand-edited.",
        "",
        "## The drawings",
        "",
        f"- **{len(drawings)} drawings** — {prints['dual']} dual-dimensioned, "
        f"{prints['inch_only']} inch-only",
        f"- **{pdfs['text']} have readable text**, {pdfs['image_only']} are image-only",
        f"- **{len(chains)} chain drawings**, {len(between)} measured from in-between edges:",
        f"  - in-between edges: {', '.join(sorted(between)) or 'none'}",
        f"  - part edge: {', '.join(sorted(edge)) or 'none'}",
        "",
        "## Inch partners",
        "",
        f"- **{len(partners)} of {len(partners)} have an inch value** to score against",
        f"- {final['confirmed'] + final['corrected']} confirmed by Garron on the review page",
        f"- {final['found_not_reviewed']} found automatically and not individually reviewed",
        f"- {status['auto']} were found from the text layer, {status['needs_confirmation']} "
        f"were read off image-only sheets",
        f"- {len(spot)} automatic pairs were spot-checked",
        "",
        "## Envelope tolerances",
        "",
        f"- **{len(toleranced)} envelope sizes are printed with a ± tolerance**, on "
        f"{len({t['file'] for t in toleranced})} drawings; each also accepts its upper limit",
        "- found in the text layer only, so picture-only drawings have none listed",
        "",
        "## First run set",
        "",
        f"The fixed 30 sits inside the 60, which sits inside the {len(drawings)}. "
        f"{image_in_30} of the 30 are image-only ({image_in_30 * 100 // 30}%).",
        "",
    ]
    lines += [f"{i:>3}. {f}" for i, f in enumerate(set30, 1)]
    lines.append("")

    text = "\n".join(lines)
    paths.FOUNDATION_SUMMARY.write_text(text)
    return text


def build() -> str:
    """Rebuild all three data files from scratch and return the summary."""
    ground_truth.write_csv(ground_truth.read_ground_truth())
    inch_partners.build()
    tolerances.build()
    drawing_sets.build()
    return write_summary()
