"""Command line entry point: `uv run vlm-eval <command>`."""

from __future__ import annotations

import sys

from vlm_eval import (
    build_foundation,
    connection_test,
    crops,
    diagnosis,
    diagnosis_review,
    extraction,
    grading_examples,
    replay,
    report,
    review_server,
    run_plan,
    runner,
)

COMMANDS = {
    "build-foundation": lambda args: print(build_foundation.build()),
    "confirm-inch-values": lambda args: review_server.serve(),
    "grading-examples": lambda args: grading_examples.write_and_open(),
    "test-connections": lambda args: connection_test.run(send="--send" in args),
    "extract": lambda args: extraction.run(_run_name(args), send="--send" in args),
    "replay": lambda args: replay.run(_run_name(args)),
    "plan-run": run_plan.cli_plan,
    "approve-run": run_plan.cli_approve,
    "run-eval": runner.cli_run,
    "stop-run": runner.cli_stop,
    "list-runs": run_plan.cli_list,
    "failure-groups": diagnosis.cli_groups,
    "check-diagnoses": diagnosis.cli_check,
    "review-diagnoses": diagnosis_review.cli,
    "drawing-numbers": crops.cli_numbers,
    "drawing-view": crops.cli_view,
    "build-report": report.cli,
}


def _run_name(args: list[str]) -> str | None:
    """The one run folder named on the command line, if any."""
    names = [a for a in args if not a.startswith("--")]
    return names[0] if names else None


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("usage: vlm-eval <command>\n\ncommands:")
        for name in COMMANDS:
            print(f"  {name}")
        return 1
    COMMANDS[sys.argv[1]](sys.argv[2:])
    return 0
