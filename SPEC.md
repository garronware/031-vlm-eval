# SPEC: VLM Bounding-Dimension Evaluation

Owner: Garron Ware
Date: 2026-09-15
Status: approved design, ready to build

This spec replaces `brainstorming-starter.md` wherever the two disagree.

---

## 1. What we're building

A system that measures how well frontier vision-language models pull the
bounding (envelope) dimensions off real 2D engineering drawings. It sends
each drawing to the models, scores every answer against Garron's ground
truth, explains why failures happened, and produces a data package that the
whitepaper project in Claude Cowork turns into a research note.

v1 covers the 141 drawings in `drawings/`. The design has to support larger
evaluations later (more hand-checked drawings, e.g. 1,000 or 5,000). It is
not a production extraction tool for the unlabeled archive.

---

## 2. Decisions and why

### 2.1 Input and prompt

| Decision | Why |
|---|---|
| Models receive the **PDF file as-is**. | Matches how people actually use these models today. |
| Each drawing is tagged **text PDF** (99) or **image-only PDF** (42), and the report splits results by this tag. | Text PDFs let a model read numbers without "seeing" the drawing. Splitting keeps that from quietly skewing the headline number. |
| Two prompts, each with its own saved calls (`runs/calls/main/` and `runs/calls/main-stock-shape/`). **`bare`:** `return bounding dimensions for this part`. **`stock-shape` (adopted 2026-09-20, the default for new runs):** "Return bounding dimensions for this part. If the part would be made from round stock, give cylindrical bounding dimensions (Dia, L). If it would be made from rectangular stock, give cuboid bounding dimensions (Thk, W, L)." | The bare prompt is how anyone would ask, and stays as the baseline. But "bounding dimensions" has two honest readings for a round part with material milled away — the stock envelope Garron's table records, and the smaller box round the finished shape — so the bare prompt asks a question the ground truth doesn't answer. Naming the shape closes that gap without doing the reading for the model. No system prompt either way. |
| Replies are **free text**. A separate extraction step (2.12) pulls out shape, values, and units afterward, and the raw reply is always kept. | Keeps the model's experience identical to a normal chat. |
| Each run is an independent call with no memory of earlier runs. The maker's default sampling settings are used and recorded. | Makes run-to-run consistency measurable. |

**Pilot for the `stock-shape` prompt (2026-09-20, 18 calls, $1.20).** The six drawings
whose wording caused grading arguments, sent to all three models. Every reply came back
as exactly Dia and L — no boxes, no second envelope — so the ambiguity is gone. 15 of 18
passed against 12 of 18 for the same replies under the bare prompt, but those six were
chosen because they were the hard cases, so that gain is not a rate. Two lessons: Opus
and GPT answered 201551-019 as Ø31.75 x 47.36, the row exactly, where the bare prompt
got the machined box; and Opus got *worse* on 201581-008 (length 177.8 for 109.8), so
the wording changes what a model attends to, not only how it formats. Calls cost about
50% more, because the models think longer.

### 2.2 Ground truth

- `drawings/ground-truth.md` stays the human-edited source. Code generates a
  clean machine-readable copy from it; nobody hand-edits the copy.
- New column `dimension_origin`:
  - `calculated_chain`: 200951, 201516, 90-100012, 90-100013
  - `explicitly_dimensioned`: the other 137 drawings
  - `calculated_trig` from the starter doc is dropped.
- Chain cells like `15.6 + 22.5 = 38.1` are parsed so both the total and the
  segments are known. Diagnosis uses the segments.
- Ground truth records where each chain is measured from, in the
  `Measured From` column: `Part Edge` (zero at an outside edge, the normal case)
  or `In-Between Edges` (zero sits between the part's two edges, so the bounding
  dimension is the sum of two dimensions on opposite sides of zero). This fact
  cannot be worked out from the drawing data and is Garron's to record.
  - `In-Between Edges`: all 4 (200951, 201516, 90-100012-B, 90-100013-A)
  - **Changed 2026-09-24 (Garron):** 90-100012-B and 90-100013-A were recorded as
    `Part Edge`. On both sheets the 0 sits on a shoulder face partway along the part,
    and the length is dimensioned out both ways from it: 6.50 and 1.00 on 90-100012-B,
    3.83 and 1.13 on 90-100013-A. That is the In-Between Edges definition. The
    diagnosis agent raised it in Chunk 8.
- **Correction from the first 30-drawing run (2026-09-19):** 90-100013-A's length was
  recorded as `3.83 + 1.00 = 4.83` but is `3.83 + 1.13 = 4.96`. Both segments are
  printed on the sheet, and all three models read it as 4.96. Garron corrected
  `ground-truth.md`; `data/` was rebuilt and the run re-scored for $0. Disagreement
  between every model and one ground-truth cell is worth a look, but the table stays
  Garron's to change — code never edits it.
- **Correction from the 141-drawing run (2026-10-09):** 90-100009-A's diameter was
  recorded as 1.489 but is 1.609. All three models answered 1.609; Garron checked the
  sheet and corrected `ground-truth.md`. `data/` was rebuilt and the run re-scored for $0,
  so all three models now pass this drawing. It is not in the 30-set, so only the
  141-drawing results changed.
- **Small-sample caveat:** only 4 drawings are `calculated_chain`, and all 4
  are measured from in-between edges (none from a part edge). The report shows these counts but
  never presents them as rates. More chain drawings are a candidate for a later
  round.

### 2.3 Units: what the prints actually contain

- **`MM` rows (128):** dual-dimensioned prints shown as `mm [in]`, e.g.
  `69.9 [2.75]`. SolidWorks rounds both displays independently from the
  native value. Garron recorded the mm display.
- **Finding from this session:** not every dual print started in inches. Some
  are clearly mm-native (e.g. 200944 `10.0 [.394]`, the 201552 series
  `20.0 [.79]`, `83.570 [3.2902]`). Both displays can also be rounded:
  201548-003 shows `15.9 [.63]`, but the true size is 0.625 in.
- **`IN` rows (13):** inch-only prints from a different drafter. Garron
  recorded the printed inch value.

### 2.4 Inch partners for dual prints

To score fairly, the system needs **both printed numbers** for every
dual-dimensioned ground-truth value.

- **Found automatically:** 233 of the 327 mm values. Their inch partners sit
  next to them in the PDF text layer, and each pair was checked with the
  conversion math.
- **Garron confirms the rest (94):** 66 on image-only PDFs and 28 where the
  text layer doesn't read cleanly. This is a one-time task on a local review
  page, about 15–20 minutes. Each value's inch box is pre-filled with a best
  guess. Garron also spot-checks 20 of the automatic pairs.
- Garron does not need to re-record the drawings.

### 2.5 Scoring rule

**A value is correct** if it matches any faithful reading of the printed
dimension:

| Print type | Accepted mm answers | Accepted inch answers |
|---|---|---|
| Dual (`MM` rows) | printed mm; printed inch × 25.4 | printed inch; printed mm ÷ 25.4 |
| Inch-only (`IN` rows) | printed inch × 25.4 | printed inch |

**Chain values also accept the segments added up**, in either unit: the printed
mm segments summed, and the printed inch segments summed (× 25.4 for an mm
answer). This is a *separate* accepted reading, not a substitute for the total.

It is needed because each mm display is rounded on its own, so the segments do
not always add to the printed total. On 200951's side view the inch segments add
exactly (0.250 + 2.620 = 2.870) while the mm segments do not (6.35 + 66.6 =
72.95 against a printed 72.91). A model that chains the printed mm segments has
read the drawing correctly and must not be failed for the drafting package's
rounding. All 4 current chain values happen to add up exactly in both units, so
this rule changes no score today — it exists so the scorer stays correct when a
chain that drifts is added later.

**Match tolerance:**
- Dual prints: an mm answer within **±0.02 mm** of an accepted mm reading, or
  an inch answer within **±0.0005 in** of an accepted inch reading.
- Inch-only prints: an inch answer within **±0.0005 in** of the printed value,
  or an mm answer within **±0.05 mm** of the exact conversion (Garron's
  choice).

**Why this rule instead of the starter's ±0.20 mm window:**
- It accepts a model that reads `2.75` and converts it itself to 69.85 mm.
  The starter rule failed that answer.
- It closes a hole. On 5 of the 233 checkable values, a *different* number
  printed on the same sheet falls within 0.20 mm of the envelope (e.g.
  201551-021: 4.060 vs 4.0; 201551-016: 19.1 vs 19.0). Under the ±0.20 rule a
  model that grabbed the wrong number would pass.
- At ±0.02 mm / ±0.0005 in, the only remaining overlaps are the same size
  printed a second way (e.g. 19.05 = .750 in), which is harmless.
- The scorer never has to know which unit is "native," so it doesn't depend on
  anyone getting that right.
- Rechecked in the Chunk 3 session against all 327 dual values: every printed
  number and exact conversion passes, and so does a model's own conversion kept
  to 2 decimals in mm or 3 in inch. Widening to ±0.05 mm / ±0.005 in would let
  in 7 other printed numbers, including 201551-016's 19.0.
- **Known cost, accepted:** a model that converts a printed number itself and
  rounds more coarsely than the print fails. That is 69 of 327 dual values if
  it rounds mm to 1 decimal (e.g. 276.2 [10.88] answered as 276.4 mm), and 54
  of 327 if it rounds inch to 2 decimals (e.g. 10.0 [.394] answered as 0.39 in).

**A toleranced size also accepts its upper limit (Garron, 2026-10-10).** A size printed
with a ± tolerance can be as large as nominal plus tolerance, so that limit is a bounding
dimension too. It is accepted in either unit, and converted, within the same windows.
- **Why:** on 201551-024, Opus read `Ø83.570 ±0.025 [Ø3.2902 ±.0010]` and answered
  83.60 mm (3.291 in), the upper limit rounded, and said so in its reply. It failed the
  ±0.02 mm window by 0.005 mm. The match window is unchanged.
- **How it still rejects wrong answers:** only the nominal and the upper limit count. The
  lower limit fails (the part can be larger), and so does any other number. A size with
  no printed tolerance gains nothing.
- **Where tolerances come from:** code reads them from the text layer at
  `build-foundation` into `data/envelope-tolerances.csv`: 11 envelope sizes on 9 text
  drawings, symmetric ± only, chains skipped. The 42 picture-only drawings have none
  listed. Of the 51 replies on those 9 drawings, this was the only one that gave a
  tolerance limit; every other reply gave the nominal. Re-scoring changed that one
  reply and no other (Opus, 141-drawing eval, 129 to 130 of 140).
- The tolerance audit lists every pass that relied on an upper limit, beside the
  converted readings.

**Units in a run:**
- If the model labels its units, the label is trusted. A number labeled mm
  that only matches as inches is wrong, and the run is marked *unit mix-up*.
- If no units are given, both readings are tried, but every value in that run
  must use the same one.
- Only mm and inch are recognized. A number written as a fraction (`5/8`,
  `1 3/8`) is read as its decimal and scored like any other number.
- If a reply gives the same dimension in both units (e.g. `8.000 mm (0.3150 in)`),
  it counts if **either** number matches.

**Run verdict:**
- **CUBE:** 3 values in any order. Thk/W/L label swaps are *not* failures.
  Values are matched to ground truth as an unordered set; never compare Thk to
  Thk, W to W, L to L. Why: that's how flat stock is ordered. The three sizes
  matter, not which face is which.
- **CYL:** Dia and L, and they are **not** interchangeable. The reply's
  diameter must match the diameter and its length the length; a swapped
  cylinder fails. If a two-value reply names only one (`Ø10 × 75`), the other
  is the remaining one. If it names neither, it is not graded and is flagged
  for Garron instead of guessed.
- **Strict pass:** every ground-truth value matched, nothing missing, nothing
  extra.
- **The prompt names no shape, so neither does the answer (Garron, 2026-09-20).** The
  bare prompt asks for bounding dimensions and nothing more, so a round part's envelope
  is correct written either way:
  - the cylinder: `Dia`, `L`
  - the box that cylinder fills: `Dia`, `Dia`, `L`

  Both come from the recorded Dia and L, so nothing new is recorded and code checks
  both. This is geometry, not a preference: the smallest box round a cylinder has sides
  equal to its diameter. A model cannot be failed for choosing a shape the prompt never
  asked for. (Garron's earlier call that a box for a round part fails was withdrawn on
  2026-09-20; it graded against an instruction the prompt didn't give.)
  - A reply may give several envelopes. Each is tried against each accepted form with a
    matching number of sizes, in a fixed order, and the best result stands; the others
    are recorded on the result page, never counted as extra values.
  - A smaller number taken from a local feature is **not** an envelope dimension. On
    90-100013-A, Gemini answered `4.96 × 1.50 × 1.368` using the across-flats size of
    the wrench flats; the Ø1.50 knurled body is full round, so that box cannot hold the
    part. It fails.
  - A cuboid part answered with round stock would need Ø = √(W² + L²). No reply has done
    it (0 of 48), so it is not built; it fails and shows on the page if it ever appears.
- **Shape mismatch** (numbers that fit neither accepted form): a plain fail, with no
  special tag.
- **Dims correct:** every run records how many ground-truth values were
  matched, out of 3 (CUBE) or 2 (CYL). It also records *which* ones were
  missed, by label and axis.
- If two values are wrong, the scorer knows which ground-truth values were
  missed, but not always which wrong number was "meant" for which. Diagnosis
  resolves that.
- **Chain parts:** models rarely add up chains yet. Ground truth writes chains
  as sums so the results can show when a model found one part. When a missed
  chain dimension was answered with one printed part, the result notes it
  (e.g. "Thk (Z) missed: gave 34.29 mm, one part of the chain 34.29 + 6.35 =
  40.64"). It is still a fail.

**Tolerance audit table:** the report lists every pass that relied on a
converted reading rather than a printed number. It's for reference only, not a
review task.

### 2.6 Failure diagnosis

**Approach chosen: script + one diagnosis subagent (Approach 2).**
- Code does all model calls, extraction, and scoring, so scores are repeatable
  and defensible.
- Grouping and diagnosis also run in Claude Code, but only on failures.
- Garron's failure labels explain *why* a model failed, and code can't see
  why. That needs someone to look at the drawing.

**Grouping:** identical failures (same drawing, same missed dimension, same
wrong value) are grouped and diagnosed once. If 201548-013 returns 85.7 in 7
runs, that's one diagnosis, applied to all 7.

**Unit of labeling:** each *missed dimension* gets exactly one label. A run
that misses Thk for one reason and L for another gets two labels.

**Labels (final):**

| Label | Definition |
|---|---|
| Proximity association | Found the right dimension line but took a nearby, unrelated number instead of the one that belongs to the line. |
| Axis mapping | Chose a dimension from the wrong axis. |
| Chain aggregation | Failed to chain dimensions, chained the wrong dimensions, or failed to subtract a dimension that overlapped. |
| Datum reconstruction | A chain aggregation failure that happened *because* the dimensions start from an internal datum instead of an outer part edge. The model missed the datum-to-edge segment on the other side of the datum. |
| Over-aggregation | Added a printed size to one that already includes it, so the size comes out too big (e.g. a flange thickness added to a length that already includes the flange). |
| Feature substitution | Correctly read a real dimension in the right axis, but that dimension belongs to a feature, not the outer envelope (e.g. main-body Ø instead of a larger flange Ø, pocket depth, hole spacing). |
| Unclassified | None fit, or the evidence is unclear. Goes to Garron. |

**Changed 2026-10-10 (Garron):**
- **One label for a wrong axis.** A number read in a view where its page direction is a
  different axis of the part (201548-013's 85.7) chose a dimension from the wrong axis, so
  it is Axis mapping; the label list no longer has a separate label for it.
- **Over-aggregation is its own label.** It was on the watch list (section 5) as
  Unclassified with `Watch list: over-aggregation`; after the 141-drawing review
  it covered 7 drawings (201258-012, 201548-030, 90-100012-B, 201007, 201057-002,
  201258-011, 18202-001), and every such case was relabelled. The agent's own proposals
  of Unclassified with that tag were relabelled too, since it followed the rule it had.
- **One piece of a chain is a chain failure even when the overall is printed elsewhere.**
  201551-017: GPT gave 87.8, one piece of 12.7 + 87.8 = 100.5 in the side view, while
  100.5 is printed in the top view. It is Chain aggregation (Datum reconstruction when
  the zero is internal).
- **What the agent reads (audit).** The agent loads no CLAUDE.md, so neither SPEC's
  history nor private notes reach it (`omitClaudeMd`). Its brief carries Garron's one-line
  reasons, not his notes. His label decides a repeat of the same drawing, missed size and
  wrong number; otherwise the playbook decides, and his reasons are examples. The
  playbook's worked examples are his labelled cards in this repo, not the earlier
  research page's, and claims not shown by the data were cut ("could this view show the
  size?", "only a reference", "models most often fail").

**Tie-breaks:**
- Datum reconstruction beats chain aggregation.
- Chain aggregation is a chain the size needed, missed or built wrong; Over-aggregation is
  a chain built where none was needed.
- If two other labels fit equally, use unclassified.
- One label per missed dimension.

**How the diagnosis agent works:**
- **Instructions:** a written diagnosis playbook covering how to set the part's
  X/Y/Z frame from the views, third-angle projection, tracing a dimension line
  to its number, chain and datum logic, reading dual `mm [in]` callouts, the
  label definitions above, and worked examples from Garron's own labelled cards.
- **Tools:** zoomed high-resolution crops of the drawing, the list of printed
  numbers with their positions (text PDFs), and a calculator.
- **Output:** a short engineer's note with checkable evidence (e.g. "85.7 is
  printed in Section B-B, upper right"), one proposed label, and the axis.
- **Automatic check:** code confirms that every number the note cites is
  actually printed on the drawing. This only confirms evidence exists; it
  never raises disagreements.
- **Learning from Garron:**
  - Every label Garron confirms or changes goes into a casebook with a
    one-line reason, and the agent reads the casebook before labeling.
  - When the same drawing returns the same wrong value later, Garron's earlier
    label is reused and marked "reused."
- Agents may propose a new label when several failures don't fit. Garron
  approves any change to the label list.

**Why one agent, not three:** AI tools are weak on engineering drawings, so
three independent agents would likely disagree on most prints and create more
review work, not less. Multi-agent diagnosis is parked until one agent has
proven useful.

**Review plan:**
- On the first 30-drawing run, Garron reviews every diagnosis, and the system
  reports how often the agent agreed with him.
- **Decision point:** if agreement is high, later runs drop to reviewing all
  Unclassified groups plus a random 20% sample, with a full review of that
  run if more than 1 in 10 sampled labels get overturned. If agreement is low,
  diagnoses stay drafts for Garron to fix and no complexity is added.
- **Decided 2026-09-28 (Garron, Chunk 9): he reviews every label the agent writes.** The
  agent agreed with him on 7 of 9 labels first time (95% range 40% to 97%), too few to
  earn sampling. Repeat failures take his casebook label automatically, so he only sees
  new ones. Revisit after the next run's new failures.
- The whitepaper states the review rate honestly, which also addresses the
  concern of Claude labeling GPT and Gemini failures.

### 2.7 Models and cost controls

**Toggles, chosen before every run (in Claude Code question boxes):**
- Model makers on/off: Anthropic, OpenAI, Google, xAI.
- Individual models on/off within each maker.
- Thinking level per model.
- Runs per model: 1–5, default 3.
- Number of drawings: 30 / 60 / 141, suggested minimum 30. Anything smaller is
  a labeled **test run** and is kept out of published results.

**Default models are one tier below each maker's top model:** Claude Opus 5,
GPT 5.6 Sol, Gemini 3.1 Pro, and a Grok model picked at build time. Exact API
names are checked against each maker's live model list during Chunk 4.
Garron edits the list freely.

**Checked in Chunk 4 (2026-09-18), recorded in `config/models.yaml`:**

| Maker | Default (on) | Top (for the follow-up) |
|---|---|---|
| Anthropic | `claude-opus-5` | `claude-fable-5-1` |
| OpenAI | `gpt-5.6-sol` | `gpt-6-astra` |
| Google | `gemini-3.1-pro-preview` | none higher released yet |
| xAI | off (see below) | — |

- **Gemini 3.1 Pro stays the default** even though it is now Google's best
  released Pro model (a preview), not one tier below. The tier below it is 3.8
  Flash, a cheaper speed tier that doesn't compare with Opus 5 or Sol. Gemini
  3.5 Pro is announced but not released. Google can retire preview models.
- **Grok is off (Garron's decision).** xAI's API takes pictures only as PNG or
  JPG. An attached PDF is turned into text on xAI's servers and searched with
  a tool, so Grok never sees the drawing. Sending it images instead would break
  the "PDF as-is" rule. Revisit if xAI starts accepting PDFs.
- **Thinking level default is each maker's own default**: nothing is sent, and
  each saved call records what that means (Opus 5: adaptive thinking, effort
  high; Sol: reasoning effort medium; Gemini 3.1 Pro: thinking level high).
- **Nothing else is sent:** no sampling settings, no system prompt, and no
  Anthropic "fallback to another model on refusal." A refusal is saved as the
  reply.
- **Retries only when no reply came back** (lost connection, timeout, rate
  limit, maker server error). A reply that arrived — refused, cut off, or
  strange — is never re-asked, since that would give the model a second try.
- **Every call is saved in full**, one JSON file per call under `runs/calls/`:
  what was sent (minus the PDF bytes and the key), the maker's complete raw
  response, reply text, exact model version, tokens, cost, and time. Chunk 5
  reads these files, so re-scoring never needs a new call.

**Built in Chunk 6 (2026-09-19):**
- Each run is a saved plan (`runs/plans/<name>.json`): models with thinking levels,
  drawings, runs per model, the estimate, and every approval. Nothing is sent until
  a plan is approved.
- Real runs save calls under `runs/calls/main/<model>/`, whatever the drawing set, so
  results add up across plans and days. A non-default thinking level gets its own
  folder (`<model>-thinking-<level>`). Test runs save under `runs/calls/test/`.
- The default test run is 5 fixed drawings from the 30-set covering the mix:
  201533-020, 201548-030, 201258-012, 202985-001, 90-100012-B.
- The estimate for each model is the average cost of its saved calls at the same
  thinking level, plus extraction. With none saved, it falls back to Chunk 4's rough
  guess, which runs high.
- Each model runs in its own thread, one call at a time. Stopping (`stop-run` or
  Ctrl+C) lets calls under way finish and be saved.
- Spending is checked before each call starts, so a run can pass the +25% limit by at
  most one call per model. Measured on the first test run (5 calls, GPT-5.6 Sol):
  estimated $0.1127, actual $0.1575, no pause, because the overshoot came on the last
  call. The smaller the run, the bigger one call looms.

**Top-model follow-up (optional):** send only the drawings that failed to each
maker's top model. It's cheap, and it answers "would the best model have gotten
this right?"

**Connection:** direct to each maker's API, using keys Garron already has.
Each maker handles PDFs its own way, which is exactly what their users get.

**Spending safety (two layers):**
1. Before a run, the system shows the plan and estimated cost and waits for
   approval. During the run it tracks real spend and **pauses if spend passes
   the approved estimate by 25%**, then asks before continuing. Finished calls
   are kept.
2. During setup, Claude walks Garron through setting a monthly spending limit
   on each maker's billing page, as a backstop.

**Resumable and additive:** a stopped run picks up where it left off, and
results add up across days. Running Claude today and GPT next week doesn't
redo Claude.

**Rough cost:** 141 drawings × 3 models × 3 runs = 1,269 calls, roughly
$25–$130 in model fees. This is a guess; Chunk 5 measures the real per-call
cost.

### 2.8 Drawing sets

When fewer than 141 drawings run, the system uses a **fixed, balanced, nested
set**:
- The 30-drawing set sits inside the 60, and the 60 sits inside the 141. The
  same drawings are used every time, so runs on different days compare fairly.
- The 30 always includes:
  - all 4 `calculated_chain` drawings
  - 201533-020 (example 1A)
  - 201548-013 (example 1B)
  - a mix of CYL/CUBE, dual/inch-only, and text/image-only PDFs
- The rest are filled at random once, then locked.
- **Why not random each time:** a random 30 has a 38% chance of containing
  none of the 4 chain drawings.

### 2.9 Operating the system

Everything runs from Claude Code commands. The two visual jobs open as simple
local pages in the browser.

| Command | What it does |
|---|---|
| `/run-eval` | Asks the toggles, shows the cost, runs, scores |
| `/confirm-inch-values` | One-time page to confirm the 94 inch partners |
| `/diagnose-failures` | Groups failures and runs the diagnosis agent |
| `/review-diagnoses` | Page showing the zoomed drawing, the reply, and the proposed label; Accept / Change / Note |
| `/build-report` | Writes the handoff folder for Cowork |
| `/retest-failures` | Optional top-model follow-up on failed drawings |
| `/show-commands` | Prints this list with one-line reminders |

A plain-English user guide (`docs/user-guide.md`) explains every command with
examples and is updated as each chunk ships.

Diagnosis agents run inside Claude Code, so they use Garron's Claude plan,
not per-call API fees.

### 2.10 Handoff to Cowork

One folder per reportable run:

```
results/<date>-<run-name>/
  README.md            the results page (GitHub shows it when the folder is opened):
                       background in plain English, key numbers, each pointing to
                       its source table; caveats (small n, review rate)
  tables/              CSV: pass rate by model; criteria correct;
                       per-print consistency (k of N runs); by dimension_origin;
                       by shape; by text vs image-only PDF; by dual vs inch-only;
                       failures by label; failures by axis (X/Y/Z) and by
                       dimension (Thk/W/L/Dia); tolerance audit
  charts/              PNG plus the data behind each chart
  every-run.csv        one row per model reply: drawing, model, version, run #,
                       values returned, pass/fail, correct, total criteria,
                       dims missed, label, evidence
  raw-replies/         full model reply text
  run-settings.json    models, versions, thinking levels, dates, prompt
  LICENSE-NOTICE.md    drawing-derived materials fall under DRAWINGS-LICENSE
```

- Pass rates include 95% confidence ranges.
- **Consistency rate:** the share of drawings where all N runs agree (all pass
  or all fail).
- Costs are logged privately in `runs/`, not in the published folder.
- **One page for both readers (Garron, 2026-09-29).** A stranger on GitHub and the
  whitepaper writer in Cowork need the same things: clear numbers, what they rest on,
  and the caveats. So the folder's `README.md` replaces the separate findings brief,
  and the repo's main README gets a short results section that links to the latest
  folder. The whitepaper is written in Cowork, and Garron designs it himself; nothing
  here is formatted for his template.
- **The Cowork message stays private.** Garron answers once what he wants the
  whitepaper to do; his answers are saved in `runs/cowork-notes.md`. Each
  `/build-report` then writes the message to paste into Cowork, naming the files to
  hand over, to `runs/cowork-message-<run>.md`. `runs/` is never uploaded.
- **Headline pass rates count each drawing once** (run 1). The 30-set gets 3 runs and
  the other 111 drawings 1 (Chunk 10b), so pooling every reply would count the 30
  three times and make the ranges look tighter than they are. Later runs feed the
  consistency table, and `every-run.csv` holds every reply.
- **Two evaluations, two papers (Garron, 2026-10-06).** The 30-drawing eval (3 runs, which
  adds consistency) and the 141-drawing eval (run 1) each get their own folder and paper.
  A folder holds only the runs every one of its drawings has, so the 141 folder is run 1
  only. Each folder's label-review figure counts only rulings on failure groups with a
  reply in that folder, so labelling the 111 new drawings' failures can't change the
  30-drawing figure; a ruling on a 30-set failure changes both. The main README lists every folder, with a short
  hand-written section on why bounding dimensions matter that links to Garron's AlphaGo
  article rather than retelling it. Until Garron has labelled every missed size, a page
  says how many await review and never ranks the labels.
- **Results pages read as research reports (Garron, 2026-10-06).** Not a story: abstract,
  introduction, method, results with numbered tables and captioned figures, limitations,
  data and code, appendices. Reference papers he chose: Bowman et al., "Measuring
  Progress on Scalable Oversight for Large Language Models" (arXiv 2211.03540); Olsson et
  al., "In-context Learning and Induction Heads" (transformer-circuits.pub, 2022); Elhage
  et al., "A Mathematical Framework for Transformer Circuits" (2021); Souly et al.,
  "Poisoning Attacks on LLMs Require a Near-constant Number of Poison Samples" (arXiv
  2510.07192); Lu et al., "The Assistant Axis" (arXiv 2601.10387). Also kept: Anthropic,
  "Measuring the persuasiveness of language models" (2024) and "Reasoning models don't
  always say what they think" (2025); MechVQA (arXiv 2605.30794).
- **Splits with fewer than 5 drawings show counts only**, never a rate: SPEC 2.2's
  chain rule applied to any small group (chains, 4 drawings; inch-only prints, 3 in
  the 30-set).

### 2.11 Publishing

Code, ground truth, drawings (under the research-use license), and full
results including raw replies all go public with the whitepaper. Built public
from day one:
- no API keys in any file
- a stable result format
- every result tagged with model version and date
- test runs kept out of `results/`

---

### 2.12 Pulling numbers out of free-text replies (extraction)

Model replies come back in many shapes: paragraphs, tables, both units at once
("Ø8.000 mm (0.3150 in)"), or lists of candidates. Hand-written text rules
would break on these, so:

- A small, cheap text-only model (Claude Haiku 4.5) reads each reply and fills
  in a fixed form: shape, each value with its label and unit, and any
  same-dimension value given in the other unit. It never sees the drawing and
  never judges correctness. It only copies what the reply says.
- When a reply gives the same dimension in both units, that counts as **one**
  value, not two.
- When a reply gives more than one envelope for the part, each envelope is recorded as
  its own set of sizes. **The extractor records sizes, labels and units only — it is
  never asked what shape an envelope is, or whether the answer is right.** Code works
  the shape out from the sizes and the words beside them, and grades it (2.5).
- **Why (2026-09-20):** an earlier version asked the extractor to group sizes *and* name
  the shape. Reading the same 90 saved replies twice gave different answers on 9 of
  them, which broke the promise that re-scoring is identical. With the judgment moved
  into code, 18 of 18 replies on the hardest drawings read the same way twice.
- `unsure` means the numbers can't be read, not that the shape or the answer is in
  doubt. Neither is the extractor's business.
- **The standard (Garron, Chunk 5):** a size counts if a person reading the
  reply would know it is the reply's answer. A size given with hedging or in a
  note still counts: on 201533-020 Gemini wrote "the thickness is not explicitly
  dimensioned ... suggest a standard plate thickness of 12.7 [.500]", and 12.7 is
  its thickness. Numbers the reply presents as something else are left out, e.g.
  Opus's "suggested stock ... 8.75 × 7.50 in" and its supporting evidence.
- If a reply lists several candidate answers, the model's final stated answer
  is used. If a person couldn't tell which is its answer, the reply is flagged.
- **Quiet check:** every number the extractor outputs must appear word for word
  in the reply, as a **whole number**: "2.7" does not count as found because
  "12.7" is in the reply, and "12.70" is not "12.7". If a number is missing, or
  the extractor marks itself unsure, the reply is flagged and never guessed.
- **A unit counts only if the reply writes one.** On 201533-020 Gemini wrote
  `215.9 [8.50]` with no unit anywhere, and the extractor filled in "mm"
  anyway. The scorer trusts a stated unit, so a wrong guess could fail a right
  answer as a unit mix-up. Code sets aside any unit the reply never writes, and
  the scorer tries both readings, as 2.5 says for replies without units.
- A reply with no dimensions (a refusal, or one cut off) is extracted as no
  values and scored as a fail, not flagged.
- Each extraction is saved once and reused, so re-scoring always gives
  identical results.
- **Checked in Chunk 5 (2026-09-19):** Haiku 4.5 is current and not scheduled
  for retirement, and it is still Anthropic's cheapest model. The extractor is
  pinned to the snapshot `claude-haiku-4-5-20251001` in `config/models.yaml`.
  It gets fixed instructions and the reply text only, and answers in a fixed
  JSON form (structured output). Extractions are saved under `runs/extractions/`.

### 2.13 Technology and folder layout

- Python, with results stored as plain CSV and JSON files. No database, so
  anyone can open the published data.
- Review pages are simple local web pages served from this computer.
- API keys live in a `.env` file that git never commits.

```
031-vlm-eval/
├── SPEC.md, CLAUDE.md, README.md, LICENSE, DRAWINGS-LICENSE
├── pyproject.toml, .env.example, .gitignore
├── drawings/            PDFs + ground-truth.md (human-edited source)
├── data/                generated: ground-truth.csv, inch-partners.csv,
│                        drawing-sets.csv, casebook.jsonl
├── config/models.yaml   makers, models, thinking levels, prices, on/off
├── src/vlm_eval/        the Python package (scoring, runner, extraction, ...)
├── tests/               quiet checks
├── .claude/commands/    run-eval, confirm-inch-values, diagnose-failures,
│                        review-diagnoses, build-report, retest-failures,
│                        show-commands
├── .claude/agents/      failure-diagnostician
├── docs/                user-guide.md, diagnosis-playbook.md, scoring-rules.md
├── runs/                private working data: raw calls, costs, test runs
├── results/             published handoff folders only
└── _tmp/                scratch, never committed
```

---

## 3. How the work is checked

**Principle:** checks exist to catch software bugs, not to second-guess
Garron's drawings.
- Ground truth and the printed numbers are the only source of truth. No check
  asserts a Claude-invented "real answer."
- Checks run quietly. Garron sees one line ("all checks passed") or a short
  grouped list of problems that would change a score. Never a conflict on
  every print.
- Garron personally reviews only three things: the 94 inch values (once),
  diagnoses on the first 30-drawing run, and the final findings.

**Checks Claude Code runs itself:**

| Area | Check |
|---|---|
| Ground truth | Every row reads cleanly; CUBE has 3 values, CYL has 2; chain formulas add up; every row has a PDF and every PDF a row; the balanced sets contain the required drawings |
| Inch partners | Every pair passes the conversion math |
| Scorer | Correct answers pass in every accepted form and in any order; made-up, clearly wrong values fail; missing, extra, and mixed-unit answers fail; dims-correct counts are right |
| Perfect/bad fake model | A fake model that answers with the ground truth scores 100% on all 141; a fake model with made-up wrong answers scores 0% |
| Repeatability | Scoring the same saved replies twice gives identical results |
| Extraction | Every extracted number literally appears in the reply text; replies the extractor isn't sure about are flagged, never guessed; extraction results are saved once and reused, so re-scoring never changes |
| Replay mode | The whole pipeline re-runs on saved replies with zero API spend |
| Cost | Estimated vs. actual cost compared after the first test run |
| Diagnosis | Cited numbers exist on the drawing; agreement rate with Garron reported |
| Known-answer | If 201548-013 fails the way the research page shows (85.7 for the thickness), its diagnosis should come out Axis mapping; it did on 2026-09-29. If 201533-020 fails with 6.35, it should come out Feature substitution. (201533-020 was research example 1A, proximity association, until Garron corrected it on 2026-09-29 to Feature substitution, since the top view could show the thickness and the model gave a hole position.) |
| Report | Every number on the results page is recomputed separately from `every-run.csv` and must match |

---

## 4. Build chunks

Every chunk:
- ends with something Garron can check himself
- works on its own, using only chunks already finished
- fits in one Claude Code session

If a chunk starts to run past one session, stop at a checkable point and
split it rather than rushing.

### Order and parallel map

```
Chunk 1  Ground-truth foundation
           │
   ┌───────┼────────────────┐
Chunk 2  Chunk 3          Chunk 4            ← parallel (separate sessions)
Inch     Scorer           Model
confirm    │              connections
   │       │                │
   │       │              Chunk 5  Extraction + replay
   │       └──────┬─────────┘
   │           Chunk 6  Run controls (toggles, cost, pause, resume)
   └──────────────┤
               Chunk 7  First real 30-drawing run (gate)
                  │
          ┌───────┴──────────┐
       Chunk 8            Chunk 10            ← parallel (separate sessions)
       Diagnosis agent    Report + handoff
          │                  │
       Chunk 9               │
       Review page +         │
       casebook              │
          └───────┬──────────┘
               Chunk 10b  Full run (the other 111 drawings)
                  │
               Chunk 11  Top-model retest, docs, publish prep
```

Chunk 2 can happen any time before Chunk 7. Until it's done, scoring uses
only the automatically found inch partners.

---

### Chunk 1: Ground-truth foundation

**Build:**
- Python project setup, `.gitignore`, `.env.example`, and the folder layout
  from 2.13.
- Ruff for linting and formatting, plus a `post-edit-formatting` hook in
  `.claude/settings.json` that runs Ruff on each Python file Claude edits.
- Add the `dimension_origin` column to `drawings/ground-truth.md`.
- Ground-truth reader, producing `data/ground-truth.csv` with parsed chains,
  shape, print type (dual/inch-only), and the text/image-only tag.
- Automatic inch-partner finder (expected: 233 found, 94 to confirm).
- Fixed, balanced, nested drawing sets (30 ⊂ 60 ⊂ 141).
- Update the project structure in `CLAUDE.md` and `README.md`. Start
  `docs/user-guide.md`.

**Garron checks:** a one-page summary showing 141 drawings, 4 chain drawings,
auto-found vs. to-confirm inch counts, and the list of drawings in the 30-set.
Plus "all checks passed."

**Parallel within:** after the reader is done, two subagents build the
inch-partner finder and the drawing sets at the same time.

---

### Chunk 2: Inch value confirmation page

**Build:**
- `/confirm-inch-values`: a local page showing each of the 94 values with the
  drawing zoomable, the recorded mm, and a pre-filled inch guess.
- A 20-value spot-check of the automatic pairs.
- Saves as Garron goes, so he can stop and resume.
- User-guide entry.

**Garron checks:** he completes the page (about 15–20 min), and the summary
shows 327 of 327 inch partners confirmed.

**Parallel:** independent of Chunks 3–6. It can be built in its own session
at any point after Chunk 1.

---

### Chunk 3: Scorer (no API spend)

**Build:**
- Faithful-reading scoring (2.5), tolerances, unordered matching, the units
  rule, and value-count and shape rules.
- Dims correct out of 3/2, plus which dims and axes were missed.
- Quiet checks: scorer, perfect/bad fake model, repeatability.

**Garron checks:** a one-page "grading examples" sheet in plain English: about
10 real drawings with made-up example answers and verdicts, e.g. "200473-005:
2.75 × 2.75 × 1.50 in → PASS, 3/3." He confirms that's how he'd grade.

**Parallel:** independent of Chunks 2 and 4; build it in its own session
alongside them.

---

### Chunk 4: Model connections

**Build:**
- `config/models.yaml` (makers, models, thinking levels, prices, on/off,
  defaults).
- Connections for Anthropic, OpenAI, Google, and xAI that send the PDF as-is
  with the fixed prompt.
- Each call records the reply, the exact model version, token counts, and time.
- Retries only on network errors.
- Verify default model names against each maker's live list, and pick the
  Grok default.
- **First task, a risk check:** confirm each maker accepts a PDF directly. If
  one doesn't, stop and ask Garron. Converting to images would break the
  "PDF as-is" decision.

**Garron checks:** a test call on 201533-020 to each maker he turns on, 1 run
each. He sees the raw replies and the actual cost (cents).

**Parallel within:** once the shared connection format is set, one subagent
per maker (4 at once).

---

### Chunk 5: Extraction and replay

**Build:**
- The extraction step from 2.12, with its quiet check.
- Extraction results saved once and reused.
- Replay mode: re-run extraction and scoring on saved replies with zero API
  spend.

**Garron checks:** a plain page listing each Chunk 4 reply next to the numbers
pulled from it, and its score, all produced in replay mode for $0.

**Parallel:** needs Chunk 4 finished. It can then be built while Chunks 2 or 3
are still in progress in other sessions. The score column uses Chunk 3's
scorer and stays blank until Chunk 3 is done.

---

### Chunk 6: Run controls

**Build:**
- `/run-eval` question boxes: makers, models, thinking levels, runs (1–5),
  and drawings (30/60/141, or a test run).
- Cost estimate and approval, and the pause at +25% over the estimate.
- Resume after a stop, and results that add up across days.
- Test runs kept out of `results/`.
- `/show-commands`, plus user-guide entries and a guide for setting billing
  limits on each maker's page.

**Garron checks:** he runs a test of 5 drawings × 1 model × 1 run, stops it
partway, resumes it, and sees estimated vs. actual cost and a plain results
table (pass/fail and dims correct per drawing).

**Parallel within:** two subagents at once: (a) the question flow and run
plan, (b) cost tracking, the pause, and resume.

---

### Chunk 7: First real 30-drawing run (gate)

**Build:** mostly running. Garron picks models and runs the 30-drawing set.
Only small fixes happen in this session; anything bigger is written down and
becomes its own session.

**Garron checks:** for each model on the 30 drawings, the strict pass rate,
dims correct, and consistency per drawing (k of N runs), plus estimated vs.
actual cost. This is the "see it work" moment.

**Parallel:** none. It's a single run.

**Built and run (2026-09-19).** The results page gained the two summaries Garron
checks: pass rate and sizes found per model, and runs passed per drawing with the
consistency rate (2.10). Garron chose 1 run per model to hold the cost down, so
consistency is still to come; a second run adds to the first with nothing re-sent.

First real run, 30 drawings x 3 models x 1 run, 90 calls, no call failed to return.
Estimated $3.29, actual $3.97 (Opus $0.0595 and Gemini $0.0401 per call, both above
the single-call estimates; the pause at $4.11 was not reached). After the
90-100013-A correction: Opus 25 of 30, GPT 24 of 29 with 1 not graded, Gemini 25 of 30.
All 4 chain drawings produced failures, as the research predicted.

---

**Second real run, the 60-set (2026-09-20).** The 30 drawings the models hadn't seen,
one run each: 90 calls, estimated $4.01, actual $3.26, none failed. Over all 60 drawings:
Opus 55 of 60 (92%), GPT 55 of 60 (92%), Gemini 48 of 59 (81%, one not graded). Pooled
splits: text PDFs 112 of 126, image-only 46 of 53, cuboid parts 90 of 99, round parts 68
of 80, inch-only 14 of 18, chain dimensions 7 of 12.

**Third real run, the 30-set under the `stock-shape` prompt (2026-09-20).** 90 calls,
estimated $6.03, actual $4.40, none failed. Opus 26 of 30 (87%), GPT 29 of 30 (97%),
Gemini 26 of 30 (87%) — against 27, 28 and 25 for the same drawings under the bare
prompt. **Accuracy barely moved: 81 of 90 against 80 of 90.** The prompt buys clarity,
not correctness: every reply came back in one shape, with nothing to disentangle, but
the wording also moves what a model attends to. On 201533-020 GPT answered the 6.35
centreline dimension it had read correctly as 12.700 under the bare prompt, and on
201581-008 Opus answered a length of 178 where it had read 109.8. Nine of 90 verdicts
flipped in each direction combined.

### Chunk 7b: Envelope sets (from the first real run)

**Build:** the 2.5 envelope rule and its 2.12 extraction change: the answer form holds
one set of values per envelope, the extractor's instructions record each envelope it
finds, and the scorer grades the set matching the ground-truth shape. Re-read the saved
replies once under a new extraction version (about 17c for 90 replies; no drawing is
re-sent) and re-score. Quiet checks: a reply with both envelopes passes on the matching
one; a cylinder answered only as a box still fails; a cube answered only as a cylinder
still fails.

**Garron checks:** the affected replies on the results page read the way he grades them
by hand.

**Parallel:** none. Chunk 8 waits for it, so failure diagnoses only explain real failures.

**Built (2026-09-20).** Answer form holds one set of sizes per envelope; the extractor
records sizes only; code works out each envelope's shape and grades every envelope
against every accepted form. Three re-reads of the 98 saved replies during the build
cost $0.73 in total; no drawing was re-sent. Extraction stability was then measured:
18 of 18 replies on the six hardest drawings read identically twice.

Scores for the first real run, after the corrections: Opus 27 of 30 (90%), GPT 28 of 30
(93%), Gemini 25 of 30 (83%), with nothing ungraded. The 10 remaining failures are
model errors: chains (200951, 90-100012-B), Gemini on 201513 and 201516, Opus on
201548-030, Gemini on 201581-007, both Opus and GPT on 201581-016, Gemini on
90-100013-A.

---

### Chunk 8: Diagnosis agent

**Remind Garron before starting:** use `/skill-creator` (already installed)
to create and test the `failure-diagnostician` agent and its playbook.

**Build:**
- Failure grouping (identical failures diagnosed once).
- Zoomed-crop tool and the printed-numbers-with-positions tool.
- `docs/diagnosis-playbook.md`, with the label definitions, tie-breaks, and
  Garron's four research examples.
- The `failure-diagnostician` subagent and `/diagnose-failures`, which output
  one engineer's note, one label, and the axis per group.
- Cited-number check.

**Garron checks:** a plain list of the diagnoses for the 30-drawing run's
failures. He reads the known-answer drawings (201533-020, 201548-013) if they
failed, plus about 5 others, and says whether the notes make sense. No scoring
of the agent yet.

**Parallel within:** three subagents at once: (a) grouping and the two tools,
(b) the playbook and agent instructions, (c) the command and cited-number
check.

**Built (2026-09-24).** The stock-shape prompt's 30-set run was diagnosed, since that
prompt is the one in use (2.1). Its 9 failed replies make 8 groups (Opus and Gemini both
gave 78.0 on 201513), with 9 missed sizes to label:
- Axis mapping 4
- Datum reconstruction 2
- Chain aggregation 1
- Proximity association 1
- Unclassified 1

90-100012-B was first labelled Chain aggregation under `Part Edge`, then Datum
reconstruction after Garron changed its Measured From (2.2).

**Checks:**
- The known-answer drawing 201533-020 came out Proximity association, as expected.
  (Corrected 2026-09-29: Garron now labels it Feature substitution. His research page
  misread the 6.36 [.251] in the bottom view as the 6.35; the 6.35 [.250] the model gave
  is printed in the top view. See Chunk 10.)
  201548-013 never failed, so it was tested with a practice case built from research
  example 1B, which came out as that example's label (now Axis mapping, 2.6).
- Without the playbook, the same agent labelled those two Feature substitution and Axis
  mapping.
- Every cited number on a text drawing was found printed. On the 3 picture-only drawings
  the citations are marked as not checkable.
- The scorer now keeps the numbers that matched nothing, and all 296 saved verdicts are
  unchanged.
- Fixed a results-page bug that listed the graded envelope as "not graded".

**Garron's read (2026-09-24): all 9 labels stand.** He read all 8 cards.
- **200951:** he first called it Datum reconstruction, then settled the rule. Datum
  reconstruction needs the model to give one side's piece of the chain and miss the
  other (34.29 without 6.35, or the reverse). Gemini gave 35.560, a hole position, so it
  stays Axis mapping.
- **201513 and 201516's Thk:** the same failure. Each time, a hole position ran the same
  way as a size the model had already found, and it filled a size the model couldn't
  find. Both stay Axis mapping, and no new label is added.
- **201258-012:** Opus added the 7.9 flange to 57.150, which is already the full length.
  This is really over-aggregation, but one case doesn't earn a label. Chain aggregation's
  definition gained a fourth case ("chained dimensions when the overall size was already
  printed"), and the case is on the watch list in section 5.
  **Changed 2026-09-28 (Garron):** the fourth case was taken back out. Building a chain
  that wasn't needed is not a failure to build one, so the definition no longer matched
  its name. 201258-012 is Unclassified with `Watch list: over-aggregation`, the same way
  201581-008 is handled.
  **Changed 2026-10-10 (Garron):** Over-aggregation is now its own label (2.6), and all
  three Opus runs of 201258-012 carry it: the same mistake each time.
- **201581-008:** he agrees it is stock-size substitution: the 7.00 in catalogue length of
  a reamer blank, taken from the material note. It stays Unclassified and is on the
  watch list.
- **201533-020:** that view has no dimension line, only two arrows at the edges, with
  12.700 off on a leader. The model isn't looking for a dimension line; it took the
  number sitting where the thickness line would be.
  **Changed 2026-09-29 (Garron): Feature substitution.** The 6.35 [.250] the model gave
  is printed in the top view, as a hole position. See Chunk 10.
- **What the review page needs (Chunk 9):** the list shows only the wrong number. Each
  card must also show Garron's sizes, what the model got right, and what it got wrong.

---

### Chunk 9: Review page and casebook

**Before starting:** Claude uses `/skill-creator` (already installed) to refine the
`failure-diagnostician` agent once it reads the casebook. Garron approves every rule
change (shown before and after) and sees the test results: his label next to the
agent's, case by case.

**Build:**
- `/review-diagnoses` page showing the zoomed drawing, the model's reply, and
  the proposed label with evidence, with Accept / Change label / Note buttons.
- Saving to the casebook, which the agent reads next time.
- Reuse of confirmed labels on repeat failures.
- Agreement-rate report.

**Garron checks:** he reviews every diagnosis from the 30-drawing run on the
page, and the system shows its agreement rate. **Decision point:** sample
review going forward, or diagnoses stay drafts.

**Parallel within:** two subagents at once: (a) the page, (b) casebook, reuse,
and agreement rate.

---

**Built (2026-09-28).**
- **Casebook** (`data/casebook.jsonl`): one line per answer Garron saves; his latest
  answer for a missed size counts. It holds his Chunk 8 read, loaded from this SPEC so he
  didn't repeat it, plus this session's two changes. His label always wins over the
  agent's.
- **`/review-diagnoses` page:** per card, his sizes against what each model gave, the
  drawing, the replies, the agent's label and note, and Accept / Change label / reason /
  note, saved on click.
- **Reuse:** a repeat failure (same drawing, missed size and wrong number) gets his label
  written automatically, marked "reused", with no agent sent. The pairing of wrong
  number to missed size comes from his confirmed entry, so a two-miss card can't swap
  labels.
- **Agent:** the brief lists the casebook as precedent. The agent is told to work from
  the playbook and casebook only, not SPEC. SPEC still reaches it through CLAUDE.md, so
  that only stops it opening the file.
- **Garron's changes this chunk:**
  - 201533-020 is not Proximity association. Research example 1A misread the 6.36 [.251]
    in the bottom view as the 6.35; the model's 6.35 [.250] is printed in the top view.
    (Settled as Feature substitution in Chunk 10.)
  - Chain aggregation's fourth case was taken back out; 201258-012 is Unclassified with
    `Watch list: over-aggregation`.
  - Playbook: a hole or feature position running the same way as a size the model
    already found, used to fill a size it couldn't find, is Axis mapping (201513,
    201516).
- **Agreement:** 7 of 9 (95% range 40% to 97%). The two differences are the two changes
  above.
- **Agent tests** (`/skill-creator`, the 8 cards, each with its own answer hidden):
  - playbook and casebook: 9 of 9
  - the Chunk 8 playbook: 7 of 9
  - the five cards the playbook doesn't name, after the don't-read-SPEC change: 6 of 6
  
  None of these is blind, since the agent sees his rulings through SPEC. The first real
  test is the next run's new failures.
- **Decision point:** he reviews every label (2.6).

### Chunk 10: Report and handoff folder

**Remind Garron before starting:** 2 more runs of the `stock-shape` prompt on the
30-drawing set, all 3 models (about $9, 180 calls; run 1 is already saved). Ask him
first, then show the plan and estimate as usual. Without them the consistency tables
have nothing in them.

**Build:**
- `/build-report`: every table and chart in 2.10, 95% ranges, small-sample
  caveats, and the tolerance audit table.
- The results page (`README.md`, 2.10), `every-run.csv`, raw replies, run settings,
  and the license notice. A short results section in the main README, and the
  private Cowork message.
- Recompute check on every number on the page.
- Works with or without diagnosis labels, adding label tables when they exist.
- **Criteria columns (Garron's request, added during Chunk 3):**
  - PASS/FAIL stays absolute: a reply passes only if it gets every criterion
    right. Anything less is a fail.
  - Beside PASS/FAIL, two data columns, numbers only, no words: **correct**
    (how many criteria the reply got right) and **total criteria**. Example:
    `FAIL | 2 | 3`.
  - Total criteria is counted from Garron's ground-truth row for that drawing,
    not fixed by shape. 201551-016 records Thk 25.4, W 63.5 and L 19.1, so its
    total is 3.
  - For chains, each individual number in the row counts: `34.29 + 6.35` is 2
    criteria. **The chain total is not a criterion (Garron, 2026-09-29).** 200951
    and 201516 have 4 criteria; 90-100012-B and 90-100013-A have 3.
  - A reply that gives the chain total gets every part of that chain. A reply that
    gives one printed part gets that part only: on the stock-shape 30-set,
    90-100012-B Opus (gave 6.50) is `FAIL | 2 | 3` and 201516 Gemini (gave 22.5)
    is `FAIL | 2 | 4`.
  - The report shows this count instead of "sizes found": the two agree on every
    drawing but the 4 chains, and two near-identical counts would confuse a reader.
  - The grading examples page gets the same two columns.

**Runs 2 and 3 on the 30-set (2026-09-29).** 180 calls, estimated $9.35, actual $8.01,
none failed to return. Over all three runs: Opus 79 of 90, GPT 84 of 90, Gemini 74 of 89
(one not graded: Gemini wrote an inch value as `.3.2902`, so extraction flagged it; its mm
sizes match). Same answer every run: GPT 93% of 30 drawings, Opus 87%, Gemini 80%.

32 failed replies made 22 groups: 8 repeats and 1 reuse took Garron's labels, 13 went to
the agent (15 missed sizes). Garron reviewed them and re-read the older ones. The agent
agreed with him on 18 of 23 (95% range 56% to 93%); he still reviews every label.
- **His tests, now in the playbook:** pair a wrong number with the size it replaced by
  direction, not by the reply's words; a different axis of the part is Axis mapping,
  including right page direction in a view where that direction is another axis
  (201548-013); the
  same axis in a view that could show the size but doesn't, with a feature's number, is
  Feature substitution (201533-020, 201513's 57.8).
- **Changes:** 201533-020 is Feature substitution (both wrong numbers, 6.35 and 0.250);
  201258-012's run-3 65.0 is Axis mapping (a diameter given as a length; **changed
  2026-10-10 (Garron):** Over-aggregation, the same mistake as runs 1 and 2); 201513 run 2
  was re-paired, Thk <- 78.0 Axis mapping and L <- 57.8 Feature substitution.
- **Checked against the replies before saving:** on 201581-007 and 201258-020 his first
  reason named the wrong size (the length and width the model had right). Shown that,
  he kept Axis mapping on both.
- 200951's length, recorded as the reference 72.91, is Datum reconstruction: the models
  gave 66.6 from one side of the internal zero.

**Garron checks:** he opens the results folder for the 30-drawing run and loads it
into Cowork, using the Cowork message, to confirm it's usable for writing.

**Split into two sessions:** (A) the shared data, `every-run.csv`, the tables and the
recompute check, ending with Garron opening `every-run.csv` in a spreadsheet; (B) the
charts, the page, the Cowork message, the READMEs and docs.

**Built (session B, 2026-10-01 to 2026-10-02).**
- **Results page** (`README.md` in the folder): what was tested, pass rate per model with
  its 95% range, same verdict every run, failures by label, splits, limits, file list.
  Headings state the finding, worked out from the data. Title (Garron): "VLM accuracy when
  extracting bounding dimensions from 2D engineering drawings", with VLM defined in the
  first sentence.
- **Charts (Garron's pick):** pass rate by model with ranges; same verdict every run; failures
  by label in run 1. Each PNG sits beside the CSV it draws.
- **Checks:** the page, chart data and the main README's results section are rebuilt from
  `every-run.csv` and must match exactly; a quiet check fails on any number typed into the
  page's own text. `tables/label-review.csv` (how often Garron kept the agent's label) is the
  one table built from the casebook, and is checked against it.
- **No name in published results (Garron, 2026-10-01):** the folder says "the evaluator".
  The agent's evidence notes have his name swapped out on publish, and the publish check
  refuses a folder that names him.
- **Folder date:** the run's last reply, so a rebuild replaces the folder.
- **Cowork message** (`runs/cowork-message-<folder>.md`): Garron's answers from
  `runs/cowork-notes.md` in the first person, the files to attach, the failure labels and
  definitions (not the playbook, whose worked examples come from earlier work with retired
  models), and the rules the paper must keep. **The paper stands alone (Garron,
  2026-10-02):** it reports pass and failure rates and labels the failures; it does not
  answer or compare with his earlier anecdotal paper.

---

### Chunk 10b: Full run (added 2026-09-29)

**Remind Garron before starting:** the other 111 drawings, once each, all 3 models
(about $16). Ask him first, then show the plan and estimate as usual.

No chunk ran all 141 drawings, so the report and Chunk 11's retest would have rested
on 30. Garron chose this over the full 141 x 3 runs x 3 models (about $62) on cost:
- **Cost basis:** $0.147 per drawing for all three models (Opus $0.067, Sol $0.031,
  Gemini $0.048), the average of the saved stock-shape calls with extraction.
- **Why 141 drawings once beats more runs:** at 30 drawings, 26 passing is 87% with a
  95% range of 69% to 96%; the same rate over 141 drawings narrows to 80% to 92%.
  Three runs on the 30 (Chunk 10) are enough to measure consistency.

**Build:** mostly running. `/diagnose-failures` on the new failures (about 1 reply in
10 failed on the 30-set, so about 33 are expected; a repeat takes Garron's label
automatically), Garron reviews every new label (2.6), then `/build-report` again.

**Garron checks:** the results page covers all 141 drawings.

---

### Chunk 11: Top-model retest, docs, publish prep

**Build:**
- `/retest-failures`: failed drawings go to each maker's top model, and the
  results appear as a report section.
- Final user guide, public README, and a check of the published folder layout
  (no keys, no costs, no test runs).

**Garron checks:** he runs the retest on the 30-drawing failures, sees the new
report section, and reads the user guide end to end without needing help.

**Parallel within:** two subagents at once: the retest command, and the docs.

---

## 5. Parked for later (only with evidence they're needed)

- **Multi-agent diagnosis** (e.g. 3 independent diagnosers), only if one agent
  proves useful and disagreement data suggests it would help.
- **Batch mode** (about half price, results within 24 hours) for large runs.
- **Ground truth from SolidWorks files:** exact native values, and a possible
  path to automatic ground truth for much larger evaluations.
- **More chain and datum-referenced drawings**, so those failure types can be
  reported as rates.
- **Extra failure labels** (callout misread, stock-size substitution), if Unclassified
  shows them recurring. **Watch list:** cases filed under an existing label until there
  are enough to judge a new one. The agent writes `Watch list: <name>` in the note, so
  one search finds them all for reclassifying. (Over-aggregation started here and became
  a label on 2026-10-10, 2.6.)
  - stock-size substitution: 201581-008 (stock-shape run, Opus), filed as Unclassified
- **A second prompt that names the answer's shape** ("...for a part that would be made
  from round stock, give Dia and L..."). Parked 2026-09-20. It was proposed to settle
  the box-versus-cylinder arguments, which the scoring fix in 2.5 settled instead. Of
  the 10 failures in the first real run, exactly one (Gemini's across-flats answer on
  90-100013-A) is a format failure the instruction would prevent; the rest are chains
  and misread views. At n=30 the 95% ranges already overlap (28 of 30 runs roughly
  79-98%), so a few points of difference could not be measured, and a second condition
  doubles the cost of every later run. **If a prompt condition is ever added, chains are
  the interesting one**, since they are the dominant failure: it would separate "can't
  see it" from "wasn't asked to add them up".
