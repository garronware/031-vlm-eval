"""Scores one model answer against ground truth (SPEC 2.5).

Pass/fail comes from this code only. A value is correct if it matches any
faithful reading of what the drawing prints: the printed mm, the printed inch,
either one converted, or, for a chain, its parts added up. Windows are tight
(±0.02 mm / ±0.0005 in) so a different number printed on the same sheet cannot
pass.

CUBE values match as an unordered set; Thk is never compared to Thk. That is how
flat stock is ordered: the three sizes matter, not which face is which. A
cylinder is different: diameter and length are not interchangeable, so a reply's
diameter must match the diameter and its length the length.
"""

from __future__ import annotations

import csv
import dataclasses
import functools
import itertools
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

from vlm_eval import paths
from vlm_eval.answers import (
    Answer,
    AnswerValue,
    Envelope,
    UnreadableNumber,
    other_unit,
    parse_number,
)
from vlm_eval.ground_truth import Dimension, Drawing, read_ground_truth

MM_PER_INCH = Decimal("25.4")

DUAL_MM_TOLERANCE = Decimal("0.02")
INCH_ONLY_MM_TOLERANCE = Decimal("0.05")  # Garron's choice for mm answers to inch-only prints
INCH_TOLERANCE = Decimal("0.0005")

# Problems a run can have. Any one of them fails the run.
MISSING_VALUE = "Missing value"
EXTRA_VALUE = "Extra value"
WRONG_VALUE = "Wrong value"
UNIT_MIX_UP = "Unit mix-up"

# Words a reply might use for each ground-truth label. Only used to break ties
# when a drawing repeats a size, so the missed dimension is reported under the
# label the reply itself used.
_LABEL_WORDS = {
    "Thk": {"thk", "thickness", "t", "thick"},
    "W": {"w", "width", "wide"},
    "L": {"l", "length", "long", "len"},
    "Dia": {"dia", "diameter", "d", "ø", "⌀", "od", "o.d", "outside diameter", "outer diameter"},
}

# What a reply might call a cylinder's length. A standing cylinder's length is
# often called its height.
_CYLINDER_LENGTH_WORDS = _LABEL_WORDS["L"] | {"overall length", "oal", "height", "h", "tall"}

CYLINDER_NOT_LABELED = (
    "Not graded: the reply gives two cylinder sizes without saying which is the "
    "diameter and which is the length. Flagged for Garron to look at."
)


class ScoringError(ValueError):
    """Ground truth the scorer cannot build a key from. Never swallowed."""


@dataclass(frozen=True)
class Reading:
    """One accepted way of stating a ground-truth dimension."""

    name: str  # e.g. "printed inch converted to mm"; reads cold in the tolerance audit
    unit: str  # mm | in
    value: Decimal
    tolerance: Decimal

    @property
    def converted(self) -> bool:
        return "converted" in self.name

    def accepts(self, number: Decimal, unit: str) -> bool:
        return unit == self.unit and abs(number - self.value) <= self.tolerance


@dataclass(frozen=True)
class ChainPart:
    """One printed part of a chain, and the ways of stating it."""

    printed: str  # as printed, e.g. "34.29"
    readings: tuple[Reading, ...]


@dataclass(frozen=True)
class DimensionKey:
    label: str
    axis: str
    readings: tuple[Reading, ...]
    printed: str = ""  # as recorded in ground truth, e.g. "34.29 + 6.35 = 40.64"
    chain_parts: tuple[ChainPart, ...] = ()  # empty unless the dimension is a chain

    @property
    def described(self) -> str:
        return f"{self.label} ({self.axis})" if self.axis else self.label

    def reading_for(self, numbers: tuple[tuple[Decimal, str], ...]) -> Reading | None:
        """The first accepted reading any of the value's numbers lands in."""
        for reading in self.readings:
            if any(reading.accepts(n, u) for n, u in numbers):
                return reading
        return None


@dataclass(frozen=True)
class DrawingKey:
    file: str
    shape: str
    print_type: str
    dimensions: tuple[DimensionKey, ...]


@dataclass(frozen=True)
class Match:
    """One answer value matched to one ground-truth dimension."""

    label: str
    axis: str
    answer_number: str
    answer_unit: str  # the unit the value was scored in
    reading: str  # the accepted reading it landed in
    converted: bool


@dataclass(frozen=True)
class UnmatchedValue:
    """A value from the reply that matched no ground-truth dimension: a wrong number."""

    number: str  # exactly as the reply wrote it
    unit: str  # the unit it was scored in
    label: str  # what the reply called it; may differ from the dimension it missed


@dataclass(frozen=True)
class Verdict:
    file: str
    scored: bool  # False when the reply was flagged or unreadable; never guessed
    strict_pass: bool
    dims_correct: int
    dims_total: int
    dims_missed: tuple[str, ...]  # e.g. ("L (Y)",)
    problems: tuple[str, ...]
    matches: tuple[Match, ...]
    note: str = ""
    # A missed chain dimension answered with one of its printed parts, e.g.
    # "Thk (Z) missed: gave 34.29, one part of the chain 34.29 + 6.35 = 40.64".
    chain_parts_given: tuple[str, ...] = ()
    # Envelopes the reply also gave that were not the graded one (SPEC 2.5).
    ignored_envelopes: tuple[str, ...] = ()
    # Values in the graded envelope that matched nothing. Diagnosis explains them.
    unmatched_values: tuple[UnmatchedValue, ...] = ()
    # Missed chain dimensions answered with one printed part: (label, part as printed).
    chain_parts_matched: tuple[tuple[str, str], ...] = ()
    # Garron's criteria (SPEC Chunk 10): each number in his ground-truth row counts,
    # a chain's parts one each and its total not at all. Pass/fail never uses these.
    criteria_correct: int = 0
    criteria_total: int = 0

    @property
    def relied_on_conversion(self) -> bool:
        """For the tolerance audit: a pass that needed a converted reading."""
        return self.strict_pass and any(m.converted for m in self.matches)


def _parts(text: str) -> tuple[list[Decimal], Decimal | None]:
    """`34.29 + 6.35 = 40.64` -> ([34.29, 6.35], 40.64); `1.350 + 0.250` -> (.., None)."""
    left, _, total = text.partition("=")
    parts = [Decimal(p.strip()) for p in left.split("+")]
    return parts, (Decimal(total.strip()) if total.strip() else None)


def _part_texts(text: str) -> list[str]:
    return [p.strip() for p in text.partition("=")[0].split("+")]


def _chain_parts(dimension: Dimension, inch_text: str | None) -> tuple[ChainPart, ...]:
    """Each printed part of a chain, readable in mm or inch like any printed number."""
    parts = _part_texts(dimension.printed)
    if len(parts) == 1:
        return ()
    out = []
    if inch_text is None:  # inch-only print: the parts are printed in inches
        for part in parts:
            inch = Decimal(part)
            out.append(
                ChainPart(
                    part,
                    (
                        Reading("printed inch", "in", inch, INCH_TOLERANCE),
                        Reading(
                            "printed inch converted to mm",
                            "mm",
                            inch * MM_PER_INCH,
                            INCH_ONLY_MM_TOLERANCE,
                        ),
                    ),
                )
            )
        return tuple(out)
    for mm_text, inch_part in zip(parts, _part_texts(inch_text), strict=True):
        mm, inch = Decimal(mm_text), Decimal(inch_part)
        out.append(
            ChainPart(
                mm_text,
                (
                    Reading("printed mm", "mm", mm, DUAL_MM_TOLERANCE),
                    Reading("printed inch", "in", inch, INCH_TOLERANCE),
                    Reading(
                        "printed inch converted to mm", "mm", inch * MM_PER_INCH, DUAL_MM_TOLERANCE
                    ),
                    Reading("printed mm converted to inch", "in", mm / MM_PER_INCH, INCH_TOLERANCE),
                ),
            )
        )
    return tuple(out)


def _dual_readings(dimension: Dimension, inch_text: str) -> list[Reading]:
    mm_parts, mm_total = _parts(dimension.printed)
    inch_parts, _ = _parts(inch_text)
    mm_tol, in_tol = DUAL_MM_TOLERANCE, INCH_TOLERANCE
    if len(mm_parts) == 1:
        mm, inch = mm_parts[0], inch_parts[0]
        return [
            Reading("printed mm", "mm", mm, mm_tol),
            Reading("printed inch", "in", inch, in_tol),
            Reading("printed inch converted to mm", "mm", inch * MM_PER_INCH, mm_tol),
            Reading("printed mm converted to inch", "in", mm / MM_PER_INCH, in_tol),
        ]
    mm_sum, inch_sum = sum(mm_parts), sum(inch_parts)
    return [
        Reading("chain total as recorded", "mm", mm_total, mm_tol),
        Reading("mm segments added up", "mm", mm_sum, mm_tol),
        Reading("inch segments added up", "in", inch_sum, in_tol),
        Reading("inch segments added up converted to mm", "mm", inch_sum * MM_PER_INCH, mm_tol),
        Reading("chain total as recorded converted to inch", "in", mm_total / MM_PER_INCH, in_tol),
        Reading("mm segments added up converted to inch", "in", mm_sum / MM_PER_INCH, in_tol),
    ]


def _inch_only_readings(dimension: Dimension) -> list[Reading]:
    parts, total = _parts(dimension.printed)
    mm_tol, in_tol = INCH_ONLY_MM_TOLERANCE, INCH_TOLERANCE
    if len(parts) == 1:
        inch = parts[0]
        return [
            Reading("printed inch", "in", inch, in_tol),
            Reading("printed inch converted to mm", "mm", inch * MM_PER_INCH, mm_tol),
        ]
    inch_sum = sum(parts)
    return [
        Reading("chain total as recorded", "in", total, in_tol),
        Reading("inch segments added up", "in", inch_sum, in_tol),
        Reading("chain total as recorded converted to mm", "mm", total * MM_PER_INCH, mm_tol),
        Reading("inch segments added up converted to mm", "mm", inch_sum * MM_PER_INCH, mm_tol),
    ]


def build_key(drawing: Drawing, inch_values: dict[tuple[str, str], str]) -> DrawingKey:
    dims = []
    for d in drawing.dimensions:
        if drawing.print_type == "dual":
            inch_text = inch_values.get((drawing.file, d.label), "")
            if not inch_text:
                raise ScoringError(f"{drawing.file} {d.label}: no inch value to score against")
            readings = _dual_readings(d, inch_text)
            parts = _chain_parts(d, inch_text)
        else:
            readings = _inch_only_readings(d)
            parts = _chain_parts(d, None)
        dims.append(DimensionKey(d.label, d.axis, tuple(readings), d.printed, parts))
    return DrawingKey(drawing.file, drawing.shape, drawing.print_type, tuple(dims))


def _inch_values() -> dict[tuple[str, str], str]:
    with paths.INCH_PARTNERS_CSV.open(newline="") as fh:
        return {(r["file"], r["label"]): r["final_inch"] for r in csv.DictReader(fh)}


@functools.cache
def load_answer_key() -> dict[str, DrawingKey]:
    """Every drawing's accepted readings, keyed by PDF file name."""
    inch_values = _inch_values()
    return {d.file: build_key(d, inch_values) for d in read_ground_truth(classify_pdfs=False)}


# --- scoring ---------------------------------------------------------------


@dataclass(frozen=True)
class _Parsed:
    value: AnswerValue
    primary: Decimal
    other: Decimal | None

    def numbers(self, unit: str) -> tuple[tuple[Decimal, str], ...]:
        """The value's numbers when its first number is read in `unit`."""
        out = ((self.primary, unit),)
        if self.other is not None:
            out += ((self.other, other_unit(unit)),)
        return out


def _words(label: str) -> str:
    return " ".join(label.lower().replace(":", " ").split()).strip(".")


def _label_agrees(answer_label: str, gt_label: str) -> bool:
    return _words(answer_label) in _LABEL_WORDS[gt_label]


def _cylinder_label(answer_label: str) -> str:
    """Dia, L, or "" when the reply's label doesn't say which it is."""
    words = _words(answer_label)
    if words in _LABEL_WORDS["Dia"] or "diam" in words:
        return "Dia"
    if words in _CYLINDER_LENGTH_WORDS or "length" in words:
        return "L"
    return ""


def _cylinder_labels(parsed: list[_Parsed]) -> tuple[str, ...]:
    """What each value of a cylinder reply claims to be.

    When a two-value reply names only one of them (`Ø10 × 75`), the other is the
    remaining one.
    """
    labels = [_cylinder_label(p.value.label) for p in parsed]
    if len(labels) == 2 and labels.count("") == 1:
        named = next(lab for lab in labels if lab)
        if named in ("Dia", "L"):
            other = "L" if named == "Dia" else "Dia"
            labels = [lab or other for lab in labels]
    return tuple(labels)


def _allowed(claims: tuple[str, ...] | None, i: int, dim: DimensionKey) -> bool:
    """A CUBE value may match any dimension; a cylinder value only the one it claims."""
    return claims is None or claims[i] == dim.label


def _best_matching(
    key: DrawingKey,
    parsed: list[_Parsed],
    units: tuple[str, ...],
    claims: tuple[str, ...] | None = None,
):
    """The best one-to-one pairing of answer values to ground-truth dimensions.

    Tries every pairing (answers are small). Best means: most dimensions matched,
    then most labels agreeing, then most matched on a printed rather than a
    converted reading. The first best found wins, so the result never varies.
    """
    options = []
    for dim in key.dimensions:
        choices = [None]
        for i, p in enumerate(parsed):
            if not _allowed(claims, i, dim):
                continue
            reading = dim.reading_for(p.numbers(units[i]))
            if reading:
                choices.append((i, reading))
        options.append(choices)

    best, best_rank = (), (-1, -1, -1)
    for combo in itertools.product(*options):
        used = [c[0] for c in combo if c]
        if len(used) != len(set(used)):
            continue
        rank = (
            len(used),
            sum(
                _label_agrees(parsed[c[0]].value.label, dim.label)
                for c, dim in zip(combo, key.dimensions, strict=True)
                if c
            ),
            sum(1 for c in combo if c and not c[1].converted),
        )
        if rank > best_rank:
            best, best_rank = combo, rank
    return best


def _matches_anything(key: DrawingKey, parsed, i: int, unit: str, claims) -> bool:
    return any(
        _allowed(claims, i, dim) and dim.reading_for(parsed[i].numbers(unit))
        for dim in key.dimensions
    )


def _units(key: DrawingKey, parsed: list[_Parsed], claims) -> tuple[str, ...]:
    """The unit each value is scored in.

    A labeled value is scored in its label. Unlabeled values are all read as mm
    or all as inch, whichever matches more (mm on a tie). They never mix.
    """
    labeled = [p.value.unit for p in parsed]

    def count(units: tuple[str, ...]) -> int:
        return sum(1 for c in _best_matching(key, parsed, units, claims) if c)

    readings = [tuple(u or unit for u in labeled) for unit in ("mm", "in")]
    return max(readings, key=count)  # max keeps the first on a tie, so mm wins ties


def _mixed_up(key: DrawingKey, parsed: list[_Parsed], units: tuple[str, ...], claims) -> set[int]:
    """Values that match nothing in the unit they were scored in, but would in the other."""
    return {
        i
        for i, u in enumerate(units)
        if not _matches_anything(key, parsed, i, u, claims)
        and _matches_anything(key, parsed, i, other_unit(u), claims)
    }


def _chain_parts_given(key, parsed, units, claims, best) -> list[tuple[DimensionKey, str, str]]:
    """Missed chain dimensions the reply answered with one printed part of the chain.

    Each is (the dimension, the part as printed, the note for the results page).
    """
    used = {c[0] for c in best if c}
    found = []
    for combo, dim in zip(best, key.dimensions, strict=True):
        if combo or not dim.chain_parts:
            continue
        for i, p in enumerate(parsed):
            if i in used or not (claims is None or claims[i] in (dim.label, "")):
                continue
            numbers = p.numbers(units[i])
            part = next(
                (
                    c
                    for c in dim.chain_parts
                    if any(r.accepts(n, u) for r in c.readings for n, u in numbers)
                ),
                None,
            )
            if part:
                note = (
                    f"{dim.described} missed: gave {p.value.number} {units[i]}, "
                    f"one part of the chain {dim.printed}"
                )
                found.append((dim, part.printed, note))
                break
    return found


def criteria_total(key: DrawingKey) -> int:
    """How many numbers Garron's row asks for: a chain's parts count, its total doesn't."""
    return sum(len(d.chain_parts) or 1 for d in key.dimensions)


def _with_criteria(verdict: Verdict, key: DrawingKey, form: DrawingKey) -> Verdict:
    """Count the reply's correct criteria against the recorded row, whatever form it took.

    A dimension counts only when every place the form uses it matched (a box form uses
    Dia twice). A matched chain gets all its parts; one printed part given gets one.
    """
    slots = Counter(d.label for d in form.dimensions)
    matched = Counter(m.label for m in verdict.matches)
    lone_parts = {label for label, _ in verdict.chain_parts_matched}
    correct = 0
    for d in key.dimensions:
        if matched[d.label] >= slots[d.label]:
            correct += len(d.chain_parts) or 1
        elif d.label in lone_parts:
            correct += 1
    return dataclasses.replace(
        verdict, criteria_correct=correct, criteria_total=criteria_total(key)
    )


def _not_scored(key: DrawingKey, note: str) -> Verdict:
    n = len(key.dimensions)
    missed = tuple(d.described for d in key.dimensions)
    return Verdict(key.file, False, False, 0, n, missed, (), (), note)


def _describe(envelope: Envelope) -> str:
    """An ignored envelope in plain words, for the results page."""
    shape = envelope.shape_from_values or envelope.shape or "unnamed"
    sizes = " x ".join(f"{v.number}{' ' + v.unit if v.unit else ''}" for v in envelope.values)
    return f"also gave a {shape} envelope ({sizes}), not graded"


BOX_FORM_NOTE = "Graded as the box the cylinder implies: Dia x Dia x L"


def accepted_forms(key: DrawingKey) -> list[DrawingKey]:
    """The shapes an envelope may be written in, all describing the same envelope.

    The bare prompt asks for bounding dimensions without naming a shape, so a round
    part's envelope is right either as the cylinder (Dia, L) or as the box that cylinder
    fills (Dia, Dia, L). Both come straight from the recorded Dia and L; neither needs
    anything new. A smaller number taken from a local feature, such as an across-flats
    size, is not an envelope dimension and is not accepted.
    """
    forms = [key]
    if key.shape == "CYL" and len(key.dimensions) == 2:
        dia = next((d for d in key.dimensions if d.label == "Dia"), None)
        length = next((d for d in key.dimensions if d.label != "Dia"), None)
        if dia and length:
            forms.append(DrawingKey(key.file, "CUBE", key.print_type, (dia, dia, length)))
    return forms


def _rank(verdict: Verdict, primary: bool) -> tuple:
    """Best verdict first: a pass, then the ground-truth form, then most sizes matched."""
    return (
        verdict.scored,
        verdict.strict_pass,
        primary,  # when both forms pass, report it in the recorded Dia/L terms
        verdict.dims_correct,
        -len(verdict.problems),
    )


def score(file: str, answer: Answer, key: DrawingKey | None = None) -> Verdict:
    """The verdict for one answer to one drawing.

    Every envelope the reply gave is tried against every accepted form of the answer,
    and the best result stands. Trying in a fixed order means the same saved reply
    always scores the same way.
    """
    key = key or load_answer_key()[file]
    if answer.flagged:
        note = "Reply flagged by extraction, not scored"
        note = f"{note}: {answer.flag_reason}" if answer.flag_reason else note
        return _with_criteria(_not_scored(key, note), key, key)

    forms = accepted_forms(key)
    # A form is only tried against an envelope with the right number of sizes, so a
    # two-size reply is never judged against the three-size box and called incomplete.
    envelopes = answer.envelopes  # built fresh on each access, so read it once
    tries = [
        (envelope, form)
        for envelope in envelopes
        for form in forms
        if len(envelope.values) == len(form.dimensions)
    ]
    if not tries:  # the reply gives the wrong number of sizes for any form; say so
        tries = [(envelopes[0], key)]

    best, best_rank, best_envelope, best_form = None, None, None, key
    for envelope, form in tries:
        verdict = _score_envelope(envelope, form)
        primary = form is key
        if not primary:
            verdict = dataclasses.replace(verdict, note=BOX_FORM_NOTE)
        rank = _rank(verdict, primary)
        if best is None or rank > best_rank:
            best, best_rank, best_envelope, best_form = verdict, rank, envelope, form
    ignored = tuple(_describe(e) for e in envelopes if e is not best_envelope)
    best = dataclasses.replace(best, ignored_envelopes=ignored)
    return _with_criteria(best, key, best_form)


def _score_envelope(envelope: Envelope, key: DrawingKey) -> Verdict:
    """One envelope from the reply, against one accepted form of the answer."""
    try:
        parsed = [
            _Parsed(
                v,
                parse_number(v.number),
                parse_number(v.number_in_other_unit) if v.number_in_other_unit else None,
            )
            for v in envelope.values
        ]
    except UnreadableNumber as exc:
        return _not_scored(key, f"Reply could not be read: {exc}")
    bad_units = [v.unit for v in envelope.values if v.unit not in ("", "mm", "in")]
    if bad_units:
        return _not_scored(key, f"Reply could not be read: unit {bad_units[0]!r}")

    claims = None
    if key.shape == "CYL":
        claims = _cylinder_labels(parsed)
        if len(parsed) == 2 and "" in claims:
            return _not_scored(key, CYLINDER_NOT_LABELED)
    units = _units(key, parsed, claims)
    mixed_up = _mixed_up(key, parsed, units, claims)
    best = _best_matching(key, parsed, units, claims)

    matches, missed = [], []
    for combo, dim in zip(best, key.dimensions, strict=True):
        if combo:
            i, reading = combo
            v = parsed[i].value
            matches.append(
                Match(dim.label, dim.axis, v.number, units[i], reading.name, reading.converted)
            )
        else:
            missed.append(dim.described)

    chain_parts = _chain_parts_given(key, parsed, units, claims, best)
    n_dims, n_values = len(key.dimensions), len(parsed)
    wrong_values = n_values - len(matches) - len(mixed_up)
    problems = []
    if n_values < n_dims:
        problems.append(MISSING_VALUE)
    if n_values > n_dims:
        problems.append(EXTRA_VALUE)
    if wrong_values > max(0, n_values - n_dims):
        problems.append(WRONG_VALUE)
    if mixed_up:
        problems.append(UNIT_MIX_UP)

    return Verdict(
        file=key.file,
        scored=True,
        strict_pass=not problems and not missed,
        dims_correct=len(matches),
        dims_total=n_dims,
        dims_missed=tuple(missed),
        problems=tuple(problems),
        matches=tuple(matches),
        chain_parts_given=tuple(note for _, _, note in chain_parts),
        chain_parts_matched=tuple((dim.label, part) for dim, part, _ in chain_parts),
        unmatched_values=tuple(
            UnmatchedValue(p.value.number, units[i], p.value.label)
            for i, p in enumerate(parsed)
            if i not in {c[0] for c in best if c}
        ),
    )
