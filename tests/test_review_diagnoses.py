"""Checks on the diagnosis review page (Chunk 9).

No API calls: the page is built from the saved diagnoses in runs/diagnoses/, and every
answer goes to a scratch casebook, never Garron's data/casebook.jsonl.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from vlm_eval import casebook, diagnosis, diagnosis_review, paths, review_page

FOLDER = "main-stock-shape"


@pytest.fixture
def scratch_casebook(tmp_path, monkeypatch):
    path = tmp_path / "casebook.jsonl"
    monkeypatch.setattr(casebook, "CASEBOOK", path)
    return path


@pytest.fixture
def items():
    if not (paths.DIAGNOSES / FOLDER).is_dir():
        pytest.skip(f"no saved diagnoses for {FOLDER} on this machine")
    found = diagnosis_review.items(FOLDER)
    if not found:
        pytest.skip(f"no diagnosed failures in {FOLDER}")
    return found


@pytest.fixture
def server(items, scratch_casebook):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), diagnosis_review.handler_for(FOLDER))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _post(url: str, body: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        url + "/api/answer",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_page_shows_every_group_and_missed_size_with_only_the_seven_labels(items, scratch_casebook):
    page = diagnosis_review.build(FOLDER)
    groups, _ = diagnosis.failure_groups(FOLDER)
    for g in groups:
        assert f"<h2>{g.drawing.removesuffix('.pdf')}</h2>" in page
    for i in items:
        assert f'data-group="{i.group}"' in page
        assert f'data-missed="{i.missed}"' in page
    selects = re.findall(r"<select[^>]*>(.*?)</select>", page, re.S)
    assert len(selects) == len(items)
    for options in selects:
        assert tuple(re.findall(r"<option[^>]*>(.*?)</option>", options)) == diagnosis.LABELS


def test_an_answer_is_saved_with_the_facts_taken_from_the_diagnosis(items, server):
    item = items[0]
    other = next(label for label in diagnosis.LABELS if label != item.agent_label)
    status, reply = _post(
        server,
        {
            "group": item.group,
            "missed": item.missed,
            "verdict": "change",
            "garron_label": other,
            "reason": "made-up reason for the check",
            # Facts the browser must not be able to set:
            "drawing": "999999.pdf",
            "agent_label": other,
            "wrong_value": "987.65",
        },
    )
    assert status == 200 and reply["ok"]
    assert reply["reviewed"] == 1 and reply["total"] == len(items)
    saved = casebook.load()[(FOLDER, item.group, item.missed)]
    assert saved["drawing"] == item.drawing
    assert saved["wrong_value"] == item.wrong_value
    assert saved["agent_label"] == item.agent_label
    assert saved["garron_label"] == other
    assert saved["verdict"] == "change"
    assert saved["reused"] == item.reused
    assert casebook.agreement(FOLDER).changed

    # A later Accept replaces it, and the page shows it as saved.
    status, reply = _post(server, {"group": item.group, "missed": item.missed, "verdict": "accept"})
    assert status == 200
    assert casebook.load()[(FOLDER, item.group, item.missed)]["garron_label"] == item.agent_label
    with urllib.request.urlopen(server + "/api/state") as response:
        state = json.loads(response.read())
    assert state["answers"][item.key]["verdict"] == "accept"
    with urllib.request.urlopen(server + "/") as response:
        assert f"Saved ✓ (Accepted: {item.agent_label})" in response.read().decode()


def test_a_change_without_a_reason_is_refused_and_nothing_is_written(
    items, server, scratch_casebook
):
    item = items[0]
    other = next(label for label in diagnosis.LABELS if label != item.agent_label)
    status, reply = _post(
        server,
        {"group": item.group, "missed": item.missed, "verdict": "change", "garron_label": other},
    )
    assert status == 400 and not reply["ok"] and "reason" in reply["error"]
    status, _ = _post(
        server,
        {
            "group": item.group,
            "missed": item.missed,
            "verdict": "change",
            "garron_label": "Made-up label",
            "reason": "x",
        },
    )
    assert status == 400
    status, _ = _post(server, {"group": "no-such-group", "missed": "L (Y)", "verdict": "accept"})
    assert status == 400
    assert not scratch_casebook.exists()


def test_pictures_are_served_only_from_inside_runs(items, server):
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(server + "/../pyproject.toml")


def test_the_inch_page_still_builds():
    page = review_page.build()
    assert page.startswith("<!doctype html>") and "/api/answer" in page
