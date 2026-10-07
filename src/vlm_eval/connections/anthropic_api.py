"""Anthropic: the PDF goes in a `document` block.

Claude reads each page as an image plus its text.
"""

from __future__ import annotations

import base64
from typing import Any

import anthropic

from vlm_eval.calls import PROMPT, MakerReply
from vlm_eval.models_config import MAKER_DEFAULT, Model

# Room for thinking plus the answer, so a reply is never cut off. Streaming is
# needed for a limit this large; it doesn't change what the model sees.
MAX_TOKENS = 64_000
TIMEOUT_SECONDS = 1800


def build_request(
    pdf_bytes: bytes, filename: str, model: Model, prompt: str = PROMPT
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "model": model.id,
        "max_tokens": MAX_TOKENS,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": base64.standard_b64encode(pdf_bytes).decode(),
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    if model.thinking != MAKER_DEFAULT:
        request["output_config"] = {"effort": model.thinking}
    return request


def _client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key, max_retries=0, timeout=TIMEOUT_SECONDS)


def send(request: dict[str, Any], api_key: str) -> MakerReply:
    client = _client(api_key)
    with client.messages.stream(**request) as stream:
        message = stream.get_final_message()
    usage = message.usage
    details = usage.output_tokens_details
    return MakerReply(
        model_version=message.model,
        reply_text="".join(b.text for b in message.content if b.type == "text"),
        stop_reason=message.stop_reason or "",
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        thinking_tokens=details.thinking_tokens if details else None,
        request_id=message.id,
        raw=message.to_dict(),
    )


def is_transient(exc: Exception) -> bool:
    if isinstance(exc, anthropic.APIConnectionError):  # includes timeouts
        return True
    if isinstance(exc, anthropic.APIStatusError):
        return exc.status_code in (408, 409, 429) or exc.status_code >= 500
    return False


def list_model_ids(api_key: str) -> set[str]:
    client = _client(api_key)
    return {m.id for m in client.models.list()}
