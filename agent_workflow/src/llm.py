from __future__ import annotations

import re
import time

import requests

from src.config import PROVIDERS, provider_key


class ProviderError(RuntimeError):
    pass


RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def chat(
    provider: str,
    model: str,
    system: str,
    user: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    timeout: int = 180,
    retries: int = 3,
) -> str:
    prov = PROVIDERS.get(provider)
    if prov is None:
        raise ProviderError(
            f"unknown provider {provider!r} (known: {', '.join(PROVIDERS)})"
        )
    key = provider_key(provider)
    if not key:
        raise ProviderError(
            f"missing API key: set {prov.key_env} for provider '{provider}', "
            "or run with --mock"
        )

    url = prov.base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    last_error = ""
    for attempt in range(retries):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except requests.RequestException as exc:
            last_error = str(exc)
            time.sleep(2**attempt)
            continue

        if resp.status_code == 200:
            try:
                content = resp.json()["choices"][0]["message"]["content"]
            except (KeyError, IndexError, ValueError) as exc:
                raise ProviderError(
                    f"malformed response from {provider}/{model}: {exc}"
                ) from exc
            if content is None:
                raise ProviderError(f"empty completion from {provider}/{model}")
            return content

        if resp.status_code in RETRYABLE_STATUS:
            last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
            time.sleep(2**attempt)
            continue
        raise ProviderError(
            f"{provider}/{model} rejected request "
            f"(HTTP {resp.status_code}): {resp.text[:300]}"
        )

    raise ProviderError(f"{provider}/{model} failed after {retries} attempts: {last_error}")


def extract_block(text: str, language: str | None = None) -> str | None:
    lang = re.escape(language) if language else r"[a-zA-Z0-9_+-]*"
    match = re.search(rf"```{lang}\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def extract_json(text: str) -> dict | None:
    fenced = extract_block(text, "json")
    candidates = [fenced] if fenced else []
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        candidates.append(brace.group(0))
    for candidate in candidates:
        try:
            import json

            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except ValueError:
            continue
    return None
