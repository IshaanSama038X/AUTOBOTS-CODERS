from src.graph import (
    route_after_acceptance,
    route_after_hitl,
    route_after_validation,
    route_after_workers,
)


def test_workers_route_failures_to_hitl_and_success_to_manager():
    assert route_after_workers({"status": "workers_done"}) == "manager"
    assert route_after_workers({"status": "workers_failed"}) == "hitl"


def test_validation_routes_by_result_and_repair_cap():
    assert route_after_validation(
        {"validation_passed": True, "repair_round": 0, "max_repair_rounds": 2}
    ) == "acceptance"
    assert route_after_validation(
        {"validation_passed": False, "repair_round": 1, "max_repair_rounds": 2}
    ) == "repair"
    assert route_after_validation(
        {"validation_passed": False, "repair_round": 2, "max_repair_rounds": 2}
    ) == "hitl"


def test_hitl_routes_each_supported_action():
    assert route_after_hitl({"status": "hitl_retry"}) == "workers"
    assert route_after_hitl({"status": "hitl_graceful"}) == "acceptance"
    assert route_after_hitl({"status": "hitl_revise"}) == "orchestrator"
    assert route_after_hitl({"status": "hitl_approved"}) == "__end__"


def test_hitl_unknown_status_restarts_orchestration():
    assert route_after_hitl({"status": "unexpected"}) == "orchestrator"


def test_acceptance_routes_final_review_back_to_hitl():
    assert route_after_acceptance({"status": "pending_final_review"}) == "hitl"
    assert route_after_acceptance({"status": "approved"}) == "__end__"