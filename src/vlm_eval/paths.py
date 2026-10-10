"""Canonical locations for everything the project reads and writes."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DRAWINGS = ROOT / "drawings"
GROUND_TRUTH_MD = DRAWINGS / "ground-truth.md"

DATA = ROOT / "data"
GROUND_TRUTH_CSV = DATA / "ground-truth.csv"
INCH_PARTNERS_CSV = DATA / "inch-partners.csv"
DRAWING_SETS_CSV = DATA / "drawing-sets.csv"
ENVELOPE_TOLERANCES_CSV = DATA / "envelope-tolerances.csv"
FOUNDATION_SUMMARY = DATA / "foundation-summary.md"
GRADING_EXAMPLES = DATA / "grading-examples.html"

CONFIG = ROOT / "config"
MODELS_YAML = CONFIG / "models.yaml"

RUNS = ROOT / "runs"  # private: never published
CALLS = RUNS / "calls"  # one JSON file per model call
CONNECTION_TEST_PAGE = RUNS / "connection-test.html"
EXTRACTIONS = RUNS / "extractions"  # one JSON file per extracted reply, saved once
REPLAY_PAGE = RUNS / "replay.html"
PLANS = RUNS / "plans"  # one JSON file per run plan: what to run, estimate, approvals
DIAGNOSES = RUNS / "diagnoses"  # failure groups, briefs, diagnoses, drawing views
DIAGNOSES_PAGE = RUNS / "diagnoses.html"
STOP_FILE = RUNS / "STOP"  # `vlm-eval stop-run` writes it; a running run stops at the next call

ENV_FILE = ROOT / ".env"
