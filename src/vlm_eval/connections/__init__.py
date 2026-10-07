"""One connection per maker. Each sends the PDF as-is with the fixed prompt.

Every connection module provides the same four things:
  build_request(pdf_bytes, filename, model) -> dict   exactly what is sent, minus the key
  send(request, api_key) -> MakerReply                  one call, the SDK's own retries off
  is_transient(exc) -> bool                             True only when no reply came back
  list_model_ids(api_key) -> set[str]                   the maker's free list of live models
"""

from __future__ import annotations

from types import ModuleType


def connection_for(maker: str) -> ModuleType:
    if maker == "anthropic":
        from vlm_eval.connections import anthropic_api as connection
    elif maker == "openai":
        from vlm_eval.connections import openai_api as connection
    elif maker == "google":
        from vlm_eval.connections import google_api as connection
    else:
        raise ValueError(f"No connection is built for {maker!r}. See config/models.yaml.")
    return connection
