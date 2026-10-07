"""Checks on Garron's casebook and the reuse of his labels (SPEC 2.6, Chunk 9).

No API calls and no agent runs. The casebook and the diagnoses folder are temporary.
Labels come from Garron's list; trap values are made up and clearly wrong (987.65).
"""

from __future__ import annotations

import json

import pytest

from vlm_eval import casebook, diagnosis, paths

TEXT_DRAWING = "201533-020.pdf"  # 12.7 and 6.35 are printed on it
OTHER_DRAWING = "201513.pdf"
MADE_UP = "987.65"
OLD, NEW = "old-run", "new-run"


@pytest.fixture(autouse=True)
def temporary_files(tmp_path, monkeypatch):
    monkeypatch.setattr(casebook, "CASEBOOK", tmp_path / "casebook.jsonl")
    monkeypatch.setattr(paths, "DIAGNOSES", tmp_path / "diagnoses")
    monkeypatch.setattr(paths, "DIAGNOSES_PAGE", tmp_path / "diagnoses.html")


def _ruling(
    missed="Thk (Z)",
    wrong="6.35",
    agent="Proximity association",
    garron=None,
    group="201533-020-Thk-6.35",
    run_folder=OLD,
    drawing=TEXT_DRAWING,
    reason="",
    **extra,
) -> dict:
    garron = garron or agent
    return casebook.save(
        {
            "run_folder": run_folder,
            "group": group,
            "drawing": drawing,
            "missed": missed,
            "wrong_value": wrong,
            "agent_label": agent,
            "garron_label": garron,
            "verdict": casebook.ACCEPT if garron == agent else casebook.CHANGE,
            "reason": reason or ("" if garron == agent else "A made-up reason."),
            **extra,
        }
    )


def _diagnosis_entry(missed="Thk (Z)", wrong="6.35", label="Feature substitution") -> dict:
    return {
        "missed": missed,
        "wrong_value": wrong,
        "label": label,
        "wrong_value_axis": "Z",
        "note": f"Original note for {missed}.",
        "evidence": [{"number": "12.7", "where": "edge view", "view": ""}],
    }


def _write_original(group: str, entries: list[dict], run_folder=OLD) -> None:
    path = paths.DIAGNOSES / run_folder / group / "diagnosis.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"group": group, "diagnoses": entries}))


def _run_briefs(monkeypatch, group: diagnosis.Group) -> dict | None:
    monkeypatch.setattr(diagnosis, "failure_groups", lambda folder: ([group], []))
    diagnosis.write_briefs(NEW)
    path = diagnosis.diagnosis_path(NEW, group)
    return json.loads(path.read_text()) if path.exists() else None


# --- saving and loading -------------------------------------------------------------


def test_the_latest_answer_for_a_missed_size_wins():
    _ruling(saved_at="2026-09-25T10:00:00")
    _ruling(garron="Axis mapping", saved_at="2026-09-26T10:00:00")
    book = casebook.load()
    assert len(book) == 1
    assert book[(OLD, "201533-020-Thk-6.35", "Thk (Z)")]["garron_label"] == "Axis mapping"


@pytest.mark.parametrize(
    "changes, complaint",
    [
        ({"verdict": casebook.ACCEPT, "garron_label": "Axis mapping"}, "agent's label"),
        ({"verdict": casebook.CHANGE, "garron_label": "Axis mapping", "reason": " "}, "reason"),
        ({"garron_label": "Made-up label"}, "not one of Garron's labels"),
    ],
)
def test_a_bad_answer_is_refused_and_nothing_is_written(changes, complaint):
    entry = {
        "run_folder": OLD,
        "group": "201533-020-Thk-6.35",
        "drawing": TEXT_DRAWING,
        "missed": "Thk (Z)",
        "wrong_value": "6.35",
        "agent_label": "Proximity association",
        "garron_label": "Proximity association",
        "verdict": casebook.ACCEPT,
        **changes,
    }
    with pytest.raises(ValueError, match=complaint):
        casebook.save(entry)
    assert not casebook.CASEBOOK.exists()


# --- agreement ----------------------------------------------------------------------


def test_agreement_counts_the_agents_own_labels_only():
    _ruling(group="a")
    _ruling(group="b", garron="Axis mapping")
    _ruling(group="c", reused=True)
    _ruling(group="d", run_folder=NEW)
    result = casebook.agreement(OLD)
    assert (result.reviewed, result.agreed) == (2, 1)
    assert [e["group"] for e in result.changed] == ["b"]


def test_the_agreement_range_is_the_exact_one():
    low, high = casebook.exact_range(9, 9)
    assert low == pytest.approx(0.664, abs=0.001) and high == 1.0


# --- reuse --------------------------------------------------------------------------


def _single(wrong="6.35") -> diagnosis.Group:
    return diagnosis.Group(f"201533-020-Thk-{wrong}", TEXT_DRAWING, ("Thk (Z)",), (wrong,), ())


def test_the_same_wrong_number_on_the_same_drawing_reuses_garrons_label(monkeypatch):
    _write_original("201533-020-Thk-6.35", [_diagnosis_entry()])
    _ruling(agent="Feature substitution", garron="Proximity association", reason="Why.")
    group = _single("6.350")  # the same size written longer
    written = _run_briefs(monkeypatch, group)
    assert written["reused"] is True
    assert written["reused_from"] == [f"{OLD}/201533-020-Thk-6.35"]
    [entry] = written["diagnoses"]
    assert entry["label"] == "Proximity association"
    assert entry["wrong_value"] == "6.350"
    assert entry["note"].startswith(f"Reused: Garron's label from {OLD}/201533-020-Thk-6.35")
    assert entry["note"].endswith("Original note for Thk (Z).")
    assert entry["evidence"] == _diagnosis_entry()["evidence"]
    assert diagnosis.check(NEW, group).done
    assert diagnosis.state(NEW, group) == diagnosis.REUSED


def test_a_different_wrong_number_is_diagnosed_afresh(monkeypatch):
    _write_original("201533-020-Thk-6.35", [_diagnosis_entry()])
    _ruling()
    group = _single(MADE_UP)
    assert _run_briefs(monkeypatch, group) is None
    assert diagnosis.state(NEW, group) == diagnosis.TO_DIAGNOSE


def test_a_missing_original_diagnosis_means_no_reuse(monkeypatch):
    _ruling()
    assert _run_briefs(monkeypatch, _single()) is None


def _two_miss() -> diagnosis.Group:
    return diagnosis.Group(
        "201533-020-Thk-L-6.35-987.65", TEXT_DRAWING, ("Thk (Z)", "L (Y)"), ("6.35", MADE_UP), ()
    )


def _two_miss_originals() -> None:
    _write_original(
        "201533-020-Thk-L-6.35-987.65",
        [_diagnosis_entry(), _diagnosis_entry("L (Y)", MADE_UP, "Axis mapping")],
    )


def test_a_two_miss_group_puts_each_label_on_its_own_size(monkeypatch):
    _two_miss_originals()
    group = "201533-020-Thk-L-6.35-987.65"
    _ruling(group=group, agent="Feature substitution", garron="Proximity association")
    _ruling(group=group, missed="L (Y)", wrong=MADE_UP, agent="Axis mapping")
    written = _run_briefs(monkeypatch, _two_miss())
    labels = {e["missed"]: (e["label"], e["wrong_value"]) for e in written["diagnoses"]}
    assert labels == {
        "Thk (Z)": ("Proximity association", "6.35"),
        "L (Y)": ("Axis mapping", MADE_UP),
    }


def test_a_two_miss_group_with_one_size_confirmed_is_diagnosed_afresh(monkeypatch):
    _two_miss_originals()
    _ruling(group="201533-020-Thk-L-6.35-987.65")
    assert _run_briefs(monkeypatch, _two_miss()) is None


def test_one_wrong_number_cannot_serve_two_missed_sizes(monkeypatch):
    _two_miss_originals()
    _ruling(group="201533-020-Thk-L-6.35-987.65")
    _ruling(group="other-group", missed="L (Y)", wrong="6.35", agent="Axis mapping")
    assert _run_briefs(monkeypatch, _two_miss()) is None


def test_an_existing_diagnosis_is_never_overwritten(monkeypatch):
    _write_original("201533-020-Thk-6.35", [_diagnosis_entry()])
    _ruling(agent="Feature substitution", garron="Proximity association", reason="Why.")
    group = _single()
    path = diagnosis.diagnosis_path(NEW, group)
    path.parent.mkdir(parents=True)
    path.write_text('{"group": "kept as it was"}')
    _run_briefs(monkeypatch, group)
    assert path.read_text() == '{"group": "kept as it was"}'


def test_a_group_garron_has_ruled_on_shows_as_confirmed_on_the_list(monkeypatch):
    group = _single()
    _write_original(group.name, [_diagnosis_entry()], run_folder=NEW)
    _ruling(run_folder=NEW, agent="Feature substitution", garron="Axis mapping")
    assert diagnosis.state(NEW, group) == diagnosis.CONFIRMED
    page = diagnosis.write_page(NEW, [diagnosis.check(NEW, group)], []).read_text()
    assert "Garron: Axis mapping · changed from Feature substitution" in page


# --- the brief ----------------------------------------------------------------------


def _casebook_part(text: str) -> str:
    return text.split("## Garron's casebook")[1].split("## Your output")[0]


def test_the_brief_lists_this_drawings_rulings_first():
    _ruling(group="201513-L-78", drawing=OTHER_DRAWING, missed="L (Y)", wrong="78")
    _ruling(reason="A reason on this drawing.")
    part = _casebook_part(diagnosis.brief(NEW, _single()))
    assert part.index("| 201533-020 |") < part.index("| 201513 |")
    assert "They outrank the playbook's general wording" in part


def test_a_trial_brief_hides_the_groups_own_ruling():
    group = _single()
    _ruling(run_folder=NEW, group=group.name, garron="Axis mapping")
    _ruling(group="201513-L-78", drawing=OTHER_DRAWING, missed="L (Y)", wrong="78")
    shown = _casebook_part(diagnosis.brief(NEW, group))
    trial = _casebook_part(diagnosis.brief(NEW, group, trial=True))
    assert "| 201533-020 |" in shown and "| 201533-020 |" not in trial
    assert "| 201513 |" in trial


def test_a_trial_brief_sends_the_diagnosis_somewhere_else(tmp_path):
    dest = diagnosis.write_trial_brief(NEW, _single(), tmp_path / "trial" / "brief.md")
    text = dest.read_text()
    assert str(tmp_path / "trial" / "diagnosis.json") in text
    assert "--file" in text


def test_an_empty_casebook_says_so():
    assert "No confirmed labels yet." in diagnosis.brief(NEW, _single())
