"""The form a model's reply is copied into before scoring.

The extraction step (Chunk 5) reads each free-text reply and fills in one
`Answer`. It copies numbers exactly as the reply wrote them and never judges
correctness. The scorer reads only this form, never the raw reply.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

UNITS = ("mm", "in")

_DECIMAL = re.compile(r"^(?:\d*\.?\d+|\d+\.)$")
_FRACTION = re.compile(r"^(?:(?P<whole>\d+)[\s-]+)?(?P<top>\d+)/(?P<bottom>\d+)$")


class UnreadableNumber(ValueError):
    """A number in the answer form that is not a plain decimal or fraction."""


@dataclass(frozen=True)
class AnswerValue:
    """One dimension as the reply gave it."""

    number: str  # exactly as written, e.g. ".750", "69.9", "1 3/8"
    unit: str = ""  # mm | in | "" when the reply gave no unit
    label: str = ""  # whatever the reply called it, e.g. "Thickness"; may be blank
    number_in_other_unit: str = ""  # the same dimension restated in the other unit


# Words a reply uses when a size is a diameter. A cylindrical envelope must have one.
DIAMETER_WORDS = ("ø", "⌀", "dia", "diameter", "o.d", "od", "outside diameter", "bore")


@dataclass(frozen=True)
class Envelope:
    """One bounding envelope a reply gave, as the reply described it."""

    values: tuple[AnswerValue, ...]
    shape: str = ""  # CUBE | CYL | "" as the reply presented it

    @property
    def shape_from_values(self) -> str:
        """The shape this envelope really is, worked out from its own sizes and labels.

        Three sizes is a rectangular box. Two sizes with one called a diameter is a
        cylinder. Code decides this rather than trusting the label the extractor
        copied, so a box can never be graded as a cylinder.
        """
        if len(self.values) == 3:
            return "CUBE"
        if len(self.values) == 2 and any(
            word in v.label.lower() for v in self.values for word in DIAMETER_WORDS
        ):
            return "CYL"
        return ""


@dataclass(frozen=True)
class Answer:
    """Everything the reply said about the part's bounding dimensions.

    Replies often give more than one envelope for the same part: a rectangular box
    and then the cylinder inside it. The first one the reply gives is `values` and
    `shape`; any others are in `other_envelopes`. The scorer grades the one that
    matches the part's real shape (SPEC 2.5); extraction never learns that shape.
    """

    values: tuple[AnswerValue, ...]
    shape: str = ""  # CUBE | CYL | "" when the reply didn't say
    flagged: bool = False  # extraction was unsure, or the reply had no clear final answer
    flag_reason: str = ""  # why, in plain words, when flagged
    other_envelopes: tuple[Envelope, ...] = ()

    @property
    def envelopes(self) -> tuple[Envelope, ...]:
        """Every envelope the reply gave, in the order it gave them."""
        return (Envelope(self.values, self.shape), *self.other_envelopes)


def parse_number(text: str) -> Decimal:
    """The value of a number as written. `5/8` is read as 0.625."""
    text = text.strip()
    if _DECIMAL.match(text):
        return Decimal(text)
    fraction = _FRACTION.match(text)
    if fraction and int(fraction.group("bottom")) != 0:
        whole = Decimal(fraction.group("whole") or 0)
        return whole + Decimal(fraction.group("top")) / Decimal(fraction.group("bottom"))
    raise UnreadableNumber(f"{text!r} is not a number the scorer can read")


def other_unit(unit: str) -> str:
    return "in" if unit == "mm" else "mm"
