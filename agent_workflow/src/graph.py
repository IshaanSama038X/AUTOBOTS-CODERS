from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src.nodes.acceptance import final_acceptance
from src.nodes.hitl import hitl_checkpoint
from src.nodes.manager import manager_compiler
from src.nodes.orchestrator import orchestrator
from src.nodes.repair import repair_agent
from src.nodes.validator import validator
from src.nodes.workers import run_workers
from src.state import AgentState


def route_after_workers(state: AgentState) -> str:
    if state.get("status") == "workers_failed":
        return "hitl"
    return "manager"


def route_after_validation(state: AgentState) -> str:
    if state["validation_passed"]:
        return "acceptance"
    if state["repair_round"] < state["max_repair_rounds"]:
        return "repair"
    return "hitl"


def route_after_hitl(state: AgentState) -> str:
    status = state.get("status", "")
    if status == "hitl_retry":
        return "workers"
    if status == "hitl_graceful":
        return "acceptance"
    if status == "hitl_revise":
        return "orchestrator"
    if status == "hitl_approved":
        return END
    return "orchestrator"


def route_after_acceptance(state: AgentState) -> str:
    if state.get("status") == "pending_final_review":
        return "hitl"
    return END


def build_graph(checkpointer=None):
    workflow = StateGraph(AgentState)

    workflow.add_node("orchestrator", orchestrator)
    workflow.add_node("workers", run_workers)
    workflow.add_node("manager_compiler", manager_compiler)
    workflow.add_node("validator", validator)
    workflow.add_node("repair_agent", repair_agent)
    workflow.add_node("hitl", hitl_checkpoint)
    workflow.add_node("final_acceptance", final_acceptance)

    workflow.add_edge(START, "orchestrator")
    workflow.add_edge("orchestrator", "workers")
    workflow.add_conditional_edges(
        "workers",
        route_after_workers,
        {"manager": "manager_compiler", "hitl": "hitl"},
    )
    workflow.add_edge("manager_compiler", "validator")
    workflow.add_conditional_edges(
        "validator",
        route_after_validation,
        {"acceptance": "final_acceptance", "repair": "repair_agent", "hitl": "hitl"},
    )
    workflow.add_edge("repair_agent", "workers")
    workflow.add_conditional_edges(
        "hitl",
        route_after_hitl,
        {
            "workers": "workers",
            "orchestrator": "orchestrator",
            "acceptance": "final_acceptance",
            END: END,
        },
    )
    workflow.add_conditional_edges(
        "final_acceptance",
        route_after_acceptance,
        {"hitl": "hitl", END: END},
    )

    return workflow.compile(checkpointer=checkpointer or MemorySaver())


def get_app():
    return build_graph()


graph = build_graph()