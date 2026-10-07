"""Checks spanning the generated data files: inch partners and the drawing sets."""

from __future__ import annotations

EXPECTED_MM_VALUES = 327
EXPECTED_AUTO = 235
EXPECTED_TO_CONFIRM = 92
EXPECTED_SPOT_CHECKS = 20

REQUIRED_IN_30 = {
    "90-100012-B.pdf",
    "90-100013-A.pdf",
    "200951.pdf",
    "201516.pdf",
    "201533-020.pdf",
    "201548-013.pdf",
}


def test_every_mm_value_is_accounted_for(partner_rows):
    assert len(partner_rows) == EXPECTED_MM_VALUES
    auto = [r for r in partner_rows if r["status"] == "auto"]
    todo = [r for r in partner_rows if r["status"] == "needs_confirmation"]
    assert len(auto) + len(todo) == EXPECTED_MM_VALUES
    assert len(auto) == EXPECTED_AUTO
    assert len(todo) == EXPECTED_TO_CONFIRM


def test_values_needing_confirmation_are_all_on_image_only_drawings(partner_rows):
    stray = [
        f"{r['file']} {r['label']}"
        for r in partner_rows
        if r["status"] == "needs_confirmation" and r["pdf_text_type"] != "image_only"
    ]
    assert not stray, stray


def test_auto_pairs_pass_the_conversion_math(partner_rows):
    """Every automatic pair must be a faithful conversion of the recorded mm value."""
    wrong = []
    for r in partner_rows:
        if r["status"] != "auto":
            continue
        mm_parts = [float(x) for x in (r["mm_segments"] or r["recorded_mm"]).split("|")]
        inch_parts = (
            [float(x) for x in r["inch_segments"].split("|")]
            if r["inch_segments"]
            else [float(r["inch_partner"])]
        )
        if len(mm_parts) != len(inch_parts):
            wrong.append(
                f"{r['file']} {r['label']}: {len(mm_parts)} mm parts, {len(inch_parts)} inch"
            )
            continue
        for mm, inch in zip(mm_parts, inch_parts, strict=True):
            decimals = len(str(mm).split(".")[-1]) if "." in str(mm) else 0
            allowance = 0.5 * 10**-decimals + 0.13
            if abs(inch * 25.4 - mm) > allowance:
                wrong.append(f"{r['file']} {r['label']}: {inch} in is not {mm} mm")
    assert not wrong, wrong


def test_chain_values_add_up_in_inches(partner_rows):
    """The inch segments must sum to the inch partner recorded for the whole value."""
    wrong = []
    for r in partner_rows:
        if r["status"] != "auto" or r["is_chain"] != "true" or not r["inch_segments"]:
            continue
        parts = [float(x) for x in r["inch_segments"].split("|")]
        if abs(sum(parts) - float(r["inch_partner"])) > 1e-9:
            wrong.append(
                f"{r['file']} {r['label']}: {parts} sums to {sum(parts)}, not {r['inch_partner']}"
            )
    assert not wrong, wrong


def test_spot_check_sample(partner_rows):
    spot = [r for r in partner_rows if r["spot_check"] == "true"]
    assert len(spot) == EXPECTED_SPOT_CHECKS
    assert all(r["status"] == "auto" for r in spot)
    assert len({r["file"] for r in spot}) == EXPECTED_SPOT_CHECKS, (
        "spot checks must span 20 drawings"
    )


def test_sets_are_the_right_size(set_rows):
    assert sum(1 for r in set_rows if r["in_set_30"] == "true") == 30
    assert sum(1 for r in set_rows if r["in_set_60"] == "true") == 60


def test_30_sits_inside_60(set_rows):
    stray = [r["file"] for r in set_rows if r["in_set_30"] == "true" and r["in_set_60"] != "true"]
    assert not stray, stray


def test_30_contains_every_required_drawing(set_rows):
    in_30 = {r["file"] for r in set_rows if r["in_set_30"] == "true"}
    assert not REQUIRED_IN_30 - in_30, sorted(REQUIRED_IN_30 - in_30)


def test_sets_cover_every_drawing_once(set_rows, gt_rows):
    assert len(set_rows) == len(gt_rows)
    assert {r["file"] for r in set_rows} == {r["file"] for r in gt_rows}


EXPECTED_CONFIRMED = 114


def test_every_value_has_an_inch_to_score_against(partner_rows):
    missing = [f"{r['file']} {r['label']}" for r in partner_rows if not r["final_inch"]]
    assert not missing, missing


def test_garrons_answers_are_recorded(partner_rows):
    confirmed = [r for r in partner_rows if r["final_source"] in ("confirmed", "corrected")]
    assert len(confirmed) == EXPECTED_CONFIRMED


def test_every_final_inch_converts_to_the_recorded_mm(partner_rows):
    """The strongest check on the 92 read off image-only sheets: a misread fails here."""
    wrong = []
    for r in partner_rows:
        if not r["final_inch"]:
            continue
        mm_parts = [float(x) for x in (r["mm_segments"] or r["recorded_mm"]).split("|")]
        inch_total = sum(float(x) for x in r["final_inch"].replace("+", " ").split())
        mm_total = sum(mm_parts)
        decimals = max(len(str(m).split(".")[-1]) if "." in str(m) else 0 for m in mm_parts)
        if abs(inch_total * 25.4 - mm_total) > 0.5 * 10**-decimals + 0.13:
            wrong.append(f"{r['file']} {r['label']}: {r['final_inch']} in vs {mm_total} mm")
    assert not wrong, wrong
