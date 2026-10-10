# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A system that evaluates how well frontier VLMs extract bounding dimensions from 2D engineering drawings. It runs 141 drawings through the models, scores answers against Garron's ground truth, diagnoses failures, and hands a data package to a separate whitepaper project in Claude Cowork.

- **@SPEC.md is the source of truth** for every design decision and the build plan. `brainstorming-starter.md` is superseded wherever they disagree.
- **Status:** Chunks 1 to 10 are built, and Chunk 10b's run is done: two evaluations are published in `results/` (30 drawings x 3 runs, and 141 drawings x run 1), each with its own folder and paper. Next: rewrite both results pages as research reports (SPEC 2.10), then Chunk 11. New runs use the `stock-shape` prompt (SPEC 2.1); the bare prompt is the baseline only. Build follows the chunks in SPEC.md section 4, one chunk per session. Each chunk ends with the check Garron runs himself. If a chunk runs long, stop at a checkable point and split it.
- **Starting a chunk:** read its SPEC.md section first. If it has a "Remind Garron before starting" line, tell him that before doing anything else.

---

## Project Structure

Layout from SPEC.md 2.13. Folders marked *(Chunk N)* don't exist yet. Update this section as chunks create them.

```
031-vlm-eval/
├── SPEC.md, CLAUDE.md, README.md, LICENSE, DRAWINGS-LICENSE
├── brainstorming-starter.md   superseded by SPEC.md; local only (git-ignored)
├── CLAUDE.local.md      Claude's private working notes; local only (git-ignored)
├── pyproject.toml, .env.example, .gitignore, .claude/settings.json
├── drawings/            141 PDFs + ground-truth.md (human-edited source) + README.md
├── data/                generated, never hand-edited: ground-truth.csv,
│                        inch-partners.csv, drawing-sets.csv, envelope-tolerances.csv, foundation-summary.md,
│                        grading-examples.html; plus files Garron's answers write:
│                        inch-confirmations.csv, casebook.jsonl (his diagnosis labels)
├── config/models.yaml   makers, models, thinking levels, prices, on/off (Grok off)
├── src/vlm_eval/        paths, ground_truth, inch_partners, drawing_sets,
│                        build_foundation, cli, review pages, answers (the form
│                        extraction fills), scoring, grading_examples,
│                        models_config, calls (send + save one call),
│                        connections/ (anthropic, openai, google), connection_test,
│                        extraction (reply -> answer form, `extract` command),
│                        replay (re-score saved files for $0, results table),
│                        run_plan (plans, estimates, approvals), runner (runs a plan),
│                        crops (drawing views and printed numbers), diagnosis
│                        (failure groups, diagnosis checks, reuse, list page),
│                        casebook (Garron's labels, agreement), diagnosis_review
│                        (the /review-diagnoses page), report (results folder,
│                        recompute and publish checks, Cowork message),
│                        report_page (the results page), report_charts
├── tests/               quiet checks
├── .claude/commands/    run-eval, show-commands, diagnose-failures,
│                        review-diagnoses, build-report; later: retest-failures
├── .claude/agents/      failure-diagnostician
├── docs/                user-guide.md, scoring-rules.md, billing-limits.md,
│                        diagnosis-playbook.md
├── runs/                private: calls/ (main/, main-stock-shape/, test/),
│                        extractions/, plans/, diagnoses/ (groups, briefs,
│                        diagnosis.json, views/), replay.html, diagnoses.html,
│                        cowork-notes.md (Garron's answers), cowork-message-*.md
├── results/             PUBLISHED handoff folders only: <date>-<run>/ with
│                        README.md (results page), every-run.csv, tables/,
│                        charts/, raw-replies/, run-settings.json
└── _tmp/                scratch
```

---

## Folder rules

- `_tmp/`: disposable scratch space. Don't review it, don't commit it. Save screenshots and pasted files here.
- `drawings/ground-truth.md` is the only human-edited ground truth. Everything in `data/` is generated from it (plus Garron's confirmed inch values); never hand-edit `data/`.
- Rebuild everything in `data/` with `uv run vlm-eval build-foundation`. Run the quiet checks with `uv run pytest`.
- `results/` will be public. Never put API keys, costs, or test runs (under 30 drawings) there. Costs and test runs live in `runs/`.
- API keys live only in `.env` (git-ignored).
- GitHub repo `garronware/031-vlm-eval` is **public**: every commit, commit message and tracked file is published. Private notes go only in git-ignored places: `CLAUDE.local.md` (Claude's working notes and rules from Garron's corrections), `runs/`, `.env`. Push each chunk to `origin main`. The repo's history before 2026-10-07 is in the private `garronware/031-vlm-eval-read-only-archive`.

---

## Invariants (easy to get wrong; details in SPEC.md)

- **Prompt:** new runs use the `stock-shape` prompt, word for word as SPEC 2.1 gives it (`run_plan.DEFAULT_PROMPT_ID`); the bare `return bounding dimensions for this part` is the baseline only. No system prompt, no other instructions.
- **PDFs are sent to tested models as-is.** Never rasterize for tested models. If a maker's API won't accept a PDF, stop and ask Garron.
- **Scores come from code only.** No LLM decides pass/fail. Extraction (Claude Haiku 4.5, text-only) is saved once and reused so re-scoring is identical.
- **Scoring (SPEC 2.5):** CUBE values match as an unordered set — never compare Thk to Thk, W to W, L to L. Accept any faithful reading (printed mm, printed inch, or either converted) within ±0.02 mm / ±0.0005 in; inch-only prints allow ±0.05 mm for mm answers. A size printed with a ± tolerance also accepts its upper limit (`data/envelope-tolerances.csv`), never the lower. Do not reintroduce the starter doc's ±0.20 mm window — it lets wrong printed numbers pass.
- **Failure labels (SPEC 2.6)** are Garron's list, one label per missed dimension. Don't add, rename, or redefine labels without his approval. One diagnosis agent only; multi-agent diagnosis is parked.
- **Paid API calls** only after showing the plan and cost estimate and getting Garron's approval. Pause at +25% over the approved estimate.
- **Drawings are licensed** under DRAWINGS-LICENSE. Send them only to the model APIs under test and the extraction/diagnosis steps in SPEC; don't upload or publish them anywhere else (e.g. artifacts, gists).
- **Shapes and units:** use the project's terms, `CUBE` and `CYL` (cylinder), never "box". `MM` rows in ground-truth.md are dual-dimensioned prints (`mm [in]`, both displays rounded independently; some inch-native, some mm-native, e.g. the 201552 series). `IN` rows are inch-only prints.
- **Chains** are written as sums on purpose (`34.29 + 6.35 = 40.64` in ground truth): the overall size isn't printed, so the model has to add the parts. Never collapse them into one number. `Measured From` applies only to chain drawings: `Part Edge` or `In-Between Edges` (the zero sits between the part's two edges); only Garron sets it.
- **Checks test the software, not the ground truth.** Never invent a "real answer" for a print; test traps use made-up, clearly wrong values. Every scoring rule must show how it rejects wrong answers, not just how it accepts right ones.
- **Published results never name the evaluator.** `results/` says "the evaluator", so a page reads the same for anyone who runs the pipeline; `report.unnamed` and the publish check enforce it.
- PDF text layer and renders: use Poppler's `pdftotext -bbox` and `pdftoppm` (installed via Homebrew). 99 PDFs have a text layer, 42 are image-only.

---

## Workflow Orchestration

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately — don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop
- After ANY correction from the user: add a rule to `CLAUDE.local.md` (private, git-ignored) to prevent the same mistake. Project facts a stranger needs go in this file instead.
- Write rules for yourself that are specific and actionable
- Ruthlessly iterate on these rules until mistake rate drops

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes — don't over-engineer
- Challenge your own work before presenting it

---

## File-Naming Conventions

### 1. For Claude Code extensions

Use lowercase `kebab-case` for all Claude Code extension names, directories,
and related implementation files. Use names that clearly state purpose; avoid
vague labels such as `helper`, `utils`, `tools`, `misc`, or numbered versions.

- **Skills:** *use gerund capability names:*
  `analyzing-drawings`, `testing-code`, `writing-documentation`.

- **Slash commands:** *use imperative action names:*
  `review-changes`, `run-quality-checks`, `prepare-release`.

- **Subagents:** *use role or capability names:*
  `drawing-analyst`, `code-reviewer`, `test-engineer`.

- **Hook scripts and identifiers:** *use lifecycle/action names:*
  `post-edit-formatting`, `pre-commit-validation`, `session-start-setup`.

- Keep the directory, frontmatter identifier, and primary implementation
  filename aligned whenever the tool does not require a different name.

### 2. For repository files

Use descriptive names with no spaces.

- **Default directories and TypeScript/JavaScript modules:** `kebab-case`.

- **Primary React component files:** `PascalCase`.

- **Python packages, modules, and tests:** `snake_case`.

- **Markdown documentation:** `kebab-case`.

- Preserve exact conventional or framework-required names, including
  `CLAUDE.md`, `README.md`, `package.json`, `pyproject.toml`, `.gitignore`,
  `.env.example`, and framework routing files.
