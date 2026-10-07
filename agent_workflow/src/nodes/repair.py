from __future__ import annotations

from src.state import AgentState


def repair_agent(state: AgentState):
    results = state.get("validation_results") or []
    failed_ids = set()
    error_parts = []
    for res in results:
        if not res["passed"]:
            failed_ids.update(res["failed_task_ids"])
            error_parts.append(f"[{res['stage']}]\n{res['log']}")
    error_log = "\n\n".join(error_parts) or "unknown validation failure"

    new_subtasks = []
    for task in state["subtasks"]:
        updated = dict(task)
        if task["id"] in failed_ids:
            updated["status"] = "pending"
            updated["error"] = error_log
        new_subtasks.append(updated)

    new_round = state["repair_round"] + 1
    entry = {
        "round": new_round,
        "failed_task_ids": sorted(failed_ids),
        "error_log": error_log,
        "assigned_to": "repair_assistant",
    }
    return {
        "repair_round": new_round,
        "subtasks": new_subtasks,
        "repair_log": [entry],
        "status": "repaired",
        "events": [
            {
                "node": "repair_agent",
                "msg": f"round {new_round}/{state['max_repair_rounds']}: routed errors back to {sorted(failed_ids)}",
            }
        ],
    }


def repair(state: AgentState) -> dict:
    return repair_agent(state)