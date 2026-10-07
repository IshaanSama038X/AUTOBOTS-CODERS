from __future__ import annotations

from langgraph.types import interrupt

from src.state import AgentState

APPROVE_WORDS = {"", "done", "ok", "okay", "approve", "approved", "yes", "y", "accept", "lgtm"}


def _infer_kind(state: AgentState) -> str:
    flags = state.get("config_flags") or {}
    if state.get("status") == "workers_failed":
        return "escalation"
    if not state.get("validation_passed") and state["repair_round"] >= state["max_repair_rounds"]:
        return "escalation"
    if flags.get("final_review"):
        return "final_review"
    if state.get("status") == "pending_final_review":
        return "final_review"
    if state.get("final_output") and not state.get("validation_passed"):
        return "escalation"
    return "clarification"


def _escalation_question(state: AgentState) -> str:
    if state.get("status") == "workers_failed":
        errors = "; ".join(
            t.get("error") or "" for t in state.get("subtasks", []) if t.get("error")
        )
        return (
            "One or more workers could not generate their deliverable:\n"
            f"  {errors}\n"
            "Options:\n"
            "  [retry]  rerun the workers\n"
            "  [accept] deliver whatever artifacts already exist\n"
            "  [anything else] treated as new requirements"
        )
    return (
        f"Repair limit reached ({state['repair_round']}/{state['max_repair_rounds']} rounds). "
        "Validation still fails. Options:\n"
        "  [retry]  reset the repair counter and run another 2 rounds\n"
        "  [accept] deliver partial output as graceful failure\n"
        "  [anything else] treated as new requirements for a fresh run"
    )


def hitl_checkpoint(state: AgentState):
    hitl = dict(state.get("hitl") or {"required": False, "kind": "", "question": "", "answer": None})
    kind = hitl.get("kind") or _infer_kind(state)

    if not hitl.get("question"):
        if kind == "escalation":
            hitl["question"] = _escalation_question(state)
        elif kind == "final_review":
            hitl["question"] = (
                "Final acceptance check passed. Review the output - "
                "type 'done' to deliver, or describe improvements/removals/additions."
            )
        else:
            hitl["question"] = "The manager needs clarification before continuing. Your answer?"

    answer_raw = interrupt(
        {"kind": kind, "question": hitl["question"], "repair_round": state["repair_round"]}
    )
    answer = (answer_raw or "").strip()
    hitl["required"] = False
    hitl["kind"] = kind
    hitl["answer"] = answer

    update: dict = {
        "hitl": hitl,
        "events": [{"node": "hitl_checkpoint", "msg": f"[{kind}] user answered: {answer or '(empty)'}"}],
    }

    if kind == "escalation":
        lowered = answer.lower()
        if lowered == "retry":
            update["repair_round"] = 0
            update["status"] = "hitl_retry"
        elif lowered in {"accept", "accept_partial"}:
            update["status"] = "hitl_graceful"
        else:
            update["user_request"] = state["user_request"] + f"\nAdditional requirements: {answer}"
            update["status"] = "hitl_revise"
    elif kind == "final_review":
        if answer.lower() in APPROVE_WORDS:
            update["status"] = "hitl_approved"
        else:
            update["user_request"] = state["user_request"] + f"\nRequested changes: {answer}"
            update["status"] = "hitl_revise"
    else:
        update["user_request"] = state["user_request"] + f"\nClarification: {answer}"
        update["status"] = "hitl_revise"

    return update


hitl = hitl_checkpoint