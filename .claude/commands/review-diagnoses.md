---
description: Review the diagnosis labels on a local page and save your answers to the casebook
---

Open the page where Garron accepts or changes each diagnosis label (SPEC 2.6, Chunk 9).
Garron is not a developer: use plain English. Nothing here calls a paid model API.

The run to review is `$ARGUMENTS` if given, otherwise `main-stock-shape` (the prompt in
use since 2026-09-20).

## 1. Open the page

Run `uv run vlm-eval review-diagnoses <folder>` in the background. It prints the page's
address and opens it in Garron's browser. If it says there are no diagnoses for that run,
tell Garron to run `/diagnose-failures` first and stop.

## 2. Tell Garron what to do

In plain words, say:
- The review page is open in his browser (give the address it printed).
- Each card is one failure: his sizes beside what each model gave (✓ right, ✗ missed and
  the number it gave instead), the whole drawing, the agent's note with the numbers it
  relies on, and the model's reply (click to open it).
- For each missed size: press **Accept** if the label is right. Otherwise pick his label
  from the list, write a one-line reason, and press **Save change**. The note box is for
  anything else he wants kept.
- Each answer saves the moment he clicks, so he can stop and come back. Saving again
  replaces his earlier answer.
- On `main-stock-shape`, reasons from his 2026-09-24 read are filled in where he gave
  one. They are marked, and nothing is saved until he clicks.
- His labels, reasons and notes go into `data/casebook.jsonl`, which will be published
  with the results.
- Tell you when he's done.

Don't poll the page while he works.

## 3. When he's done

Stop the page. Then run:

```
uv run python -c "from vlm_eval import casebook; a = casebook.agreement('<folder>'); print(a.text()); [print(e) for e in a.changed]"
```

Report, in plain words:
- how many labels he reviewed, out of how many on the page
- the agreement rate and its 95% range, exactly as `text()` gives it
- for each label he changed: the drawing, his sizes, what the model got right and what it
  got wrong (from the page's table or `runs/diagnoses/<folder>/<group>/brief.md`), the
  agent's label → his label, and his reason

On `main-stock-shape`, say that this is a second read of labels he already saw on
2026-09-24, not a blind test.

Then remind him of the SPEC 2.6 decision point: if agreement is high, later runs review
every Unclassified group plus a random 20% sample; if it is low, diagnoses stay drafts for
him to fix. The decision is his.
