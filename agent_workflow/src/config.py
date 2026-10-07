from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    key_env: str


PROVIDERS: dict[str, Provider] = {
    "nebius": Provider(
        name="nebius",
        base_url=os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1"),
        key_env="NEBIUS_API_KEY",
    ),
    "nvidia": Provider(
        name="nvidia",
        base_url=os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        key_env="NVIDIA_API_KEY",
    ),
}

DEFAULT_ROUTES: dict[str, tuple[str, str]] = {
    "orchestrator": ("nebius", "meta-llama/Llama-3.3-70B-Instruct"),
    "coder": ("nebius", "Qwen/Qwen2.5-Coder-32B-Instruct"),
    "tester": ("nvidia", "qwen/qwen2.5-coder-32b-instruct"),
    "doc_writer": ("nvidia", "meta/llama-3.3-70b-instruct"),
    "reviewer": ("nebius", "Qwen/Qwen3-32B"),
    "researcher": ("nvidia", "meta/llama-3.3-70b-instruct"),
}

KNOWN_WORKERS = {"coder", "tester", "doc_writer", "reviewer", "researcher"}


def _env_routes() -> dict[str, tuple[str, str]]:
    raw = os.environ.get("WORKER_ROUTES_JSON", "")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"WORKER_ROUTES_JSON is not valid JSON: {exc}") from exc
    routes = {}
    for role, spec in parsed.items():
        provider, _, model = spec.partition(":")
        if not model:
            raise ValueError(f"WORKER_ROUTES_JSON[{role!r}] must be 'provider:model'")
        routes[role] = (provider, model)
    return routes


def resolve_route(role: str, force_provider: str | None = None) -> tuple[str, str]:
    routes = {**DEFAULT_ROUTES, **_env_routes()}
    role = role if role in routes else "coder"
    provider, model = routes[role]
    if force_provider:
        provider = force_provider
    return provider, model


def provider_key(provider_name: str) -> str | None:
    prov = PROVIDERS.get(provider_name)
    if not prov:
        return None
    value = os.environ.get(prov.key_env, "").strip()
    return value or None


def available_providers() -> list[str]:
    return [name for name in PROVIDERS if provider_key(name)]
