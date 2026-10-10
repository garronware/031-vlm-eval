# User guide

Plain-English guide to running this project. Updated as each chunk ships.

## What the project does

It sends 141 engineering drawings to several AI models, asks each one for the
part's bounding dimensions, and scores the answers against the dimensions you
recorded by hand. Then it explains why the failures happened and packages the
results for the whitepaper.

## Where things live

| Folder | What's in it |
|---|---|
| `drawings/` | The 141 PDFs and `ground-truth.md` — your table. The only file you edit by hand. |
| `data/` | Generated from your table. Never edit these; rebuild them instead. |
| `runs/` | Private working data: raw model replies, costs, test runs. Never published. |
| `results/` | Finished handoff folders, meant to be public. No keys, no costs, no test runs. |
| `_tmp/` | Scratch. Screenshots, pasted files. Never committed. |

## Commands available so far

### `uv run vlm-eval build-foundation`

Rebuilds everything in `data/` from your table and prints a summary. Costs
nothing and calls no model. Run it any time you change `ground-truth.md`.

It produces three files:

- **`data/ground-truth.csv`** — your table in a form code can read, plus four
  things worked out from it: whether the drawing is dual-dimensioned or
  inch-only, whether its text is readable or it's an image-only scan, whether
  its dimensions are chained, and where a chain is measured from.
- **`data/inch-partners.csv`** — for each millimetre value you recorded, the
  inch number printed beside it on the sheet. Most are found automatically; the
  rest are marked for you to confirm.
- **`data/drawing-sets.csv`** — which drawings are in the fixed 30 and the fixed
  60. These never change, so runs on different days can be compared.

### `uv run vlm-eval grading-examples`

Opens a page in your browser showing how replies will be graded: pretend
replies to real drawings from your set, each with PASS, FAIL or NOT GRADED and a
plain reason. The right answer is always your own number from ground-truth.md.
For each row, ask: if a model replied this, would I grade it the same way? The
results come from the scorer itself, so a row that looks wrong means the scorer
needs fixing. The page is saved as `data/grading-examples.html`.

The full rules are in `docs/scoring-rules.md`.

### `uv run vlm-eval confirm-inch-values`

Opens the one-time review page in your browser for confirming the inch value
printed beside each mm value. Your answers save as you go. Done: all 327 values
now have an inch value to score against.

### `uv run pytest`

Runs the quiet checks. You should see one line saying everything passed. If
something is wrong you get a short list of the specific problems, not a wall of
output.

## Your table: `drawings/ground-truth.md`

This is the only file you edit by hand. A few things worth knowing:

- **Chain dimensions** are written as a sum, like `15.6 + 22.5 = 38.1`. Code
  reads both the pieces and the total from that, so you never need a separate
  column saying it's a chain.
- **`Measured From`** applies only to chain drawings. `Part Edge` means zero is
  at an outside edge of the part, which is normal. `In-Between Edges` means zero
  sits between the two edges, so the bounding dimension is the sum of two
  dimensions on opposite sides of zero. Nothing else in the file can tell us
  this — it only comes from you.
- Everything in `data/` is thrown away and rebuilt from this file, so an edit
  here is never lost.

### `uv run vlm-eval test-connections`

Checks that the models can be reached, for free. It makes sure each switched-on
maker's key is in `.env`, and asks each maker whether the model names in
`config/models.yaml` exist. Then it prints the plan and the estimated cost, and
stops. Nothing is sent to any model.

### `uv run vlm-eval test-connections --send`

Costs money (about 50 cents). Sends drawing 201533-020 once to each switched-on
model, with the fixed prompt and the PDF exactly as it is. Stops early if
spending passes the estimate by 25%. When done it opens a page showing each
model's reply word for word, the exact model version, tokens, time and cost.
Running it again the same day doesn't pay twice: calls already saved are shown,
not re-sent.

Every call is saved in `runs/calls/` (private, never published), one file per
call, with everything the maker sent back.

### `uv run vlm-eval extract`

Free. Lists the saved replies that haven't had their numbers pulled out yet,
and shows the estimated cost of doing it. Nothing is sent.

### `uv run vlm-eval extract --send`

Costs a little (about a third of a cent per reply). A small model, Claude Haiku
4.5, reads each reply as plain text and copies out the sizes it gives. It never
sees the drawing or your numbers, and it never decides right or wrong. It
follows your standard: a size counts if a person reading the reply would know
it's the answer, even if it's hedged or in a note. A stock size to order or a
number given as evidence is left out.

Code then checks that every number it copied is really in the reply, as a whole
number. If the reply never writes a unit, any unit the small model filled in is
set aside and both mm and inch are tried. If one isn't, or the reply has no clear answer, the reply is marked
**NOT GRADED** with the reason, never guessed.

Each reply is done once and saved in `runs/extractions/`. Running it again skips
replies already done. It stops early if spending passes the estimate by 25%.

### `uv run vlm-eval replay`

Free, always. Scores every saved reply again from the saved files and opens a
page (`runs/replay.html`) showing each reply, the numbers pulled from it, your
numbers, and the result. It never sends anything to any model, so running it
twice gives the same page. Add a run name (e.g. `uv run vlm-eval replay
connection-test-2026-09-18`) to show just that run.

### `/run-eval` (in Claude Code)

The way to run an evaluation. Claude asks four things in one box: which models, how
many drawings (30, 60, 141, or a 5-drawing test run), how many runs per model, and
thinking level. Then it shows the plan and the estimated cost, and sends nothing until
you say yes. The estimate is based on the average of the calls already saved for each
model, and the plan says so.

- **Stopping:** say "stop" (or run `uv run vlm-eval stop-run`). The calls under way
  finish and are saved, so nothing you paid for is lost.
- **Resuming:** run `/run-eval` again. It offers to finish the stopped run, and only
  sends what's left. Nothing is ever sent twice.
- **Pausing:** if spending passes what you approved by 25%, the run pauses itself.
  `/run-eval` shows what was spent and asks you to approve the rest. The check happens
  before each call starts, so a run can go past the limit by one call. On the first
  5-drawing test run that was 4.5 cents; on a 30-drawing run one call is a fraction
  of a percent.
- **Adding up across days:** real runs share one set of saved calls. Running GPT next
  week doesn't redo Claude, and a 60-drawing run after a 30-drawing run only sends the
  30 new drawings. A different thinking level is saved separately, so settings never mix.
- **Test runs** (fewer than 30 drawings) are saved separately and marked TEST RUN, so
  they never reach published results.
- **Results:** when a run ends, the results page shows estimated vs actual cost and
  three things: **by model** (replies passed, pass rate, sizes found, and how often the
  model gave the same verdict on a drawing every run), **runs passed per drawing**
  (2 of 3, 3 of 3, and so on, only when there's more than one run), and **every reply**
  with its pass/fail and what it missed. `uv run vlm-eval replay
  <plan name>` reopens it at any time for $0.

**Two prompts.** New runs ask the `stock-shape` prompt, which says to give Dia and L for
a part made from round stock and Thk, W and L for one made from rectangular stock. The
original bare prompt (`return bounding dimensions for this part`) is still available and
its results are kept. Each prompt's calls are saved in their own folder, so the two never
mix and neither counts as done for the other. The plan prints which prompt it will ask
and where the calls will be saved.

### `/show-commands` (in Claude Code)

Lists every command with a one-line reminder.

### `uv run vlm-eval list-runs`

Every run plan, its status (planned, running, stopped, paused over estimate, done),
and how many calls are left.

### `/diagnose-failures` (in Claude Code)

Explains why models failed, using your failure labels. It costs nothing in API fees: the
explaining is done by Claude Code agents on your Claude plan.

- It diagnoses the stock-shape prompt run by default. `/diagnose-failures main` does the
  bare-prompt run instead.
- Identical failures are grouped first (same drawing, same missed size, same wrong
  number) and explained once. On the stock-shape 30-set, 9 failed replies make 8 groups,
  because Opus and Gemini both gave 78.0 on 201513.
- For each missed size you get one label from your list, a short note, and the numbers
  the note relies on, with zoomed pictures of the drawing.
- Code checks that every cited number is printed on the drawing. On the 42 picture-only
  drawings there is no text to check against, so their citations say "can't check".
- The list opens as `runs/diagnoses.html`. `uv run vlm-eval check-diagnoses --no-open`
  rebuilds it without opening it.
- The agent's instructions are in `docs/diagnosis-playbook.md`.

### `/review-diagnoses` (in Claude Code)

Opens a page where you check the diagnosis labels. Free.
- One card per failed drawing: your sizes next to what each model gave, the drawing, the
  model's reply, and the agent's label with its note and evidence.
- For each missed size, press **Accept**, or pick another label, write a one-line reason
  and press **Save change**. Answers save as you click; you can stop and come back.
- Your answers go into `data/casebook.jsonl`, which the agent reads before labelling.
  When the same drawing fails with the same wrong number again, your label is applied
  automatically and marked "reused".
- The top of the page shows how often the agent agreed with you.
- Your reasons and notes will be published with the results.
- Terminal version: `uv run vlm-eval review-diagnoses [run] [--no-open]`.

### `/build-report` (in Claude Code)

Builds the results folder that gets published, and the private message for Cowork. Free:
it reads saved replies and sends nothing.
- The folder is `results/<date>-<run>/`, dated by the run's last reply. Rebuilding replaces
  it.
- Its `README.md` is the results page, laid out as a research report: an abstract, then
  numbered sections for the introduction, method, results, limitations, and data and code,
  then appendices (the failure labels, one example of each, and the tolerance audit).
  Tables and figures are numbered and captioned. The 30-drawing page has a section on
  consistency across runs; the 141-drawing page doesn't.
- `every-run.csv` carries your recorded sizes beside each reply.
- It holds three charts, every table as CSV, `every-run.csv` (one row per reply), every
  model's full reply, and the run settings.
- Every number on the page and in the charts is rebuilt from `every-run.csv` and must
  match. A second check keeps costs, keys and private paths out, and your name: the
  published folder says "the evaluator".
- A folder holds only the runs every one of its drawings has. So the 141-drawing folder
  holds run 1, and the 30-drawing folder holds runs 1 to 3. Each folder is one evaluation,
  and each can back its own paper.
- The label-review figure in each folder counts only your rulings on that folder's
  replies. Labelling failures on the 111 drawings outside the 30-drawing set never changes
  the 30-drawing figure; a ruling on one of the 30 drawings' failures can.
- The main `README.md` gets a results section listing every folder, smallest first, each
  with its own headline table and link. Every build rewrites it.
- The Cowork message goes to `runs/cowork-message-<folder>.md` (private). It is built from
  your answers in `runs/cowork-notes.md`; paste it into Cowork and attach the files it
  lists.
- Terminal version: `uv run vlm-eval build-report [run]` builds the 141-drawing folder.
- `uv run vlm-eval build-report --drawings 30` builds the 30-drawing folder.

### `uv run vlm-eval failure-groups [run]`

Lists the failure groups and which are still waiting for a diagnosis. Free.

### `uv run vlm-eval drawing-view <drawing>` and `drawing-numbers <drawing>`

The two drawing tools the diagnosis agent uses:
- `drawing-view` saves a picture of the whole sheet with a grid, or a sharp zoom of one
  region.
- `drawing-numbers` lists the numbers printed on a text drawing and where they sit.

You can run them yourself to look at a drawing the same way the agent does.

## Spending limits

The run controls are the first safety net. The second is a monthly limit on each
maker's billing page: `docs/billing-limits.md` has the steps for all three. For OpenAI,
tick **Enforce a hard limit**, or it only sends alerts.

## Your settings file: `config/models.yaml`

Lists each maker and model, whether it's switched on, its thinking level, and
its price. The `extractor` section at the bottom is the small model that pulls
numbers out of replies; it's never one of the models being tested. Edit it freely. A model runs only if both it and its maker are
switched on. Grok is switched off because xAI's API can't look at a PDF; the
reason is written in the file.

API keys go in `.env`, never in this file. `.env` is never committed.

## Coming next

- `/retest-failures`
