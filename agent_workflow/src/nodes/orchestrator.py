from __future__ import annotations

from src.config import KNOWN_WORKERS, resolve_route
from src.llm import ProviderError, chat, extract_json
from src.state import AgentState

ORCHESTRATOR_SYSTEM = (
    "You are the orchestrator of a multi-agent software engineering team. "
    "Decompose the user's request into 3 to 5 concrete subtasks and assign each "
    f"to one worker from this exact set: {sorted(KNOWN_WORKERS)}. "
    "Coverage rule: include coding, testing and documentation subtasks unless the "
    "request makes one irrelevant. "
    "Reply with ONLY a JSON object, no prose, in this form: "
    '{"subtasks": [{"description": "<specific instruction for one worker>", '
    '"worker": "<worker name>"}]}'
)


def _make_subtask(index: int, description: str, worker: str, force: str | None) -> dict:
    provider, model = resolve_route(worker, force)
    return {
        "id": f"t{index}",
        "description": description,
        "worker": worker,
        "provider": provider,
        "model": model,
        "status": "pending",
        "artifact": None,
        "error": None,
    }


def _default_subtasks(request: str, force: str | None) -> list[dict]:
    specs = [
        (f"Implement the core feature for: {request}", "coder"),
        (f"Write automated tests covering: {request}", "tester"),
        (f"Write usage documentation for: {request}", "doc_writer"),
    ]
    return [
        _make_subtask(i, desc, worker, force)
        for i, (desc, worker) in enumerate(specs, start=1)
    ]


def _llm_subtasks(state: AgentState) -> tuple[list[dict], str]:
    force = state["config_flags"].get("force_provider")
    provider, model = resolve_route("orchestrator", force)
    last_error = "no response"
    for _ in range(2):
        text = chat(
            provider,
            model,
            ORCHESTRATOR_SYSTEM,
            f"User request:\n{state['user_request']}",
            max_tokens=1200,
        )
        data = extract_json(text)
        if data and isinstance(data.get("subtasks"), list):
            parsed = []
            for item in data["subtasks"][:6]:
                if not isinstance(item, dict):
                    continue
                desc = str(item.get("description", "")).strip()
                worker = str(item.get("worker", "coder")).strip()
                if not desc:
                    continue
                if worker not in KNOWN_WORKERS:
                    worker = "coder"
                parsed.append((desc, worker))
            if len(parsed) >= 2:
                subtasks = [
                    _make_subtask(i, desc, worker, force)
                    for i, (desc, worker) in enumerate(parsed, start=1)
                ]
                return subtasks, f"LLM decomposition via {provider}/{model}"
            last_error = f"unusable JSON: {str(data)[:200]}"
        else:
            last_error = "model did not return JSON"
    return _default_subtasks(state["user_request"], force), (
        f"LLM decomposition failed ({last_error}); used fallback plan"
    )


def orchestrator(state: AgentState):
    flags = state.get("config_flags") or {}
    force = flags.get("force_provider")

    if flags.get("mock"):
        subtasks = _default_subtasks(state["user_request"], force)
        how = "mock decomposition (no LLM call)"
    else:
        try:
            subtasks, how = _llm_subtasks(state)
        except ProviderError as exc:
            subtasks = _default_subtasks(state["user_request"], force)
            how = f"provider error: {exc}; used fallback plan"

    routes = ", ".join(
        f"{t['worker']}->{t['provider']}:{t['model']}" for t in subtasks
    )
    return {
        "subtasks": subtasks,
        "artifacts": {},
        "compiled_output": "",
        "validation_results": [],
        "validation_passed": False,
        "repair_round": 0,
        "hitl": {"required": False, "kind": "", "question": "", "answer": None},
        "final_output": None,
        "status": "orchestrated",
        "events": [
            {"node": "orchestrator", "msg": f"{how}; {len(subtasks)} subtasks"},
            {"node": "orchestrator", "msg": f"routing: {routes}"},
        ],
    }
