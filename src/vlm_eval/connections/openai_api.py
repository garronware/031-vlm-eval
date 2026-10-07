"""OpenAI: the PDF goes in an `input_file` part (Responses API).

The model gets each page's image and its text.
"""

from __future__ import annotations

import base64
from typing import Any

import openai

from vlm_eval.calls import PROMPT, MakerReply
from vlm_eval.models_config import MAKER_DEFAULT, Model

TIMEOUT_SECONDS = 1800


def build_request(
    pdf_bytes: bytes, filename: str, model: Model, prompt: str = PROMPT
) -> dict[str, Any]:
    data = base64.standard_b64encode(pdf_bytes).decode()
    request: dict[str, Any] = {
        "model": model.id,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "filename": filename,
                        "file_data": f"data:application/pdf;base64,{data}",
                    },
                    {"type": "input_text", "text": prompt},
                ],
            }
        ],
    }
    if model.thinking != MAKER_DEFAULT:
        request["reasoning"] = {"effort": model.thinking}
    return request


def _client(api_key: str) -> openai.OpenAI:
    return openai.OpenAI(api_key=api_key, max_retries=0, timeout=TIMEOUT_SECONDS)


def send(request: dict[str, Any], api_key: str) -> MakerReply:
    client = _client(api_key)
    response = client.responses.create(**request)
    usage = response.usage
    stop_reason = response.status or ""
    if response.incomplete_details and response.incomplete_details.reason:
        stop_reason += f": {response.incomplete_details.reason}"
    return MakerReply(
        model_version=response.model,
        reply_text=response.output_text,
        stop_reason=stop_reason,
        input_tokens=usage.input_tokens if usage else 0,
        output_tokens=usage.output_tokens if usage else 0,
        thinking_tokens=usage.output_tokens_details.reasoning_tokens if usage else None,
        request_id=response._request_id or response.id,
        raw=response.to_dict(),
    )


def is_transient(exc: Exception) -> bool:
    if isinstance(exc, openai.APIConnectionError):  # includes timeouts
        return True
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code in (408, 409, 429) or exc.status_code >= 500
    return False


def list_model_ids(api_key: str) -> set[str]:
    client = _client(api_key)
    return {m.id for m in client.models.list()}
