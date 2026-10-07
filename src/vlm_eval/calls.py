"""Sends one drawing to one model and saves everything about the call.

Every call becomes one JSON file under runs/calls/, written once and never edited:
what was sent (minus the PDF bytes and the key), the maker's complete raw
response, the reply text, the exact model version, token counts, cost, and time.
Extraction and scoring (Chunk 5) read these files, so re-scoring never needs a
new call.

Retries happen only when no reply came back: a lost connection, a timeout, a
rate limit, or a maker server error. A reply that did arrive — a refusal, one
cut off, or a strange one — is saved as it is and never re-asked, because
asking again would let a model have a second try.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from vlm_eval import paths
from vlm_eval.models_config import MAKER_DEFAULT, Model

PROMPT = "return bounding dimensions for this part"

# The prompts a run may use. `bare` is the original question, asked the way anyone would
# ask it. `stock-shape` names the shape of answer wanted, because "bounding dimensions"
# alone has two honest readings for a round part with material milled away (SPEC 2.1).
# Every call records the prompt it was sent, and each prompt's calls are saved apart.
STOCK_SHAPE_PROMPT = (
    "Return bounding dimensions for this part. If the part would be made from round "
    "stock, give cylindrical bounding dimensions (Dia, L). If it would be made from "
    "rectangular stock, give cuboid bounding dimensions (Thk, W, L)."
)
PROMPTS = {"bare": PROMPT, "stock-shape": STOCK_SHAPE_PROMPT}
RECORD_VERSION = 1
MAX_ATTEMPTS = 5


@dataclass(frozen=True)
class MakerReply:
    """What a connection pulls out of the maker's response."""

    model_version: str  # the exact version the maker says answered
    reply_text: str  # the visible answer, thinking left out
    stop_reason: str  # the maker's own words, e.g. end_turn, completed, STOP
    input_tokens: int
    output_tokens: int  # everything billed as output, thinking included
    thinking_tokens: int | None  # the thinking share of output_tokens, when reported
    request_id: str
    raw: dict[str, Any]  # the complete response, as the maker sent it


def model_folder(model: Model) -> str:
    """The folder a model's calls go in. A thinking level of its own gets its own folder,
    so calls made with two different settings never mix."""
    if model.thinking == MAKER_DEFAULT:
        return model.id
    return f"{model.id}-thinking-{model.thinking}"


def call_path(run_name: str, folder: str, drawing: str, run_number: int) -> Path:
    stem = Path(drawing).stem
    return paths.CALLS / run_name / folder / f"{stem}-run{run_number}.json"


def load_call(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def is_done(path: Path) -> bool:
    """A saved call with a reply. Failed calls are saved too, but don't count as done."""
    return path.exists() and load_call(path).get("error") is None


def cost_usd(model: Model, input_tokens: int, output_tokens: int) -> Decimal:
    return (input_tokens * model.input_price + output_tokens * model.output_price) / 1_000_000


def without_pdf(value: Any, pdf_b64: str, label: str) -> Any:
    """The request as saved: the PDF's bytes swapped for a short label, everything else kept."""
    if isinstance(value, dict):
        return {k: without_pdf(v, pdf_b64, label) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [without_pdf(v, pdf_b64, label) for v in value]
    if isinstance(value, bytes):
        return label
    if isinstance(value, str) and pdf_b64 in value:
        return value.replace(pdf_b64, label)
    return value


def send_with_retries(connection: Any, request: Any, api_key: str, sleep=time.sleep):
    """One reply, asking again only while no reply has come back.

    Returns (reply or None, the errors before it). Every failure is recorded, not raised.
    """
    reply, errors = None, []
    while len(errors) < MAX_ATTEMPTS:
        try:
            reply = connection.send(request, api_key)
            break
        except Exception as exc:  # noqa: BLE001 - every failure is recorded, not raised
            errors.append(f"{type(exc).__name__}: {exc}")
            if not connection.is_transient(exc) or len(errors) == MAX_ATTEMPTS:
                break
            sleep(min(60, 2 ** len(errors)))
    return reply, errors


def send_drawing(
    model: Model,
    drawing: str,
    run_name: str,
    run_number: int,
    *,
    connection: Any = None,
    api_key: str | None = None,
    sleep=time.sleep,
    plan_name: str | None = None,
    prompt: str = PROMPT,
) -> dict[str, Any]:
    """Send one drawing to one model, save the call, and return the saved record."""
    if connection is None:
        from vlm_eval.connections import connection_for

        connection = connection_for(model.maker)
    if api_key is None:
        api_key = os.environ.get(model.key, "")

    pdf_bytes = (paths.DRAWINGS / drawing).read_bytes()
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    request = connection.build_request(pdf_bytes, drawing, model, prompt)

    started = datetime.now(UTC)
    reply, errors = send_with_retries(connection, request, api_key, sleep)
    finished = datetime.now(UTC)

    label = f"<PDF {drawing}, {len(pdf_bytes)} bytes, sha256 {sha256}>"
    record: dict[str, Any] = {
        "record_version": RECORD_VERSION,
        "run_name": run_name,
        "run_number": run_number,
        "plan_name": plan_name,  # the run plan that sent it, when one did
        "drawing": drawing,
        "drawing_sha256": sha256,
        "maker": model.maker,
        "model_requested": model.id,
        "model_name": model.name,
        "thinking": model.thinking,
        "maker_default_thinking": model.maker_default,
        "prompt": prompt,
        "request": without_pdf(request, base64.b64encode(pdf_bytes).decode(), label),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "seconds": round((finished - started).total_seconds(), 1),
        "attempts": len(errors) + (1 if reply else 0),
        "price_per_million_tokens": {
            "input": str(model.input_price),
            "output": str(model.output_price),
        },
        "error": None if reply else errors[-1],
        "errors_before_reply": errors if reply else [],
    }
    if reply:
        record |= asdict(reply) | {
            "cost_usd": str(cost_usd(model, reply.input_tokens, reply.output_tokens)),
        }
        record["raw"] = record.pop("raw")  # keep the long raw response last in the file

    path = call_path(run_name, model_folder(model), drawing, run_number)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, default=str) + "\n")
    return record
