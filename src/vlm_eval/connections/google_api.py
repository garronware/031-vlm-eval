"""Google: the PDF goes in as an inline `application/pdf` part.

Gemini reads each page as an image plus its text.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from google import genai
from google.genai import errors, types

from vlm_eval.calls import PROMPT, MakerReply
from vlm_eval.models_config import MAKER_DEFAULT, Model

TIMEOUT_MS = 1_800_000

# The SDK warns about "automatic function calling" on every first call. No tools
# are sent, so it never happens; the warning is noise.
logging.getLogger("google_genai.models").setLevel(logging.ERROR)


def build_request(
    pdf_bytes: bytes, filename: str, model: Model, prompt: str = PROMPT
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "model": model.id,
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"inline_data": {"mime_type": "application/pdf", "data": pdf_bytes}},
                    {"text": prompt},
                ],
            }
        ],
    }
    if model.thinking != MAKER_DEFAULT:
        request["config"] = {"thinking_config": {"thinking_level": model.thinking}}
    return request


def _client(api_key: str) -> genai.Client:
    # No retry_options: the SDK then tries once, and calls.py decides about retrying.
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))


def send(request: dict[str, Any], api_key: str) -> MakerReply:
    client = _client(api_key)  # held in a variable: the SDK closes a client once it's discarded
    response = client.models.generate_content(**request)
    candidate = response.candidates[0] if response.candidates else None
    parts = candidate.content.parts if candidate and candidate.content else None
    usage = response.usage_metadata
    thinking = (usage.thoughts_token_count or 0) if usage else 0
    answer = (usage.candidates_token_count or 0) if usage else 0
    return MakerReply(
        model_version=response.model_version or "",
        reply_text="".join(p.text for p in parts or [] if p.text and not p.thought),
        stop_reason=str(candidate.finish_reason.value)
        if candidate and candidate.finish_reason
        else "",
        input_tokens=(usage.prompt_token_count or 0) if usage else 0,
        # Gemini counts thinking separately from the answer; both are billed as output.
        output_tokens=answer + thinking,
        thinking_tokens=thinking,
        request_id=response.response_id or "",
        raw=response.model_dump(mode="json", exclude_none=True),
    )


def is_transient(exc: Exception) -> bool:
    if isinstance(exc, httpx.TransportError):  # lost connection or timeout
        return True
    if isinstance(exc, errors.APIError):
        return exc.code in (408, 429) or exc.code >= 500
    return False


def list_model_ids(api_key: str) -> set[str]:
    client = _client(api_key)  # the list is fetched page by page, so keep the client open
    return {m.name.removeprefix("models/") for m in client.models.list() if m.name}
