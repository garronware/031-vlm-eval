---
description: Build the published results folder and the private Cowork message for a run
---

Build the results folder for a run (SPEC 2.10, Chunk 10). Garron is not a developer: use
plain English. Nothing here calls a paid model API; it reads saved replies only.

The run is `$ARGUMENTS` if given, otherwise `main-stock-shape` (the prompt in use since
2026-09-20).

## 1. Build

Run `uv run vlm-eval build-report <folder>`. It writes `results/<date>-<run>/`, dated by the
run's last reply, so a rebuild replaces the folder rather than adding a second one. It also
updates the results section of the main `README.md` and writes the Cowork message.

There are two evaluations, each with its own folder and paper: without `--drawings`, the
141-drawing eval (run 1 only); with `--drawings 30`, the 30-drawing eval (runs 1 to 3). A
folder holds only the runs every one of its drawings has. Every build rewrites the main
README's results section to list every folder in `results/`. If Garron's labels or ground
truth changed, rebuild both.

The results page is a research report (SPEC 2.10): abstract; numbered sections for the
introduction, method, results, limitations, and data and code; appendices for the failure
labels, one example of each, and the tolerance audit. Every number, including section,
table and figure numbers, comes from code.

It prints one line per check:
- **recompute:** every table, chart and number on the results page, rebuilt from
  `every-run.csv`, matches.
- **publish:** no costs, keys, private paths or Garron's name in the folder.
- **main README:** the README's results section matches every results folder.

If a check found problems, show Garron the grouped list it printed and stop: don't commit
a folder that fails a check. If it says replies still need their numbers pulled out, or
that missed sizes don't have Garron's label yet, say so in one line each.

## 2. The Cowork message

If it printed `Cowork message: runs/cowork-message-<folder>.md`, that file is the private
message Garron pastes into Cowork, naming the files to attach. If it printed "No Cowork
message yet", ask Garron the Cowork questions one at a time (what the paper is for, who
reads it, anything it must or must not say), save his answers in his own words, in the first
person, to `runs/cowork-notes.md`, and run the build again.

## 3. Show Garron

Commit the folder and the README, push to `origin main`, then open the folder on GitHub for
him (`open https://github.com/garronware/031-vlm-eval/tree/main/results/<folder>`): the
results page shows under the file list, with its charts. Tell him the headline numbers in
two or three lines and what to look at.
