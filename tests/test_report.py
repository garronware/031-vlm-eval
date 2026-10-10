"""Quiet checks for the results folder (SPEC 2.10, Chunk 10).

Made-up replies only: nothing here reads the private runs/ folder or calls a model.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from vlm_eval import diagnosis, replay, report, scoring
from vlm_eval.answers import Answer, AnswerValue
from vlm_eval.scoring import Verdict, criteria_total, load_answer_key, score

TAGS = {
    "shape": "CUBE",
    "print_type": "dual",
    "pdf_type": "text",
    "dimension_origin": "explicitly_dimensioned",
}
MADE_UP_WRONG = "99.99"  # printed on no drawing's envelope


def _reply(drawing, model="Model A", run="1", passed=True, tags=None, labels=(), status=""):
    file = f"{drawing}.pdf"
    verdict = None
    if not status:
        verdict = Verdict(
            file=file,
            scored=True,
            strict_pass=passed,
            dims_correct=3 if passed else 2,
            dims_total=3,
            dims_missed=() if passed else ("L (Y)",),
            problems=() if passed else (scoring.WRONG_VALUE,),
            matches=(),
            criteria_correct=3 if passed else 2,
            criteria_total=3,
        )
    call = {
        "drawing": file,
        "model_name": model,
        "model_requested": model.lower().replace(" ", "-"),
        "model_version": "made-up-version",
        "maker": "made-up maker",
        "thinking": "maker default",
        "prompt": "made-up prompt",
        "started_at": "2026-01-01T00:00:00",
        "reply_text": "made-up reply",
    }
    row = replay.Row(Path(f"x/{model}/{drawing}-run{run}.json"), call, None, verdict, status)
    return report.Reply(row, model, drawing, run, {**TAGS, **(tags or {})}, labels)


def _thirty(**kwargs):
    return [_reply(f"D{i:02}", **kwargs) for i in range(1, 31)]


def _value(dim, index=0):
    """A printed reading of a ground-truth dimension, as a reply would write it."""
    reading = dim.readings[index]
    return str(reading.value.normalize()), reading.unit


# --- the criteria columns ------------------------------------------------------------


def _200951(thk):
    return Answer(
        (
            AnswerValue(thk, "mm", "Thk"),
            AnswerValue("91.0", "mm", "W"),
            AnswerValue("72.91", "mm", "L"),
        )
    )


def test_a_chain_total_is_not_a_criterion_but_its_parts_are():
    whole = score("200951.pdf", _200951("40.64"))
    one_part = score("200951.pdf", _200951("34.29"))
    wrong = score("200951.pdf", _200951(MADE_UP_WRONG))
    assert (whole.strict_pass, whole.criteria_correct, whole.criteria_total) == (True, 4, 4)
    assert (one_part.strict_pass, one_part.criteria_correct) == (False, 3)
    assert (wrong.strict_pass, wrong.criteria_correct) == (False, 2)

    rod = Answer((AnswerValue("1.1240", "in", "Dia"), AnswerValue("1.00", "in", "L")))
    verdict = score("90-100012-B.pdf", rod)
    assert (verdict.strict_pass, verdict.criteria_correct, verdict.criteria_total) == (
        False,
        2,
        3,
    )


def test_criteria_equal_sizes_on_every_drawing_without_a_chain():
    for key in load_answer_key().values():
        chains = sum(bool(d.chain_parts) for d in key.dimensions)
        extra = sum(len(d.chain_parts) - 1 for d in key.dimensions if d.chain_parts)
        assert criteria_total(key) == len(key.dimensions) + extra
        if not chains:
            assert criteria_total(key) == len(key.dimensions)


def test_a_box_for_a_round_part_counts_the_diameter_once_and_only_if_both_match():
    key = next(
        k
        for k in load_answer_key().values()
        if k.shape == "CYL" and not any(d.chain_parts for d in k.dimensions)
    )
    dia = next(d for d in key.dimensions if d.label == "Dia")
    length = next(d for d in key.dimensions if d.label != "Dia")
    (d, du), (n, nu) = _value(dia), _value(length)
    right = score(key.file, Answer((AnswerValue(d, du), AnswerValue(d, du), AnswerValue(n, nu))))
    half = score(
        key.file,
        Answer((AnswerValue(d, du), AnswerValue(MADE_UP_WRONG, du), AnswerValue(n, nu))),
    )
    assert (right.strict_pass, right.criteria_correct, right.criteria_total) == (True, 2, 2)
    assert (half.strict_pass, half.criteria_correct) == (False, 1)


# --- the tables ----------------------------------------------------------------------


def test_headline_counts_run_1_only_and_later_runs_feed_consistency():
    replies = [
        _reply("D01", run="1", passed=True),
        _reply("D01", run="2", passed=False),
        _reply("D02", run="1", passed=False),
        _reply("D02", run="2", passed=False),
    ]
    t = report.tables(replies)
    model = t["pass-rate-by-model"][0]
    assert (model["drawings"], model["passed"]) == ("2", "1")
    assert t["consistency-by-model"][0] == {
        "model": "Model A",
        "drawings_run_more_than_once": "2",
        "always_passed": "0",
        "always_failed": "1",
        "mixed": "1",
        "same_answer_every_run_percent": "50",
    }


def test_a_reply_that_could_not_be_graded_is_neither_pass_nor_fail_for_consistency(tmp_path):
    import dataclasses

    flagged = _reply("D01", run="3")
    verdict = dataclasses.replace(flagged.row.verdict, scored=False, strict_pass=False)
    flagged = dataclasses.replace(flagged, row=dataclasses.replace(flagged.row, verdict=verdict))
    assert flagged.result == report.NOT_GRADED
    replies = [*_thirty(), _reply("D01", run="2"), flagged]

    t = report.tables(replies)
    assert t["runs-passed-per-drawing"][0] == {"drawing": "D01", "Model A": "2 of 2"}
    assert t["consistency-by-model"][0]["always_passed"] == "1"
    assert t["consistency-by-model"][0]["mixed"] == "0"
    out = report.write_folder(replies, "made-up-run", results=tmp_path)
    assert report.recompute_check(out) == []


def test_a_split_under_5_drawings_shows_counts_but_no_rate():
    chains = {"dimension_origin": "calculated_chain"}
    replies = [_reply(f"C{i}", tags=chains) for i in range(4)] + _thirty()
    rows = {r["dimension_origin"]: r for r in report.tables(replies)["by-dimension-origin"]}
    assert (rows["calculated_chain"]["passed"], rows["calculated_chain"]["pass_rate_percent"]) == (
        "4",
        "",
    )
    assert rows["explicitly_dimensioned"]["pass_rate_percent"] == "100"


# --- the folder and its checks -------------------------------------------------------


@pytest.fixture
def folder(tmp_path):
    replies = _thirty() + [
        _reply("D01", model="Model B", passed=False, labels=(("L (Y)", "Axis mapping", "made"),))
    ]
    return report.write_folder(replies, "made-up-run", results=tmp_path)


def test_the_folder_passes_both_checks(folder):
    assert report.recompute_check(folder) == []
    assert report.publish_check(folder) == []


def test_the_recompute_check_catches_a_planted_wrong_number(folder):
    path = folder / "tables" / "pass-rate-by-model.csv"
    rows = list(csv.DictReader(path.open(newline="")))
    rows[0]["passed"] = "29"  # the made-up replies all passed: 30
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    assert report.recompute_check(folder) == [
        "tables/pass-rate-by-model.csv disagrees with every-run.csv"
    ]


@pytest.mark.parametrize("planted", ["cost $4.40", "see runs/calls/main", "cost_usd"])
def test_the_publish_check_catches_private_things(folder, planted):
    (folder / "tables" / "failures-by-label.csv").write_text(planted)
    assert len(report.publish_check(folder)) == 1


def test_test_runs_and_small_runs_are_refused(tmp_path):
    with pytest.raises(report.ReportError, match="Test runs"):
        report.build("test", results=tmp_path)
    with pytest.raises(report.ReportError, match="under 30"):
        report.write_folder(_thirty()[:29], "made-up-run", results=tmp_path)
    waiting = _thirty() + [_reply("D31", status=replay.NOT_EXTRACTED)]
    with pytest.raises(report.ReportError, match="numbers pulled out"):
        report.write_folder(waiting, "made-up-run", results=tmp_path)
    assert not list(tmp_path.iterdir())


def test_a_changed_label_publishes_garrons_reason_not_the_agents_note(monkeypatch):
    monkeypatch.setattr(diagnosis, "_original", lambda entry: {"note": "the agent's note"})
    changed = {
        "verdict": "change",
        "agent_label": "Axis mapping",
        "garron_label": "Feature substitution",
        "reason": "Garron's made-up reason",
    }
    accepted = {
        "verdict": "accept",
        "agent_label": "Axis mapping",
        "garron_label": "Axis mapping",
        "reason": "",
    }
    # An old change that a merged label turned into agreement publishes the agent's note.
    merged = {**accepted, "verdict": "change", "reason": "Garron's made-up reason"}
    assert report._evidence(changed) == "Garron's made-up reason"
    assert report._evidence(accepted) == "the agent's note"
    assert report._evidence(merged) == "the agent's note"


# --- the results page, charts and main README ----------------------------------------


def test_the_folder_is_named_by_its_last_reply_and_a_rebuild_replaces_it(tmp_path, folder):
    assert folder.name == "2026-01-01-made-up-run-30-drawings"
    again = report.write_folder(_thirty(), "made-up-run", results=tmp_path)
    assert again == folder
    assert [p.name for p in tmp_path.iterdir()] == [folder.name]


def test_the_page_and_charts_are_written_and_pass_the_checks(folder):
    assert (folder / "README.md").exists()
    assert (folder / "charts" / "pass-rate-by-model.png").exists()
    assert (folder / "tables" / "label-review.csv").exists()
    assert report.recompute_check(folder) == []


def test_the_recompute_check_catches_a_changed_number_on_the_page(folder):
    page = folder / "README.md"
    page.write_text(page.read_text().replace("30 of 30", "29 of 30", 1))
    assert report.recompute_check(folder) == ["README.md disagrees with every-run.csv"]


def test_the_recompute_check_catches_a_changed_chart(folder):
    path = folder / "charts" / "pass-rate-by-model.csv"
    path.write_text(path.read_text().replace(",30,", ",29,", 1))
    assert report.recompute_check(folder) == [
        "charts/pass-rate-by-model.csv disagrees with every-run.csv"
    ]


def test_the_publish_check_reads_the_page(folder):
    page = folder / "README.md"
    page.write_text(page.read_text() + "\nThis run cost $9.\n")
    assert report.publish_check(folder) == ["README.md contains a dollar amount"]


def test_failures_without_garrons_label_still_build_and_say_so(tmp_path):
    waiting = (("L (Y)", report.NOT_DIAGNOSED, ""),)
    unreviewed = (("L (Y)", report.NOT_REVIEWED, ""),)
    replies = _thirty() + [
        _reply("D01", model="Model B", passed=False, labels=waiting),
        _reply("D02", model="Model B", passed=False, labels=unreviewed),
    ]
    out = report.write_folder(replies, "made-up-run", results=tmp_path)
    assert report.recompute_check(out) == []
    assert "2 missed sizes still wait for a label" in (out / "README.md").read_text()


def test_the_main_readme_section_points_at_the_folder_and_is_checked(tmp_path, folder):
    readme = tmp_path / "README.md"
    readme.write_text("# Project\n\nIntro.\n\n## License\n\nMIT.\n")
    report.update_readme(readme, tmp_path)
    text = readme.read_text()
    assert text.startswith("# Project\n\nIntro.\n\n<!-- results:start -->")
    assert text.endswith("<!-- results:end -->\n\n## License\n\nMIT.\n")
    assert f"]({folder.name}/)" in text
    assert report.readme_check(readme, tmp_path) == []

    report.update_readme(readme, tmp_path)  # a rebuild replaces the section, never adds one
    assert readme.read_text() == text

    readme.write_text(text.replace("30 of 30", "29 of 30", 1))
    assert report.readme_check(readme, tmp_path) == [
        "README.md's results section disagrees with the results folders"
    ]


def test_the_main_readme_lists_every_evaluation_and_says_which_contains_which(tmp_path):
    small = [r for i in (1, 2) for r in _thirty(run=str(i))]
    large = _thirty() + [_reply(f"E{i:02}") for i in range(1, 11)]
    report.write_folder(small, "made-up-run", results=tmp_path / "results")
    report.write_folder(large, "made-up-run", results=tmp_path / "results")
    readme = tmp_path / "README.md"
    readme.write_text("# Project\n\n## License\n\nMIT.\n")
    report.update_readme(readme, tmp_path / "results")
    text = readme.read_text()
    assert "### 30 drawings, each answered 2 times by each model" in text
    assert "### 40 drawings, each answered once by each model" in text
    assert text.index("### 30 drawings") < text.index("### 40 drawings")
    assert "It includes the 30 drawings above, with the same run 1 answers." in text
    assert report.readme_check(readme, tmp_path / "results") == []


def test_a_folder_holds_only_the_runs_every_drawing_has():
    replies = [_reply("D01", run="1"), _reply("D01", run="2"), _reply("D02", run="1")]
    assert [(r.drawing, r.run) for r in report.runs_every_drawing_has(replies)] == [
        ("D01", "1"),
        ("D02", "1"),
    ]


def test_a_folder_run_once_has_no_consistency_section_or_chart(folder):
    page = (folder / "README.md").read_text()
    assert "same verdict" not in page and "ran more than once" not in page
    assert not (folder / "charts" / "consistency-by-model.png").exists()


def _numbers(page: str, pattern: str) -> list[str]:
    import re

    return re.findall(pattern, page, re.M)


def test_the_page_is_a_report_with_numbered_sections_tables_and_figures(tmp_path, folder):
    three_runs = [r for i in (1, 2, 3) for r in _thirty(run=str(i))]
    again = report.write_folder(three_runs, "made-up-run", results=tmp_path / "three")
    for out, consistency in ((folder, False), (again, True)):
        page = (out / "README.md").read_text()
        assert page.index("**Abstract.**") < page.index("## 1. Introduction")
        assert _numbers(page, r"^## (\d+)\. ") == ["1", "2", "3", "4", "5"]
        assert _numbers(page, r"^## (\D.*)$") == [
            "Appendix A: Failure labels",
            "Appendix B: One example of each failure label",
            "Appendix C: Tolerance audit",
        ]
        subs = _numbers(page, r"^### (3\.\d+)\. ")
        assert subs == [f"3.{i}" for i in range(1, len(subs) + 1)]  # no gap
        assert ("Consistency across runs" in page) == consistency
        for kind in ("Table", "Figure"):
            found = _numbers(page, rf"\b{kind} (\d+)\.")
            assert found == [str(i) for i in range(1, len(found) + 1)], kind
        assert report.recompute_check(out) == []


def test_the_abstract_states_the_pass_rate_tables_numbers(folder):
    page = (folder / "README.md").read_text()
    abstract = page.split("**Abstract.**")[1].split("\n")[0]
    rows = list(csv.DictReader((folder / "tables" / "pass-rate-by-model.csv").open(newline="")))
    for r in rows:
        if r["model"] != report.ALL_MODELS:
            assert (
                f"{r['model']} passed {r['passed']} of {r['replies_graded']} drawings" in abstract
            )


def test_appendix_b_shows_one_example_per_label_with_the_recorded_sizes(tmp_path):
    first = (("L (Y)", "Axis mapping", "made-up evidence one"),)
    second = (("L (Y)", "Axis mapping", "made-up evidence two"),)
    other = (("L (Y)", "Feature substitution", "made-up evidence three"),)
    recorded = {"recorded": "Thk (Z) 1.0 mm; W (X) 2.0 mm; L (Y) 3.0 mm"}
    replies = _thirty() + [
        _reply("D01", model="Model B", passed=False, labels=first, tags=recorded),
        _reply("D02", model="Model B", passed=False, labels=second, tags=recorded),
        _reply("D03", model="Model B", passed=False, labels=other, tags=recorded),
    ]
    out = report.write_folder(replies, "made-up-run", results=tmp_path)
    appendix = (out / "README.md").read_text().split("## Appendix B")[1].split("## Appendix C")[0]
    assert appendix.count("**Axis mapping.**") == 1
    assert appendix.count("**Feature substitution.**") == 1
    assert "made-up evidence one" in appendix and "made-up evidence two" not in appendix
    assert appendix.count("Recorded sizes: Thk (Z) 1.0 mm; W (X) 2.0 mm; L (Y) 3.0 mm") == 2
    assert report.recompute_check(out) == []


def test_every_run_carries_the_recorded_sizes():
    row = {"units": "MM", "dia": "", "thk": "34.29 + 6.35 = 40.64", "thk_axis": "Z",
           "w": "91.0", "w_axis": "X", "l": "72.91", "l_axis": "Y"}  # fmt: skip
    assert report._recorded(row) == "Thk (Z) 34.29 + 6.35 = 40.64 mm; W (X) 91.0 mm; L (Y) 72.91 mm"
    rod = {"units": "IN", "dia": "1.609", "thk": "", "w": "", "l": "0.750", "l_axis": "X"}
    assert report._recorded(rod) == "Dia 1.609 in; L (X) 0.750 in"


def test_unreviewed_labels_are_never_ranked(tmp_path):
    unreviewed = (("L (Y)", report.NOT_REVIEWED, ""),)
    labelled = (("L (Y)", "Axis mapping", "made"),)
    replies = _thirty() + [
        _reply("D01", model="Model B", passed=False, labels=unreviewed),
        _reply("D02", model="Model B", passed=False, labels=unreviewed),
        _reply("D03", model="Model B", passed=False, labels=labelled),
    ]
    page = (report.write_folder(replies, "made-up-run", results=tmp_path) / "README.md").read_text()
    assert "are under review: 2 of 3 missed sizes" in page
    assert "caused the most missed sizes" not in page


def test_each_folder_counts_only_the_label_reviews_for_its_own_replies(monkeypatch):
    from vlm_eval import casebook

    group = diagnosis.Group("D01-L-99.99", "D01.pdf", ("L (Y)",), ("99.99",), ())
    group.replies.append(diagnosis.Reply("Model B", "2", Path("x"), "", "v", ()))
    monkeypatch.setattr(diagnosis, "failure_groups", lambda folder: ([group], []))
    ruling = {"run_folder": "made-up-run", "group": group.name, "reused": False}
    monkeypatch.setattr(
        casebook, "entries", lambda: [{**ruling, "agent_label": "A", "garron_label": "A"}]
    )
    run_2 = [{"drawing": "D01", "model": "Model B", "run": "2"}]
    run_1 = [{"drawing": "D01", "model": "Model B", "run": "1"}]
    assert report.folder_agreement("made-up-run", run_2).reviewed == 1
    assert report.folder_agreement("made-up-run", run_1).reviewed == 0


def test_no_number_is_typed_into_the_page_text():
    """Every number on the page must come from the data, never from the page's own text.

    The exceptions name things rather than count them: the confidence level "95%", and
    "2D" in the title.
    """
    import ast

    from vlm_eval import report_page

    tree = ast.parse(Path(report_page.__file__).read_text())
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.FunctionDef | ast.ClassDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
    }
    typed = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and any(ch.isdigit() for ch in node.value.replace("95%", "").replace("2D", ""))
    ]
    assert typed == []


def test_the_published_folder_never_names_the_evaluator(tmp_path, folder):
    assert report.unnamed("Garron's ruling. This matches Garron Ware's label") == (
        "The evaluator's ruling. This matches the evaluator's label"
    )
    noted = (("L (Y)", "Axis mapping", "This follows Garron's ruling on 201513."),)
    replies = _thirty() + [_reply("D01", model="Model B", passed=False, labels=noted)]
    out = report.write_folder(replies, "made-up-run", results=tmp_path / "named")
    assert report.publish_check(out) == []
    assert "the evaluator's ruling" in (out / "every-run.csv").read_text()

    (folder / "README.md").write_text("Garron sent the drawings.")
    assert report.publish_check(folder) == ["README.md contains the evaluator's name"]


def test_no_cowork_message_until_the_notes_exist(tmp_path, folder):
    assert (
        report.write_cowork_message(folder, tmp_path / "missing.md", tmp_path, tmp_path / "x")
        is None
    )
    assert not list(tmp_path.glob("cowork-message-*"))


def test_the_cowork_message_carries_the_notes_and_names_every_file(tmp_path, folder):
    notes = tmp_path / "notes.md"
    notes.write_text("# Notes\n\nPrivate.\n\n## Who reads it\n\nMade-up readers.\n")
    model = tmp_path / "made-up-model-paper.pdf"
    model.write_text("made-up")
    pointer = tmp_path / "model-paper.txt"
    pointer.write_text(str(model))
    path = report.write_cowork_message(folder, notes, tmp_path, pointer)
    text = path.read_text()
    assert f"`{model}`: my earlier research note" in text
    assert "Headings name the topic" in text and "overrides any instruction" in text
    assert "Goes to Garron" not in text
    without = report.cowork_message(folder, notes, tmp_path / "missing.txt")
    assert "made-up-model-paper" not in without
    assert path.name == f"cowork-message-{folder.name}.md"
    assert "### Who reads it\n\nMade-up readers." in text
    assert "Private." not in text
    for name in ("README.md", "tables", "charts", "every-run.csv", "run-settings.json"):
        assert f"`{folder / name}`" in text
    assert "scoring-rules.md" in text
    assert "- **Datum reconstruction:** A chain aggregation failure" in text
    assert "research example" not in text and "diagnosis-playbook.md" not in text


def test_a_folder_can_be_rebuilt_from_one_fixed_drawing_set():
    from vlm_eval import run_plan

    thirty = set(run_plan.drawings_for("30"))
    inside = next(iter(sorted(thirty))).removesuffix(".pdf")
    outside = next(f for f in run_plan.drawings_for("141") if f not in thirty).removesuffix(".pdf")
    replies = [_reply(inside), _reply(outside)]
    assert [r.drawing for r in report.only_drawing_set(replies, "30")] == [inside]
