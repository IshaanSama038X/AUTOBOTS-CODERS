from __future__ import annotations

from pathlib import Path

from sandbox.extract import artifact_to_files, split_blocks, unique_name
from sandbox.runner import run_checks
from src.nodes.validator import validator
from src.state import initial_state


def _task(worker: str, task_id: str = "t1") -> dict:
    return {"id": task_id, "worker": worker}


def test_split_blocks_separates_code_and_docs():
    text = "intro\n```python\nx = 1\n```\nmid\n```markdown\n# hi\n```\nend"
    code, docs = split_blocks(text)
    assert code == ["x = 1"]
    assert docs == ["# hi"]


def test_coder_artifact_becomes_main_py():
    files = artifact_to_files(_task("coder"), "text\n```python\nprint(1)\n```\ndone")
    assert files == {"main.py": "print(1)\n"}


def test_coder_raw_artifact_without_fences():
    files = artifact_to_files(_task("coder"), "def solve():\n    return 42\n")
    assert "main.py" in files
    assert "return 42" in files["main.py"]


def test_tester_and_doc_artifacts():
    tester = artifact_to_files(_task("tester"), "```python\nassert True\n```")
    doc = artifact_to_files(_task("doc_writer"), "```markdown\n# Readme\n```")
    assert "test_main.py" in tester
    assert "README.md" in doc


def test_unique_name_avoids_collisions():
    assert unique_name("main.py", set()) == "main.py"
    assert unique_name("main.py", {"main.py"}) == "main_2.py"


def test_good_sandbox_passes_all_stages(tmp_path: Path):
    (tmp_path / "main.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "test_main.py").write_text(
        "from main import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    results = {result["stage"]: result for result in run_checks(tmp_path)}
    assert results["compile"]["passed"], results["compile"]
    assert results["lint"]["passed"], results["lint"]
    assert results["test"]["passed"], results["test"]


def test_syntax_error_fails_compile_and_maps_file(tmp_path: Path):
    (tmp_path / "main.py").write_text("def broken(:\n", encoding="utf-8")
    results = {result["stage"]: result for result in run_checks(tmp_path)}
    assert not results["compile"]["passed"]
    assert "main.py" in results["compile"]["failed_files"]


def test_failing_test_maps_test_file(tmp_path: Path):
    (tmp_path / "main.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (tmp_path / "test_main.py").write_text(
        "from main import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    results = {result["stage"]: result for result in run_checks(tmp_path)}
    assert not results["test"]["passed"]
    assert "test_main.py" in results["test"]["failed_files"]


def test_lint_flags_unused_import(tmp_path: Path):
    (tmp_path / "main.py").write_text("import os\n", encoding="utf-8")
    results = {result["stage"]: result for result in run_checks(tmp_path)}
    assert not results["lint"]["passed"]
    assert "main.py" in results["lint"]["failed_files"]


def test_empty_sandbox_fails(tmp_path: Path):
    results = run_checks(tmp_path)
    assert not results[0]["passed"]
    assert "no Python files" in results[0]["log"]


def test_validator_maps_failures_to_task_ids(tmp_path: Path):
    (tmp_path / "main.py").write_text("def broken(:\n", encoding="utf-8")
    state = initial_state("x")
    state["subtasks"] = [
        {"id": "t1", "worker": "coder", "status": "done", "artifact": "x"},
        {"id": "t2", "worker": "tester", "status": "done", "artifact": "y"},
    ]
    state["artifacts"] = {"t1": "x", "t2": "y"}
    state["sandbox_dir"] = str(tmp_path)
    state["file_map"] = {"main.py": "t1"}
    state["repair_round"] = 0
    result = validator(state)
    assert not result["validation_passed"]
    failed_ids = set()
    for validation in result["validation_results"]:
        failed_ids.update(validation["failed_task_ids"])
    assert "t1" in failed_ids


def test_validator_forced_failure_still_simulated():
    state = initial_state("x", fail_rounds=1)
    state["subtasks"] = [
        {"id": "t1", "worker": "coder", "status": "done", "artifact": "x"}
    ]
    state["artifacts"] = {"t1": "x"}
    state["repair_round"] = 0
    result = validator(state)
    assert not result["validation_passed"]
    assert "simulated" in result["validation_results"][0]["log"]