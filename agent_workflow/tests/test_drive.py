from __future__ import annotations

import uuid

from langgraph.types import Command

from src.graph import build_graph
from src.state import initial_state


def drive(request: str, *, fail_rounds: int = 0, final_review: bool = False,
          answers: list[str] | None = None):
    app = build_graph()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": 100}
    payload = initial_state(request, fail_rounds=fail_rounds, final_review=final_review)
    for answer in answers or []:
        app.invoke(payload, config)
        snapshot = app.get_state(config)
        assert snapshot.next, "graph finished before scripted answers ran out"
        payload = Command(resume=answer)
    app.invoke(payload, config)
    return app.get_state(config).values


def test_happy_path_approved():
    state = drive("build a CLI todo app")
    assert state["status"] == "approved"
    assert state["repair_round"] == 0
    assert len(state["subtasks"]) == 3
    assert "t1" in state["artifacts"]


def test_two_repair_rounds_then_pass():
    state = drive("build a REST API", fail_rounds=2)
    assert state["status"] == "approved"
    assert state["repair_round"] == 2
    assert len(state["repair_log"]) == 2
    assert state["repair_log"][0]["round"] == 1


def test_escalation_accept_graceful_failure():
    state = drive("build a scraper", fail_rounds=99, answers=["accept"])
    assert state["status"] == "graceful_failure"
    assert state["repair_round"] == 2
    assert state["final_output"].startswith("[PARTIAL OUTPUT")
    assert state["hitl"]["kind"] == "escalation"


def test_escalation_retry_resets_counter():
    state = drive("build a scraper", fail_rounds=99, answers=["retry", "accept"])
    assert state["status"] == "graceful_failure"
    assert len(state["repair_log"]) == 4
    assert state["repair_log"][2]["round"] == 1


def test_escalation_free_text_becomes_new_requirements():
    state = drive("build a scraper", fail_rounds=99, answers=["add rate limiting", "accept"])
    assert state["status"] == "graceful_failure"
    assert "add rate limiting" in state["user_request"]


def test_final_review_approve():
    state = drive("build a chatbot", final_review=True, answers=["done"])
    assert state["status"] == "hitl_approved"
    assert state["hitl"]["kind"] == "final_review"
    assert state["final_output"]


def test_final_review_revision_reruns_pipeline():
    state = drive(
        "build a chatbot",
        final_review=True,
        answers=["add streaming responses", "ok"],
    )
    assert state["status"] == "hitl_approved"
    assert "add streaming responses" in state["user_request"]
    assert "add streaming responses" in state["compiled_output"]


def test_repair_cap_never_exceeded_without_hitl():
    state = drive("build a scraper", fail_rounds=99, answers=["accept"])
    assert state["repair_round"] <= state["max_repair_rounds"] or state["status"] == "graceful_failure"
    rounds = [entry["round"] for entry in state["repair_log"]]
    assert rounds == sorted(rounds)
    assert all(1 <= r <= 2 for r in rounds)
