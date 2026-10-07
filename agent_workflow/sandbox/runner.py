from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

TIMEOUT = 60
LOG_LIMIT = 6000


def _minimal_env(workspace: Path) -> dict[str, str]:
    keep = [
        "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
        "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "HOME",
    ]
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "0"
    env["PYTHONPATH"] = str(workspace)
    return env


def _run(cmd: list[str], workspace: Path) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(workspace),
            env=_minimal_env(workspace),
            stdin=subprocess.DEVNULL,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {TIMEOUT}s: {' '.join(cmd)}"
    except OSError as exc:
        return 125, f"failed to launch {' '.join(cmd)}: {exc}"
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output.strip()


def _clip(text: str) -> str:
    if len(text) <= LOG_LIMIT:
        return text
    return "...[truncated]\n" + text[-LOG_LIMIT:]


def _stage(name: str, passed: bool, log: str, failed_files: list[str]) -> dict:
    return {
        "stage": name,
        "passed": passed,
        "log": _clip(log),
        "failed_files": sorted(set(failed_files)),
    }


def _check_compile(workspace: Path, py_files: list[Path]) -> dict:
    failed, logs = [], []
    for file in py_files:
        code, out = _run([sys.executable, "-m", "py_compile", file.name], workspace)
        if code != 0:
            failed.append(file.name)
            logs.append(f"{file.name}:\n{out or '(no output)'}")
    if not logs:
        logs = [f"py_compile OK for {len(py_files)} file(s)"]
    return _stage("compile", not failed, "\n".join(logs), failed)


def _check_lint(workspace: Path) -> dict:
    code, out = _run(
        [sys.executable, "-m", "ruff", "check", ".", "--no-cache"], workspace
    )
    if "No module named ruff" in out or code == 125:
        return _stage("lint", True, "ruff not available; lint skipped", [])
    if code == 0:
        return _stage("lint", True, "ruff: no issues", [])
    if code == 2:
        return _stage("lint", False, f"ruff failed to run:\n{out}", [])
    failed = []
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith("--> "):
            token = stripped[4:].split(":")[0]
        else:
            token = stripped.split(":")[0]
        if token.endswith(".py"):
            failed.append(Path(token).name)
    return _stage("lint", False, out, failed)


def _check_tests(workspace: Path) -> dict:
    code, out = _run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"],
        workspace,
    )
    if code == 0:
        return _stage("test", True, out or "pytest: all passed", [])
    if code == 5:
        return _stage("test", True, "pytest: no tests collected", [])
    if code == 124:
        return _stage("test", False, out, [])
    failed = []
    for line in out.splitlines():
        stripped = line.strip()
        for marker in ("FAILED ", "ERROR "):
            if stripped.startswith(marker):
                file_part = stripped[len(marker):].split("::")[0].split(" ")[0]
                if file_part.endswith(".py"):
                    failed.append(Path(file_part).name)
    return _stage("test", False, out, failed)


def run_checks(workspace: Path) -> list[dict]:
    py_files = sorted(workspace.glob("*.py"))
    if not py_files:
        return [
            _stage(
                "compile",
                False,
                "sandbox contains no Python files; nothing to validate",
                [],
            ),
            _stage("test", False, "skipped: no Python files", []),
        ]
    results = [_check_compile(workspace, py_files), _check_lint(workspace)]
    results.append(_check_tests(workspace))
    return results
