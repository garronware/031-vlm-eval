# VLM accuracy when extracting bounding dimensions from 2D engineering drawings

*141 drawings, each answered once by each of 3 models.*

**Abstract.** This report measures how often 3 vision-language models (VLMs) return the correct bounding dimensions of a machined part from its 2D engineering drawing. The evaluator sent 141 drawings to Claude Opus 5, GPT-5.6 Sol and Gemini 3.1 Pro (preview) with the same one-line prompt, and code graded every answer against sizes the evaluator recorded by hand. On each model's first answer (run 1), GPT-5.6 Sol passed 138 of 140 drawings (99%, 95% range 95% to 100%), Claude Opus 5 passed 130 of 140 drawings (93%, 95% range 87% to 97%) and Gemini 3.1 Pro (preview) passed 121 of 139 drawings (87%, 95% range 80% to 92%). The 95% ranges separate GPT-5.6 Sol from Gemini 3.1 Pro (preview); the other models' ranges overlap, so 141 drawings are too few to rank them. Of the 35 sizes the models missed in run 1, Axis mapping accounts for 19. An AI model proposed a failure label for each missed size, and the evaluator reviewed every label.

## 1 Introduction

A part's bounding dimensions are the overall sizes of the stock it is machined from. A part cut from rectangular stock (a cuboid, CUBE in this report) has three: thickness, width and length. A part cut from round stock (a cylinder, CYL) has two: diameter and length. A machinist reads them from the part's engineering drawing before choosing material, workholding and operations. [Why this matters](../../README.md#why-this-matters), in the repository's main README, explains why the evaluator measured them.

This report asks one question: how often does a general-purpose vision-language model (VLM), an AI model that reads images as well as text, return every bounding dimension of a part correctly when given only the part's drawing?

Each model answered each drawing once, so this evaluation does not measure run-to-run consistency. The repository's [main README](../../README.md#results) lists every evaluation and says which drawings and answers they share.

## 2 Method

### 2.1 Drawings and recorded sizes

Each drawing is a PDF of one machined part; none is an assembly. The evaluation uses all 141 drawings in the repository.

78 parts are cuboids and 63 are cylinders. 128 drawings print every size in millimetres with inches in brackets, and 13 print inches only. 99 PDFs carry a text layer, so a model can read their numbers as text; 42 are images only. On 4 drawings at least one bounding dimension is never printed whole: the reader must add printed dimensions together, which this report calls a chain.

The evaluator recorded each part's bounding dimensions by hand from its drawing, in [`drawings/ground-truth.md`](../../drawings/ground-truth.md). On drawings that print both units, the evaluator recorded the millimetre value, and code found the inch value printed beside it. A chain is recorded as its parts and their sum.

### 2.2 Models and prompt

Each model received the drawing's PDF file unchanged and this prompt, with no system prompt and no other instructions:

> Return bounding dimensions for this part. If the part would be made from round stock, give cylindrical bounding dimensions (Dia, L). If it would be made from rectangular stock, give cuboid bounding dimensions (Thk, W, L).

Each model answered 141 drawings once. Each answer came from a fresh conversation with no memory of earlier answers. The models answered between 2026-09-20 and 2026-10-03, each at its maker's default thinking setting.

**Table 1.** The models tested.

| Model | Version | Maker's default thinking setting |
|---|---|---|
| Claude Opus 5 | `claude-opus-5` | adaptive thinking, effort high |
| GPT-5.6 Sol | `gpt-5.6-sol` | reasoning effort medium |
| Gemini 3.1 Pro (preview) | `gemini-3.1-pro-preview` | thinking level high |

### 2.3 Grading

Code decides whether an answer passes; no person or AI model judges it. A small AI model (`claude-haiku-4-5-20251001`) copies the numbers out of each free-text reply and never sees the drawing or judges the numbers.

An answer passes only when it matches every recorded size and adds no extra size. A size matches when the answer is within 0.02 mm of the printed millimetre value or within 0.0005 in of the printed inch value, or of either one converted to the other unit. On drawings printed in inches only, a millimetre answer must be within 0.05 mm of the exact conversion. A size printed with a plus-or-minus tolerance also matches at its upper limit, because the part can be that large.

A cuboid's three sizes may come in any order, because stock is ordered by its three sizes, not by which face is which. A cylinder's diameter and length may not be swapped. A cylinder answered as the box it fills (diameter, diameter, length) also passes. A chain matches when the answer gives its sum.

The 95% range given with each pass rate is an exact binomial range: the span of true pass rates that could plausibly produce the count observed. [The grading rules](../../docs/scoring-rules.md) give every detail.

### 2.4 Failure labels

Each size a model missed gets one label that says why the model missed it. Claude, an AI model made by Anthropic, studied the drawing and proposed a label with evidence from the sheet. The evaluator reviewed every proposed label and kept or changed it. A failure that repeats an earlier one (the same drawing, missed size and wrong number) takes the evaluator's earlier label. Claude also labelled failures by Anthropic's own model, which is one reason the evaluator reviewed every label. The evaluator kept Claude's label on 30 of 33 (91%, 95% range 76% to 98%) and changed the rest. [`tables/label-review.csv`](tables/label-review.csv) holds these counts; it is the one table built from the evaluator's review record rather than from [`every-run.csv`](every-run.csv).

Appendix A defines the labels, and Appendix B gives one example of each.

## 3 Results

### 3.1 Pass rate by model

The table counts each model's first answer (run 1) to each drawing, so each drawing counts once per model. GPT-5.6 Sol passed 138 of 140 drawings (99%, 95% range 95% to 100%), Claude Opus 5 passed 130 of 140 drawings (93%, 95% range 87% to 97%) and Gemini 3.1 Pro (preview) passed 121 of 139 drawings (87%, 95% range 80% to 92%). The 95% ranges separate GPT-5.6 Sol from Gemini 3.1 Pro (preview); the other models' ranges overlap, so 141 drawings are too few to rank them.

**Table 2.** Drawings passed per model, run 1. Sizes right counts every recorded size, and each part of a chain, separately. The row for all models has no range (see Limitations). Source: [`tables/pass-rate-by-model.csv`](tables/pass-rate-by-model.csv).

| Model | Drawings passed | Pass rate | 95% range | Sizes right |
|---|---|---|---|---|
| Claude Opus 5 | 130 of 140 | 93% | 87% to 97% | 351 of 362 |
| GPT-5.6 Sol | 138 of 140 | 99% | 95% to 100% | 360 of 362 |
| Gemini 3.1 Pro (preview) | 121 of 139 | 87% | 80% to 92% | 336 of 359 |
| All three models | 389 of 419 | 93% | none | 1047 of 1083 |

![Drawings passed per model in run 1, with 95% ranges.](charts/pass-rate-by-model.png)

*Figure 1. Drawings passed per model in run 1, with 95% ranges.*

### 3.2 Missed sizes by failure label

The models missed 35 sizes in run 1. Axis mapping accounts for 19 of them.

**Table 3.** Missed sizes in run 1 by failure label and model. Source: [`tables/failures-by-label.csv`](tables/failures-by-label.csv). The same sizes by axis are in [`tables/failures-by-axis.csv`](tables/failures-by-axis.csv) and by size name in [`tables/failures-by-dimension.csv`](tables/failures-by-dimension.csv).

| Label | Claude Opus 5 | GPT-5.6 Sol | Gemini 3.1 Pro (preview) | Total |
|---|---|---|---|---|
| Axis mapping | 3 | 0 | 16 | 19 |
| Chain aggregation | 0 | 1 | 0 | 1 |
| Datum reconstruction | 1 | 0 | 1 | 2 |
| Feature substitution | 2 | 1 | 3 | 6 |
| Over-aggregation | 4 | 0 | 2 | 6 |
| Unclassified | 1 | 0 | 0 | 1 |

![Missed sizes in run 1 by failure label.](charts/failures-by-label.png)

*Figure 2. Missed sizes in run 1 by failure label.*

### 3.3 Results by kind of drawing

Each cell gives drawings passed in run 1, the pass rate and its 95% range. A group with fewer than 5 drawings shows only the count, because a rate from so few drawings would mislead. The column for all models has no range, for the reason given under limitations.

**Table 4.** Run 1 results by where the size comes from. Source: [`tables/by-dimension-origin.csv`](tables/by-dimension-origin.csv).

| Group | Claude Opus 5 | GPT-5.6 Sol | Gemini 3.1 Pro (preview) | All three models |
|---|---|---|---|---|
| Chain: the reader must add printed dimensions, 4 drawings | 3 of 4 | 4 of 4 | 2 of 4 | 9 of 12 |
| Printed as one dimension, 136 drawings | 127 of 136, 93% (88% to 97%) | 134 of 136, 99% (95% to 100%) | 119 of 135, 88% (81% to 93%) | 380 of 407, 93% |

**Table 5.** Run 1 results by shape of the part. Source: [`tables/by-shape.csv`](tables/by-shape.csv).

| Group | Claude Opus 5 | GPT-5.6 Sol | Gemini 3.1 Pro (preview) | All three models |
|---|---|---|---|---|
| Cuboid (CUBE), 78 drawings | 72 of 78, 92% (84% to 97%) | 76 of 78, 97% (91% to 100%) | 61 of 77, 79% (68% to 88%) | 209 of 233, 90% |
| Cylinder (CYL), 62 drawings | 58 of 62, 94% (84% to 98%) | 62 of 62, 100% (94% to 100%) | 60 of 62, 97% (89% to 100%) | 180 of 186, 97% |

**Table 6.** Run 1 results by kind of PDF. Source: [`tables/by-pdf-type.csv`](tables/by-pdf-type.csv).

| Group | Claude Opus 5 | GPT-5.6 Sol | Gemini 3.1 Pro (preview) | All three models |
|---|---|---|---|---|
| Image-only PDF, 42 drawings | 37 of 42, 88% (74% to 96%) | 42 of 42, 100% (92% to 100%) | 36 of 42, 86% (71% to 95%) | 115 of 126, 91% |
| PDF with a text layer, 98 drawings | 93 of 98, 95% (88% to 98%) | 96 of 98, 98% (93% to 100%) | 85 of 97, 88% (79% to 93%) | 274 of 293, 94% |

**Table 7.** Run 1 results by units printed on the drawing. Source: [`tables/by-print-type.csv`](tables/by-print-type.csv).

| Group | Claude Opus 5 | GPT-5.6 Sol | Gemini 3.1 Pro (preview) | All three models |
|---|---|---|---|---|
| Millimetres and inches, 128 drawings | 120 of 128, 94% (88% to 97%) | 126 of 128, 98% (94% to 100%) | 112 of 128, 88% (80% to 93%) | 358 of 384, 93% |
| Inches only, 12 drawings | 10 of 12, 83% (52% to 98%) | 12 of 12, 100% (74% to 100%) | 9 of 11, 82% (48% to 98%) | 31 of 35, 89% |

## 4 Limitations

- The "All three models" row has no 95% range. All the models answered the same drawings, so their answers are not independent tries, and a range that treated them as independent would be too narrow.
- Only 4 drawings need a chain, so the chain results are counts, not rates.
- Every answer responds to one prompt wording. The evaluation does not show how answers change under other wordings.
- Each model ran at its maker's default thinking setting. The evaluation does not test other settings.
- One person, the evaluator, recorded every bounding dimension and reviewed every failure label. No second person checked them.
- Code reads printed tolerances only from PDFs with a text layer, so on image-only PDFs only the nominal size matches.
- Code could not grade 4 of 423 replies, because the small AI model that copies out numbers flagged those replies as unreadable. Those replies count as neither pass nor fail, and [`every-run.csv`](every-run.csv) marks them NOT GRADED.
- 1 passes in run 1 relied on a number not printed as written: the model converting a printed number between millimetres and inches itself, or giving a size's upper tolerance limit. Appendix C lists them.

## 5 Data and code

- [`every-run.csv`](every-run.csv): one row per reply: the recorded sizes, the values returned, the verdict, sizes right, sizes missed, and the evaluator's label and evidence for each missed size
- [`tables/`](tables/): every table this report quotes, as CSV
- [`charts/`](charts/): each figure as a picture, with the numbers it draws beside it as CSV
- [`raw-replies/`](raw-replies/): every model's full reply, word for word
- [`run-settings.json`](run-settings.json): the models, versions, thinking settings, dates and prompt
- [`LICENSE-NOTICE.md`](LICENSE-NOTICE.md): the license these drawing-derived files fall under

The code, the drawings and the recorded sizes are in this repository. [The user guide](../../docs/user-guide.md) explains how to run the evaluation on other models.

## Appendix A: Failure labels

**Table 8.** The failure labels and their definitions. Source: [the diagnosis playbook](../../docs/diagnosis-playbook.md).

| Label | Definition |
|---|---|
| Proximity association | Found the right dimension line but took a nearby, unrelated number instead of the one that belongs to the line. |
| Axis mapping | Chose a dimension from the wrong axis. |
| Chain aggregation | Failed to chain dimensions, chained the wrong dimensions, or failed to subtract a dimension that overlapped. |
| Datum reconstruction | A chain aggregation failure that happened *because* the dimensions start from an internal datum instead of an outer part edge. The model missed the datum-to-edge segment on the other side of the datum. |
| Over-aggregation | Added a printed size to one that already includes it, so the size comes out too big (e.g. a flange thickness added to a length that already includes the flange). |
| Feature substitution | Correctly read a real dimension in the right axis, but that dimension belongs to a feature, not the outer envelope (e.g. main-body Ø instead of a larger flange Ø, pocket depth, hole spacing). |
| Unclassified | None fit, or the evidence is unclear. Goes to the evaluator. |

## Appendix B: One example of each failure label

Each example is the first reply in [`every-run.csv`](every-run.csv) with that label, taking run 1 first. The evidence is the evaluator's reason where the evaluator changed Claude's label, and Claude's note where the evaluator kept it.

**Axis mapping.** Drawing 17872-006, Gemini 3.1 Pro (preview), run 1.
- Recorded sizes: Thk (Z) 2 in; W (X) 29.62 in; L (Y) 33.00 in
- The model gave: Thickness 1.00; Width 27.00; Length 33.00
- Missed: W (X)
- Evidence: 27.00 TYP. is an ordinate in the column at the left edge of the plan view, near the bottom: it gives the position down the sheet (Y) where the lower-left 45 degree chamfer starts (33.00 less the 6.00 TYP. chamfer). It runs the same way as the 33.00 O.A.L. length Gemini already had right, and it filled the X width it couldn't find. The width is the 29.62 O.A.L. ordinate printed rotated at the upper right of the plan view (zoom 17872-006-0.76-0.38-0.83-0.5-400dpi.png; its rotated text is not in the text layer, so it can't be cited). Same failure as the evaluator's 201513 and 201516 rulings: a feature position along a size already found, used for a missing size.

**Chain aggregation.** Drawing 201551-017, GPT-5.6 Sol, run 1.
- Recorded sizes: Thk (Z) 100.5 mm; W (X) 57.2 mm; L (Y) 114.3 mm
- The model gave: 57.2 mm (2.25); 87.8 mm (3.45); 114.3 mm (4.50)
- Missed: Thk (Z)
- Evidence: GPT gave 87.8, one piece of 12.7 + 87.8 = 100.5 in the side view; taking a piece is Chain aggregation even though 100.5 is printed in the top view.

**Datum reconstruction.** Drawing 201516, Gemini 3.1 Pro (preview), run 1.
- Recorded sizes: Thk (Z) 25.4 mm; W (X) 62.7 mm; L (Y) 15.6 + 22.5 = 38.1 mm
- The model gave: Thickness/Height 22.5 mm (0.884); Width 32.68 mm (1.287); Length 62.7 mm (2.468)
- Missed: L (Y)
- Evidence: 22.5 is the upper ordinate in the right-side view, measured from a 0 that sits on the bore centreline inside the part, not on an edge. The part's Y extent is 22.5 above that zero plus 15.6 below it, both printed on the same view. Gemini called 22.5 the 'overall vertical dimension' of that view, so it treated the zero as an edge and never looked across the datum for the 15.6 segment. It named the value Thickness, but label names don't count; the number is half of the Y chain.

**Over-aggregation.** Drawing 18202-001, Claude Opus 5, run 1.
- Recorded sizes: Thk (Z) 1.75 in; W (X) 26.00 in; L (Y) 19.00 in
- The model gave: Thickness 4.75 in; Width 19.00 in; Length 29.00 in
- Missed: Thk (Z)
- Evidence: 4.75 is printed nowhere on the sheet: it is not a dimension, and the hole tables at the left hold no 4.750. The side view's only horizontal dimension is the 1.75 thickness (side view, top, 0.31-0.36 across). 1.75 + 2 x 1.50 = 4.75 matches the reply exactly, the same +3.00 the model added to the 26.00 width. The 1.50 X 45° corner chamfers lie in the plan view (X-Y) and cannot change the Z thickness, so this looks like the same chamfer addition applied without regard to direction. The 19.00 length was left alone, and the reply shows no working, so the label is Unclassified. Watch list: over-aggregation

**Feature substitution.** Drawing 17872-006, Gemini 3.1 Pro (preview), run 1.
- Recorded sizes: Thk (Z) 2 in; W (X) 29.62 in; L (Y) 33.00 in
- The model gave: Thickness 1.00; Width 27.00; Length 33.00
- Missed: Thk (Z)
- Evidence: 1.00 TYP. is a horizontal arrow dimension in the right-side view, about halfway down that view: it runs from the view's left face to a step in a hidden-line hole, so it is a feature depth through the plate, along Z. The plan-view callout 'DR. & C'BORE-(TO DIM. SHOWN) ... .75 DIA. C'BORE-(TO DIM. SHOWN) 3 PLACES' (zoom 17872-006-0.66-0.72-0.78-0.8-400dpi.png) sends its depths to this view, so 1.00 is most likely one of those counterbore/push-fit depths. The same view prints the plate's full thickness, 2.00, across its top edge, and 1.00 measures about half that width on the sheet. Gemini read the right axis in the right view but gave a feature depth instead of the overall 2.00. Unlike 201533-020, this view does dimension the thickness; the definition still fits (a real Z dimension that belongs to a feature, like a pocket depth), and the 2.00 is too far from 1.00 for Proximity association.

**Unclassified.** Drawing 201581-008, Claude Opus 5, run 1.
- Recorded sizes: Dia 9.525 mm; L (X) 109.8 mm
- The model gave: Dia. 9.53 mm (0.375); Length 178 mm (7.0)
- Missed: L (X)
- Evidence: 178 is printed nowhere on the sheet. The length is dimensioned once, 109.8 [4.32] from the 0 at the nose end to the pin's left end, above the side view. To the left of that end, the extension lines for the 9.525 [.3750] and 1.5 [.06] FLAT callouts and the thin projection lines to the end view carry the shank's outline further left. Opus read these as 'additional shank', decided 109.8 was not the overall length, and replaced it with the 7.00 in catalogue length of a 3/8 in reamer blank (177.8 mm), which comes from the material note, not the drawing. No label fits a number taken from outside the sheet; it looks like a stock-size substitution, which is on the parked list of possible extra labels.

## Appendix C: Tolerance audit

**Table 9.** Passes in run 1 that relied on a number not printed as written. Source: [`tables/tolerance-audit.csv`](tables/tolerance-audit.csv).

| Drawing | Model | Run | Reading used |
|---|---|---|---|
| 201551-024 | Claude Opus 5 | 1 | Dia: 83.60 mm matched the upper tolerance limit of the printed mm |
