from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class Subtask(TypedDict):
    id: str
    description: str
    worker: str
    provider: str
    model: str
    status: str
    artifact: str | None
    error: str | None


class ValidationResult(TypedDict):
    passed: bool
    stage: str
    log: str
    failed_task_ids: list[str]


class HITLState(TypedDict):
    required: bool
    kind: str
    question: str
    answer: str | None


class AgentState(TypedDict):
    user_request: str
    subtasks: list[Subtask]
    artifacts: dict[str, str]
    compiled_output: str
    validation_results: list[ValidationResult]
    validation_passed: bool
    repair_round: int
    max_repair_rounds: int
    repair_log: Annotated[list[dict], operator.add]
    hitl: HITLState
    final_output: str | None
    status: str
    sandbox_dir: str
    file_map: dict[str, str]
    events: Annotated[list[dict], operator.add]
    config_flags: dict[str, Any]


def initial_state(
    request: str,
    *,
    fail_rounds: int = 0,
    final_review: bool = False,
    mock: bool = True,
    force_provider: str | None = None,
) -> AgentState:
    return {
        "user_request": request,
        "subtasks": [],
        "artifacts": {},
        "compiled_output": "",
        "validation_results": [],
        "validation_passed": False,
        "repair_round": 0,
        "max_repair_rounds": 2,
        "repair_log": [],
        "hitl": {"required": False, "kind": "", "question": "", "answer": None},
        "final_output": None,
        "status": "new",
        "sandbox_dir": "",
        "file_map": {},
        "events": [],
        "config_flags": {
            "fail_rounds": fail_rounds,
            "final_review": final_review,
            "mock": mock,
            "force_provider": force_provider,
        },
    }