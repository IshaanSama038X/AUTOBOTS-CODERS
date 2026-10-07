from sandbox.extract import artifact_to_files, split_blocks, unique_name


def test_split_blocks_separates_code_docs_and_ignores_other_languages():
    text = (
        "```python\nx = 1\n```\n"
        "```markdown\n# Notes\n```\n"
        "```json\n{}\n```"
    )
    assert split_blocks(text) == (["x = 1"], ["# Notes"])


def test_artifact_to_files_uses_worker_file_conventions():
    assert artifact_to_files({"worker": "coder"}, "```py\nx = 1\n```") == {
        "main.py": "x = 1\n"
    }
    assert artifact_to_files({"worker": "tester"}, "```python\ndef test_x(): pass\n```") == {
        "test_main.py": "def test_x(): pass\n"
    }
    assert artifact_to_files({"worker": "doc_writer"}, "```md\n# Guide\n```") == {
        "README.md": "# Guide\n"
    }


def test_artifact_to_files_falls_back_to_plain_text_and_skips_empty():
    assert artifact_to_files({"worker": "coder"}, "x = 1") == {"main.py": "x = 1\n"}
    assert artifact_to_files({"worker": "coder"}, "") == {}


def test_unique_name_appends_available_suffix():
    assert unique_name("main.py", {"main.py", "main_2.py"}) == "main_3.py"