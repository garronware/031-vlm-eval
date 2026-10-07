---
description: List every command in this project with a one-line reminder
---

Print this list for Garron exactly as written, nothing else:

**In Claude Code**
- `/run-eval`: pick models and drawings, see the cost, approve, run. Also resumes a stopped run.
- `/diagnose-failures`: groups the failures in a run and explains each with your labels. No API fees.
- `/review-diagnoses`: the page where you accept or change each label. Saves to your casebook.
- `/build-report`: builds the published results folder and the private Cowork message. Free.
- `/show-commands`: this list.

**In the terminal (or type `!` first in Claude Code)**
- `uv run vlm-eval list-runs`: every run plan, its status, and what's left.
- `uv run vlm-eval stop-run`: stops a running run after the calls under way. Nothing paid for is lost.
- `uv run vlm-eval run-eval <plan>`: resumes a stopped run.
- `uv run vlm-eval approve-run <plan>`: approves a plan, or a paused run's next stretch.
- `uv run vlm-eval replay [plan]`: re-scores saved replies and opens the results page. Always $0.
- `uv run vlm-eval extract [--send]`: pulls numbers out of saved replies (free without `--send`).
- `uv run vlm-eval test-connections [--send]`: checks each model can be reached (free without `--send`).
- `uv run vlm-eval failure-groups [run]`: lists failure groups and which still need a diagnosis. Free.
- `uv run vlm-eval check-diagnoses [run]`: checks the diagnoses and opens the list page. Free.
- `uv run vlm-eval review-diagnoses [run]`: opens the review page. Free.
- `uv run vlm-eval build-report [run]`: builds the results folder and the Cowork message. Free.
- `uv run vlm-eval drawing-view <drawing>` / `drawing-numbers <drawing>`: look at a drawing the way the diagnosis agent does.
- `uv run vlm-eval grading-examples`: opens the page showing how replies are graded.
- `uv run vlm-eval confirm-inch-values`: the one-time inch-value review page (done).
- `uv run vlm-eval build-foundation`: rebuilds `data/` after you edit `ground-truth.md`.
- `uv run pytest`: the quiet checks. One line if everything is fine.

Full guide: `docs/user-guide.md`. Spending limits: `docs/billing-limits.md`.
