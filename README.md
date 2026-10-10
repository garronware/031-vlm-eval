# VLM Bounding-Dimension Evaluation

This repo measures the rate at which vision-language models (VLMs) extract accurate
bounding dimensions from 2D engineering drawings. The context is manufacturing: the
engineering drawings in this repo are manufacturing prints.

The point of this repo is to provide evaluators with a turnkey VLM evaluation tool,
complete with drawings, two eval protocols (30 drawings run three times, and 141 drawings
run once), and agentic failure diagnosis. So when a new model releases, an evaluator can clone the
repo, add their API keys, and choose the models they want to test.

When the eval is finished, the evaluator will have an accuracy rate for each of the models
they decided to test. That accuracy rate essentially means: what percentage of the time
does the model in question return the perfect bounding dimensions for a given drawing?

All drawings included in this repo are for individual parts only. That is, there are no
assembly drawings. This is just parts.

## Why this matters

This evaluation matters because it can give manufacturing professionals a sense of how
close general-purpose AI models (i.e., models that aren't specifically trained on
manufacturing and engineering data) are to "understanding" a manufactured part without the
CAD model. Anyone who's used language models to interpret manufactured part prints knows
how capable the models already are, and how good they are at providing machining advice,
workholding advice, and setup advice. Accurate bounding dimensions are honestly one of the
last things preventing a general-purpose AI from being meaningfully useful to, say, a
machine shop owner or a CNC machinist.

See [SPEC.md](SPEC.md) for the design and [docs/user-guide.md](docs/user-guide.md)
for how to run it.

## Layout

| Path | What's in it |
|---|---|
| `drawings/` | 141 PDFs and `ground-truth.md`, the only hand-edited source of truth |
| `data/` | Generated from the table above; rebuild, never hand-edit |
| `src/vlm_eval/` | The Python package |
| `tests/` | Quiet checks |
| `config/` | Models, thinking levels, prices, on/off |
| `docs/` | User guide, diagnosis playbook, scoring rules |
| `runs/` | Private working data: raw calls, costs, test runs, failure diagnoses |
| `results/` | Published handoff folders only |

## Getting started

```sh
uv sync
uv run vlm-eval build-foundation   # rebuild data/ from the ground-truth table
uv run vlm-eval grading-examples   # open the grading examples page
uv run vlm-eval test-connections   # free check that each model can be reached
uv run pytest                      # quiet checks
```

<!-- results:start -->

## Results

This repository holds 2 evaluations, each with its own results folder.

### 30 drawings, each answered 3 times by each model

The models answered between 2026-09-20 and 2026-09-29. The table counts each model's first answer (run 1) for each drawing. Running every drawing more than once also shows whether a model gives the same verdict every time.

| Model | Drawings passed | 95% range |
|---|---|---|
| Claude Opus 5 | 26 of 30 | 69% to 96% |
| GPT-5.6 Sol | 29 of 30 | 83% to 100% |
| Gemini 3.1 Pro (preview) | 26 of 30 | 69% to 96% |

[The results page](results/2026-09-29-stock-shape-30-drawings/) has every table and chart, and every reply.

### 141 drawings, each answered once by each model

The models answered between 2026-09-20 and 2026-10-03. The table counts each model's first answer (run 1) for each drawing. It includes the 30 drawings above, with the same run 1 answers.

| Model | Drawings passed | 95% range |
|---|---|---|
| Claude Opus 5 | 129 of 140 | 86% to 96% |
| GPT-5.6 Sol | 138 of 140 | 95% to 100% |
| Gemini 3.1 Pro (preview) | 121 of 139 | 80% to 92% |

[The results page](results/2026-10-03-stock-shape-141-drawings/) has every table and chart, and every reply.

<!-- results:end -->

## License

The repository has separate licenses for its software and engineering
materials:

- **Source code and software-focused documentation:** licensed under the
  [MIT License](LICENSE).

- **Engineering drawings, scans, images, datasets, annotations, and drawing-derived materials:** 
  licensed under the [Jus-Rite Engineering Research-Use Materials License](DRAWINGS-LICENSE).

The drawings and related materials may be used for research and experimental
development-including AI/ML training, evaluation, annotation, and commercially
funded research-subject to `DRAWINGS-LICENSE`.

They may not be used without separate written permission for production
manufacturing, fabrication, construction, operational engineering, safety or
compliance decisions, or as engineering content in a commercial product or
service beyond research and experimental development.

The drawings are historical research materials and are not verified for
current manufacturing, safety, regulatory, or operational use.
