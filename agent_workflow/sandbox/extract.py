from __future__ import annotations

import re

BLOCK_RE = re.compile(r"```([a-zA-Z0-9_+-]*)[ \t]*\r?\n(.*?)```", re.DOTALL)

CODE_LANGS = {"", "python", "py"}
DOC_LANGS = {"markdown", "md", "text", "txt"}


def split_blocks(text: str) -> tuple[list[str], list[str]]:
    code_blocks = []
    doc_blocks = []
    for lang, body in BLOCK_RE.findall(text):
        lang = lang.lower()
        if lang in CODE_LANGS:
            code_blocks.append(body.strip())
        elif lang in DOC_LANGS:
            doc_blocks.append(body.strip())
    return code_blocks, doc_blocks


def artifact_to_files(task: dict, artifact: str) -> dict[str, str]:
    worker = task.get("worker", "coder")
    task_id = task.get("id", "t0")
    code_blocks, doc_blocks = split_blocks(artifact)

    if worker == "coder":
        body = "\n\n".join(code_blocks)
        if not body and not BLOCK_RE.search(artifact) and artifact.strip():
            body = artifact.strip()
        return {"main.py": body + "\n"} if body.strip() else {}

    if worker == "tester":
        body = "\n\n".join(code_blocks)
        if not body and not BLOCK_RE.search(artifact) and artifact.strip():
            body = artifact.strip()
        return {"test_main.py": body + "\n"} if body.strip() else {}

    if worker == "doc_writer":
        body = "\n\n".join(doc_blocks)
        if not body and artifact.strip():
            body = artifact.strip()
        return {"README.md": body + "\n"} if body.strip() else {}

    body = "\n\n".join(doc_blocks) or artifact.strip()
    return {f"notes_{task_id}.md": body + "\n"} if body.strip() else {}


def unique_name(name: str, taken: set[str]) -> str:
    if name not in taken:
        return name
    stem, dot, ext = name.partition(".")
    counter = 2
    while f"{stem}_{counter}{dot}{ext}" in taken:
        counter += 1
    return f"{stem}_{counter}{dot}{ext}"
