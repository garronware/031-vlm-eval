"""Checks on the model connections (SPEC 2.1, 2.7). No API calls: every maker is faked.

What matters: each model gets exactly the fixed prompt and the PDF unchanged, with
nothing else added; every call is saved in full without the key; and a reply that
arrived is never asked for again.
"""

from __future__ import annotations

import base64
import json
from decimal import Decimal

import anthropic
import httpx
import httpx2
import openai
import pytest
from google.genai import errors as google_errors

from vlm_eval import calls, paths
from vlm_eval.calls import PROMPT, MakerReply, is_done, send_drawing
from vlm_eval.connections import anthropic_api, connection_for, google_api, openai_api
from vlm_eval.models_config import MAKER_DEFAULT, load_models

DRAWING = "201533-020.pdf"
PDF = (paths.DRAWINGS / DRAWING).read_bytes()
MODELS = {m.id: m for m in load_models()}
FAKE_KEY = "sk-test-NOT-A-REAL-KEY-7f3a9c"

# Settings that would change what the model sees or which model answers.
FORBIDDEN_KEYS = {
    "system",
    "instructions",
    "system_instruction",
    "temperature",
    "top_p",
    "top_k",
    "fallbacks",
    "tools",
}

CONNECTIONS = {
    "claude-opus-5": anthropic_api,
    "gpt-5.6-sol": openai_api,
    "gemini-3.1-pro-preview": google_api,
}


def _walk(value):
    """Every (key, value) pair anywhere in a nested request."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(value, list | tuple):
        for v in value:
            yield from _walk(v)


def _pdf_sent(request) -> bytes:
    for k, v in _walk(request):
        if k == "data" and isinstance(v, bytes):  # Google: raw bytes
            return v
        if k == "data" and isinstance(v, str):  # Anthropic: base64
            return base64.b64decode(v)
        if k == "file_data":  # OpenAI: data URL
            return base64.b64decode(v.split(",", 1)[1])
    raise AssertionError("no PDF in request")


# --- config -------------------------------------------------------------------------


def test_switched_on_models_are_ready_to_run():
    on = [m for m in MODELS.values() if m.enabled]
    assert on, "no model is switched on"
    for m in on:
        assert m.input_price > 0 and m.output_price > 0, m.id
        assert m.thinking == MAKER_DEFAULT or m.thinking in m.levels, m.id
        connection_for(m.maker)  # raises if no connection is built


def test_grok_is_off():
    assert not any(m.enabled for m in MODELS.values() if m.maker == "xai")


# --- what each maker is sent ----------------------------------------------------------


@pytest.mark.parametrize("model_id", CONNECTIONS)
def test_request_is_the_pdf_unchanged_and_the_prompt_only(model_id):
    request = CONNECTIONS[model_id].build_request(PDF, DRAWING, MODELS[model_id])
    texts = [v for k, v in _walk(request) if k == "text"]
    assert texts == [PROMPT]
    assert _pdf_sent(request) == PDF
    assert not FORBIDDEN_KEYS & {k for k, _ in _walk(request)}
    assert request["model"] == model_id


@pytest.mark.parametrize("model_id", CONNECTIONS)
def test_maker_default_thinking_sends_no_thinking_setting(model_id):
    request = CONNECTIONS[model_id].build_request(PDF, DRAWING, MODELS[model_id])
    keys = {k for k, _ in _walk(request)}
    assert not keys & {"output_config", "reasoning", "config", "thinking"}


# --- saving a call ----------------------------------------------------------------------


class FakeConnection:
    """Answers from a script: an exception to raise, or a reply to return."""

    def __init__(self, *script, transient=(ConnectionError,)):
        self.script = list(script)
        self.transient = transient
        self.sent = 0

    def build_request(self, pdf_bytes, filename, model, prompt=PROMPT):
        data = base64.standard_b64encode(pdf_bytes).decode()
        return {"model": model.id, "pdf": data, "raw_pdf": pdf_bytes, "text": PROMPT}

    def send(self, request, api_key):
        self.sent += 1
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    def is_transient(self, exc):
        return isinstance(exc, self.transient)


def _reply(stop_reason="end_turn", text="10 x 20 x 30 mm"):
    return MakerReply(
        model_version="claude-opus-5",
        reply_text=text,
        stop_reason=stop_reason,
        input_tokens=4_000,
        output_tokens=6_000,
        thinking_tokens=5_000,
        request_id="msg_test",
        raw={"id": "msg_test", "content": [{"type": "text", "text": text}]},
    )


@pytest.fixture
def calls_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "CALLS", tmp_path)
    return tmp_path


def _send(connection):
    model = MODELS["claude-opus-5"]
    return send_drawing(
        model, DRAWING, "test", 1, connection=connection, api_key=FAKE_KEY, sleep=lambda s: None
    )


def test_saved_call_has_everything_and_no_key_or_pdf(calls_dir):
    _send(FakeConnection(_reply()))
    path = calls.call_path("test", "claude-opus-5", DRAWING, 1)
    text = path.read_text()
    saved = json.loads(text)
    for field in (
        "drawing",
        "drawing_sha256",
        "model_requested",
        "model_version",
        "prompt",
        "request",
        "reply_text",
        "stop_reason",
        "input_tokens",
        "output_tokens",
        "thinking_tokens",
        "request_id",
        "cost_usd",
        "started_at",
        "seconds",
        "raw",
    ):
        assert field in saved, field
    assert saved["prompt"] == PROMPT
    assert FAKE_KEY not in text
    assert base64.standard_b64encode(PDF).decode() not in text
    assert is_done(path)


def test_cost_is_tokens_times_config_price(calls_dir):
    saved = _send(FakeConnection(_reply()))
    model = MODELS["claude-opus-5"]
    expected = (4_000 * model.input_price + 6_000 * model.output_price) / 1_000_000
    assert Decimal(saved["cost_usd"]) == expected


def test_lost_connection_is_retried(calls_dir):
    fake = FakeConnection(ConnectionError("reset"), ConnectionError("reset"), _reply())
    saved = _send(fake)
    assert fake.sent == 3 and saved["attempts"] == 3
    assert saved["error"] is None and saved["reply_text"]


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_reply_that_arrived_is_never_asked_again(calls_dir, stop_reason):
    fake = FakeConnection(_reply(stop_reason, text=""), _reply())
    saved = _send(fake)
    assert fake.sent == 1
    assert saved["stop_reason"] == stop_reason


def test_rejected_request_is_saved_as_failed_not_retried(calls_dir):
    fake = FakeConnection(ValueError("400 bad request"), _reply())
    saved = _send(fake)
    assert fake.sent == 1
    assert saved["error"] and not is_done(calls.call_path("test", "claude-opus-5", DRAWING, 1))


# --- each maker's retry rule ----------------------------------------------------------


def _anthropic(cls, status):
    request = httpx2.Request("POST", "https://x")
    return cls("x", response=httpx2.Response(status, request=request), body=None)


def _openai(cls, status):
    request = httpx.Request("POST", "https://x")
    return cls("x", response=httpx.Response(status, request=request), body=None)


@pytest.mark.parametrize(
    "connection, exc, transient",
    [
        (anthropic_api, anthropic.APIConnectionError(request=httpx2.Request("GET", "x:")), True),
        (anthropic_api, _anthropic(anthropic.RateLimitError, 429), True),
        (anthropic_api, _anthropic(anthropic.BadRequestError, 400), False),
        (openai_api, openai.APIConnectionError(request=httpx.Request("GET", "x:")), True),
        (openai_api, _openai(openai.InternalServerError, 503), True),
        (openai_api, _openai(openai.BadRequestError, 400), False),
        (google_api, httpx.ConnectError("x"), True),
        (google_api, google_errors.ServerError(503, {"error": {"message": "x"}}), True),
        (google_api, google_errors.ClientError(400, {"error": {"message": "x"}}), False),
    ],
)  # fmt: skip
def test_only_calls_with_no_reply_are_retried(connection, exc, transient):
    assert connection.is_transient(exc) is transient
