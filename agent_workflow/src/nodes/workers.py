from __future__ import annotations

from src.config import resolve_route
from src.llm import ProviderError, chat
from src.state import AgentState

MOCK_CODE = '''"""{desc}"""

SOLVER_WORKER = "{worker}"
SOLVER_MODEL = "{model}"


def solve() -> str:
    """Return the deliverable produced by {worker}."""
    return "ok"
'''

ROLE_SYSTEM = {
    "coder": (
        "You are a senior Python engineer on a multi-agent software team. "
        "Implement the given task as ONE complete, runnable Python file. "
        "Reply with a single fenced ```python code block and nothing else."
    ),
    "tester": (
        "You are a QA engineer on a multi-agent software team. "
        "Write pytest tests for the provided implementation. "
        "Cover the happy path and at least two edge cases. "
        "Reply with a single fenced ```python code block and nothing else."
    ),
    "doc_writer": (
        "You are a technical writer on a multi-agent software team. "
        "Write a concise README.md for the project: what it does, install, usage, "
        "and a short example. Reply with a single fenced ```markdown code block "
        "and nothing else."
    ),
    "reviewer": (
        "You are a senior code reviewer. Review the provided implementation for "
        "bugs, edge cases and style problems. Reply with a single fenced "
        "```markdown block containing your review notes."
    ),
    "researcher": (
        "You are a technical researcher. Summarize the design decisions and "
        "alternatives for the given task. Reply with a single fenced ```markdown "
        "block and nothing else."
    ),
}

DEFAULT_SYSTEM = ROLE_SYSTEM["coder"]


def _clip(text: str, limit: int = 6000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


def _user_prompt(task: dict, state: AgentState, artifacts: dict[str, str]) -> str:
    worker = task["worker"]
    existing = "\n\n".join(
        f"--- artifact {tid} ---\n{code}" for tid, code in sorted(artifacts.items())
    )
    parts = [f"Project request:\n{state['user_request']}"]
    if worker == "tester" and existing:
        parts.append(f"Implementation to test (lives in main.py):\n{_clip(existing)}")
    elif worker in {"doc_writer", "reviewer"} and existing:
        parts.append(f"Project artifacts:\n{_clip(existing)}")
    elif worker == "researcher" and existing:
        parts.append(f"Existing artifacts:\n{_clip(existing, 2000)}")
    parts.append(f"Your task:\n{task['description']}")
    if task.get("error"):
        parts.append(
            "Your previous attempt failed verification. Error log:\n"
            f"{_clip(task['error'], 4000)}\n"
            "Produce a corrected version that fixes these errors."
        )
    return "\n\n".join(parts)


def _generate(task: dict, state: AgentState, artifacts: dict[str, str]) -> tuple[str, str, str]:
    force = state["config_flags"].get("force_provider")
    provider, model = resolve_route(task["worker"], force)
    system = ROLE_SYSTEM.get(task["worker"], DEFAULT_SYSTEM)
    text = chat(provider, model, system, _user_prompt(task, state, artifacts))
    return text, provider, model


def run_workers(state: AgentState):
    flags = state.get("config_flags") or {}
    mock = flags.get("mock", True)
    artifacts = dict(state.get("artifacts") or {})
    new_subtasks = []
    events = []

    for task in state["subtasks"]:
        updated = dict(task)
        if task["status"] != "done":
            if mock:
                provider, model = resolve_route(
                    task["worker"], flags.get("force_provider")
                )
                artifact = MOCK_CODE.format(
                    desc=task["description"], worker=task["worker"], model=model
                )
            else:
                try:
                    artifact, provider, model = _generate(task, state, artifacts)
                except ProviderError as exc:
                    updated["status"] = "pending"
                    updated["error"] = str(exc)
                    new_subtasks.append(updated)
                    events.append(
                        {
                            "node": "workers",
                            "msg": f"{task['worker']} FAILED to generate: {exc}",
                        }
                    )
                    continue
                updated["provider"] = provider
                updated["model"] = model
            updated["artifact"] = artifact
            updated["status"] = "done"
            updated["error"] = None
            artifacts[task["id"]] = artifact
            events.append(
                {
                    "node": "workers",
                    "msg": (
                        f"{task['worker']} [{updated['provider']}/{updated['model']}] "
                        f"completed {task['id']} ({len(artifact)} chars)"
                    ),
                }
            )
        new_subtasks.append(updated)

    if any(t["status"] != "done" for t in new_subtasks):
        status = "workers_failed"
    else:
        status = "workers_done"
    return {"subtasks": new_subtasks, "artifacts": artifacts, "status": status, "events": events}


workers = run_workers
