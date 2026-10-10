# Scoring rules

How a model's answer is graded against your ground truth. Code does all the
grading; no AI model decides pass or fail. To see these rules applied to real
drawings, run `uv run vlm-eval grading-examples`.

## What counts as a correct value

A value is correct if it matches any faithful reading of the dimension printed
on the drawing:

| Print type | Accepted mm answers | Accepted inch answers |
|---|---|---|
| Dual-dimensioned (`MM` rows, printed `mm [in]`) | the printed mm; the printed inch × 25.4 | the printed inch; the printed mm ÷ 25.4 |
| Inch-only (`IN` rows) | the printed inch × 25.4 | the printed inch |

**Chains** (written as sums in your table, like `34.29 + 6.35 = 40.64`) also
accept their parts added up, in either unit: the mm parts summed, and the inch
parts summed (× 25.4 for an mm answer). SolidWorks rounds each mm display on its
own, so the mm parts don't always add to the printed total. A model that adds up
the printed parts has read the drawing correctly and isn't failed for that
rounding.

## How close is close enough

| Print type | mm answer | inch answer |
|---|---|---|
| Dual-dimensioned | within ±0.02 mm | within ±0.0005 in |
| Inch-only | within ±0.05 mm of the exact conversion | within ±0.0005 in |

The windows are tight on purpose: **a different number printed on the same
sheet must not pass.** On 201551-016 the envelope is 19.1 mm, and 19.0 is also
printed on the sheet. A wider window, like ±0.20 mm, would pass a model that
grabbed the 19.0. At these widths the only overlaps left are the same size
printed a second way (19.05 mm is .750 in), which is harmless.

## Sizes printed with a tolerance

A size printed with a ± tolerance also accepts its **upper limit**, because the
part can be that large. On 201551-024 the diameter is printed `Ø83.570 ±0.025
[Ø3.2902 ±.0010]`, so 83.595 mm (or 3.2912 in) also counts, within the same
windows; an answer of 83.60 mm passes. The lower limit, 83.545, fails: the part
can be bigger than that. Code finds these tolerances in the drawing's text when
`build-foundation` runs (`data/envelope-tolerances.csv`), so picture-only
drawings have none.

## Units

- **A stated unit is trusted.** A number labeled mm that only matches as inches
  is wrong, and the answer is marked **unit mix-up**. Example: 2.75 labeled mm
  on a part that is 2.75 in.
- **No units stated:** all the values are read as mm, or all as inch, whichever
  matches better. They are never mixed within one answer.
- **Both units given for one size**, like `Ø8.000 mm (0.3150 in)`, count as one
  value. If either number is right, the value is right.
- Only mm and inch are recognised. A number written as a fraction, like `5/8`
  or `1 3/8`, is read as its decimal (0.625, 1.375).

## The verdict

- **CUBE values match in any order.** The labels a model uses (thickness, width,
  length) don't matter; 69.9 × 38.1 × 69.9 grades the same as 38.1 × 69.9 × 69.9.
  A size that appears twice, like 69.9 and 69.9, must be given twice.
- **Cylinder:** diameter and length, and they are **not** interchangeable.
  The reply's diameter must match your diameter, and its length your length. A
  reply that swaps them fails. A reply like `Ø10 × 75` that names only the
  diameter is fine; the other number is the length. A reply that names neither
  isn't graded; it's flagged for you to look at.
- **Why CUBE sizes can be in any order but cylinder sizes can't:** flat stock is
  ordered by its three sizes, not by which face is which. A cylinder's diameter
  and length are different things.
- **Strict pass:** every dimension found, nothing missing, nothing extra. One
  wrong value fails the answer.
- **Dims correct:** how many dimensions were found, out of 3 for a CUBE or 2 for
  a cylinder, and which ones were missed (label and axis). This shows partial
  credit that pass/fail hides.
- **A cylinder answered with 3 values** fails with an extra value. Only a
  value named as the diameter or the length can count toward dims correct.
- **One part of a chain:** models rarely add chains up yet. When a reply gives
  one printed part instead of the total, it fails, and the result says so (for
  example "Thk (Z) missed: gave 34.29 mm, one part of the chain 34.29 + 6.35 =
  40.64") so you can see it at a glance.
- **Replies that can't be read** are not scored. If the step that pulls numbers
  out of a reply is unsure, or the reply has no clear final answer, the reply is
  flagged for a person to look at. It is never guessed.

## The one known cost

A model that converts a printed number itself and rounds more coarsely than the
print fails. On 201057-002 the width is printed `276.2 [10.88]`. 10.88 in is
276.352 mm, so an answer of 276.4 mm is 0.048 mm from the nearest accepted
reading and fails. Accepting it would need a ±0.05 mm window, and that would
also pass the wrong 19.0 on 201551-016 (its .75 in converts to 19.05 mm).
Failing the occasional coarse conversion is the smaller problem.

## Tolerance audit

Every pass that relied on a converted reading or an upper tolerance limit,
rather than a number printed on the sheet, is listed in the report for
reference.
