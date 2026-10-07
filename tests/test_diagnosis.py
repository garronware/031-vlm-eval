"""Checks on failure grouping and the diagnosis checks (SPEC 2.6).

No API calls and no agent runs: grouping works on made-up verdicts, and the
diagnosis checks on hand-written diagnosis files. Right values come from the answer
key; trap values are made up and clearly wrong (987.65).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vlm_eval import crops, diagnosis, paths, replay
from vlm_eval.answers import Answer, AnswerValue, Envelope
from vlm_eval.scoring import UnmatchedValue, Verdict, load_answer_key, score

TEXT_DRAWING = "201533-020.pdf"  # Thk 12.700, W 215.9, L 184.2; has a text layer
PICTURE_ONLY_DRAWING = "201581-007.pdf"
MADE_UP = "987.65"


# --- the scorer names the wrong numbers --------------------------------------------


def _answer(*numbers: str) -> Answer:
    return Answer(tuple(AnswerValue(n, "mm") for n in numbers))


def test_a_wrong_number_is_kept_for_diagnosis_and_a_right_answer_has_none():
    key = load_answer_key()[TEXT_DRAWING]
    right = [d.printed for d in key.dimensions]
    assert score(TEXT_DRAWING, _answer(*right), key).unmatched_values == ()
    wrong = score(TEXT_DRAWING, _answer(MADE_UP, *right[1:]), key)
    assert not wrong.strict_pass
    assert [u.number for u in wrong.unmatched_values] == [MADE_UP]


def test_only_envelopes_that_were_not_graded_are_listed_as_ignored():
    key = load_answer_key()[TEXT_DRAWING]
    right = tuple(AnswerValue(d.printed, "mm") for d in key.dimensions)
    assert score(TEXT_DRAWING, Answer(right), key).ignored_envelopes == ()
    extra = Envelope((AnswerValue(MADE_UP, "mm"), AnswerValue("1", "mm")))
    two = score(TEXT_DRAWING, Answer(right, other_envelopes=(extra,)), key)
    assert two.strict_pass
    assert len(two.ignored_envelopes) == 1 and MADE_UP in two.ignored_envelopes[0]


# --- grouping -----------------------------------------------------------------------


def _row(drawing: str, model: str, missed, wrong, passed=False, scored=True) -> replay.Row:
    verdict = Verdict(
        file=drawing,
        scored=scored,
        strict_pass=passed,
        dims_correct=2,
        dims_total=3,
        dims_missed=missed,
        problems=(),
        matches=(),
        unmatched_values=tuple(UnmatchedValue(n, "mm", "Width") for n in wrong),
    )
    call = {"drawing": drawing, "model_name": model, "reply_text": "made-up reply"}
    call_file = Path(f"runs/calls/x/{model}/{drawing[:-4]}-run1.json")
    return replay.Row(call_file, call, None, verdict, "")


def test_identical_failures_from_different_models_are_one_group(monkeypatch):
    rows = [
        _row("201513.pdf", "Model A", ("L (Y)",), ("78.0",)),
        _row("201513.pdf", "Model B", ("L (Y)",), ("78.00",)),  # same size, written longer
        _row("201513.pdf", "Model C", ("L (Y)",), (MADE_UP,)),  # a different wrong number
        _row("201513.pdf", "Model D", (), (), passed=True),
        _row("201513.pdf", "Model E", ("L (Y)",), ("78.0",), scored=False),
    ]
    monkeypatch.setattr(replay, "replay", lambda folder: rows)
    groups, ungraded = diagnosis.failure_groups("x")
    assert [(g.name, g.models) for g in groups] == [
        ("201513-L-78", ["Model A", "Model B"]),
        (f"201513-L-{MADE_UP}", ["Model C"]),
    ]
    assert [replay.parts(r)[0] for r in ungraded] == ["Model E"]


# --- the drawing tools --------------------------------------------------------------


def test_printed_numbers_come_with_positions_on_the_sheet():
    key = load_answer_key()[TEXT_DRAWING]
    found = crops.printed_numbers(TEXT_DRAWING)
    width = next(d for d in key.dimensions if d.label == "W").printed
    spots = [p for p in found if p.number == width]
    assert spots and all(0 <= p.across <= 1 and 0 <= p.down <= 1 for p in spots)
    assert not any(p.number == MADE_UP for p in found)


def test_picture_only_drawings_are_known_from_the_ground_truth_tag():
    assert crops.is_picture_only(PICTURE_ONLY_DRAWING)
    assert not crops.is_picture_only(TEXT_DRAWING)


# --- checking a diagnosis -----------------------------------------------------------


@pytest.fixture
def group(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DIAGNOSES", tmp_path)
    return diagnosis.Group("t", TEXT_DRAWING, ("Thk (Z)",), ("6.35",), ())


def _write(folder_group, entries) -> None:
    path = diagnosis.diagnosis_path("x", folder_group)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"group": folder_group.name, "diagnoses": entries}))


def _entry(label="Proximity association", cited=("12.7",), missed="Thk (Z)") -> dict:
    return {
        "missed": missed,
        "wrong_value": "6.35",
        "label": label,
        "wrong_value_axis": "Z",
        "note": "A short note.",
        "evidence": [{"number": n, "where": "somewhere", "view": ""} for n in cited],
    }


def test_a_complete_diagnosis_citing_printed_numbers_passes(group):
    _write(group, [_entry()])
    assert diagnosis.check("x", group).done


def test_a_cited_number_not_on_the_drawing_is_caught(group):
    _write(group, [_entry(cited=("12.7", MADE_UP))])
    result = diagnosis.check("x", group)
    assert not result.done
    assert any(MADE_UP in p for p in result.problems)


def test_labels_off_garrons_list_and_missing_dimensions_are_rejected(group):
    _write(group, [_entry(label="Made-up label")])
    assert any("not one of Garron's labels" in p for p in diagnosis.check("x", group).problems)
    _write(group, [_entry(missed="W (X)")])
    problems = diagnosis.check("x", group).problems
    assert any("Thk (Z)" in p for p in problems) and any("W (X)" in p for p in problems)


def test_citations_on_picture_only_drawings_are_marked_unchecked(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DIAGNOSES", tmp_path)
    group = diagnosis.Group("p", PICTURE_ONLY_DRAWING, ("Dia",), ("6.35",), ())
    _write(group, [_entry(missed="Dia", cited=(MADE_UP,))])
    result = diagnosis.check("x", group)
    assert result.done
    assert [c.printed for _, cited in result.citations for c in cited] == [None]
