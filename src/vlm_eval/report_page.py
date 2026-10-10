"""The results page, `README.md` in each results folder (SPEC 2.10).

The page is a research report (Garron, 2026-10-06): title, abstract, introduction,
method, results with numbered tables and captioned figures, limitations, data and code,
and appendices. Headings are neutral and numbered; numbers are stated flatly. It speaks of
"the evaluator", never a name, so it reads the same for anyone who runs the pipeline.

Everything the page states is worked out here from its inputs: the rows of
`every-run.csv`, the tables, the run settings, the label-review table, the failure label
definitions and the scoring windows. The build and the recompute check call `page()` on
the same inputs, so the check can demand the same page byte for byte.

No number is typed into this file's text, not even a section or table number: every
number comes from the inputs or from a counter. A quiet check reads this file and fails
on a digit in any piece of fixed text.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

DOCS = "../../docs"  # the page sits two folders below the repository root
ROOT = "../.."

TITLE = "VLM accuracy when extracting bounding dimensions from 2D engineering drawings"

# Plain names for the ground-truth tags the split tables use.
TAG_NAMES = {
    "dimension_origin": "where the size comes from",
    "shape": "shape of the part",
    "pdf_type": "kind of PDF",
    "print_type": "units printed on the drawing",
}
GROUP_NAMES = {
    "calculated_chain": "Chain: the reader must add printed dimensions",
    "explicitly_dimensioned": "Printed as one dimension",
    "CUBE": "Cuboid (CUBE)",
    "CYL": "Cylinder (CYL)",
    "text": "PDF with a text layer",
    "image_only": "Image-only PDF",
    "dual": "Millimetres and inches",
    "inch_only": "Inches only",
}


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def _and(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _times(n: int) -> str:
    return "once" if n == 1 else f"{n} times"


def _rate(r: dict) -> str:
    """'26 of 30, 87% (69% to 96%)'; counts only for a group too small for a rate."""
    text = f"{r['passed']} of {r['replies_graded']}"
    if r["pass_rate_percent"]:
        text += f", {r['pass_rate_percent']}%"
    if r["range_low_percent"]:
        text += f" ({r['range_low_percent']}% to {r['range_high_percent']}%)"
    return text


def _range(r: dict) -> str:
    return (
        f"{r['range_low_percent']}% to {r['range_high_percent']}%"
        if r["range_low_percent"]
        else "none"
    )


def _source(name: str) -> str:
    return f"Source: [`{name}`]({name})."


class Numbers:
    """Hands out section, table and figure numbers in order, so none is typed."""

    def __init__(self) -> None:
        self.section = 0
        self.sub = 0
        self.tables = 0
        self.figures = 0

    def heading(self, title: str) -> str:
        self.section += 1
        self.sub = 0
        return f"## {self.section}. {title}"

    def subheading(self, title: str) -> str:
        self.sub += 1
        return f"### {self.section}.{self.sub}. {title}"

    def next_table(self) -> int:
        self.tables += 1
        return self.tables

    def table(self, caption: str, table: str) -> str:
        """Caption above the table, as research papers place it."""
        return f"**Table {self.next_table()}.** {caption}\n\n{table}"

    def figure(self, path: str, caption: str) -> str:
        """Caption below the figure."""
        self.figures += 1
        return f"![{caption}]({path})\n\n*Figure {self.figures}. {caption}*"


# --- what the inputs say -------------------------------------------------------------


class Facts:
    """Everything the page states, worked out once from the inputs."""

    def __init__(
        self,
        every_run,
        tables,
        settings,
        review,
        pooled,
        headline_run,
        small_group,
        label_definitions=(),
        windows=None,
    ):
        self.rows = every_run
        self.tables = tables
        self.settings = settings
        self.review = review[0] if review else {}
        self.pooled = pooled
        self.headline_run = headline_run
        self.small_group = small_group
        self.label_definitions = list(label_definitions)
        self.windows = windows or {}
        self.by_model = [r for r in tables["pass-rate-by-model"] if r["model"] != pooled]
        self.all_models = next(r for r in tables["pass-rate-by-model"] if r["model"] == pooled)
        self.first = [r for r in every_run if r["run"] == headline_run]

    @property
    def model_names(self) -> list[str]:
        return [r["model"] for r in self.by_model]

    def most_runs(self) -> int:
        return max((int(r["run"]) for r in self.rows), default=0)

    def runs_per_drawing(self) -> list[tuple[int, int]]:
        """(drawings, runs each), most runs first."""
        runs: dict[str, int] = defaultdict(int)
        for r in self.rows:
            runs[r["drawing"]] = max(runs[r["drawing"]], int(r["run"]))
        counts = Counter(runs.values())
        return [(counts[k], k) for k in sorted(counts, reverse=True)]

    def ran_again(self) -> bool:
        return any(k > 1 for _, k in self.runs_per_drawing())

    def drawings_with(self, tag: str) -> Counter:
        """Drawings per value of a ground-truth tag, each drawing counted once."""
        seen = {r["drawing"]: r[tag] for r in self.rows}
        return Counter(seen.values())

    def ranges_apart(self) -> list[tuple[str, str]]:
        """(higher, lower) model pairs whose 95% ranges don't overlap."""
        rows = [r for r in self.by_model if r["range_low_percent"]]
        return [
            (a["model"], b["model"])
            for a in rows
            for b in rows
            if int(a["range_low_percent"]) > int(b["range_high_percent"])
        ]

    def waiting(self) -> int:
        """Missed sizes still without the evaluator's label, across every run."""
        from vlm_eval.report import NOT_DIAGNOSED, NOT_REVIEWED

        return sum(
            label.endswith((NOT_DIAGNOSED, NOT_REVIEWED))
            for r in self.rows
            for label in r["label"].split("; ")
            if label
        )

    def labels_by_run(self) -> tuple[set[str], dict[str, set[str]]]:
        """Labels seen in run 1, and the labels each later run added."""

        def labels(row):
            return {p.split(": ", 1)[1] for p in row["label"].split("; ") if ": " in p}

        first = set().union(*(labels(r) for r in self.first))
        later: dict[str, set[str]] = defaultdict(set)
        for r in self.rows:
            if r["run"] != self.headline_run:
                later[r["run"]] |= labels(r) - first
        return first, later

    def failure_counts(self) -> tuple[int, int, list[dict]]:
        """(missed sizes in the headline run, those awaiting a label, the labelled rows)."""
        from vlm_eval.report import NOT_DIAGNOSED, NOT_REVIEWED

        rows = self.tables["failures-by-label"]
        total = sum(int(r["total"]) for r in rows)
        waiting = sum(int(r["total"]) for r in rows if r["label"] in (NOT_DIAGNOSED, NOT_REVIEWED))
        labelled = [r for r in rows if r["label"] not in (NOT_DIAGNOSED, NOT_REVIEWED)]
        return total, waiting, labelled

    def top_labels(self) -> tuple[list[str], int]:
        _, _, labelled = self.failure_counts()
        if not labelled:
            return [], 0
        most = max(int(r["total"]) for r in labelled)
        return [r["label"] for r in labelled if int(r["total"]) == most], most

    def consistency_rows(self) -> list[dict]:
        rows = [
            r for r in self.tables["consistency-by-model"] if r["same_answer_every_run_percent"]
        ]
        return sorted(rows, key=lambda r: int(r["same_answer_every_run_percent"]), reverse=True)

    def count(self, result: str, rows=None) -> int:
        return sum(r["result"] == result for r in (self.rows if rows is None else rows))

    def chain_drawings(self) -> int:
        return len({r["drawing"] for r in self.rows if r["dimension_origin"] == "calculated_chain"})


# --- the front matter ----------------------------------------------------------------


def _subtitle(f: Facts) -> str:
    runs = _and([f"{n} drawings, each answered {_times(k)}" for n, k in f.runs_per_drawing()])
    return f"*{runs} by each of {len(f.model_names)} models.*"


def _model_results(f: Facts) -> str:
    rows = sorted(f.by_model, key=lambda r: int(r["passed"]), reverse=True)
    parts = [
        f"{r['model']} passed {r['passed']} of {r['replies_graded']} drawings"
        + (f" ({r['pass_rate_percent']}%, 95% range {_range(r)})" if r["pass_rate_percent"] else "")
        for r in rows
    ]
    return _and(parts)


def _ranking(f: Facts) -> str:
    apart = f.ranges_apart()
    drawings = f.settings["drawings"]
    if apart:
        return (
            "The 95% ranges separate "
            + _and([f"{hi} from {lo}" for hi, lo in apart])
            + f"; the other models' ranges overlap, so {drawings} drawings are too few to "
            "rank them."
        )
    return (
        f"The 95% ranges of all {len(f.model_names)} models overlap, so {drawings} drawings "
        "are too few to rank the models."
    )


def _abstract(f: Facts) -> str:
    s = f.settings
    sentences = [
        f"This report measures how often {len(f.model_names)} vision-language models (VLMs) "
        "return the correct bounding dimensions of a machined part from its 2D engineering "
        "drawing.",
        f"The evaluator sent {s['drawings']} drawings to {_and(f.model_names)} with the same "
        "one-line prompt, and code graded every answer against sizes the evaluator recorded "
        "by hand.",
        f"On each model's first answer (run {f.headline_run}), {_model_results(f)}.",
        _ranking(f),
    ]
    consistency = f.consistency_rows()
    if f.ran_again() and consistency:
        low = consistency[-1]["same_answer_every_run_percent"]
        high = consistency[0]["same_answer_every_run_percent"]
        spread = f"{low}%" if low == high else f"between {low}% and {high}%"
        sentences.append(
            f"Each model answered each drawing {_times(f.most_runs())}; each gave the same "
            f"verdict on every run for {spread} of the drawings."
        )
    total, waiting, _ = f.failure_counts()
    top, most = f.top_labels()
    if waiting:
        sentences.append(
            f"The evaluator's labels for why models missed sizes are still under review "
            f"({waiting} of {total} missed sizes in run {f.headline_run} await a label)."
        )
    elif top:
        sentences.append(
            f"Of the {total} sizes the models missed in run {f.headline_run}, "
            f"{_and(top)} {'accounts' if len(top) == 1 else 'each account'} for {most}."
        )
    sentences.append(
        "An AI model proposed a failure label for each missed size, and the evaluator "
        "reviewed every label."
    )
    return "**Abstract.** " + " ".join(sentences)


def _introduction(f: Facts, n: Numbers) -> str:
    runs = f.most_runs()
    design = (
        f"Each model answered each drawing {_times(runs)}, so this evaluation also measures "
        "whether a model gives the same verdict every time it sees the same drawing."
        if f.ran_again()
        else "Each model answered each drawing once, so this evaluation does not measure "
        "run-to-run consistency."
    )
    return "\n\n".join(
        [
            n.heading("Introduction"),
            "A part's bounding dimensions are the overall sizes of the stock it is machined "
            "from. A part cut from rectangular stock (a cuboid, CUBE in this report) has "
            "three: thickness, width and length. A part cut from round stock (a cylinder, CYL) "
            "has two: diameter and length. A machinist reads them from the part's engineering "
            "drawing before choosing material, workholding and operations. "
            f"[Why this matters]({ROOT}/README.md#why-this-matters), in the repository's main "
            "README, explains why the evaluator measured them.",
            "This report asks one question: how often does a general-purpose vision-language "
            "model (VLM), an AI model that reads images as well as text, return every bounding "
            "dimension of a part correctly when given only the part's drawing?",
            design + f" The repository's [main README]({ROOT}/README.md#results) lists every "
            "evaluation and says which drawings and answers they share.",
        ]
    )


# --- method --------------------------------------------------------------------------


def _drawings(f: Facts, n: Numbers) -> str:
    s = f.settings
    shapes = f.drawings_with("shape")
    prints = f.drawings_with("print_type")
    pdfs = f.drawings_with("pdf_type")
    chains = f.chain_drawings()
    available = s.get("drawings_in_repository")
    chosen = (
        f"These {s['drawings']} drawings are a fixed subset of the {available} drawings in the "
        "repository, chosen once to mix shapes, units and kinds of PDF and to include every "
        "drawing whose size must be added up from printed dimensions. The same drawings are "
        "used every time, so runs on different days compare fairly."
        if available and available > s["drawings"]
        else f"The evaluation uses all {s['drawings']} drawings in the repository."
    )
    return "\n\n".join(
        [
            n.subheading("Drawings and recorded sizes"),
            f"Each drawing is a PDF of one machined part; none is an assembly. {chosen}",
            f"{shapes['CUBE']} parts are cuboids and {shapes['CYL']} are cylinders. "
            f"{prints['dual']} drawings print every size in millimetres with inches in "
            f"brackets, and {prints['inch_only']} print inches only. {pdfs['text']} PDFs carry "
            "a text layer, so a model can read their numbers as text; "
            f"{pdfs['image_only']} are images only. On {chains} drawings at least one bounding "
            "dimension is never printed whole: the reader must add printed dimensions "
            "together, which this report calls a chain.",
            "The evaluator recorded each part's bounding dimensions by hand from its drawing, "
            "in [`drawings/ground-truth.md`]"
            f"({ROOT}/drawings/ground-truth.md). On drawings that print both units, the "
            "evaluator recorded the millimetre value, and code found the inch value printed "
            "beside it. A chain is recorded as its parts and their sum.",
        ]
    )


def _models(f: Facts, n: Numbers) -> str:
    s = f.settings
    quoted = "\n\n".join(f"> {p}" for p in s["prompt"])
    models = [
        [m["name"], ", ".join(f"`{v}`" for v in m["versions"]), m["what_the_maker_default_means"]]
        for m in s["models"].values()
    ]
    runs = _and([f"{d} drawings {_times(k)}" for d, k in f.runs_per_drawing()])
    return "\n\n".join(
        [
            n.subheading("Models and prompt"),
            "Each model received the drawing's PDF file unchanged and this prompt, with no "
            "system prompt and no other instructions:",
            quoted,
            f"Each model answered {runs}. Each answer came from a fresh conversation with no "
            f"memory of earlier answers. The models answered between {s['dates']['first']} "
            f"and {s['dates']['last']}, each at its maker's default thinking setting.",
            n.table(
                "The models tested.",
                _md_table(["Model", "Version", "Maker's default thinking setting"], models),
            ),
        ]
    )


def _grading(f: Facts, n: Numbers) -> str:
    w = f.windows
    extractor = ", ".join(f"`{e}`" for e in f.settings["extraction_model"])
    return "\n\n".join(
        [
            n.subheading("Grading"),
            "Code decides whether an answer passes; no person or AI model judges it. A small "
            f"AI model ({extractor}) copies the numbers out of each free-text reply and never "
            "sees the drawing or judges the numbers.",
            "An answer passes only when it matches every recorded size and adds no extra "
            "size. A size matches when the answer is within "
            f"{w.get('dual_mm', '')} mm of the printed millimetre value or within "
            f"{w.get('inch', '')} in of the printed inch value, or of either one converted to "
            "the other unit. On drawings printed in inches only, a millimetre answer must be "
            f"within {w.get('inch_only_mm', '')} mm of the exact conversion. A size printed "
            "with a plus-or-minus tolerance also matches at its upper limit, because the part "
            "can be that large.",
            "A cuboid's three sizes may come in any order, because stock is ordered by its "
            "three sizes, not by which face is which. A cylinder's diameter and length may "
            "not be swapped. A cylinder answered as the box it fills (diameter, diameter, "
            "length) also passes. A chain matches when the answer gives its sum.",
            "The 95% range given with each pass rate is an exact binomial range: the span of "
            "true pass rates that could plausibly produce the count observed. "
            f"[The grading rules]({DOCS}/scoring-rules.md) give every detail.",
        ]
    )


def _labelling(f: Facts, n: Numbers) -> str:
    review = f.review
    reviewed = int(review.get("agent_labels_evaluator_reviewed") or 0)
    kept = (
        f" The evaluator kept Claude's label on {review['evaluator_kept_agent_label']} of "
        f"{reviewed} ({review['kept_percent']}%, 95% range {review['range_low_percent']}% to "
        f"{review['range_high_percent']}%) and changed the rest. "
        "[`tables/label-review.csv`](tables/label-review.csv) holds these counts; it is the "
        "one table built from the evaluator's review record rather than from "
        "[`every-run.csv`](every-run.csv)."
        if reviewed
        else ""
    )
    return "\n\n".join(
        [
            n.subheading("Failure labels"),
            "Each size a model missed gets one label that says why the model missed it. "
            "Claude, an AI model made by Anthropic, studied the drawing and proposed a label "
            "with evidence from the sheet. The evaluator reviewed every proposed label and "
            "kept or changed it. A failure that repeats an earlier one (the same drawing, "
            "missed size and wrong number) takes the evaluator's earlier label. Claude also "
            "labelled failures by Anthropic's own model, which is one reason the evaluator "
            f"reviewed every label.{kept}",
            "Appendix A defines the labels, and Appendix B gives one example of each.",
        ]
    )


def _method(f: Facts, n: Numbers) -> str:
    heading = n.heading("Method")
    return "\n\n".join([heading, _drawings(f, n), _models(f, n), _grading(f, n), _labelling(f, n)])


# --- results -------------------------------------------------------------------------


def _pass_rates(f: Facts, n: Numbers, charts: set[str]) -> str:
    table = _md_table(
        ["Model", "Drawings passed", "Pass rate", "95% range", "Sizes right"],
        [
            [
                r["model"],
                f"{r['passed']} of {r['replies_graded']}",
                f"{r['pass_rate_percent']}%" if r["pass_rate_percent"] else "too few to say",
                _range(r),
                f"{r['criteria_correct']} of {r['criteria_total']}",
            ]
            for r in f.tables["pass-rate-by-model"]
        ],
    )
    out = [
        n.subheading("Pass rate by model"),
        f"The table counts each model's first answer (run {f.headline_run}) to each drawing, "
        f"so each drawing counts once per model. {_model_results(f)}. {_ranking(f)}",
        n.table(
            f"Drawings passed per model, run {f.headline_run}. Sizes right counts every "
            "recorded size, and each part of a chain, separately. The row for all models has "
            "no range (see Limitations). " + _source("tables/pass-rate-by-model.csv"),
            table,
        ),
    ]
    if "pass-rate-by-model" in charts:
        out.append(
            n.figure(
                "charts/pass-rate-by-model.png",
                f"Drawings passed per model in run {f.headline_run}, with 95% ranges.",
            )
        )
    return "\n\n".join(out)


def _consistency(f: Facts, n: Numbers, charts: set[str]) -> str:
    rows = f.consistency_rows()
    heading = n.subheading("Consistency across runs")
    if not rows:
        return f"{heading}\n\nEach model answered each drawing once."
    stated = _and([f"{r['same_answer_every_run_percent']}% for {r['model']}" for r in rows])
    counts = sorted({r["drawings_run_more_than_once"] for r in rows})
    out_of = (
        f"each out of the {counts[0]} drawings it answered more than once"
        if len(counts) == 1
        else "out of the drawings each model answered more than once, as the table below shows"
    )
    table = _md_table(
        ["Model", "Drawings run more than once", "Passed every run", "Mixed", "Failed every run"],
        [
            [
                r["model"],
                r["drawings_run_more_than_once"],
                r["always_passed"],
                r["mixed"],
                r["always_failed"],
            ]
            for r in f.tables["consistency-by-model"]
        ],
    )
    out = [
        heading,
        "A drawing counts as consistent for a model when the model passed it on every run or "
        "failed it on every run. A mixed drawing passed on some runs and failed on others. "
        f"The share of drawings with the same verdict on every run was {stated}, {out_of}.",
        n.table(
            "Verdicts per model across runs. "
            + _source("tables/consistency-by-model.csv")
            + " Each drawing's runs passed are in "
            "[`tables/runs-passed-per-drawing.csv`](tables/runs-passed-per-drawing.csv).",
            table,
        ),
    ]
    if "consistency-by-model" in charts:
        out.append(
            n.figure(
                "charts/consistency-by-model.png",
                "Share of drawings each model passed every run, failed every run, or mixed.",
            )
        )
    return "\n\n".join(out)


def _failures(f: Facts, n: Numbers, charts: set[str]) -> str:
    heading = n.subheading("Missed sizes by failure label")
    rows = f.tables["failures-by-label"]
    if not rows:
        return f"{heading}\n\nNo model missed a size in run {f.headline_run}."
    total, waiting, _ = f.failure_counts()
    if waiting:
        lead = (
            f"Failure labels for run {f.headline_run} are under review: {waiting} of {total} "
            "missed sizes don't have the evaluator's label yet. Until the review is finished, "
            "the counts below are not a ranking of why the models failed."
        )
    else:
        top, most = f.top_labels()
        lead = (
            f"The models missed {total} sizes in run {f.headline_run}. {_and(top)} "
            f"{'accounts' if len(top) == 1 else 'each account'} for {most} of them."
        )
    models = [c for c in rows[0] if c not in ("label", "total")]
    table = _md_table(
        ["Label", *models, "Total"],
        [[r["label"], *(r[m] for m in models), r["total"]] for r in rows],
    )
    out = [
        heading,
        lead,
        n.table(
            f"Missed sizes in run {f.headline_run} by failure label and model. "
            + _source("tables/failures-by-label.csv")
            + " The same sizes by axis are in "
            "[`tables/failures-by-axis.csv`](tables/failures-by-axis.csv) and by size name in "
            "[`tables/failures-by-dimension.csv`](tables/failures-by-dimension.csv).",
            table,
        ),
    ]
    if "failures-by-label" in charts:
        out.append(
            n.figure(
                "charts/failures-by-label.png",
                f"Missed sizes in run {f.headline_run} by failure label.",
            )
        )
    _, later = f.labels_by_run()
    for run in sorted(later, key=int):
        if later[run]:
            out.append(
                f"Run {run} also produced missed sizes labelled {_and(sorted(later[run]))}, "
                f"which run {f.headline_run} did not. [`every-run.csv`](every-run.csv) lists "
                "every reply's labels."
            )
    return "\n\n".join(out)


def _split_cell(rows: list[dict], group_key: str, group: str, model: str) -> str:
    row = next((r for r in rows if r[group_key] == group and r["model"] == model), None)
    return _rate(row) if row else ""


def _splits(f: Facts, n: Numbers) -> str:
    out = [
        n.subheading("Results by kind of drawing"),
        f"Each cell gives drawings passed in run {f.headline_run}, the pass rate and its 95% "
        f"range. A group with fewer than {f.small_group} drawings shows only the count, "
        "because a rate from so few drawings would mislead. The column for all models has "
        "no range, for the reason given under limitations.",
    ]
    columns = [*f.model_names, f.pooled]
    for name, key in (
        ("by-dimension-origin", "dimension_origin"),
        ("by-shape", "shape"),
        ("by-pdf-type", "pdf_type"),
        ("by-print-type", "print_type"),
    ):
        rows = f.tables[name]
        groups = sorted({r[key] for r in rows})
        out.append(
            n.table(
                f"Run {f.headline_run} results by {TAG_NAMES[key]}. "
                + _source(f"tables/{name}.csv"),
                _md_table(
                    ["Group", *columns],
                    [
                        [
                            f"{GROUP_NAMES.get(g, g)}, "
                            f"{next(r['drawings'] for r in rows if r[key] == g)} drawings",
                            *(_split_cell(rows, key, g, m) for m in columns),
                        ]
                        for g in groups
                    ],
                ),
            )
        )
    return "\n\n".join(out)


def _results(f: Facts, n: Numbers, charts: set[str]) -> str:
    parts = [n.heading("Results"), _pass_rates(f, n, charts)]
    if f.ran_again():
        parts.append(_consistency(f, n, charts))
    parts += [_failures(f, n, charts), _splits(f, n)]
    return "\n\n".join(parts)


# --- limitations, data and appendices ------------------------------------------------


def _limits(f: Facts, n: Numbers) -> str:
    bullets = []
    if f.ran_again():
        bullets.append(
            f"The pass rates use run {f.headline_run} only, so each drawing counts once per "
            "model. Counting every run would count the drawings that ran more than once "
            "several times over and make the ranges look narrower than the evidence supports. "
            "The later runs feed only the consistency results."
        )
    bullets.append(
        f"The \"{f.pooled}\" row has no 95% range. All the models answered the same drawings, "
        "so their answers are not independent tries, and a range that treated them as "
        "independent would be too narrow."
    )
    chains = f.chain_drawings()
    if chains:
        bullets.append(
            f"Only {chains} drawings need a chain, so the chain results are counts, not rates."
        )
    bullets += [
        "Every answer responds to one prompt wording. The evaluation does not show how "
        "answers change under other wordings.",
        "Each model ran at its maker's default thinking setting. The evaluation does not "
        "test other settings.",
        "One person, the evaluator, recorded every bounding dimension and reviewed every "
        "failure label. No second person checked them.",
        "Code reads printed tolerances only from PDFs with a text layer, so on image-only "
        "PDFs only the nominal size matches.",
    ]
    waiting = f.waiting()
    if waiting:
        bullets.append(
            f'{waiting} missed sizes still wait for a label: they read "Not diagnosed yet" '
            'or "Not reviewed by the evaluator yet" in the tables.'
        )
    not_graded = f.count("NOT GRADED")
    if not_graded:
        one = not_graded == 1
        bullets.append(
            f"Code could not grade {not_graded} of {len(f.rows)} replies, because the small "
            "AI model that copies out numbers flagged "
            f"{'that reply' if one else 'those replies'} as unreadable. "
            f"{'That reply counts' if one else 'Those replies count'} as neither pass nor "
            "fail, and [`every-run.csv`](every-run.csv) marks "
            f"{'it' if one else 'them'} NOT GRADED."
        )
    audit = f.tables["tolerance-audit"]
    if audit:
        bullets.append(
            f"{len(audit)} passes in run {f.headline_run} relied on a number not printed as "
            "written: the model converting a printed number between millimetres and inches "
            "itself, or giving a size's upper tolerance limit. Appendix C lists them."
        )
    else:
        bullets.append(
            f"No pass in run {f.headline_run} relied on a model converting a printed number "
            "between millimetres and inches, or on a tolerance limit: every passing size "
            "matched a printed number."
        )
    return n.heading("Limitations") + "\n\n" + "\n".join(f"- {b}" for b in bullets)


def _files(n: Numbers, charts: set[str]) -> str:
    files = [
        ("every-run.csv", "one row per reply: the recorded sizes, the values returned, the "
         "verdict, sizes right, sizes missed, and the evaluator's label and evidence for "
         "each missed size"),
        ("tables/", "every table this report quotes, as CSV"),
        ("charts/", "each figure as a picture, with the numbers it draws beside it as CSV"),
        ("raw-replies/", "every model's full reply, word for word"),
        ("run-settings.json", "the models, versions, thinking settings, dates and prompt"),
        ("LICENSE-NOTICE.md", "the license these drawing-derived files fall under"),
    ]  # fmt: skip
    if not charts:
        files = [f for f in files if f[0] != "charts/"]
    return "\n\n".join(
        [
            n.heading("Data and code"),
            "\n".join(f"- [`{name}`]({name}): {what}" for name, what in files),
            "The code, the drawings and the recorded sizes are in this repository. "
            f"[The user guide]({DOCS}/user-guide.md) explains how to run the evaluation on "
            "other models.",
        ]
    )


def _definitions(f: Facts, n: Numbers) -> str:
    return "\n\n".join(
        [
            "## Appendix A: Failure labels",
            n.table(
                "The failure labels and their definitions. Source: "
                f"[the diagnosis playbook]({DOCS}/diagnosis-playbook.md).",
                _md_table(["Label", "Definition"], [[a, b] for a, b in f.label_definitions]),
            ),
        ]
    )


def _example(row: dict, size: str, label: str) -> str:
    evidence = next(
        (
            part.split(": ", 1)[1]
            for part in row["evidence"].split(" || ")
            if part.startswith(f"{size}: ")
        ),
        "",
    )
    lines = [
        f"**{label}.** Drawing {row['drawing']}, {row['model']}, run {row['run']}.",
        f"- Recorded sizes: {row.get('recorded') or 'not recorded'}",
        f"- The model gave: {row['values_returned']}",
        f"- Missed: {size}",
    ]
    if evidence:
        lines.append(f"- Evidence: {evidence}")
    return "\n".join(lines)


def _examples(f: Facts) -> str:
    from vlm_eval.report import NOT_DIAGNOSED, NOT_REVIEWED

    order = [label for label, _ in f.label_definitions]
    found: dict[str, tuple[dict, str]] = {}
    rows = sorted(f.rows, key=lambda r: r["run"] != f.headline_run)  # run 1 first, stable
    for r in rows:
        for part in r["label"].split("; "):
            if ": " not in part:
                continue
            size, label = part.split(": ", 1)
            if label not in (NOT_DIAGNOSED, NOT_REVIEWED) and label not in found:
                found[label] = (r, size)
    labels = sorted(found, key=lambda x: (order.index(x) if x in order else len(order), x))
    body = (
        "\n\n".join(_example(*found[label], label) for label in labels)
        if labels
        else "No missed size has a label yet."
    )
    return "\n\n".join(
        [
            "## Appendix B: One example of each failure label",
            f"Each example is the first reply in [`every-run.csv`](every-run.csv) with that "
            f"label, taking run {f.headline_run} first. The evidence is the evaluator's reason "
            "where the evaluator changed Claude's label, and Claude's note where the evaluator "
            "kept it.",
            body,
        ]
    )


def _audit(f: Facts, n: Numbers) -> str:
    rows = f.tables["tolerance-audit"]
    if not rows:
        body = f"No pass in run {f.headline_run} relied on a converted number or a tolerance limit."
    else:
        body = n.table(
            f"Passes in run {f.headline_run} that relied on a number not printed as written. "
            + _source("tables/tolerance-audit.csv"),
            _md_table(
                ["Drawing", "Model", "Run", "Reading used"],
                [[r["drawing"], r["model"], r["run"], r["converted_readings_used"]] for r in rows],
            ),
        )
    return "\n\n".join(["## Appendix C: Tolerance audit", body])


def page(
    every_run: list[dict],
    tables: dict[str, list[dict]],
    settings: dict,
    review: list[dict],
    charts: set[str],
    *,
    pooled: str,
    headline_run: str,
    small_group: int,
    label_definitions: list[tuple[str, str]] = (),
    windows: dict[str, str] | None = None,
) -> str:
    """The results page, from these inputs only."""
    f = Facts(
        every_run,
        tables,
        settings,
        review,
        pooled,
        headline_run,
        small_group,
        label_definitions,
        windows,
    )
    n = Numbers()
    sections = [
        f"# {TITLE}",
        _subtitle(f),
        _abstract(f),
        _introduction(f, n),
        _method(f, n),
        _results(f, n, charts),
        _limits(f, n),
        _files(n, charts),
        _definitions(f, n),
        _examples(f),
        _audit(f, n),
    ]
    return "\n\n".join(sections) + "\n"
# --- the main README's results section -----------------------------------------------

START = "<!-- results:start -->"
END = "<!-- results:end -->"


@dataclass(frozen=True)
class Evaluation:
    """One results folder, as the main README describes it."""

    link: str
    tables: dict[str, list[dict]]
    settings: dict
    first_answers: set[tuple[str, str]]  # (drawing, model) in the headline run


def _evaluation(e: Evaluation, earlier: list[Evaluation], pooled: str, headline_run: str) -> str:
    s = e.settings
    runs = s["most_runs_per_drawing"]
    text = (
        f"The models answered between {s['dates']['first']} and {s['dates']['last']}. "
        f"The table counts each model's first answer (run {headline_run}) for each drawing."
    )
    if runs > 1:
        text += (
            " Running every drawing more than once also shows whether a model gives the "
            "same verdict every time."
        )
    for other in earlier:
        if other.first_answers <= e.first_answers:
            text += (
                f" It includes the {other.settings['drawings']} drawings above, with the "
                f"same run {headline_run} answers."
            )
    rows = [r for r in e.tables["pass-rate-by-model"] if r["model"] != pooled]
    table = _md_table(
        ["Model", "Drawings passed", "95% range"],
        [
            [
                r["model"],
                f"{r['passed']} of {r['replies_graded']}",
                f"{r['range_low_percent']}% to {r['range_high_percent']}%"
                if r["range_low_percent"]
                else "none",
            ]
            for r in rows
        ],
    )
    return "\n\n".join(
        [
            f"### {s['drawings']} drawings, each answered {_times(runs)} by each model",
            text,
            table,
            f"[The full report]({e.link}) has every table and figure, and every reply.",
        ]
    )


def readme_section(evaluations: list[Evaluation], pooled: str, headline_run: str) -> str:
    """The results section the main README carries, between its two markers."""
    count = len(evaluations)
    intro = (
        "This repository holds one evaluation."
        if count == 1
        else f"This repository holds {count} evaluations, each with its own results folder."
    )
    return "\n\n".join(
        [
            START,
            "## Results",
            intro,
            *(
                _evaluation(e, evaluations[:i], pooled, headline_run)
                for i, e in enumerate(evaluations)
            ),
            END,
        ]
    )


def replace_section(readme: str, section: str) -> str:
    """The README with its results section swapped for this one (added if missing)."""
    if START in readme and END in readme:
        head, _, rest = readme.partition(START)
        _, _, tail = rest.partition(END)
        return head + section + tail
    head, sep, tail = readme.partition("\n## License")
    return head.rstrip("\n") + "\n\n" + section + "\n" + sep + tail
