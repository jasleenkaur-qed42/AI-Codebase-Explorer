import subprocess
import pytest

from explorer import history_miner


def _run(repo_dir, *args):
    subprocess.run(["git", *args], cwd=repo_dir, check=True, capture_output=True)


@pytest.fixture
def scripted_repo(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _run(repo_dir, "init", "-q")
    _run(repo_dir, "config", "user.email", "jane@example.com")
    _run(repo_dir, "config", "user.name", "Jane")

    (repo_dir / "foo.py").write_text("def foo():\n    return 1\n")
    _run(repo_dir, "add", "foo.py")
    _run(repo_dir, "commit", "-q", "-m", "add foo")

    (repo_dir / "bar.py").write_text("def bar():\n    return 2\n")
    _run(repo_dir, "add", "bar.py")
    _run(repo_dir, "commit", "-q", "-m", "add bar")

    _run(repo_dir, "config", "user.email", "bob@example.com")
    _run(repo_dir, "config", "user.name", "Bob")
    (repo_dir / "foo.py").write_text("def foo():\n    return 1\n\ndef foo2():\n    return 3\n")
    (repo_dir / "bar.py").write_text("def bar():\n    return 22\n")
    _run(repo_dir, "add", "foo.py", "bar.py")
    _run(repo_dir, "commit", "-q", "-m", "touch both foo and bar")

    return repo_dir


def test_mine_history_extracts_all_commits(scripted_repo):
    result = history_miner.mine(str(scripted_repo))

    assert len(result.commits) == 3
    messages = {c["message"] for c in result.commits}
    assert messages == {"add foo", "add bar", "touch both foo and bar"}


def test_mine_history_extracts_distinct_authors(scripted_repo):
    result = history_miner.mine(str(scripted_repo))

    emails = {a["email"] for a in result.authors}
    assert emails == {"jane@example.com", "bob@example.com"}


def test_mine_history_derives_co_changed_with_edge(scripted_repo):
    result = history_miner.mine(str(scripted_repo))

    co_change = [e for e in result.edges if e["type"] == "co_changed_with"]
    assert len(co_change) == 1
    edge = co_change[0]
    assert {edge["src_id"], edge["dst_id"]} == {"file:foo.py", "file:bar.py"}
    assert edge["attrs"]["count"] == 1


def test_mine_history_creates_modifies_edges_per_commit(scripted_repo):
    result = history_miner.mine(str(scripted_repo))

    modifies_to_foo = [e for e in result.edges if e["type"] == "modifies" and e["dst_id"] == "file:foo.py"]
    assert len(modifies_to_foo) == 2
