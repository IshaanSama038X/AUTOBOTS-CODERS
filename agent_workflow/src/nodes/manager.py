from __future__ import annotations

import tempfile
from pathlib import Path

from sandbox.extract import artifact_to_files, unique_name
from src.state import AgentState

CLEAN_SUFFIXES = {".py", ".md", ".txt", ".json"}


def manager_compiler(state: AgentState):
    sandbox_dir = state.get("sandbox_dir") or tempfile.mkdtemp(prefix="agent_sandbox_")
    workspace = Path(sandbox_dir)
    workspace.mkdir(parents=True, exist_ok=True)

    for stale in workspace.iterdir():
        if stale.is_file() and stale.suffix in CLEAN_SUFFIXES:
            stale.unlink()
        elif stale.is_dir() and stale.name == "__pycache__":
            for child in stale.iterdir():
                child.unlink()
            stale.rmdir()

    file_map: dict[str, str] = {}
    written: list[str] = []
    artifacts = state.get("artifacts") or {}

    for task in state["subtasks"]:
        artifact = artifacts.get(task["id"])
        if not artifact:
            continue
        for filename, content in artifact_to_files(task, artifact).items():
            filename = unique_name(filename, set(file_map))
            target = workspace / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            file_map[filename] = task["id"]
            written.append(filename)

    parts = [
        f"### artifact: {task_id}\n{code}"
        for task_id, code in sorted(artifacts.items())
    ]
    compiled = "\n\n".join(parts)

    return {
        "compiled_output": compiled,
        "sandbox_dir": sandbox_dir,
        "file_map": file_map,
        "status": "assembled",
        "events": [
            {
                "node": "manager_compiler",
                "msg": (
                    f"wrote {len(written)} file(s) [{', '.join(written) or 'none'}] "
                    f"to sandbox {sandbox_dir}"
                ),
            }
        ],
    }


def manager(state: AgentState) -> dict:
    return manager_compiler(state)