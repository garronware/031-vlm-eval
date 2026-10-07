"""Shared fixtures. Tests read the generated files in data/, not the models' internals."""

from __future__ import annotations

import csv

import pytest

from vlm_eval import paths
from vlm_eval.ground_truth import read_ground_truth


def _rows(path):
    if not path.exists():
        pytest.fail(f"{path.name} is missing. Run: uv run vlm-eval build-foundation")
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="session")
def drawings():
    return read_ground_truth()


@pytest.fixture(scope="session")
def gt_rows():
    return _rows(paths.GROUND_TRUTH_CSV)


@pytest.fixture(scope="session")
def partner_rows():
    return _rows(paths.INCH_PARTNERS_CSV)


@pytest.fixture(scope="session")
def set_rows():
    return _rows(paths.DRAWING_SETS_CSV)
