"""Checks on run plans and the runner (SPEC 2.7, 2.8, Chunk 6). No API calls: makers are faked.

What matters: a run sends nothing until it is approved; it stops cleanly when
asked and resumes without sending anything twice; it pauses when spending passes
the approval by 25%; results add up across plans without redoing calls; test runs
stay separate from real ones; and "actual cost" counts only the plan's own calls.
"""

from __future__ import annotations

import json

import pytest

from vlm_eval import extraction, paths, replay, run_plan, runner
from vlm_eval.calls import PROMPT, MakerReply, cost_usd, model_folder
from vlm_eval.models_config import load_extractor
from vlm_eval.run_plan import (
    DONE,
    PAUSED,
    STOPPED,
    TEST_DRAWINGS,
    PlanError,
    approve,
    drawings_for,
    make_plan,
)

OPUS, GPT = "claude-opus-5", "gpt-5.6-sol"
REPLY = "Overall size 10.0 x 20.0 x 30.0 mm"  # made up, clearly wrong for every drawing


def _form(numbers):
    return {
        "envelopes": [
            {
                "shape": "CUBE",
                "values": [
                    {"number": n, "unit": "mm", "label": "", "number_in_other_unit": ""}
                    for n in numbers
                ],
            }
        ],
        "no_clear_answer": False,
        "unsure": False,
        "reason": "",
    }


FORM = _form(("10.0", "20.0", "30.0"))


def _reply(text, model="fake"):
    return MakerReply(
        model_version=model,
        reply_text=text,
        stop_reason="end_turn",
        input_tokens=1_000,
        output_tokens=1_000,
        thinking_tokens=None,
        request_id="fake",
        raw={},
    )


class FakeMaker:
    """Stands in for a maker. Records every drawing sent; can run a hook after each call."""

    def __init__(self, after_send=None):
        self.sent = []
        self.after_send = after_send

    def build_request(self, pdf_bytes, filename, model, prompt=PROMPT):
        return {"model": model.id, "file": filename}

    def send(self, request, api_key):
        self.sent.append(request["file"])
        if self.after_send:
            self.after_send(len(self.sent))
        return _reply(REPLY, request["model"])

    def is_transient(self, exc):
        return False


class FakeExtractor:
    def send(self, request, api_key):
        return _reply(json.dumps(FORM), "claude-haiku-4-5-20251001")

    def is_transient(self, exc):
        return False


@pytest.fixture
def runs(tmp_path, monkeypatch):
    """Private runs folders in a temporary place, so the real runs/ is never touched."""
    for name, sub in [
        ("CALLS", "calls"),
        ("EXTRACTIONS", "extractions"),
        ("PLANS", "plans"),
        ("STOP_FILE", "STOP"),
        ("REPLAY_PAGE", "replay.html"),
    ]:
        monkeypatch.setattr(paths, name, tmp_path / sub)
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    return tmp_path


def _run(plan, makers):
    return runner.run(
        plan.name, connections=makers, extract_connection=FakeExtractor(), sleep=lambda s: None
    )


# --- what a plan covers -------------------------------------------------------------


def test_sets_are_nested_and_test_runs_are_separate(runs):
    s30, s60, s141 = (set(drawings_for(n)) for n in ("30", "60", "141"))
    assert (len(s30), len(s60), len(s141)) == (30, 60, 141)
    assert s30 < s60 < s141
    test = make_plan([OPUS], "test", runs=1, prompt_id="bare")
    assert tuple(test.drawings) == TEST_DRAWINGS and set(TEST_DRAWINGS) <= s30
    assert test.test_run and test.calls_folder == "test"
    real = make_plan([OPUS], "30", runs=1, prompt_id="bare")
    assert not real.test_run and real.calls_folder == "main"


def test_a_thinking_level_gets_its_own_folder_and_xai_is_refused(runs):
    plan = make_plan([OPUS, GPT], "test", runs=1, thinking={OPUS: "low"})
    folders = {model_folder(m) for m in run_plan.plan_models(plan)}
    assert folders == {"claude-opus-5-thinking-low", "gpt-5.6-sol"}
    with pytest.raises(PlanError):
        make_plan(["grok-4.5"], "test", runs=1)
    with pytest.raises(PlanError):
        make_plan([OPUS], "test", runs=1, thinking={OPUS: "not-a-level"})


def test_each_prompt_keeps_its_own_calls(runs):
    """Answers to two different questions never mix, and neither counts for the other."""
    bare = make_plan([OPUS], "test", runs=1, prompt_id="bare")
    shaped = make_plan([OPUS], "test", runs=1, prompt_id="stock-shape")
    assert bare.calls_folder == "test" and shaped.calls_folder == "test-stock-shape"
    assert bare.prompt != shaped.prompt and shaped.prompt.startswith("Return bounding")

    maker = FakeMaker()
    approve(bare.name)
    _run(bare, {"anthropic": maker})
    assert len(maker.sent) == len(TEST_DRAWINGS)

    # The same drawings, asked the other way, are still to do.
    assert len(run_plan.todo(run_plan.load(shaped.name))) == len(TEST_DRAWINGS)
    shaped_maker = FakeMaker()
    approve(shaped.name)
    _run(shaped, {"anthropic": shaped_maker})
    assert len(shaped_maker.sent) == len(TEST_DRAWINGS)
    sent_prompts = {extraction.load_call(f)["prompt"] for f in paths.CALLS.glob("*/*/*.json")}
    assert sent_prompts == {bare.prompt or PROMPT, shaped.prompt}


# --- approval, stop, resume, pause ------------------------------------------------------


def test_nothing_is_sent_without_approval(runs):
    maker = FakeMaker()
    plan = make_plan([OPUS], "test", runs=1)
    _run(plan, {"anthropic": maker})
    assert maker.sent == []


def test_a_full_run_sends_each_call_once_and_finishes(runs):
    maker = FakeMaker()
    plan = make_plan([OPUS], "test", runs=2)
    approve(plan.name)
    assert _run(plan, {"anthropic": maker}) == DONE
    assert sorted(maker.sent) == sorted(TEST_DRAWINGS * 2)
    assert run_plan.todo(run_plan.load(plan.name)) == []
    page = paths.REPLAY_PAGE.read_text()
    assert "TEST RUN" in page and "Estimated $" in page and "Actual $" in page


def test_stop_then_resume_sends_nothing_twice(runs):
    stop_after_two = FakeMaker(after_send=lambda n: n == 2 and runner.request_stop())
    plan = make_plan([OPUS], "test", runs=1)
    approve(plan.name)
    assert _run(plan, {"anthropic": stop_after_two}) == STOPPED
    assert len(stop_after_two.sent) == 2  # the call under way finished; no new one started

    rest = FakeMaker()
    assert _run(plan, {"anthropic": rest}) == DONE
    assert sorted(stop_after_two.sent + rest.sent) == sorted(TEST_DRAWINGS)


def test_spending_past_the_approval_pauses_until_approved_again(runs):
    maker = FakeMaker()
    plan = make_plan([OPUS], "test", runs=1)
    approve(plan.name)
    tiny = run_plan.load(plan.name)
    tiny.approvals[-1]["approved_usd"] = "0.000001"  # any real call goes past it
    run_plan.save(tiny)

    assert _run(plan, {"anthropic": maker}) == PAUSED
    assert len(maker.sent) == 1
    assert _run(plan, {"anthropic": maker}) == PAUSED  # still paused: no new approval
    assert len(maker.sent) == 1

    approve(plan.name)
    assert _run(plan, {"anthropic": maker}) == DONE
    assert sorted(maker.sent) == sorted(TEST_DRAWINGS)


# --- adding up across plans, and money ----------------------------------------------------


def test_results_add_up_across_plans_without_redoing_calls(runs):
    first_opus = FakeMaker()
    first = make_plan([OPUS], "test", runs=1)
    approve(first.name)
    _run(first, {"anthropic": first_opus})

    opus, gpt = FakeMaker(), FakeMaker()
    both = make_plan([OPUS, GPT], "test", runs=1)
    approve(both.name)
    assert _run(both, {"anthropic": opus, "openai": gpt}) == DONE
    assert opus.sent == [] and sorted(gpt.sent) == sorted(TEST_DRAWINGS)

    # The second plan's actual cost is only the GPT calls it sent and their extractions.
    gpt_model = next(m for m in run_plan.plan_models(both) if m.id == GPT)
    per_gpt_call = cost_usd(gpt_model, 1_000, 1_000)
    per_extraction = cost_usd(load_extractor(), 1_000, 1_000)
    expected = len(TEST_DRAWINGS) * (per_gpt_call + per_extraction)
    assert run_plan.spent(run_plan.load(both.name)) == expected


def test_actual_cost_counts_only_the_plans_own_calls(runs):
    first = make_plan([OPUS], "test", runs=1)
    approve(first.name)
    _run(first, {"anthropic": FakeMaker()})
    spent_first = run_plan.spent(run_plan.load(first.name))
    assert spent_first > 0

    again = make_plan([OPUS], "test", runs=1)  # everything already saved by `first`
    assert run_plan.todo(again) == []
    assert run_plan.spent(again) == 0


def test_estimate_uses_saved_calls_when_there_are_some(runs):
    plan = make_plan([OPUS], "test", runs=1)
    model = run_plan.plan_models(plan)[0]
    _, basis = run_plan.per_call_estimate(model)
    assert basis.startswith("rough guess")

    approve(plan.name)
    _run(plan, {"anthropic": FakeMaker()})
    per_call, basis = run_plan.per_call_estimate(model)
    assert basis == "average of 5 saved calls"
    assert per_call == (1_000 * model.input_price + 1_000 * model.output_price) / 1_000_000


# --- adding the results up (Chunk 7) --------------------------------------------------

RIGHT_FOR_201533_020 = "Overall size 12.700 x 215.9 x 184.2 mm"  # Garron's numbers for it


class CorrectMaker(FakeMaker):
    """Answers every drawing with 201533-020's sizes, so it passes that one and fails others."""

    def send(self, request, api_key):
        self.sent.append(request["file"])
        return _reply(RIGHT_FOR_201533_020, request["model"])


class CopyingExtractor:
    """Copies whichever numbers the reply held, the way the real extractor would."""

    def send(self, request, api_key):
        reply = request["messages"][0]["content"]
        numbers = ("12.700", "215.9", "184.2") if "12.700" in reply else ("10.0", "20.0", "30.0")
        return _reply(json.dumps(_form(numbers)), "claude-haiku-4-5-20251001")

    def is_transient(self, exc):
        return False


def test_summaries_match_the_replies_they_count(runs):
    """Two drawings, two models, two runs each: one model right on one drawing, one never right."""
    plan = make_plan([OPUS, GPT], "test", runs=2, test_count=2)
    assert plan.drawings == ["201533-020.pdf", "201548-030.pdf"]  # a CUBE and a cylinder
    approve(plan.name)
    correct, wrong = CorrectMaker(), FakeMaker()
    runner.run(
        plan.name,
        connections={"anthropic": correct, "openai": wrong},
        extract_connection=CopyingExtractor(),
        sleep=lambda s: None,
    )
    rows = replay.replay(plan.name)

    tallies = {t.model: t for t in replay.by_model(rows)}
    assert tallies["Claude Opus 5"].replies == 4  # 2 drawings x 2 runs
    assert sum(t.calls for t in tallies.values()) == len(rows)
    assert sum(t.passed for t in tallies.values()) == sum(
        1 for r in rows if r.verdict and r.verdict.strict_pass
    )
    assert sum(t.sizes_found for t in tallies.values()) == sum(
        r.verdict.dims_correct for r in rows if r.verdict and r.verdict.scored
    )
    assert tallies["Claude Opus 5"].passed == 2 and tallies["Claude Opus 5"].pass_rate == "50%"
    assert tallies["GPT-5.6 Sol"].passed == 0 and tallies["GPT-5.6 Sol"].pass_rate == "0%"

    per_drawing = replay.by_drawing(rows)
    assert per_drawing["201533-020"]["Claude Opus 5"] == (2, 2)
    assert per_drawing["201548-030"]["Claude Opus 5"] == (0, 2)
    assert per_drawing["201533-020"]["GPT-5.6 Sol"] == (0, 2)

    agreed = {c.model: c for c in replay.consistency(rows)}
    assert (agreed["Claude Opus 5"].all_pass, agreed["Claude Opus 5"].all_fail) == (1, 1)
    assert agreed["Claude Opus 5"].mixed == 0 and agreed["Claude Opus 5"].rate == "100%"
    assert agreed["GPT-5.6 Sol"].all_fail == 2

    page = paths.REPLAY_PAGE.read_text()
    assert "By model" in page and "Runs passed, per drawing" in page and "2 of 2" in page


def test_a_model_that_answers_differently_each_run_shows_as_mixed(runs):
    """Consistency counts a drawing as mixed when the runs disagree."""
    replies = iter([RIGHT_FOR_201533_020, "Overall size 10.0 x 20.0 x 30.0 mm"])

    class Flaky(FakeMaker):
        def send(self, request, api_key):
            self.sent.append(request["file"])
            return _reply(next(replies), request["model"])

    plan = make_plan([OPUS], "test", runs=2, test_count=1)
    approve(plan.name)
    runner.run(
        plan.name,
        connections={"anthropic": Flaky()},
        extract_connection=CopyingExtractor(),
        sleep=lambda s: None,
    )
    rows = replay.replay(plan.name)
    assert replay.by_drawing(rows)["201533-020"]["Claude Opus 5"] == (1, 2)
    only = replay.consistency(rows)[0]
    assert (only.all_pass, only.all_fail, only.mixed, only.rate) == (0, 0, 1, "0%")


def test_calls_not_sent_yet_are_left_out_of_the_per_drawing_counts(runs):
    plan = make_plan([OPUS], "test", runs=1)
    rows = replay.replay(plan.name)  # nothing sent
    assert all(r.status == replay.NOT_SENT for r in rows)
    assert replay.by_drawing(rows) == {} and replay.consistency(rows) == []
    tally = replay.by_model(rows)[0]
    assert tally.not_sent == len(TEST_DRAWINGS) and tally.replies == 0
    assert tally.pass_rate == "-"
