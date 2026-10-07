from __future__ import annotations

import os
import uuid

from langgraph.types import Command

from src.config import DEFAULT_ROUTES, KNOWN_WORKERS, PROVIDERS, resolve_route
from src.graph import build_graph
from src.llm import ProviderError, extract_block, extract_json
from src.state import initial_state


def test_route_defaults_are_known_providers():
    for role in DEFAULT_ROUTES:
        provider, model = resolve_route(role)
        assert provider in PROVIDERS
        assert model


def test_unknown_role_falls_back_to_coder_model():
    assert resolve_route("banana") == resolve_route("coder")


def test_force_provider_overrides_route():
    provider, model = resolve_route("coder", force_provider="nvidia")
    assert provider == "nvidia"
    assert model == resolve_route("coder")[1]


def test_extract_block_and_json():
    text = "here you go:\n```python\nx = 1\n```\nand done"
    assert extract_block(text, "python") == "x = 1"
    data = extract_json('noise {"subtasks": [{"description": "d", "worker": "coder"}]} tail')
    assert data["subtasks"][0]["worker"] == "coder"


def test_worker_roles_are_constrained():
    assert KNOWN_WORKERS == {"coder", "tester", "doc_writer", "reviewer", "researcher"}


def test_worker_generation_failure_gates_to_hitl():
    app = build_graph()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": 100}
    payload = initial_state(
        "build a thing", mock=False, force_provider="not_a_provider"
    )
    app.invoke(payload, config)
    snapshot = app.get_state(config)
    assert snapshot.next == ("hitl",)
    kinds = [
        t.interrupts[0].value.get("kind")
        for t in snapshot.tasks
        if getattr(t, "interrupts", None)
    ]
    assert kinds == ["escalation"]
    final = app.invoke(Command(resume="accept"), config)
    assert final["status"] == "graceful_failure"


def test_live_mode_requires_key_message():
    saved = os.environ.pop("NEBIUS_API_KEY", None)
    try:
        from src.llm import chat

        try:
            chat("nebius", "some-model", "s", "u")
        except ProviderError as exc:
            assert "NEBIUS_API_KEY" in str(exc)
            assert "--mock" in str(exc)
        else:
            raise AssertionError("expected ProviderError without a key")
    finally:
        if saved is not None:
            os.environ["NEBIUS_API_KEY"] = saved
