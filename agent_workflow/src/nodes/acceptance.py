from __future__ import annotations

from src.state import AgentState


def final_acceptance(state: AgentState):
    flags = state.get("config_flags") or {}
    compiled = state.get("compiled_output") or "\n\n".join(
        f"### artifact: {tid}\n{code}" for tid, code in sorted(state.get("artifacts", {}).items())
    )
    if state.get("validation_passed"):
        verdict = "approved"
        final = compiled
        msg = "main agent: compiled output accepted"
    else:
        verdict = "graceful_failure"
        final = "[PARTIAL OUTPUT - validation never passed after repair limit]\n\n" + compiled
        msg = "main agent: delivering partial output as graceful failure"

    update = {
        "final_output": final,
        "status": verdict,
        "events": [{"node": "final_acceptance", "msg": msg}],
    }
    if verdict == "approved" and flags.get("final_review"):
        update["status"] = "pending_final_review"
        update["events"].append(
            {"node": "final_acceptance", "msg": "pausing for user final review (HITL)"}
        )
    return update


def acceptance(state: AgentState) -> dict:
    return final_acceptance(state)