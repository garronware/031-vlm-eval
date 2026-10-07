"""The results page, `README.md` in each results folder (SPEC 2.10, Chunk 10).

One page for a stranger on GitHub and for the whitepaper writer in Cowork. Everything
the page states is worked out here from four inputs: the rows of `every-run.csv`, the
tables, the run settings and the label-review table. The build and the recompute check
call `page()` on the same inputs, so the check can demand the same page byte for byte.

No number is typed into this file's text: every number comes from the inputs. A quiet
check reads this file and fails on a digit in any piece of fixed text.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

DOCS = "../../docs"  # the page sits two folders below the repository root

# Plain names for the ground-truth tags the split tables use.
TAG_NAMES = {
    "dimension_origin": "Where the size comes from",
    "shape": "Shape of the part",
    "pdf_type": "Kind of PDF",
    "print_type": "Units printed on the drawing",
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


# --- what the inputs say -------------------------------------------------------------


class Facts:
    """Everything the page states, worked out once from the inputs."""

    def __init__(self, every_run, tables, settings, review, pooled, headline_run, small_group):
        self.rows = every_run
        self.tables = tables
        self.settings = settings
        self.review = review[0] if review else {}
        self.pooled = pooled
        self.headline_run = headline_run
        self.small_group = small_group
        self.by_model = [r for r in tables["pass-rate-by-model"] if r["model"] != pooled]
        self.all_models = next(r for r in tables["pass-rate-by-model"] if r["model"] == pooled)
        self.first = [r for r in every_run if r["run"] == headline_run]

    @property
    def model_names(self) -> list[str]:
        return [r["model"] for r in self.by_model]

    def runs_per_drawing(self) -> list[tuple[int, int]]:
        """(drawings, runs each), most runs first."""
        runs: dict[str, int] = defaultdict(int)
        for r in self.rows:
            runs[r["drawing"]] = max(runs[r["drawing"]], int(r["run"]))
        counts = Counter(runs.values())
        return [(counts[k], k) for k in sorted(counts, reverse=True)]

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

    def count(self, result: str, rows=None) -> int:
        return sum(r["result"] == result for r in (self.rows if rows is None else rows))

    def chain_drawings(self) -> int:
        return len({r["drawing"] for r in self.rows if r["dimension_origin"] == "calculated_chain"})


# --- the sections --------------------------------------------------------------------


def _intro(f: Facts) -> str:
    drawings = f.settings["drawings"]
    return (
        "# VLM accuracy when extracting bounding dimensions from 2D engineering drawings\n\n"
        "This folder holds the results of one evaluation of vision-language models (VLMs): "
        "AI models that read images as well as text. The evaluator (the person who ran "
        f"this evaluation) sent {drawings} engineering drawings to {len(f.model_names)} VLMs "
        f"({_and(f.model_names)}) and asked each model for the part's bounding dimensions: "
        "the overall size of the stock the part is made from. Code then graded every "
        "answer against the sizes the evaluator recorded by hand from each drawing."
    )


def _setup(f: Facts) -> str:
    s = f.settings
    prompts = s["prompt"]
    quoted = "\n\n".join(f"> {p}" for p in prompts)
    models = [
        [m["name"], ", ".join(f"`{v}`" for v in m["versions"]), m["what_the_maker_default_means"]]
        for m in s["models"].values()
    ]
    runs = _and([f"{n} drawings {_times(k)}" for n, k in f.runs_per_drawing()])
    extractor = ", ".join(f"`{e}`" for e in s["extraction_model"])
    return "\n\n".join(
        [
            "## Each model received the drawing as a PDF and the same one-line question",
            "Each model received the drawing's PDF file unchanged and this question, with "
            "no system prompt and no other instructions:",
            quoted,
            f"Each model answered {runs}. Each answer came from a fresh conversation with "
            "no memory of earlier answers. The models answered between "
            f"{s['dates']['first']} and {s['dates']['last']}, each at its maker's default "
            "thinking setting:",
            _md_table(["Model", "Version", "Maker's default thinking setting"], models),
            "Code, not a person or an AI model, decides whether an answer passes. A small AI "
            f"model ({extractor}) copies the numbers out of each free-text reply and never "
            "judges them. An answer passes only when every size matches the evaluator's recorded "
            "size, read from either the printed millimetre value or the printed inch value. "
            "A cuboid part's three sizes may come in any order. "
            f"[The grading rules]({DOCS}/scoring-rules.md) give the exact tolerances.",
        ]
    )


def _pass_rates(f: Facts, charts: set[str]) -> str:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in f.by_model:
        groups[r["passed"]].append(r)
    order = sorted(groups, key=int, reverse=True)
    parts = []
    for i, passed in enumerate(order):
        names = _and([r["model"] for r in groups[passed]])
        total = groups[passed][0]["replies_graded"]
        each = " each" if len(groups[passed]) > 1 else ""
        drawings = " drawings" if i == 0 else ""
        parts.append(f"{names}{each} passed {passed} of {total}{drawings}")
    heading = "## " + ", ".join(parts)

    table = _md_table(
        ["Model", f"Passed (run {f.headline_run})", "Pass rate", "95% range", "Sizes right"],
        [
            [
                r["model"],
                f"{r['passed']} of {r['replies_graded']}",
                f"{r['pass_rate_percent']}%" if r["pass_rate_percent"] else "too few to say",
                f"{r['range_low_percent']}% to {r['range_high_percent']}%"
                if r["range_low_percent"]
                else "none",
                f"{r['criteria_correct']} of {r['criteria_total']}",
            ]
            for r in f.tables["pass-rate-by-model"]
        ],
    )
    apart = f.ranges_apart()
    if apart:
        verdict = "The 95% ranges separate " + _and(
            [f"{hi} from {lo}, whose range lies wholly below" for hi, lo in apart]
        )
        verdict += f". The other models' ranges overlap, so {f.settings['drawings']} drawings "
        verdict += "are too few to rank them."
    else:
        verdict = (
            f"The 95% ranges of all {len(f.model_names)} models overlap, so "
            f"{f.settings['drawings']} drawings are too few to say which model reads "
            "drawings best."
        )
    out = [
        heading,
        f"These counts use each model's first answer (run {f.headline_run}) for each "
        "drawing, so each drawing counts once per model.",
        table,
        verdict,
        "The 95% range is the span of true pass rates that could plausibly produce the "
        "count observed (an exact binomial range). A size counts as right when it matches "
        "the evaluator's recorded size. A chain counts each of its parts separately: a chain is a "
        "size the drawing never prints whole, which the reader must add up from smaller "
        "printed dimensions.",
        "Source: [`tables/pass-rate-by-model.csv`](tables/pass-rate-by-model.csv).",
    ]
    if "pass-rate-by-model" in charts:
        out.insert(3, "![Drawings passed by each model](charts/pass-rate-by-model.png)")
    return "\n\n".join(out)


def _consistency(f: Facts, charts: set[str]) -> str:
    rows = [r for r in f.tables["consistency-by-model"] if r["same_answer_every_run_percent"]]
    if not rows:
        return (
            "## No drawing ran more than once, so this run can't show consistency\n\n"
            "Each model answered each drawing once."
        )
    rows = sorted(rows, key=lambda r: int(r["same_answer_every_run_percent"]), reverse=True)
    lead, *rest = rows
    heading = (
        f"## {lead['model']} gave the same verdict on every run for "
        f"{lead['same_answer_every_run_percent']}% of the {lead['drawings_run_more_than_once']} "
        "drawings run more than once"
    )
    if rest:
        heading += ", " + _and(
            [f"{r['model']} for {r['same_answer_every_run_percent']}%" for r in rest]
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
        "A drawing counts as consistent when a model passed it on every run or failed it on "
        "every run. A mixed drawing passed on some runs and failed on others, so a single "
        "answer from that model on that drawing can't be trusted.",
        table,
        "Sources: [`tables/consistency-by-model.csv`](tables/consistency-by-model.csv), and "
        "[`tables/runs-passed-per-drawing.csv`](tables/runs-passed-per-drawing.csv) for "
        "each drawing.",
    ]
    if "consistency-by-model" in charts:
        out.insert(2, "![Same verdict on every run](charts/consistency-by-model.png)")
    return "\n\n".join(out)


def _failures(f: Facts, charts: set[str]) -> str:
    rows = f.tables["failures-by-label"]
    if not rows:
        return f"## No model missed a size in run {f.headline_run}"
    from vlm_eval.report import NOT_DIAGNOSED, NOT_REVIEWED

    total = sum(int(r["total"]) for r in rows)
    waiting = sum(int(r["total"]) for r in rows if r["label"] in (NOT_DIAGNOSED, NOT_REVIEWED))
    labelled = [r for r in rows if r["label"] not in (NOT_DIAGNOSED, NOT_REVIEWED)]
    intro = (
        "The evaluator gave each missed size one label that says why the model missed it. "
        f"[The diagnosis playbook]({DOCS}/diagnosis-playbook.md) defines every label."
    )
    if waiting:
        heading = (
            f"## Failure labels for run {f.headline_run} are under review: {waiting} of "
            f"{total} missed sizes don't have the evaluator's label yet"
        )
        intro += (
            " Until the review is finished, the counts below are not a ranking of why the "
            "models failed."
        )
    else:
        most = max(int(r["total"]) for r in labelled)
        top = [r["label"] for r in labelled if int(r["total"]) == most]
        verb = "caused" if len(top) == 1 else "each caused"
        heading = (
            f"## {_and(top)} {verb} the most missed sizes in run {f.headline_run}: "
            f"{most} of {total}"
        )
    models = [c for c in rows[0] if c not in ("label", "total")]
    table = _md_table(
        ["Label", *models, "Total"],
        [[r["label"], *(r[m] for m in models), r["total"]] for r in rows],
    )
    out = [heading, intro, table]
    if "failures-by-label" in charts:
        out.insert(2, "![Missed sizes by label](charts/failures-by-label.png)")
    _, later = f.labels_by_run()
    for run in sorted(later, key=int):
        if later[run]:
            out.append(
                f"Run {run} also produced missed sizes labelled "
                f"{_and(sorted(later[run]))}, which run {f.headline_run} did not. "
                "[`every-run.csv`](every-run.csv) lists every reply's labels."
            )
    out.append(
        "Sources: [`tables/failures-by-label.csv`](tables/failures-by-label.csv); missed "
        "sizes by axis in [`tables/failures-by-axis.csv`](tables/failures-by-axis.csv) and "
        "by size name in [`tables/failures-by-dimension.csv`](tables/failures-by-dimension.csv)."
    )
    return "\n\n".join(out)


def _split_cell(rows: list[dict], group_key: str, group: str, model: str) -> str:
    row = next((r for r in rows if r[group_key] == group and r["model"] == model), None)
    return _rate(row) if row else ""


def _splits(f: Facts) -> str:
    out = [
        f"## Splits by kind of drawing show counts only for groups under {f.small_group} drawings",
        "Each cell gives drawings passed in run "
        f"{f.headline_run}, the pass rate and its 95% range. A group with fewer than "
        f"{f.small_group} drawings shows only the count, because a rate from so few "
        "drawings would mislead. The all-models column has no range, for the reason "
        "given under the limits below.",
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
        out.append(f"**{TAG_NAMES[key]}** ([`tables/{name}.csv`](tables/{name}.csv))")
        out.append(
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
            )
        )
    return "\n\n".join(out)


def _limits(f: Facts) -> str:
    bullets = []
    if any(k > 1 for _, k in f.runs_per_drawing()):
        bullets.append(
            f"The headline numbers use run {f.headline_run} only, so each drawing counts "
            "once per model. Counting every run would count the drawings that ran more "
            "than once several times over, and make the ranges look narrower than the "
            "evidence supports. The later runs feed only the consistency numbers."
        )
    bullets.append(
        f"The {f.pooled} row has no 95% range. All the models answered the same drawings, "
        "so their answers are not independent tries, and a range that treated them as "
        "independent would be too narrow."
    )
    chains = f.chain_drawings()
    if chains:
        bullets.append(
            f"Only {chains} drawings need a chain, so the chain results are counts, not rates."
        )
    review = f.review
    waiting = f.waiting()
    reviewed = int(review.get("agent_labels_evaluator_reviewed") or 0)
    kept = (
        " The evaluator kept Claude's label on "
        f"{review['evaluator_kept_agent_label']} of {reviewed} "
        f"({review['kept_percent']}%, 95% range {review['range_low_percent']}% to "
        f"{review['range_high_percent']}%) and changed the rest."
        if reviewed
        else ""
    )
    who = (
        "The evaluator reviewed every label Claude proposed."
        if not waiting
        else f"The evaluator reviews every label Claude proposes, and {waiting} missed sizes still "
        'wait for a label: they read "Not diagnosed yet" or "Not reviewed by the '
        'evaluator yet" in the tables.'
    )
    bullets.append(
        "Claude, an AI model made by Anthropic, proposed a label for each new kind of "
        "failure, including failures by Anthropic's own model. A failure that repeats an "
        f"earlier one takes the evaluator's earlier label. {who}{kept} Every label published here "
        "is the evaluator's. [`tables/label-review.csv`](tables/label-review.csv) holds these "
        "counts. That table is the one table built from the evaluator's review record "
        "rather than from "
        "[`every-run.csv`](every-run.csv)."
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
            f"{len(audit)} passes in run {f.headline_run} relied on the model converting a "
            "printed number between millimetres and inches itself. "
            "[`tables/tolerance-audit.csv`](tables/tolerance-audit.csv) lists them."
        )
    else:
        bullets.append(
            f"No pass in run {f.headline_run} relied on a model converting a printed number "
            "between millimetres and inches: every passing size matched a printed number."
        )
    return "## Limits on what these numbers show\n\n" + "\n".join(f"- {b}" for b in bullets)


def _files(charts: set[str]) -> str:
    files = [
        ("every-run.csv", "one row per reply: the values returned, the verdict, sizes "
         "right, sizes missed, and the evaluator's label and evidence for each missed size"),
        ("tables/", "every table this page quotes, as CSV"),
        ("charts/", "each chart as a picture, with the numbers it draws beside it as CSV"),
        ("raw-replies/", "every model's full reply, word for word"),
        ("run-settings.json", "the models, versions, thinking settings, dates and question"),
        ("LICENSE-NOTICE.md", "the license these drawing-derived files fall under"),
    ]  # fmt: skip
    if not charts:
        files = [f for f in files if f[0] != "charts/"]
    return "## What's in this folder\n\n" + "\n".join(
        f"- [`{name}`]({name}): {what}" for name, what in files
    )


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
) -> str:
    """The results page, from these inputs only."""
    f = Facts(every_run, tables, settings, review, pooled, headline_run, small_group)
    ran_again = any(k > 1 for _, k in f.runs_per_drawing())
    sections = [
        _intro(f),
        _setup(f),
        _pass_rates(f, charts),
        *([_consistency(f, charts)] if ran_again else []),
        _failures(f, charts),
        _splits(f),
        _limits(f),
        _files(charts),
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
            f"[The results page]({e.link}) has every table and chart, and every reply.",
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
