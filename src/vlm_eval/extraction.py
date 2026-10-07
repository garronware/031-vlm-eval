"""Copies each saved model reply into the answer form the scorer reads (SPEC 2.12).

A small text-only model (the `extractor` in config/models.yaml) reads the reply
and fills in a fixed form. It never sees the drawing or the ground truth and never
judges correctness; it only records what the reply says.

The standard is Garron's: a size counts if a person reading the reply would know
it is the reply's answer, even when it is hedged or sits in a note. Numbers the
reply presents as something else (a stock size to order, supporting evidence) are
left out. A reply is flagged, never guessed, when a person couldn't tell either.

Code then checks that every number in the form appears in the reply as a whole
number, character for character. "2.7" does not pass because "12.7" is in the reply.

Each extraction is saved once under runs/extractions/ and reused from then on, so
re-scoring always gives the same result.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from vlm_eval import paths
from vlm_eval.answers import Answer, AnswerValue, Envelope
from vlm_eval.calls import cost_usd, load_call, send_with_retries
from vlm_eval.models_config import Model, load_extractor

EXTRACTION_VERSION = 4  # 4: sizes only; code works out the shape (SPEC 2.5)
MAX_TOKENS = 4096

# A rough guess per reply, for the cost estimate before extracting.
CHARS_PER_TOKEN = 3
ESTIMATED_OUTPUT_TOKENS = 500
PAUSE_OVER_ESTIMATE = Decimal("1.25")

INSTRUCTIONS = """\
You copy an answer out of a reply. Another AI model was shown an engineering \
drawing of a part and asked: "return bounding dimensions for this part". Its reply \
is given to you inside <reply> tags. Fill in the form with the bounding (overall \
envelope) dimensions the reply gives for the part. You never see the drawing, and \
you never judge whether the reply is right. You only record what it says.

Replies often give more than one envelope for the same part, for example a \
rectangular box and then the cylinder inside it. Record each envelope as its own entry \
in envelopes, in the order the reply gives them. Most replies have exactly one.

Rules for envelopes, which matter more than anything else here:
- Keep every size of an envelope together, and never drop one. A rectangular envelope \
has three sizes; a round one has two, a diameter and a length. Never move a size from \
one envelope to another.
- When the reply gives a box and also names a maximum diameter and an overall or axial \
length, that is two envelopes. Example: "Bounding dimensions 90.4 x 90.4 x 57.15 mm. \
Maximum diameter: Ø90.4 mm. Overall axial length: 57.15 mm." is one envelope of 90.4, \
90.4, 57.15 and a second of Ø90.4 and 57.15.
- Never invent an envelope the reply didn't give. If the reply gives only a box, record \
only that box, even when the part sounds round.
- When the reply gives the same dimension at two precisions, such as "Ø83.570 ± 0.025" \
in a table and "Ø83.60" in a summary line, record the more precise figure (83.570). \
Record the nominal size; leave out ± tolerances.
- You are not asked to say whether an envelope is round or rectangular, and you are \
never asked whether the answer is right. Copy the sizes and the words beside them; the \
rest is worked out from what you record.

Which numbers to record:
- Record the sizes the reply gives as the part's overall or bounding dimensions. \
The test is: would a person reading the reply know that this number is its answer \
for that dimension?
- A size stated with hedging, or in a note, still counts when it is the reply's \
answer for that dimension. Example: "The thickness is not dimensioned, but the \
holes suggest a plate thickness of 12.7 [.500]" gives a thickness of 12.7.
- Leave out numbers the reply presents as something else: a stock or blank size to \
order, feature sizes, hole positions, supporting evidence, calculations, tolerances.
- When the same dimension appears more than once with the same size (for example \
in a table and again in a summary line), record it once.
- When the reply gives two or more different sizes for the same dimension and a \
person could not tell which one is its answer, set no_clear_answer to true.

How to record each value:
- number: copy it exactly as the reply writes it, character for character. Keep \
trailing zeros and leading dots ("12.70", ".750"). Keep fractions as written \
("5/8", "1 3/8"). Never convert, round, or recalculate. No unit and no symbols \
(no Ø, no ", no mm).
- unit: "mm" or "in" only when the reply states the unit for that number: mm, \
millimeters, in, inch, the " sign, a unit column header, or a unit stated for the \
whole list. Otherwise "". Never guess a unit from the size of the number.
- number_in_other_unit: when the reply gives the same dimension in both units, \
such as "215.9 mm [8.50 in]", "8.50 in (215.9 mm)" or "215.9 [8.50]", put the first \
number in number and the second here, copied exactly. That is one value, not two. \
If the reply names the unit of only one number in the pair, the other number is in \
the other unit. Otherwise "".
- label: the reply's own word for the dimension ("Thickness", "Width", "Height", \
"Length", "Diameter", "Ø"), or "" if it gives none. Keep the reply's word even if \
it seems wrong.

For each envelope:
- values: the sizes of that envelope only, in the order the reply gives them.

The other fields:
- no_clear_answer: true only when a person could not tell what the reply's answer is, \
for example when it offers two different sizes for the same dimension and picks neither.
- unsure: true only when you cannot read the numbers or cannot tell which sizes belong \
together. Never set it because you are unsure whether the part is round or rectangular, \
or whether the reply is right: neither is your job.
- reason: when no_clear_answer or unsure is true, one short sentence saying why. \
Otherwise "".
- If the reply gives no dimensions at all (for example it refuses or is cut off), \
return an empty envelopes list with both flags false.
"""

_VALUE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "number": {"type": "string"},
        "unit": {"type": "string", "enum": ["mm", "in", ""]},
        "label": {"type": "string"},
        "number_in_other_unit": {"type": "string"},
    },
    "required": ["number", "unit", "label", "number_in_other_unit"],
    "additionalProperties": False,
}

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "envelopes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"values": {"type": "array", "items": _VALUE_SCHEMA}},
                "required": ["values"],
                "additionalProperties": False,
            },
        },
        "no_clear_answer": {"type": "boolean"},
        "unsure": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["envelopes", "no_clear_answer", "unsure", "reason"],
    "additionalProperties": False,
}

# Whole numbers as a reply writes them, longest form first: mixed fractions
# (1 3/8, 1-3/8), fractions (5/8), decimals (12.70, .750), whole numbers. A number
# never starts in the middle of another one, so "12.7" never yields "2.7".
_NUMBER = re.compile(r"(?<![\d.])(?:\d+(?:[^\S\n]+|-)\d+/\d+|\d+/\d+|\d*\.\d+|\d+)")


# Signs that a reply writes a unit at all. A unit the extractor fills in for a
# reply that never writes one is a guess, and a guessed unit would be trusted by
# the scorer, so it is set aside and both readings are tried (SPEC 2.5).
_UNIT_WORDS = {
    "mm": re.compile(r"\bmm\b|millimet", re.IGNORECASE),
    "in": re.compile(r"\binch|\d\s*(?:in\b|\"|″)|[\[(]\s*in\b|\bin\s*[\])]", re.IGNORECASE),
}


class ExtractionError(RuntimeError):
    """A saved extraction that no longer fits its reply. Never silently redone."""


def _tidy(number: str) -> str:
    return " ".join(number.split())


def numbers_in(text: str) -> set[str]:
    """Every number written in the text, as whole numbers."""
    return {_tidy(m.group()) for m in _NUMBER.finditer(text)}


def form_envelopes(form: dict[str, Any]) -> list[dict[str, Any]]:
    """The envelopes in a saved form, whichever version wrote it.

    Version 4 records sizes only; earlier versions also carried a shape the extractor
    guessed, which code no longer uses.
    """
    if "envelopes" in form:
        return [{"shape": e.get("shape", ""), "values": e["values"]} for e in form["envelopes"]]
    return [{"shape": form.get("shape", ""), "values": form.get("values", [])}]  # version 1


def form_values(form: dict[str, Any]) -> list[dict[str, str]]:
    """Every value in the form, across every envelope."""
    return [v for envelope in form_envelopes(form) for v in envelope["values"]]


def numbers_not_in_reply(form: dict[str, Any], reply_text: str) -> list[str]:
    """Numbers in the form that the reply does not contain, character for character."""
    found = numbers_in(reply_text)
    missing = []
    for value in form_values(form):
        for number in (value["number"], value["number_in_other_unit"]):
            if number and _tidy(number) not in found and number not in missing:
                missing.append(number)
    return missing


def units_written(reply_text: str) -> set[str]:
    """The units a reply writes anywhere: mm, in, both, or neither."""
    return {unit for unit, words in _UNIT_WORDS.items() if words.search(reply_text)}


def reply_sha256(reply_text: str) -> str:
    return hashlib.sha256(reply_text.encode()).hexdigest()


def extraction_path(call_file: Path) -> Path:
    """Where a call's extraction is saved: the same run/model/drawing path as the call."""
    return paths.EXTRACTIONS / call_file.relative_to(paths.CALLS)


def is_current(call_file: Path) -> bool:
    """True when this reply has an extraction made by the version in use now."""
    path = extraction_path(call_file)
    if not path.exists():
        return False
    return json.loads(path.read_text()).get("extraction_version") == EXTRACTION_VERSION


def build_request(reply_text: str, extractor: Model) -> dict[str, Any]:
    """Exactly what the extractor is sent: the instructions and the reply text, nothing else."""
    return {
        "model": extractor.id,
        "max_tokens": MAX_TOKENS,
        "system": INSTRUCTIONS,
        "messages": [{"role": "user", "content": f"<reply>\n{reply_text}\n</reply>"}],
        "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
    }


def _flag(form: dict[str, Any] | None, missing: list[str]) -> str:
    """Why the extraction is flagged, or "" when it isn't."""
    if form is None:
        return "The extractor's answer could not be read"
    if missing:
        listed = ", ".join(f"{n!r}" for n in missing)
        return f"Extractor gave {listed}, which the reply does not contain"
    if form["no_clear_answer"]:
        return f"No clear final answer: {form['reason']}".rstrip(": ")
    if form["unsure"]:
        return f"Extractor unsure: {form['reason']}".rstrip(": ")
    return ""


def extract(
    call_file: Path,
    *,
    extractor: Model | None = None,
    connection: Any = None,
    api_key: str | None = None,
    sleep=time.sleep,
    plan_name: str | None = None,
) -> dict[str, Any]:
    """The extraction for one saved reply: the saved one if it exists, otherwise a new one.

    A new extraction is saved only when the extractor replied. When no reply came
    back, the returned record carries the error and nothing is saved, so it is
    tried again next time.
    """
    call = load_call(call_file)
    if call.get("error"):
        raise ValueError(f"{call_file.name}: no reply came back, so there is nothing to extract")
    reply_text = call["reply_text"]
    digest = reply_sha256(reply_text)

    out = extraction_path(call_file)
    if out.exists():
        saved = json.loads(out.read_text())
        if saved["reply_sha256"] != digest:
            raise ExtractionError(f"{out} was made from a different reply than {call_file}")
        if saved["extraction_version"] == EXTRACTION_VERSION:
            return saved
        # The form itself changed, so this reply is read once more under the new
        # version and the old extraction is replaced. Saved calls are untouched.

    extractor = extractor or load_extractor()
    if connection is None:
        from vlm_eval.connections import connection_for

        connection = connection_for(extractor.maker)
    if api_key is None:
        api_key = os.environ.get(extractor.key, "")

    request = build_request(reply_text, extractor)
    started = datetime.now(UTC)
    reply, errors = send_with_retries(connection, request, api_key, sleep)
    finished = datetime.now(UTC)

    record: dict[str, Any] = {
        "extraction_version": EXTRACTION_VERSION,
        "call_file": str(call_file.relative_to(paths.ROOT)),
        "drawing": call["drawing"],
        "model_requested": call["model_requested"],
        "run_name": call["run_name"],
        "run_number": call["run_number"],
        "plan_name": plan_name,  # the run plan that made it, when one did
        "reply_sha256": digest,
        "extractor_requested": extractor.id,
        "request": request,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "seconds": round((finished - started).total_seconds(), 1),
        "attempts": len(errors) + (1 if reply else 0),
        "error": None if reply else errors[-1],
        "errors_before_reply": errors if reply else [],
    }
    if not reply:
        return record

    try:
        form = json.loads(reply.reply_text)
    except json.JSONDecodeError:
        form = None
    missing = numbers_not_in_reply(form, reply_text) if form else []
    reason = _flag(form, missing)
    record |= {
        "form": form,
        "numbers_not_in_reply": missing,
        "flagged": bool(reason),
        "flag_reason": reason,
    }
    record |= asdict(reply) | {
        "cost_usd": str(cost_usd(extractor, reply.input_tokens, reply.output_tokens)),
    }
    record["raw"] = record.pop("raw")  # keep the long raw response last in the file

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, default=str) + "\n")
    return record


def answer_from_record(record: dict[str, Any], reply_text: str) -> Answer:
    """The answer form the scorer reads, from a saved extraction and its reply.

    A unit the reply never writes is left blank, so the scorer tries both readings.
    """
    form = record.get("form") or {}
    written = units_written(reply_text)

    def envelope(entry: dict[str, Any]) -> Envelope:
        return Envelope(
            values=tuple(
                AnswerValue(
                    number=v["number"],
                    unit=v["unit"] if v["unit"] in written else "",
                    label=v["label"],
                    number_in_other_unit=v["number_in_other_unit"],
                )
                for v in entry["values"]
            ),
            shape=entry["shape"],
        )

    envelopes = [envelope(e) for e in form_envelopes(form)] or [Envelope(())]
    first = envelopes[0]
    return Answer(
        values=first.values,
        shape=first.shape,
        flagged=record["flagged"],
        flag_reason=record["flag_reason"],
        other_envelopes=tuple(envelopes[1:]),
    )


# --- the `extract` command ----------------------------------------------------


def saved_calls(run_name: str | None = None) -> list[Path]:
    """Every saved call, or every call in one run, in a fixed order."""
    pattern = f"{run_name or '*'}/*/*.json"
    return sorted(paths.CALLS.glob(pattern))


def waiting(run_name: str | None = None) -> list[Path]:
    """Saved calls with a reply and no up-to-date extraction, so a version bump is included."""
    return [
        f for f in saved_calls(run_name) if load_call(f).get("error") is None and not is_current(f)
    ]


def estimate(call_file: Path, extractor: Model) -> Decimal:
    chars = len(INSTRUCTIONS) + len(load_call(call_file)["reply_text"])
    return cost_usd(extractor, chars // CHARS_PER_TOKEN, ESTIMATED_OUTPUT_TOKENS)


def run(run_name: str | None = None, send: bool = False) -> None:
    """Free by default: shows what would be extracted and the estimated cost."""
    from dotenv import load_dotenv

    extractor = load_extractor()
    pending = waiting(run_name)
    where = f"run {run_name}" if run_name else "all runs"
    if not pending:
        print(f"Every saved reply in {where} is already extracted. Nothing to do.")
        return

    total = sum((estimate(f, extractor) for f in pending), Decimal(0))
    print(f"Plan: {extractor.name} ({extractor.id}) reads {len(pending)} saved replies")
    print(f"in {where} and copies their numbers into the answer form. Text only.")
    for f in pending:
        print(f"  {f.relative_to(paths.CALLS)}")
    print(f"Estimated cost: about ${total:.4f}.")
    print(f"Stops early if spending passes ${total * PAUSE_OVER_ESTIMATE:.4f} (+25%).")
    if not send:
        print("\nNothing was sent. To extract, run: uv run vlm-eval extract --send")
        return

    load_dotenv(paths.ENV_FILE)
    if not os.environ.get(extractor.key, "").strip():
        print(f"\nNo key: add {extractor.key} to .env. Nothing was sent.")
        return

    spent = Decimal(0)
    for f in pending:
        if spent > total * PAUSE_OVER_ESTIMATE:
            print(f"  Stopped before {f.name}: spent ${spent:.4f}, over the +25% limit.")
            break
        record = extract(f, extractor=extractor)
        spent += Decimal(record.get("cost_usd") or 0)
        name = f.relative_to(paths.CALLS)
        if record["error"]:
            print(f"  {name}: FAILED after {record['attempts']} attempt(s): {record['error']}")
        else:
            flag = f"  FLAGGED: {record['flag_reason']}" if record["flagged"] else ""
            form = record["form"] or {}
            envelopes = form_envelopes(form) if form else []
            found = f"{len(form_values(form))} value(s)" if form else "unreadable"
            if len(envelopes) > 1:
                found += f" in {len(envelopes)} envelopes"
            print(f"  {name}: {found}, ${Decimal(record['cost_usd']):.4f}{flag}")
    print(f"\nSpent ${spent:.4f} against an estimate of ${total:.4f}.")
    print("To see the results, run: uv run vlm-eval replay")
