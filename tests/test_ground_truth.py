"""Checks on the hand-edited table and the copy generated from it."""

from __future__ import annotations

from vlm_eval import paths
from vlm_eval.ground_truth import CUBE_LABELS, CYL_LABELS

EXPECTED_DRAWINGS = 141
EXPECTED_TEXT_PDFS = 99
EXPECTED_IMAGE_PDFS = 42


def test_every_row_reads(drawings):
    assert len(drawings) == EXPECTED_DRAWINGS


def test_value_counts_match_shape(drawings):
    wrong = [
        f"{d.file}: {d.shape} has {len(d.dimensions)} values"
        for d in drawings
        if len(d.dimensions) != (3 if d.shape == "CUBE" else 2)
    ]
    assert not wrong, wrong


def test_expected_labels_present(drawings):
    wrong = []
    for d in drawings:
        expected = set(CUBE_LABELS if d.shape == "CUBE" else CYL_LABELS)
        found = {dim.label for dim in d.dimensions}
        if found != expected:
            wrong.append(f"{d.file}: expected {sorted(expected)}, found {sorted(found)}")
    assert not wrong, wrong


def test_chain_formulas_add_up_in_mm(drawings):
    """The segments Garron wrote must sum to the total he wrote."""
    wrong = []
    for d in drawings:
        for dim in d.dimensions:
            if not dim.is_chain:
                continue
            total = round(sum(dim.segments), 6)
            # Compare at the precision of the recorded total, so a value written to
            # one decimal is not failed for arithmetic noise below that.
            decimals = len(dim.printed.split("=")[-1].strip().split(".")[-1])
            if round(total, decimals) != round(dim.total, decimals):
                wrong.append(
                    f"{d.file} {dim.label}: {dim.segments} sums to {total}, not {dim.total}"
                )
    assert not wrong, wrong


def test_every_drawing_has_a_row_and_every_row_a_drawing(drawings):
    on_disk = {p.name for p in paths.DRAWINGS.glob("*.pdf")}
    in_table = {d.file for d in drawings}
    assert not in_table - on_disk, f"in table, no PDF: {sorted(in_table - on_disk)}"
    assert not on_disk - in_table, f"PDF, no row: {sorted(on_disk - in_table)}"


def test_text_layer_split(drawings):
    counts = {"text": 0, "image_only": 0}
    for d in drawings:
        counts[d.pdf_text_type] += 1
    assert counts == {"text": EXPECTED_TEXT_PDFS, "image_only": EXPECTED_IMAGE_PDFS}


def test_measured_from_only_on_chains(drawings):
    wrong = [
        f"{d.file}: Measured From is set but this is not a chain drawing"
        for d in drawings
        if d.measured_from and d.dimension_origin != "calculated_chain"
    ]
    wrong += [
        f"{d.file}: chain drawing with no Measured From value"
        for d in drawings
        if d.dimension_origin == "calculated_chain" and not d.measured_from
    ]
    assert not wrong, wrong


def test_generated_csv_matches_the_table(drawings, gt_rows):
    assert len(gt_rows) == len(drawings)
    assert {r["file"] for r in gt_rows} == {d.file for d in drawings}
