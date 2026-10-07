"""Checks on the scorer (SPEC 2.5): right answers pass in every faithful form, wrong ones fail.

Answers carry the ground-truth label for each value: CUBE values match in any order,
but a cylinder's diameter must be given as the diameter and its length as the length.

Right answers come only from the answer key built from ground truth and the printed
inch values. Trap answers use made-up values that are clearly wrong (x 1.37 + 5, 9999).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pytest

from vlm_eval.answers import Answer, AnswerValue
from vlm_eval.ground_truth import Dimension, Drawing
from vlm_eval.scoring import (
    EXTRA_VALUE,
    MISSING_VALUE,
    UNIT_MIX_UP,
    WRONG_VALUE,
    build_key,
    load_answer_key,
    score,
)

EXPECTED_DRAWINGS = 141
EXPECTED_REPEATED_SIZE_DRAWINGS = 6
EXPECTED_CYLINDERS = 63
MIN_UNIT_MIX_UP_DRAWINGS = 100
CHAIN_DRAWINGS = {"200951.pdf", "201516.pdf", "90-100012-B.pdf", "90-100013-A.pdf"}


# --- helpers ---------------------------------------------------------------


@pytest.fixture(scope="module")
def key():
    return load_answer_key()


def text(value: Decimal, places: str = "0.000001") -> str:
    """A Decimal written the way a reply would: `25.4`, not `25.400000`."""
    return format(value.quantize(Decimal(places), ROUND_HALF_UP).normalize(), "f")


def wrong(value: Decimal) -> Decimal:
    return value * Decimal("1.37") + 5


def printed(dim, unit):
    """The number the drawing itself prints in `unit` (for a chain, its total)."""
    return next(r for r in dim.readings if r.unit == unit and not r.converted)


def given(reading, unit=None, label="", other=""):
    return AnswerValue(text(reading.value), reading.unit if unit is None else unit, label, other)


def perfect(drawing):
    return [given(dim.readings[0], label=dim.label) for dim in drawing.dimensions]


def summary(verdict) -> str:
    return (
        f"{verdict.file}: {verdict.dims_correct}/{verdict.dims_total}, "
        f"problems {list(verdict.problems)}, missed {list(verdict.dims_missed)}"
    )


def failures(cases) -> list[str]:
    """Each case is (file, values, why); lists the ones that did not strict-pass."""
    out = []
    for file, values, why in cases:
        verdict = score(file, Answer(tuple(values)))
        if not verdict.strict_pass:
            out.append(f"{why}: {summary(verdict)}")
    return out


def dual(key):
    return [d for d in key.values() if d.print_type == "dual"]


# --- correct answers pass --------------------------------------------------


def test_every_accepted_reading_passes_in_any_order(key):
    """CUBE answers are reversed with labels left in place; cylinders keep their labels."""
    cases = []
    for drawing in key.values():
        names = {r.name for dim in drawing.dimensions for r in dim.readings}
        for name in sorted(names):
            readings = [
                next((r for r in dim.readings if r.name == name), dim.readings[0])
                for dim in drawing.dimensions
            ]
            values = [given(r) for r in readings]
            labels = [dim.label for dim in drawing.dimensions]
            labeled = [
                AnswerValue(v.number, v.unit, lab) for v, lab in zip(values, labels, strict=True)
            ]
            if drawing.shape == "CUBE":  # labels stay put, so Thk/W/L swaps are tested too
                reversed_ = [
                    AnswerValue(v.number, v.unit, lab)
                    for v, lab in zip(values[::-1], labels, strict=True)
                ]
            else:  # a cylinder's numbers keep their own labels; only the order changes
                reversed_ = labeled[::-1]
            cases += [(drawing.file, labeled, name), (drawing.file, reversed_, f"{name}, reversed")]
    assert len({c[0] for c in cases}) == EXPECTED_DRAWINGS
    bad = failures(cases)
    assert not bad, bad


def test_natural_rounding_of_conversions_passes(key):
    cases = []
    for drawing in dual(key):
        dims = drawing.dimensions
        to_mm = [
            AnswerValue(text(printed(d, "in").value * Decimal("25.4"), "0.01"), "mm", d.label)
            for d in dims
        ]
        cases.append((drawing.file, to_mm, "printed inch converted to mm, 2 places"))
        for places in ("0.001", "0.0001"):
            to_in = [
                AnswerValue(text(printed(d, "mm").value / Decimal("25.4"), places), "in", d.label)
                for d in dims
            ]
            cases.append((drawing.file, to_in, f"printed mm converted to inch, {places}"))
    bad = failures(cases)
    assert not bad, bad


def test_answers_with_no_units_still_pass(key):
    cases = []
    for drawing in key.values():
        for unit in ("mm", "in"):
            values = [
                given(next(r for r in dim.readings if r.unit == unit), unit="", label=dim.label)
                for dim in drawing.dimensions
            ]
            cases.append((drawing.file, values, f"all {unit}, unit not given"))
    bad = failures(cases)
    assert not bad, bad


# --- fake models -----------------------------------------------------------


def test_perfect_fake_model_scores_every_drawing(key):
    verdicts = [score(d.file, Answer(tuple(perfect(d)))) for d in key.values()]
    bad = [summary(v) for v in verdicts if not v.strict_pass]
    assert not bad, bad
    assert sum(v.strict_pass for v in verdicts) == EXPECTED_DRAWINGS


def test_bad_fake_model_scores_nothing(key):
    verdicts = []
    for d in key.values():
        values = [
            AnswerValue(text(wrong(dim.readings[0].value)), dim.readings[0].unit, dim.label)
            for dim in d.dimensions
        ]
        verdicts.append(score(d.file, Answer(tuple(values))))
    bad = [summary(v) for v in verdicts if v.strict_pass or v.dims_correct]
    assert not bad, bad


# --- missing, extra, wrong -------------------------------------------------


def test_missing_extra_and_wrong_values_fail(key):
    bad = []
    for d in key.values():
        n, right = len(d.dimensions), perfect(d)
        for i, value in enumerate(right):
            v = value.number
            # A cylinder answered with three sizes is judged as the box its cylinder
            # fills, so a made-up third size reads as a wrong value, not an extra one.
            extra_problem = WRONG_VALUE if d.shape == "CYL" else EXTRA_VALUE
            trials = [
                ("missing", right[:i] + right[i + 1 :], MISSING_VALUE, n - 1),
                ("extra", [*right, AnswerValue("9999", value.unit)], extra_problem, n),
                (
                    "wrong",
                    [*right[:i], AnswerValue(text(wrong(Decimal(v))), value.unit), *right[i + 1 :]],
                    WRONG_VALUE,
                    n - 1,
                ),
            ]
            for why, values, problem, correct in trials:
                verdict = score(d.file, Answer(tuple(values)))
                if (
                    verdict.strict_pass
                    or verdict.problems != (problem,)
                    or verdict.dims_correct != correct
                ):
                    bad.append(f"{why} {value.label}: {summary(verdict)}")
    assert not bad, bad


def test_a_cylinder_answered_with_a_made_up_third_size_fails(key):
    cylinders = [d for d in key.values() if d.shape == "CYL"]
    bad = []
    for d in cylinders:
        values = [*perfect(d), AnswerValue(text(wrong(d.dimensions[0].readings[0].value)), "mm")]
        verdict = score(d.file, Answer(tuple(values), shape="CUBE"))
        if verdict.strict_pass:
            bad.append(summary(verdict))
    assert not bad, bad


def test_the_box_a_cylinder_fills_is_a_correct_answer(key):
    """The bare prompt names no shape, so Dia x Dia x L is the same envelope as Dia, L.

    Nothing new is recorded for this: both forms come from the recorded Dia and L.
    """
    cylinders = [d for d in key.values() if d.shape == "CYL"]
    assert cylinders
    bad = []
    for d in cylinders:
        dia = next(v for v in perfect(d) if v.label == "Dia")
        length = next(v for v in perfect(d) if v.label != "Dia")
        verdict = score(d.file, Answer((dia, dia, length), shape="CUBE"))
        if not verdict.strict_pass or verdict.dims_correct != 3:
            bad.append(summary(verdict))
    assert not bad, bad


def test_a_smaller_size_from_a_local_feature_is_not_an_envelope(key):
    """90-100013-A: a box using the across-flats size instead of the diameter fails."""
    d = key["90-100013-A.pdf"]  # Dia 1.5000, L 3.83 + 1.13 = 4.96, inch-only print
    dia = next(v for v in perfect(d) if v.label == "Dia")
    length = next(v for v in perfect(d) if v.label != "Dia")
    across_flats = AnswerValue("1.368", "in")  # printed on the sheet, but a wrench flat
    verdict = score(d.file, Answer((across_flats, dia, length), shape="CUBE"))
    assert verdict.scored and not verdict.strict_pass


def _mix_up_cases(key):
    """One printed-inch number among correct mm numbers, labeled mm and unlabeled.

    Skips a dimension whose inch number, read as mm, lands in some mm window by chance.
    """
    cases = []
    for d in dual(key):
        mm = [given(printed(dim, "mm"), label=dim.label) for dim in d.dimensions]
        windows = [r for dim in d.dimensions for r in dim.readings if r.unit == "mm"]
        for i, dim in enumerate(d.dimensions):
            inch = printed(dim, "in").value
            if any(r.accepts(inch, "mm") for r in windows):
                continue
            labeled = [*mm[:i], AnswerValue(text(inch), "mm", dim.label), *mm[i + 1 :]]
            unlabeled = [AnswerValue(v.number, "", v.label) for v in labeled]
            cases += [(d.file, labeled, "labeled mm"), (d.file, unlabeled, "no units")]
            break
    return cases


def test_an_inch_number_given_as_mm_is_a_unit_mix_up(key):
    cases = _mix_up_cases(key)
    assert len({c[0] for c in cases}) > MIN_UNIT_MIX_UP_DRAWINGS
    bad = []
    for file, values, why in cases:
        verdict = score(file, Answer(tuple(values)))
        if verdict.strict_pass or verdict.problems != (UNIT_MIX_UP,):
            bad.append(f"{why}: {summary(verdict)}")
    assert not bad, bad


# --- special cases ---------------------------------------------------------


def test_a_repeated_size_given_once_misses_one_dimension(key):
    bad, found = [], 0
    for d in key.values():
        firsts = [dim.readings[0].value for dim in d.dimensions]
        repeated = [i for i, v in enumerate(firsts) if firsts.count(v) > 1]
        if not repeated:
            continue
        found += 1
        kept, dropped = repeated[0], repeated[1]
        values = [v for i, v in enumerate(perfect(d)) if i != dropped]
        verdict = score(d.file, Answer(tuple(values)))
        expected_miss = (d.dimensions[dropped].described,)
        if verdict.strict_pass or verdict.dims_correct != len(d.dimensions) - 1:
            bad.append(summary(verdict))
        elif verdict.dims_missed != expected_miss:
            bad.append(f"{summary(verdict)}; answer said {d.dimensions[kept].label}")
    assert found == EXPECTED_REPEATED_SIZE_DRAWINGS
    assert not bad, bad


def _chain_ways(gt_row, partner, label):
    """(why, number, unit) for the chain total and its segments, straight from the data files."""
    col = label.lower()
    segments = gt_row[f"{col}_segments"].split("|")
    total = gt_row[col].partition("=")[2].strip()
    first_unit = "mm" if gt_row["print_type"] == "dual" else "in"
    ways = [
        ("total", total, first_unit),
        ("segments added up", str(sum(map(Decimal, segments))), first_unit),
    ]
    pieces = [(f"only segment {s}", s, first_unit) for s in segments]
    if partner:
        inch_segments = [s.strip() for s in partner["final_inch"].split("+")]
        ways.append(("inch segments added up", str(sum(map(Decimal, inch_segments))), "in"))
        pieces += [(f"only segment {s} in", s, "in") for s in inch_segments]
    return ways, pieces


def test_chains_pass_as_total_or_segments_and_fail_on_one_segment(key, gt_rows, partner_rows):
    rows = {r["file"]: r for r in gt_rows}
    partners = {(r["file"], r["label"]): r for r in partner_rows}
    assert {
        f for f, r in rows.items() if r["dimension_origin"] == "calculated_chain"
    } == CHAIN_DRAWINGS
    bad = []
    for file in sorted(CHAIN_DRAWINGS):
        drawing, right = key[file], perfect(key[file])
        for i, dim in enumerate(drawing.dimensions):
            if not rows[file][f"{dim.label.lower()}_segments"]:
                continue
            ways, pieces = _chain_ways(rows[file], partners.get((file, dim.label)), dim.label)
            for why, number, unit in ways + pieces:
                values = [*right[:i], AnswerValue(number, unit, dim.label), *right[i + 1 :]]
                verdict = score(file, Answer(tuple(values)))
                should_pass = not why.startswith("only")
                if verdict.strict_pass != should_pass or (
                    not should_pass and verdict.dims_missed != (dim.described,)
                ):
                    bad.append(f"{dim.label} {why}: {summary(verdict)}")
    assert not bad, bad


def test_chain_segments_that_do_not_add_to_the_printed_total_still_pass():
    """Made-up drawing: the mm segments sum to 72.95, the printed total is 72.91 (SPEC 2.5).

    No real chain drifts today, so without this the segments rule would go untested.
    """
    file = "made-up-chain.pdf"
    dims = (
        Dimension("Thk", "Z", "10.0", 10.0),
        Dimension("W", "X", "50.0", 50.0),
        Dimension("L", "Y", "6.35 + 66.6 = 72.91", 72.91, (6.35, 66.6)),
    )
    drawing = Drawing(file, "made-up-chain", "CUBE", "MM", "", "", "", "Part Edge", dims)
    inch = {(file, "Thk"): ".39", (file, "W"): "1.97", (file, "L"): "0.250 + 2.620"}
    made_up_key = build_key(drawing, inch)
    bad = []
    for number, unit, should_pass in [
        ("72.91", "mm", True),
        ("72.95", "mm", True),
        ("2.870", "in", True),
        ("72.99", "mm", False),
        ("66.6", "mm", False),
    ]:
        values = (AnswerValue("10.0", "mm"), AnswerValue("50.0", "mm"), AnswerValue(number, unit))
        verdict = score(file, Answer(values), key=made_up_key)
        if verdict.strict_pass != should_pass:
            bad.append(f"L as {number} {unit}: {summary(verdict)}")
    assert not bad, bad


def test_one_right_unit_is_enough_when_a_reply_gives_both(key):
    cases = []
    for d in dual(key):
        labels = [dim.label for dim in d.dimensions]
        mm = [printed(dim, "mm").value for dim in d.dimensions]
        inch = [printed(dim, "in").value for dim in d.dimensions]
        mm_right = [
            AnswerValue(text(m), "mm", lab, text(wrong(i)))
            for m, i, lab in zip(mm, inch, labels, strict=True)
        ]
        inch_right = [
            AnswerValue(text(wrong(m)), "mm", lab, text(i))
            for m, i, lab in zip(mm, inch, labels, strict=True)
        ]
        cases += [
            (d.file, mm_right, "mm right, inch wrong"),
            (d.file, inch_right, "inch right, mm wrong"),
        ]
    bad = failures(cases)
    assert not bad, bad


def test_fractions_are_read_as_decimals(key):
    file = "201551-016.pdf"
    printed_inch = sorted(printed(dim, "in").value for dim in key[file].dimensions)
    assert printed_inch == [Decimal("0.75"), Decimal("1.00"), Decimal("2.50")]
    values = [AnswerValue(n, "in") for n in ("1", "2 1/2", "3/4")]
    assert not failures([(file, values, "fractions")])


def test_nearby_wrong_printed_numbers_fail(key):
    """Numbers a hair off the true size (19.0 vs 19.1 mm, .31 vs .3150 in) must not pass."""
    block = [AnswerValue("25.4", "mm"), AnswerValue("63.5", "mm"), AnswerValue("19.0", "mm")]
    rod = [AnswerValue(".31", "in", "Dia"), AnswerValue("2.00", "in", "L")]
    block_verdict = score("201551-016.pdf", Answer(tuple(block)))
    rod_verdict = score("201548-019.pdf", Answer(tuple(rod)))
    assert block_verdict.dims_missed == ("L (Y)",), summary(block_verdict)
    assert rod_verdict.dims_missed == ("Dia",), summary(rod_verdict)
    assert not block_verdict.strict_pass and not rod_verdict.strict_pass


@pytest.mark.parametrize(
    "answer",
    [
        Answer((AnswerValue("25.4", "mm"),), flagged=True),
        Answer((AnswerValue("8 ft", "mm"),)),
        Answer((AnswerValue("abc", ""),)),
        Answer((AnswerValue("25.4", "cm"),)),
    ],
    ids=["flagged", "8 ft", "abc", "cm"],
)
def test_flagged_or_unreadable_replies_are_not_scored(answer):
    verdict = score("201551-016.pdf", answer)
    assert not verdict.scored and not verdict.strict_pass and verdict.dims_correct == 0


def test_scoring_the_same_answers_twice_gives_identical_verdicts(key):
    batch = [(d.file, perfect(d), "perfect") for d in key.values()]
    batch += [
        (
            d.file,
            [
                AnswerValue(text(wrong(dim.readings[0].value)), "", dim.label)
                for dim in d.dimensions
            ],
            "bad",
        )
        for d in key.values()
    ]
    batch += _mix_up_cases(key)
    first = [score(f, Answer(tuple(v))) for f, v, _ in batch]
    second = [score(f, Answer(tuple(v))) for f, v, _ in batch]
    assert first == second


def test_missed_dimensions_are_named_by_label_and_axis(key, gt_rows):
    """Axes come from the ground-truth file, not the key, so a wiring slip shows up."""
    rows = {r["file"]: r for r in gt_rows}
    bad = []
    for d in key.values():
        right = perfect(d)
        for i, dim in enumerate(d.dimensions):
            axis = rows[d.file].get(f"{dim.label.lower()}_axis", "")
            expected = f"{dim.label} ({axis})" if axis else dim.label
            verdict = score(d.file, Answer(tuple(right[:i] + right[i + 1 :])))
            if verdict.dims_missed != (expected,):
                bad.append(f"expected {expected}: {summary(verdict)}")
    assert not bad, bad


# --- cylinders -------------------------------------------------------------


def _cylinders(key):
    cylinders = [d for d in key.values() if d.shape == "CYL"]
    assert len(cylinders) == EXPECTED_CYLINDERS
    return cylinders


def test_a_cylinder_with_diameter_and_length_swapped_fails(key):
    bad, tested = [], 0
    for d in _cylinders(key):
        dia, length = (printed(dim, dim.readings[0].unit) for dim in d.dimensions)
        if dia.value == length.value:  # same size both ways; a swap changes nothing
            continue
        tested += 1
        values = [given(length, label="Dia"), given(dia, label="L")]
        verdict = score(d.file, Answer(tuple(values)))
        if verdict.strict_pass or verdict.dims_correct:
            bad.append(summary(verdict))
    assert tested >= EXPECTED_CYLINDERS - 1
    assert not bad, bad


def test_a_cylinder_reply_naming_only_one_size_still_passes(key):
    """`Ø10 × 75`: the unnamed number is the other size."""
    cases = []
    for d in _cylinders(key):
        right = perfect(d)
        for i in range(2):
            values = [v if j == i else AnswerValue(v.number, v.unit) for j, v in enumerate(right)]
            cases.append((d.file, values, f"only {right[i].label} named"))
    bad = failures(cases)
    assert not bad, bad


def test_a_cylinder_reply_naming_neither_size_is_not_graded(key):
    bad = []
    for d in _cylinders(key):
        values = [AnswerValue(v.number, v.unit) for v in perfect(d)]
        verdict = score(d.file, Answer(tuple(values)))
        if verdict.scored:
            bad.append(summary(verdict))
    assert not bad, bad


# --- chain notes -----------------------------------------------------------


def test_giving_one_part_of_a_chain_is_noted(key):
    bad = []
    for file in sorted(CHAIN_DRAWINGS):
        drawing, right = key[file], perfect(key[file])
        if score(file, Answer(tuple(right))).chain_parts_given:
            bad.append(f"{file}: note on a correct answer")
        for i, dim in enumerate(drawing.dimensions):
            for part in dim.chain_parts:
                for reading in part.readings:
                    values = [*right[:i], given(reading, label=dim.label), *right[i + 1 :]]
                    verdict = score(file, Answer(tuple(values)))
                    note = verdict.chain_parts_given
                    if len(note) != 1 or f"one part of the chain {dim.printed}" not in note[0]:
                        bad.append(f"{file} {dim.label} {reading.name} {part.printed}: {note}")
    assert not bad, bad
