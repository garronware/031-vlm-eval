"""Garron's confirmed failure labels: the casebook (SPEC 2.6, Chunk 9).

Each time Garron accepts or changes a diagnosis label on the review page, one line is
appended to data/casebook.jsonl. The file is never rewritten, so every answer he ever
gave is kept; the latest answer for a missed size is the one that counts.

The casebook is what the failure-diagnostician reads before labelling, what reuse
copies onto repeat failures, and where the report takes its labels from. Garron's
label always wins over the agent's draft.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from math import comb

from vlm_eval import paths
from vlm_eval.answers import UnreadableNumber, parse_number

CASEBOOK = paths.DATA / "casebook.jsonl"

ACCEPT = "accept"
CHANGE = "change"
VERDICTS = (ACCEPT, CHANGE)

FIELDS = (
    "run_folder",  # the calls folder the failure came from, e.g. main-stock-shape
    "group",  # the failure group, e.g. 201513-L-78
    "drawing",  # PDF file name
    "missed",  # the missed size as the scorer names it, e.g. "L (Y)"
    "wrong_value",  # the number the agent paired with this size, or "none"
    "agent_label",  # the label the agent proposed
    "garron_label",  # the label Garron confirmed
    "verdict",  # accept | change
    "reason",  # Garron's one-line reason
    "note",  # anything else he wants kept
    "reused",  # True when the label shown was reused, not the agent's own work
    "saved_at",
)


def _key(entry: dict) -> tuple[str, str, str]:
    return entry["run_folder"], entry["group"], entry["missed"]


def save(entry: dict) -> dict:
    """Append one answer. Refuses an answer that would put a wrong label in the book."""
    from vlm_eval.diagnosis import LABELS  # diagnosis imports this module

    row = {f: entry.get(f, "") for f in FIELDS}
    row["reused"] = bool(entry.get("reused"))
    if row["garron_label"] not in LABELS:
        raise ValueError(f"{row['garron_label']!r} is not one of Garron's labels")
    if row["verdict"] not in VERDICTS:
        raise ValueError(f"verdict must be {' or '.join(VERDICTS)}")
    if row["verdict"] == ACCEPT and row["garron_label"] != row["agent_label"]:
        raise ValueError("an accepted label must be the agent's label")
    if row["verdict"] == CHANGE and not str(row["reason"]).strip():
        raise ValueError("a changed label needs a one-line reason")
    for f in ("run_folder", "group", "drawing", "missed"):
        if not row[f]:
            raise ValueError(f"{f} is missing")
    row["saved_at"] = row["saved_at"] or datetime.now().isoformat(timespec="seconds")
    CASEBOOK.parent.mkdir(exist_ok=True)
    with CASEBOOK.open("a") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


def load() -> dict[tuple[str, str, str], dict]:
    """(run folder, group, missed size) -> Garron's latest answer for it."""
    if not CASEBOOK.exists():
        return {}
    latest = {}
    for line in CASEBOOK.read_text().splitlines():
        if line.strip():
            entry = json.loads(line)
            latest[_key(entry)] = entry
    return latest


def entries() -> list[dict]:
    """Every missed size Garron has ruled on, his latest answer each, oldest first."""
    return sorted(load().values(), key=lambda e: e["saved_at"])


def _same_number(a: str, b: str) -> bool:
    if a == b:
        return True
    try:
        return parse_number(a) == parse_number(b)
    except UnreadableNumber:
        return False


def confirmed(drawing: str, missed: str, wrong_value: str) -> dict | None:
    """Garron's label for this drawing, missed size and wrong number, if he has given one.

    All three must match. The wrong number is the one the diagnosis paired with this
    size, so on a reply that missed two sizes a label can't land on the wrong one.
    """
    matches = [
        e
        for e in entries()
        if e["drawing"] == drawing
        and e["missed"] == missed
        and _same_number(str(e["wrong_value"]), wrong_value)
    ]
    return matches[-1] if matches else None


# --- how often the agent agreed with Garron -----------------------------------------


def _binomial_cdf(k: int, n: int, p: float) -> float:
    return sum(comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))


def _crossing(f, target: float) -> float:
    """p in [0, 1] where the rising function f(p) reaches target."""
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if f(mid) >= target else (mid, hi)
    return (lo + hi) / 2


def exact_range(agreed: int, reviewed: int) -> tuple[float, float]:
    """The exact (Clopper-Pearson) 95% range for agreed out of reviewed."""
    if reviewed == 0:
        return 0.0, 1.0
    k, n = agreed, reviewed
    # Low end: the p at which k or more agreements has a 2.5% chance.
    low = 0.0 if k == 0 else _crossing(lambda p: 1 - _binomial_cdf(k - 1, n, p), 0.025)
    # High end: the p at which k or fewer agreements has a 2.5% chance.
    high = 1.0 if k == n else _crossing(lambda p: 1 - _binomial_cdf(k, n, p), 0.975)
    return low, high


@dataclass(frozen=True)
class Agreement:
    reviewed: int  # the agent's own labels Garron has ruled on
    agreed: int
    changed: tuple[dict, ...]  # the entries where he chose a different label

    @property
    def range(self) -> tuple[float, float]:
        return exact_range(self.agreed, self.reviewed)

    def text(self) -> str:
        if not self.reviewed:
            return "No labels reviewed yet."
        low, high = self.range
        return (
            f"The agent agreed with you on {self.agreed} of {self.reviewed} labels "
            f"(95% range {100 * low:.0f}% to {100 * high:.0f}%)."
        )


def agreement(run_folder: str, groups: set[str] | None = None) -> Agreement:
    """Garron's rulings on the agent's own labels for one run. Reused labels don't count.

    `groups` limits it to those failure groups, e.g. the ones a results folder covers.
    """
    own = [
        e
        for e in entries()
        if e["run_folder"] == run_folder
        and not e.get("reused")
        and (groups is None or e["group"] in groups)
    ]
    changed = tuple(e for e in own if e["garron_label"] != e["agent_label"])
    return Agreement(len(own), len(own) - len(changed), changed)
