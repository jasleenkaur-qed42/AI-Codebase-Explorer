"""Boots a throwaway ingested repo + the FastAPI app for Playwright specs to hit."""
import subprocess
import tempfile
from pathlib import Path


def _run(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def make_repo(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    _run(root, "init", "-q")
    _run(root, "config", "user.email", "jane@example.com")
    _run(root, "config", "user.name", "Jane")
    (root / "foo.py").write_text(
        'def helper():\n'
        '    """Parses configuration files."""\n'
        '    return 1\n\n'
        'def main():\n'
        '    return helper()\n'
    )
    _run(root, "add", ".")
    _run(root, "commit", "-q", "-m", "initial commit")

    # A second commit by a different author, touching the same file --
    # lets the commit-first graph view exercise two independently
    # expandable commits with distinct per-commit authors.
    _run(root, "config", "user.email", "bob@example.com")
    _run(root, "config", "user.name", "Bob")
    (root / "foo.py").write_text(
        'def helper():\n'
        '    """Parses configuration files."""\n'
        '    return 1\n\n'
        'def main():\n'
        '    """Entry point."""\n'
        '    return helper()\n'
    )
    _run(root, "add", ".")
    _run(root, "commit", "-q", "-m", "document main")

    _run(root, "remote", "add", "origin", "https://github.com/acme/app.git")


def main():
    repo_dir = Path(tempfile.mkdtemp()) / "repo"
    make_repo(repo_dir)

    from explorer.cli import ingest
    ingest(str(repo_dir))

    import uvicorn
    from explorer.web.api import create_app

    app = create_app(str(repo_dir))
    uvicorn.run(app, host="127.0.0.1", port=8420)


if __name__ == "__main__":
    main()
