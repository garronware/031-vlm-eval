"""Checks on extraction and replay (SPEC 2.12, section 3). No API calls: the extractor is faked.

What matters: every number the extractor hands the scorer is really in the reply,
as a whole number; anything unsure is flagged, never guessed; each extraction is
saved once and reused; and replay re-scores from saved files without calling
any model. The replies here are made up, and their wrong values are clearly wrong.
"""

from __future__ import annotations

import json

import pytest

from vlm_eval import extraction, paths, replay
from vlm_eval.answers import AnswerValue, Envelope
from vlm_eval.calls import MakerReply, load_call
from vlm_eval.connections import anthropic_api
from vlm_eval.extraction import answer_from_record, extract, numbers_not_in_reply, units_written
from vlm_eval.models_config import load_extractor
from vlm_eval.scoring import score

DRAWING = "201533-020.pdf"  # ground truth 12.700 x 215.9 x 184.2, a CUBE
RIGHT_REPLY = "Overall size: 215.9 mm [8.50 in] x 184.2 mm [7.25 in] x 12.7 mm [.500 in]."
FAKE_KEY = "sk-test-NOT-A-REAL-KEY-7f3a9c"


def _value(number, unit="", label="", other=""):
    return {"number": number, "unit": unit, "label": label, "number_in_other_unit": other}


def _form(values, shape="CUBE", no_clear_answer=False, unsure=False, reason="", extra=()):
    """One envelope, plus any others the reply gave."""
    return {
        "envelopes": [{"shape": shape, "values": values}, *extra],
        "no_clear_answer": no_clear_answer,
        "unsure": unsure,
        "reason": reason,
    }


def _envelope(values, shape):
    return {"shape": shape, "values": values}


RIGHT_FORM = _form(
    [
        _value("215.9", "mm", "Length", "8.50"),
        _value("184.2", "mm", "Width", "7.25"),
        _value("12.7", "mm", "Thickness", ".500"),
    ]
)


class FakeExtractor:
    """Stands in for the extractor's maker. Counts calls; returns a fixed form."""

    def __init__(self, form=None, text=None):
        self.text = text if text is not None else json.dumps(form)
        self.requests = []

    def send(self, request, api_key):
        self.requests.append(request)
        return MakerReply(
            model_version="claude-haiku-4-5-20251001",
            reply_text=self.text,
            stop_reason="end_turn",
            input_tokens=1_000,
            output_tokens=200,
            thinking_tokens=None,
            request_id="msg_fake",
            raw={"fake": True},
        )

    def is_transient(self, exc):
        return False


class NeverCalled:
    def send(self, request, api_key):
        raise AssertionError("a model was called")

    def is_transient(self, exc):
        return False


@pytest.fixture
def runs(tmp_path, monkeypatch):
    """Private runs folders in a temporary place, so the real runs/ is never touched."""
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    monkeypatch.setattr(paths, "CALLS", tmp_path / "calls")
    monkeypatch.setattr(paths, "EXTRACTIONS", tmp_path / "extractions")
    monkeypatch.setattr(paths, "REPLAY_PAGE", tmp_path / "replay.html")
    return tmp_path


def _save_call(reply_text=RIGHT_REPLY, model_id="fake-model", run_number=1, error=None):
    path = paths.CALLS / "test-run" / model_id / f"201533-020-run{run_number}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "run_name": "test-run",
        "run_number": run_number,
        "drawing": DRAWING,
        "model_requested": model_id,
        "model_name": "Fake Model",
        "model_version": model_id,
        "error": error,
        "reply_text": None if error else reply_text,
    }
    path.write_text(json.dumps(record))
    return path


def _extract(call_file, fake):
    return extract(call_file, connection=fake, api_key=FAKE_KEY, sleep=lambda s: None)


def _answer(record):
    """The form the scorer reads, from a saved extraction and its saved reply."""
    reply = load_call(paths.ROOT / record["call_file"])["reply_text"]
    return answer_from_record(record, reply)


# --- the whole-number check -----------------------------------------------------


@pytest.mark.parametrize(
    "reply, number, found",
    [
        ("Thickness 12.7 mm", "2.7", False),  # a piece of another number
        ("Thickness 12.7 mm", "12.70", False),  # not written that way
        ("Thickness 12.70 mm", "12.7", False),
        ("Thickness 12.7 mm", "12.7", True),
        ("Width [.750]", ".750", True),
        ("Width 0.750 in", ".750", False),
        ("Dia 5/8 in", "5/8", True),
        ("Length 1 3/8 in", "1 3/8", True),
        ("Length 1 3/8 in", "3/8", False),  # a piece of a mixed fraction
        ("Envelope 8.50 × 7.25 × 0.50 in", "7.25", True),
        ("**12.7 mm**", "12.7", True),
    ],
)
def test_numbers_must_be_whole_numbers_in_the_reply(reply, number, found):
    missing = numbers_not_in_reply(_form([_value(number)]), reply)
    assert (missing == []) is found


def test_number_not_in_reply_is_flagged_and_not_graded(runs):
    wrong = _form([_value("2.7", "mm"), _value("215.9", "mm"), _value("184.2", "mm")])
    record = _extract(_save_call("Size 12.7 x 215.9 x 184.2 mm"), FakeExtractor(wrong))
    assert record["flagged"] and "2.7" in record["flag_reason"]
    verdict = score(DRAWING, _answer(record))
    assert not verdict.scored and "2.7" in verdict.note


@pytest.mark.parametrize(
    "form",
    [
        _form([], no_clear_answer=True, reason="gives 12.7 and 15.0 for thickness"),
        _form([_value("12.7")], unsure=True, reason="table is garbled"),
    ],
)
def test_unsure_or_no_clear_answer_is_flagged_never_guessed(runs, form):
    record = _extract(_save_call("Thickness 12.7 or 15.0"), FakeExtractor(form))
    answer = _answer(record)
    assert answer.flagged and answer.flag_reason
    assert not score(DRAWING, answer).scored


def test_unreadable_extractor_answer_is_flagged(runs):
    record = _extract(_save_call(), FakeExtractor(text="not json"))
    assert record["flagged"] and record["form"] is None


# --- the form -------------------------------------------------------------------


def test_both_units_are_one_value_and_a_right_reply_passes(runs):
    record = _extract(_save_call(), FakeExtractor(RIGHT_FORM))
    answer = _answer(record)
    assert len(answer.values) == 3 and answer.values[0].number_in_other_unit == "8.50"
    verdict = score(DRAWING, answer)
    assert verdict.strict_pass and verdict.dims_correct == 3


@pytest.mark.parametrize(
    "reply, units",
    [
        ("215.9 [8.50] x 184.2 [7.25] x 12.7 [.500]", set()),
        ("215.9 mm [8.50 in]", {"mm", "in"}),
        ("| Axis | Inch | Metric |", {"in"}),
        ('8.50" x 7.25"', {"in"}),
        ("Thickness: 12.7 millimetres", {"mm"}),
        ("Shown in the plan view: 215.9 [8.50]", set()),  # "in" as an ordinary word
    ],
)
def test_units_written_in_a_reply(reply, units):
    assert units_written(reply) == units


def test_a_unit_the_reply_never_writes_is_not_used(runs):
    """A guessed unit would be trusted, so a right answer could fail as a unit mix-up."""
    guessed = _form([_value("215.9", "in"), _value("184.2", "in"), _value("12.7", "in")])
    record = _extract(_save_call("Size 215.9 x 184.2 x 12.7"), FakeExtractor(guessed))
    answer = _answer(record)
    assert [v.unit for v in answer.values] == ["", "", ""]
    assert score(DRAWING, answer).strict_pass


def test_a_unit_the_reply_writes_is_kept_even_when_wrong(runs):
    stated = _form([_value("8.50", "mm"), _value("7.25", "mm"), _value(".500", "mm")])
    record = _extract(_save_call("Size 8.50 x 7.25 x .500 mm"), FakeExtractor(stated))
    verdict = score(DRAWING, _answer(record))
    assert not verdict.strict_pass and "Unit mix-up" in verdict.problems


# --- more than one envelope in a reply (SPEC 2.5) --------------------------------------

CYL_DRAWING = "201011.pdf"  # ground truth Dia 8.000, L 90.0
BOX_AND_CYLINDER = (
    "Bounding box 8.000 x 8.000 x 90.0 mm. Cylindrical envelope Ø8.000 x 90.0 mm long."
)


def test_the_envelope_matching_the_part_is_the_one_graded(runs):
    form = _form(
        [
            _value("8.000", "mm", "width"),
            _value("8.000", "mm", "height"),
            _value("90.0", "mm", "length"),
        ],
        "CUBE",
        extra=[_envelope([_value("8.000", "mm", "Ø"), _value("90.0", "mm", "long")], "CYL")],
    )
    record = _extract(_save_call(BOX_AND_CYLINDER), FakeExtractor(form))
    answer = _answer(record)
    assert answer.shape == "CUBE" and len(answer.other_envelopes) == 1
    verdict = score(CYL_DRAWING, answer)
    assert verdict.strict_pass and verdict.dims_correct == 2
    assert verdict.ignored_envelopes and "CUBE" in verdict.ignored_envelopes[0]


def test_a_box_that_the_cylinder_fills_is_correct(runs):
    """No shape was asked for, so 8.000 x 8.000 x 90.0 is the same envelope as Ø8.000 x 90.0."""
    form = _form(
        [
            _value("8.000", "mm", "width"),
            _value("8.000", "mm", "height"),
            _value("90.0", "mm", "length"),
        ],
        "CUBE",
    )
    record = _extract(_save_call("Bounding box 8.000 x 8.000 x 90.0 mm."), FakeExtractor(form))
    verdict = score(CYL_DRAWING, _answer(record))
    assert verdict.strict_pass and verdict.note


def test_a_box_that_is_too_small_for_the_cylinder_fails(runs):
    """A box narrower than the diameter could not contain the part."""
    form = _form(
        [
            _value("6.000", "mm", "width"),
            _value("8.000", "mm", "height"),
            _value("90.0", "mm", "length"),
        ],
        "CUBE",
    )
    record = _extract(_save_call("Bounding box 6.000 x 8.000 x 90.0 mm."), FakeExtractor(form))
    verdict = score(CYL_DRAWING, _answer(record))
    assert verdict.scored and not verdict.strict_pass


def test_a_cube_answered_only_as_a_cylinder_still_fails(runs):
    form = _form([_value("215.9", "mm", "Ø"), _value("184.2", "mm", "long")], "CYL")
    record = _extract(
        _save_call("Cylindrical envelope Ø215.9 x 184.2 mm long"), FakeExtractor(form)
    )
    verdict = score(DRAWING, _answer(record))  # 201533-020 is a CUBE with 3 sizes
    assert verdict.scored and not verdict.strict_pass


def test_every_envelope_is_checked_against_the_reply(runs):
    """A number invented in a second envelope is caught like any other."""
    form = _form(
        [_value("8.000", "mm", "Ø"), _value("90.0", "mm", "long")],
        "CYL",
        extra=[_envelope([_value("8.000", "mm"), _value("99.9", "mm")], "CUBE")],
    )
    record = _extract(_save_call("Cylindrical envelope Ø8.000 x 90.0 mm long"), FakeExtractor(form))
    assert record["flagged"] and "99.9" in record["flag_reason"]


def test_a_version_bump_reads_each_reply_once_more(runs):
    """The form changed in version 2, so a version 1 extraction is replaced, once."""
    call_file = _save_call(BOX_AND_CYLINDER)
    first = _extract(call_file, FakeExtractor(_form([_value("8.000", "mm", "Ø")], "CYL")))
    assert first["extraction_version"] == extraction.EXTRACTION_VERSION

    old = dict(first, extraction_version=1)
    extraction.extraction_path(call_file).write_text(json.dumps(old))
    again = _extract(call_file, FakeExtractor(_form([_value("90.0", "mm", "long")], "CYL")))
    assert again["extraction_version"] == extraction.EXTRACTION_VERSION
    assert again["form"] != old["form"]  # it really was read again
    third = _extract(call_file, NeverCalled())  # and only once
    assert third["form"] == again["form"]


def test_a_version_one_form_can_still_be_read(runs):
    """Saved version 1 forms keep working: one envelope, shape and values at the top."""
    form = {
        "shape": "CYL",
        "values": [_value("8.000", "mm", "Ø"), _value("90.0", "mm", "long")],
        "no_clear_answer": False,
        "unsure": False,
        "reason": "",
    }
    assert extraction.form_envelopes(form) == [{"shape": "CYL", "values": form["values"]}]
    assert len(extraction.form_values(form)) == 2


def test_refusal_is_a_fail_not_a_flag(runs):
    record = _extract(_save_call("I can't help with that."), FakeExtractor(_form([], shape="")))
    verdict = score(DRAWING, _answer(record))
    assert not record["flagged"]
    assert verdict.scored and not verdict.strict_pass and verdict.dims_correct == 0


def test_request_is_the_reply_text_only(runs):
    fake = FakeExtractor(RIGHT_FORM)
    record = _extract(_save_call(), fake)
    request = fake.requests[0]
    text = json.dumps(request)
    assert request["model"] == load_extractor().id == "claude-haiku-4-5-20251001"
    assert RIGHT_REPLY in text
    assert '"document"' not in text and "application/pdf" not in text
    assert FAKE_KEY not in json.dumps(record)


def test_reply_hash_mismatch_is_an_error_not_a_redo(runs):
    call_file = _save_call()
    _extract(call_file, FakeExtractor(RIGHT_FORM))
    _save_call("A different reply 1.0 x 2.0 x 3.0 mm")
    with pytest.raises(extraction.ExtractionError):
        _extract(call_file, NeverCalled())


def test_no_reply_is_not_extracted(runs):
    with pytest.raises(ValueError):
        _extract(_save_call(error="APIConnectionError: lost"), NeverCalled())


# --- saved once, reused; replay makes no calls ------------------------------------


def test_extraction_is_saved_once_and_reused(runs):
    call_file = _save_call()
    first = _extract(call_file, FakeExtractor(RIGHT_FORM))
    again = _extract(call_file, NeverCalled())
    assert again == json.loads(json.dumps(first, default=str))
    assert _answer(again) == _answer(first)
    assert extraction.waiting() == []


def test_replay_calls_no_model_and_repeats_exactly(runs, monkeypatch):
    _extract(_save_call(model_id="model-a"), FakeExtractor(RIGHT_FORM))
    wrong = _form([_value("999.9", "mm"), _value("888.8", "mm"), _value("777.7", "mm")])
    _extract(_save_call("Size 999.9 x 888.8 x 777.7 mm", model_id="model-b"), FakeExtractor(wrong))
    _save_call(model_id="model-c")  # not extracted yet
    _save_call(model_id="model-d", error="APIConnectionError: lost")

    def no_calls(*args, **kwargs):
        raise AssertionError("replay called a model")

    monkeypatch.setattr(anthropic_api, "send", no_calls)
    monkeypatch.setattr(extraction, "send_with_retries", no_calls)

    first = replay.summary(replay.replay())
    replay.write_page(replay.replay())
    assert first == replay.summary(replay.replay())
    lines = first.splitlines()
    assert "model-a" in lines[0] and "PASS, 3 of 3" in lines[0]
    assert "model-b" in lines[1] and "FAIL, 0 of 3" in lines[1]
    assert replay.NOT_EXTRACTED in lines[2]
    assert replay.NO_REPLY in lines[3]
    assert "spent $0" in paths.REPLAY_PAGE.read_text()


def test_three_sizes_are_judged_as_a_box_whatever_the_extractor_called_them(runs):
    """201581-008: Opus gave the box 109.8 x 9.525 x 9.525, which is that cylinder's box."""
    box = _form(
        [
            _value("109.8", "mm", "Length (X)"),
            _value("9.525", "mm", "Width (Y)"),
            _value("9.525", "mm", "Height (Z)"),
        ],
        "CYL",  # the extractor's label; code reads three sizes as a box
    )
    reply = "Bounding box 109.8 mm L x 9.525 mm W x 9.525 mm H. Part is a round shank."
    record = _extract(_save_call(reply), FakeExtractor(box))
    verdict = score("201581-008.pdf", _answer(record))  # ground truth Dia 9.525, L 109.8
    assert verdict.strict_pass and verdict.dims_correct == 3


@pytest.mark.parametrize(
    "values, shape",
    [
        ([_value("8.000", "mm", "Ø"), _value("90.0", "mm", "long")], "CYL"),
        ([_value("8.000", "mm", "diameter"), _value("90.0", "mm", "length")], "CYL"),
        ([_value("8.000", "mm", "OD"), _value("90.0", "mm", "thickness")], "CYL"),
        ([_value("8.000", "mm"), _value("90.0", "mm")], ""),  # nothing says diameter
        ([_value("1", "mm"), _value("2", "mm"), _value("3", "mm")], "CUBE"),
    ],
)
def test_shape_comes_from_the_sizes_and_labels(values, shape):
    envelope = Envelope(tuple(AnswerValue(**v) for v in values))
    assert envelope.shape_from_values == shape
