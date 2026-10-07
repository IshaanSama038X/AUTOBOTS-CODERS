from __future__ import annotations

from pathlib import Path

from sandbox.runner import run_checks
from src.state import AgentState


def _simulated_failure(state: AgentState, failing: list[str]) -> dict:
    log = (
        "compile: FAILED\n"
        "  File \"main.py\", line 1\n"
        "    SyntaxError: invalid syntax (simulated)\n"
        "lint: SKIPPED\ntest: SKIPPED"
    )
    result = {
        "passed": False,
        "stage": "compile",
        "log": log,
        "failed_task_ids": failing,
    }
    return {
        "validation_results": [result],
        "validation_passed": False,
        "status": "validation_failed",
        "events": [
            {
                "node": "validator",
                "msg": f"simulated compile FAILED on repair round {state['repair_round']}; failing: {failing}",
            }
        ],
    }


def _run_sandbox(state: AgentState) -> dict:
    sandbox_dir = state.get("sandbox_dir") or ""
    workspace = Path(sandbox_dir) if sandbox_dir else None
    if not workspace or not workspace.is_dir():
        result = {
            "passed": False,
            "stage": "compile",
            "log": "sandbox directory missing; manager did not assemble artifacts",
            "failed_task_ids": [],
        }
        return {
            "validation_results": [result],
            "validation_passed": False,
            "status": "validation_failed",
            "events": [{"node": "validator", "msg": "validation FAILED: no sandbox"}],
        }

    stage_results = run_checks(workspace)
    if not stage_results:
        result = {
            "passed": False,
            "stage": "compile",
            "log": "sandbox produced no files to validate",
            "failed_task_ids": [],
        }
        return {
            "validation_results": [result],
            "validation_passed": False,
            "status": "validation_failed",
            "events": [{"node": "validator", "msg": "validation FAILED: no output files"}],
        }

    file_map = state.get("file_map") or {}

    validation_results = []
    events = []
    for stage in stage_results:
        failed_ids = sorted(
            {file_map[f] for f in stage["failed_files"] if f in file_map}
        )
        validation_results.append(
            {
                "passed": stage["passed"],
                "stage": stage["stage"],
                "log": stage["log"],
                "failed_task_ids": failed_ids,
            }
        )
        mark = "OK" if stage["passed"] else "FAILED"
        events.append(
            {
                "node": "validator",
                "msg": f"{stage['stage']}: {mark}"
                + (f" -> tasks {failed_ids}" if failed_ids and not stage["passed"] else ""),
            }
        )

    passed = all(stage["passed"] for stage in stage_results)

    if not passed:
        any_mapped = any(r["failed_task_ids"] for r in validation_results)
        if not any_mapped:
            all_ids = sorted(
                t["id"] for t in state["subtasks"] if (state.get("artifacts") or {}).get(t["id"])
            )
            for res in validation_results:
                if not res["passed"]:
                    res["failed_task_ids"] = all_ids
            events.append(
                {
                    "node": "validator",
                    "msg": f"no file->task match; routing all artifact tasks to repair: {all_ids}",
                }
            )

    return {
        "validation_results": validation_results,
        "validation_passed": passed,
        "status": "validation_passed" if passed else "validation_failed",
        "events": events,
    }


def validator(state: AgentState):
    flags = state.get("config_flags") or {}
    fail_rounds = int(flags.get("fail_rounds", 0))

    if state["repair_round"] < fail_rounds:
        failing = [t["id"] for t in state["subtasks"] if t["status"] == "done"][:1]
        return _simulated_failure(state, failing)

    return _run_sandbox(state)