import fnmatch
from pathlib import Path

DOC_PATTERNS = ["README*", "docs/*.md", "docs/*/*.md"]
IGNORED_DIRS = {".git", ".venv", "__pycache__", ".explorer", "node_modules"}


def find_doc_files(repo_path: str):
    root = Path(repo_path)
    found = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        rel = path.relative_to(root).as_posix()
        if any(fnmatch.fnmatch(rel, pattern) for pattern in DOC_PATTERNS):
            found.append(path)
    return found


def walk(repo_path: str, doc_paths, read_file):
    docs = []
    for rel_path in doc_paths:
        text = read_file(rel_path)
        docs.append({
            "id": f"doc:{rel_path}",
            "type": "doc",
            "name": rel_path,
            "path": rel_path,
            "text": text,
        })
    return docs
