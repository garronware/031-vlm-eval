---
description: Pick models and drawings, see the cost, approve, and run the evaluation
---

Run an evaluation for Garron (SPEC 2.7, Chunk 6). Garron is not a developer: use plain
English, and put everything he needs to answer inside each question box (text above
the box is hidden while it is open). Every number you show comes from the commands
below, never from your own arithmetic. Paid calls happen only after he approves.

## 1. Check for an unfinished run first

Run `uv run vlm-eval list-runs`. If any plan is `stopped` or `paused over estimate`, ask
(one question box) whether to resume it or start a new run. Put its name, status, and
how many calls are left in the question.
- **Resume a stopped run:** go to step 5 with that plan name. It is already approved.
- **Continue a paused run:** go to step 4 (show it and ask for a new approval).

## 2. Ask what to run (one box, four questions)

1. **Models** (multiSelect): Claude Opus 5 (`claude-opus-5`), GPT-5.6 Sol
   (`gpt-5.6-sol`), Gemini 3.1 Pro (`gemini-3.1-pro-preview`). Say in the question
   that Grok is off because xAI's API can't read a PDF.
2. **Drawings:** 30 (Recommended, the fixed balanced set) / 60 / 141 / Test run (5
   drawings, kept out of published results). "Other" can give a test run of 1 to 29.
3. **Runs per model:** 1 / 3 (Recommended) / 5. Say "Other" takes 2 or 4.
4. **Thinking:** Each maker's default (Recommended: what users get) / Choose per model.

If he picks "Choose per model", ask one more box with one question per chosen model.
Offer the maker default plus up to 3 levels from `levels` in `config/models.yaml`, and
say "Other" takes any other listed level.

## 3. Make the plan (free)

```
uv run vlm-eval plan-run --models <ids,comma-separated> --drawings <30|60|141|test> \
  [--test-count N] --runs <1-5> [--thinking <id>=<level>,...]
```

Show Garron the printed plan as-is.

## 4. Ask for approval (one box)

The question includes the plan name, the estimated cost, what the estimate is based
on, and the spending that would pause the run (+25%). Options: "Yes, run it" / "No".
If yes: `uv run vlm-eval approve-run <plan name>`.

## 5. Run it in the background

Start `uv run vlm-eval run-eval <plan name>` with `run_in_background`, and tell
Garron he can say "stop" at any time. If he does, run `uv run vlm-eval stop-run`: the
run stops after the calls under way finish, and nothing paid for is lost. Don't poll;
wait for the finish notice.

## 6. When it ends

Read the output and tell Garron in plain words:
- **done:** estimated vs actual cost, how many passed, and that the results page is
  `runs/replay.html` (`uv run vlm-eval replay <plan name>` reopens it for $0).
- **stopped:** how many are left, and that `/run-eval` resumes it.
- **paused over estimate:** spent vs approved, then go to step 4 for a new approval.
- Any "NO REPLY" lines: say which calls got no reply. Running again retries only those.
