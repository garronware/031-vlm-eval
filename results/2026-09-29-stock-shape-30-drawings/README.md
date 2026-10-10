# VLM accuracy when extracting bounding dimensions from 2D engineering drawings

*30 drawings, each answered 3 times by each of 3 models.*

**Abstract.** This report measures how often 3 vision-language models (VLMs) return the correct bounding dimensions of a machined part from its 2D engineering drawing. The evaluator sent 30 drawings to Claude Opus 5, GPT-5.6 Sol and Gemini 3.1 Pro (preview) with the same one-line prompt, and code graded every answer against sizes the evaluator recorded by hand. On each model's first answer (run 1), GPT-5.6 Sol passed 29 of 30 drawings (97%, 95% range 83% to 100%), Claude Opus 5 passed 26 of 30 drawings (87%, 95% range 69% to 96%) and Gemini 3.1 Pro (preview) passed 26 of 30 drawings (87%, 95% range 69% to 96%). The 95% ranges of all 3 models overlap, so 30 drawings are too few to rank the models. Each model answered each drawing 3 times; each gave the same verdict on every run for between 83% and 93% of the drawings. Of the 10 sizes the models missed in run 1, Axis mapping accounts for 5. An AI model proposed a failure label for each missed size, and the evaluator reviewed every label.

## 1. Introduction

A part's bounding dimensions are the overall sizes of the stock it is machined from. A part cut from rectangular stock (a cuboid, CUBE in this report) has three: thickness, width and length. A part cut from round stock (a cylinder, CYL) has two: diameter and length. A machinist reads them from the part's engineering drawing before choosing material, workholding and operations. [Why this matters](../../README.md#why-this-matters), in the repository's main README, explains why the evaluator measured them.

This report asks one question: how often does a general-purpose vision-language model (VLM), an AI model that reads images as well as text, return every bounding dimension of a part correctly when given only the part's drawing?

Each model answered each drawing 3 times, so this evaluation also measures whether a model gives the same verdict every time it sees the same drawing. The repository's [main README](../../README.md#results) lists every evaluation and says which drawings and answers they share.

## 2. Method

### 2.1. Drawings and recorded sizes

Each drawing is a PDF of one machined part; none is an assembly. These 30 drawings are a fixed subset of the 141 drawings in the repository, chosen once to mix shapes, units and kinds of PDF and to include every drawing whose size must be added up from printed dimensions. The same drawings are used every time, so runs on different days compare fairly.

16 parts are cuboids and 14 are cylinders. 27 drawings print every size in millimetres with inches in brackets, and 3 print inches only. 21 PDFs carry a text layer, so a model can read their numbers as text; 9 are images only. On 4 drawings at least one bounding dimension is never printed whole: the reader must add printed dimensions together, which this report calls a chain.

The evaluator recorded each part's bounding dimensions by hand from its drawing, in [`drawings/ground-truth.md`](../../drawings/ground-truth.md). On drawings that print both units, the evaluator recorded the millimetre value, and code found the inch value printed beside it. A chain is recorded as its parts and their sum.

### 2.2. Models and prompt

Each model received the drawing's PDF file unchanged and this prompt, with no system prompt and no other instructions:

> Return bounding dimensions for this part. If the part would be made from round stock, give cylindrical bounding dimensions (Dia, L). If it would be made from rectangular stock, give cuboid bounding dimensions (Thk, W, L).

Each model answered 30 drawings 3 times. Each answer came from a fresh conversation with no memory of earlier answers. The models answered between 2026-09-20 and 2026-09-29, each at its maker's default thinking setting.

**Table 1.** The models tested.

| Model | Version | Maker's default thinking setting |
|---|---|---|
| Claude Opus 5 | `claude-opus-5` | adaptive thinking, effort high |
| GPT-5.6 Sol | `gpt-5.6-sol` | reasoning effort medium |
| Gemini 3.1 Pro (preview) | `gemini-3.1-pro-preview` | thinking level high |

### 2.3. Grading

Code decides whether an answer passes; no person or AI model judges it. A small AI model (`claude-haiku-4-5-20251001`) copies the numbers out of each free-text reply and never sees the drawing or judges the numbers.

An answer passes only when it matches every recorded size and adds no extra size. A size matches when the answer is within 0.02 mm of the printed millimetre value or within 0.0005 in of the printed inch value, or of either one converted to the other unit. On drawings printed in inches only, a millimetre answer must be within 0.05 mm of the exact conversion. A size printed with a plus-or-minus tolerance also matches at its upper limit, because the part can be that large.

A cuboid's three sizes may come in any order, because stock is ordered by its three sizes, not by which face is which. A cylinder's diameter and length may not be swapped. A cylinder answered as the box it fills (diameter, diameter, length) also passes. A chain matches when the answer gives its sum.

The 95% range given with each pass rate is an exact binomial range: the span of true pass rates that could plausibly produce the count observed. [The grading rules](../../docs/scoring-rules.md) give every detail.

### 2.4. Failure labels

Each size a model missed gets one label that says why the model missed it. Claude, an AI model made by Anthropic, studied the drawing and proposed a label with evidence from the sheet. The evaluator reviewed every proposed label and kept or changed it. A failure that repeats an earlier one (the same drawing, missed size and wrong number) takes the evaluator's earlier label. Claude also labelled failures by Anthropic's own model, which is one reason the evaluator reviewed every label. The evaluator kept Claude's label on 20 of 24 (83%, 95% range 63% to 95%) and changed the rest. [`tables/label-review.csv`](tables/label-review.csv) holds these counts; it is the one table built from the evaluator's review record rather than from [`every-run.csv`](every-run.csv).

Appendix A defines the labels, and Appendix B gives one example of each.

## 3. Results

### 3.1. Pass rate by model

The table counts each model's first answer (run 1) to each drawing, so each drawing counts once per model. GPT-5.6 Sol passed 29 of 30 drawings (97%, 95% range 83% to 100%), Claude Opus 5 passed 26 of 30 drawings (87%, 95% range 69% to 96%) and Gemini 3.1 Pro (preview) passed 26 of 30 drawings (87%, 95% range 69% to 96%). The 95% ranges of all 3 models overlap, so 30 drawings are too few to rank the models.

**Table 2.** Drawings passed per model, run 1. Sizes right counts every recorded size, and each part of a chain, separately. The row for all models has no range (see Limitations). Source: [`tables/pass-rate-by-model.csv`](tables/pass-rate-by-model.csv).

| Model | Drawings passed | Pass rate | 95% range | Sizes right |
|---|---|---|---|---|
| Claude Opus 5 | 26 of 30 | 87% | 69% to 96% | 76 of 80 |
| GPT-5.6 Sol | 29 of 30 | 97% | 83% to 100% | 79 of 80 |
| Gemini 3.1 Pro (preview) | 26 of 30 | 87% | 69% to 96% | 74 of 80 |
| All three models | 81 of 90 | 90% | none | 229 of 240 |

![Drawings passed per model in run 1, with 95% ranges.](charts/pass-rate-by-model.png)

*Figure 1. Drawings passed per model in run 1, with 95% ranges.*

### 3.2. Consistency across runs

A drawing counts as consistent for a model when the model passed it on every run or failed it on every run. A mixed drawing passed on some runs and failed on others. The share of drawings with the same verdict on every run was 93% for GPT-5.6 Sol, 87% for Claude Opus 5 and 83% for Gemini 3.1 Pro (preview), each out of the 30 drawings it answered more than once.

**Table 3.** Verdicts per model across runs. Source: [`tables/consistency-by-model.csv`](tables/consistency-by-model.csv). Each drawing's runs passed are in [`tables/runs-passed-per-drawing.csv`](tables/runs-passed-per-drawing.csv).

| Model | Drawings run more than once | Passed every run | Mixed | Failed every run |
|---|---|---|---|---|
| Claude Opus 5 | 30 | 24 | 4 | 2 |
| GPT-5.6 Sol | 30 | 27 | 2 | 1 |
| Gemini 3.1 Pro (preview) | 30 | 22 | 5 | 3 |

![Share of drawings each model passed every run, failed every run, or mixed.](charts/consistency-by-model.png)

*Figure 2. Share of drawings each model passed every run, failed every run, or mixed.*

### 3.3. Missed sizes by failure label

The models missed 10 sizes in run 1. Axis mapping accounts for 5 of them.

**Table 4.** Missed sizes in run 1 by failure label and model. Source: [`tables/failures-by-label.csv`](tables/failures-by-label.csv). The same sizes by axis are in [`tables/failures-by-axis.csv`](tables/failures-by-axis.csv) and by size name in [`tables/failures-by-dimension.csv`](tables/failures-by-dimension.csv).

| Label | Claude Opus 5 | GPT-5.6 Sol | Gemini 3.1 Pro (preview) | Total |
|---|---|---|---|---|
| Axis mapping | 1 | 0 | 4 | 5 |
| Datum reconstruction | 1 | 0 | 1 | 2 |
| Feature substitution | 0 | 1 | 0 | 1 |
| Over-aggregation | 1 | 0 | 0 | 1 |
| Unclassified | 1 | 0 | 0 | 1 |

![Missed sizes in run 1 by failure label.](charts/failures-by-label.png)

*Figure 3. Missed sizes in run 1 by failure label.*

### 3.4. Results by kind of drawing

Each cell gives drawings passed in run 1, the pass rate and its 95% range. A group with fewer than 5 drawings shows only the count, because a rate from so few drawings would mislead. The column for all models has no range, for the reason given under limitations.

**Table 5.** Run 1 results by where the size comes from. Source: [`tables/by-dimension-origin.csv`](tables/by-dimension-origin.csv).

| Group | Claude Opus 5 | GPT-5.6 Sol | Gemini 3.1 Pro (preview) | All three models |
|---|---|---|---|---|
| Chain: the reader must add printed dimensions, 4 drawings | 3 of 4 | 4 of 4 | 2 of 4 | 9 of 12 |
| Printed as one dimension, 26 drawings | 23 of 26, 88% (70% to 98%) | 25 of 26, 96% (80% to 100%) | 24 of 26, 92% (75% to 99%) | 72 of 78, 92% |

**Table 6.** Run 1 results by shape of the part. Source: [`tables/by-shape.csv`](tables/by-shape.csv).

| Group | Claude Opus 5 | GPT-5.6 Sol | Gemini 3.1 Pro (preview) | All three models |
|---|---|---|---|---|
| Cuboid (CUBE), 16 drawings | 15 of 16, 94% (70% to 100%) | 15 of 16, 94% (70% to 100%) | 13 of 16, 81% (54% to 96%) | 43 of 48, 90% |
| Cylinder (CYL), 14 drawings | 11 of 14, 79% (49% to 95%) | 14 of 14, 100% (77% to 100%) | 13 of 14, 93% (66% to 100%) | 38 of 42, 90% |

**Table 7.** Run 1 results by kind of PDF. Source: [`tables/by-pdf-type.csv`](tables/by-pdf-type.csv).

| Group | Claude Opus 5 | GPT-5.6 Sol | Gemini 3.1 Pro (preview) | All three models |
|---|---|---|---|---|
| Image-only PDF, 9 drawings | 7 of 9, 78% (40% to 97%) | 9 of 9, 100% (66% to 100%) | 8 of 9, 89% (52% to 100%) | 24 of 27, 89% |
| PDF with a text layer, 21 drawings | 19 of 21, 90% (70% to 99%) | 20 of 21, 95% (76% to 100%) | 18 of 21, 86% (64% to 97%) | 57 of 63, 90% |

**Table 8.** Run 1 results by units printed on the drawing. Source: [`tables/by-print-type.csv`](tables/by-print-type.csv).

| Group | Claude Opus 5 | GPT-5.6 Sol | Gemini 3.1 Pro (preview) | All three models |
|---|---|---|---|---|
| Millimetres and inches, 27 drawings | 24 of 27, 89% (71% to 98%) | 26 of 27, 96% (81% to 100%) | 23 of 27, 85% (66% to 96%) | 73 of 81, 90% |
| Inches only, 3 drawings | 2 of 3 | 3 of 3 | 3 of 3 | 8 of 9 |

## 4. Limitations

- The pass rates use run 1 only, so each drawing counts once per model. Counting every run would count the drawings that ran more than once several times over and make the ranges look narrower than the evidence supports. The later runs feed only the consistency results.
- The "All three models" row has no 95% range. All the models answered the same drawings, so their answers are not independent tries, and a range that treated them as independent would be too narrow.
- Only 4 drawings need a chain, so the chain results are counts, not rates.
- Every answer responds to one prompt wording. The evaluation does not show how answers change under other wordings.
- Each model ran at its maker's default thinking setting. The evaluation does not test other settings.
- One person, the evaluator, recorded every bounding dimension and reviewed every failure label. No second person checked them.
- Code reads printed tolerances only from PDFs with a text layer, so on image-only PDFs only the nominal size matches.
- Code could not grade 1 of 270 replies, because the small AI model that copies out numbers flagged that reply as unreadable. That reply counts as neither pass nor fail, and [`every-run.csv`](every-run.csv) marks it NOT GRADED.
- No pass in run 1 relied on a model converting a printed number between millimetres and inches, or on a tolerance limit: every passing size matched a printed number.

## 5. Data and code

- [`every-run.csv`](every-run.csv): one row per reply: the recorded sizes, the values returned, the verdict, sizes right, sizes missed, and the evaluator's label and evidence for each missed size
- [`tables/`](tables/): every table this report quotes, as CSV
- [`charts/`](charts/): each figure as a picture, with the numbers it draws beside it as CSV
- [`raw-replies/`](raw-replies/): every model's full reply, word for word
- [`run-settings.json`](run-settings.json): the models, versions, thinking settings, dates and prompt
- [`LICENSE-NOTICE.md`](LICENSE-NOTICE.md): the license these drawing-derived files fall under

The code, the drawings and the recorded sizes are in this repository. [The user guide](../../docs/user-guide.md) explains how to run the evaluation on other models.

## Appendix A: Failure labels

**Table 9.** The failure labels and their definitions. Source: [the diagnosis playbook](../../docs/diagnosis-playbook.md).

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

**Axis mapping.** Drawing 200951, Gemini 3.1 Pro (preview), run 1.
- Recorded sizes: Thk (Z) 34.29 + 6.35 = 40.64 mm; W (X) 91.0 mm; L (Y) 72.91 mm
- The model gave: Thickness 35.560 mm (1.40000); Width 72.90 mm (2.870); Length 91.000 mm (3.58268)
- Missed: Thk (Z)
- Evidence: 35.560 [1.40000] is a boxed vertical ordinate on the right of the left side view: it places the centre of the large counterbored bore 35.560 down from the 0 line through the top hole centres, so it runs along Y (the same vertical direction as the 72.91 [2.870] length in the front view). The thickness is the horizontal ordinate row above that same view, 34.29 [1.350] on one side of 0 and 6.35 [0.250] on the other. Gemini said it read 35.560 'along the horizontal axis', so it took a vertical Y-axis hole position as the Z thickness; it also gave 72.90 as its width, so Y was used twice. It gave neither printed chain part, so this is not a chain or datum failure.

**Datum reconstruction.** Drawing 201516, Gemini 3.1 Pro (preview), run 1.
- Recorded sizes: Thk (Z) 25.4 mm; W (X) 62.7 mm; L (Y) 15.6 + 22.5 = 38.1 mm
- The model gave: Thickness/Height 22.5 mm (0.884); Width 32.68 mm (1.287); Length 62.7 mm (2.468)
- Missed: L (Y)
- Evidence: 22.5 is the upper ordinate in the right-side view, measured from a 0 that sits on the bore centreline inside the part, not on an edge. The part's Y extent is 22.5 above that zero plus 15.6 below it, both printed on the same view. Gemini called 22.5 the 'overall vertical dimension' of that view, so it treated the zero as an edge and never looked across the datum for the 15.6 segment. It named the value Thickness, but label names don't count; the number is half of the Y chain.

**Over-aggregation.** Drawing 201258-012, Claude Opus 5, run 1.
- Recorded sizes: Dia 90.4 mm; L (Y) 57.150 mm
- The model gave: Diameter 90.4 mm (3.56); Length 65.1 mm (2.56)
- Missed: L (Y)
- Evidence: Opus added the 7.9 flange to 57.150, which is already the full length.

**Feature substitution.** Drawing 201533-020, GPT-5.6 Sol, run 1.
- Recorded sizes: Thk (Z) 12.700 mm; W (X) 215.9 mm; L (Y) 184.2 mm
- The model gave: Thk 6.35 mm (0.250); W 184.2 mm (7.25); L 215.9 mm (8.50)
- Missed: Thk (Z)
- Evidence: Thickness could be shown in this view, roughly where 6.35 appears; the model substituted a hole position for the thickness.

**Unclassified.** Drawing 201581-008, Claude Opus 5, run 1.
- Recorded sizes: Dia 9.525 mm; L (X) 109.8 mm
- The model gave: Dia. 9.53 mm (0.375); Length 178 mm (7.0)
- Missed: L (X)
- Evidence: 178 is printed nowhere on the sheet. The length is dimensioned once, 109.8 [4.32] from the 0 at the nose end to the pin's left end, above the side view. To the left of that end, the extension lines for the 9.525 [.3750] and 1.5 [.06] FLAT callouts and the thin projection lines to the end view carry the shank's outline further left. Opus read these as 'additional shank', decided 109.8 was not the overall length, and replaced it with the 7.00 in catalogue length of a 3/8 in reamer blank (177.8 mm), which comes from the material note, not the drawing. No label fits a number taken from outside the sheet; it looks like a stock-size substitution, which is on the parked list of possible extra labels.

## Appendix C: Tolerance audit

No pass in run 1 relied on a converted number or a tolerance limit.
