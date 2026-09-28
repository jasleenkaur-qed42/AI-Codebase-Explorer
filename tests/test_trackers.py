import inspect
import subprocess

import pytest

from explorer import store, trackers


class _FakeResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data


def _make_repo(tmp_path, remote_url=None):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)
    if remote_url:
        subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=repo_dir, check=True)
    return repo_dir


def _patch_credentials(monkeypatch, **overrides):
    credentials = {"GITHUB_TOKEN": None, "JIRA_BASE_URL": None, "JIRA_EMAIL": None, "JIRA_API_TOKEN": None}
    credentials.update(overrides)
    monkeypatch.setattr(trackers.config, "load_tracker_credentials", lambda: credentials)


def test_github_owner_repo_parses_https_remote_url(tmp_path):
    repo_dir = _make_repo(tmp_path, "https://github.com/acme/app.git")
    assert trackers.github_owner_repo(str(repo_dir)) == ("acme", "app")


def test_github_owner_repo_parses_ssh_remote_url(tmp_path):
    repo_dir = _make_repo(tmp_path, "git@github.com:acme/app.git")
    assert trackers.github_owner_repo(str(repo_dir)) == ("acme", "app")


def test_github_owner_repo_returns_none_when_no_remote(tmp_path):
    repo_dir = _make_repo(tmp_path)
    assert trackers.github_owner_repo(str(repo_dir)) is None


def test_fetch_github_pr_returns_json_on_success(monkeypatch):
    monkeypatch.setattr(
        trackers.requests, "get",
        lambda url, headers=None, timeout=None: _FakeResponse(200, {"title": "Migrate to app router"}),
    )
    assert trackers.fetch_github_pr("acme", "app", 456, "tok") == {"title": "Migrate to app router"}


def test_fetch_github_pr_returns_none_on_404(monkeypatch):
    monkeypatch.setattr(trackers.requests, "get", lambda url, headers=None, timeout=None: _FakeResponse(404))
    assert trackers.fetch_github_pr("acme", "app", 456, "tok") is None


def test_fetch_github_pr_returns_none_on_network_error(monkeypatch):
    def _raise(*args, **kwargs):
        raise trackers.requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(trackers.requests, "get", _raise)
    assert trackers.fetch_github_pr("acme", "app", 456, "tok") is None


def test_fetch_jira_issue_returns_json_on_success(monkeypatch):
    monkeypatch.setattr(
        trackers.requests, "get",
        lambda url, auth=None, timeout=None: _FakeResponse(200, {"fields": {"summary": "Design change"}}),
    )
    result = trackers.fetch_jira_issue("https://acme.atlassian.net", "a@b.com", "tok", "DESIGN-77")
    assert result == {"fields": {"summary": "Design change"}}


def test_link_commits_creates_pr_node_and_references_edge(tmp_path, monkeypatch):
    _patch_credentials(monkeypatch, GITHUB_TOKEN="tok")
    repo_dir = _make_repo(tmp_path, "https://github.com/acme/app.git")

    pr_payload = {
        "title": "Migrate project to app router", "body": "Switches routing to app dir",
        "state": "closed", "html_url": "https://github.com/acme/app/pull/456",
        "merged_at": "2026-01-05T10:00:00Z", "assignee": {"login": "jane"},
    }
    monkeypatch.setattr(trackers.requests, "get", lambda url, headers=None, timeout=None: _FakeResponse(200, pr_payload))

    conn = store.connect(":memory:")
    commits = [{"hash": "c1", "message": "Migrate project to app router (#456)"}]

    trackers.link_commits_to_trackers(conn, commits, str(repo_dir))

    node = store.get_node(conn, "pr:acme/app:456")
    assert node is not None
    assert node["attrs"]["merged_at"] == "2026-01-05T10:00:00Z"
    edges = store.get_edges(conn, src_id="commit:c1", dst_id="pr:acme/app:456", type="references")
    assert len(edges) == 1
    search_hits = store.search_fts(conn, "trackers", "router")
    assert any(h["node_id"] == "pr:acme/app:456" for h in search_hits)


def test_link_commits_skips_refetch_when_pr_node_already_exists(tmp_path, monkeypatch):
    _patch_credentials(monkeypatch, GITHUB_TOKEN="tok")
    repo_dir = _make_repo(tmp_path, "https://github.com/acme/app.git")

    conn = store.connect(":memory:")
    store.upsert_node(conn, id="pr:acme/app:456", type="pr", name="Migrate project to app router")

    calls = []
    monkeypatch.setattr(
        trackers.requests, "get",
        lambda url, headers=None, timeout=None: calls.append(url) or _FakeResponse(200, {}),
    )

    commits = [{"hash": "c1", "message": "Migrate project to app router (#456)"}]
    trackers.link_commits_to_trackers(conn, commits, str(repo_dir))

    assert calls == []
    edges = store.get_edges(conn, src_id="commit:c1", dst_id="pr:acme/app:456", type="references")
    assert len(edges) == 1


def test_link_commits_creates_ticket_node_from_jira_key(tmp_path, monkeypatch):
    _patch_credentials(
        monkeypatch, JIRA_BASE_URL="https://acme.atlassian.net", JIRA_EMAIL="a@b.com", JIRA_API_TOKEN="tok",
    )
    repo_dir = _make_repo(tmp_path)

    jira_payload = {"fields": {
        "summary": "Design change request for buttons", "description": "Update spacing",
        "status": {"name": "Done"}, "assignee": {"displayName": "Jane Doe"},
    }}
    monkeypatch.setattr(trackers.requests, "get", lambda url, auth=None, timeout=None: _FakeResponse(200, jira_payload))

    conn = store.connect(":memory:")
    commits = [{"hash": "c1", "message": "DESIGN-77: apply design change request"}]

    trackers.link_commits_to_trackers(conn, commits, str(repo_dir))

    node = store.get_node(conn, "ticket:DESIGN-77")
    assert node is not None
    assert node["attrs"]["status"] == "Done"
    edges = store.get_edges(conn, src_id="commit:c1", dst_id="ticket:DESIGN-77", type="references")
    assert len(edges) == 1


def test_link_commits_is_noop_when_no_tokens_configured(tmp_path, monkeypatch):
    _patch_credentials(monkeypatch)
    repo_dir = _make_repo(tmp_path, "https://github.com/acme/app.git")

    calls = []
    monkeypatch.setattr(trackers.requests, "get", lambda *a, **k: calls.append(1) or _FakeResponse(200, {}))

    conn = store.connect(":memory:")
    commits = [{"hash": "c1", "message": "Migrate project to app router (#456)"}]

    trackers.link_commits_to_trackers(conn, commits, str(repo_dir))

    assert calls == []
    assert store.get_edges(conn, src_id="commit:c1", type="references") == []


def test_link_commits_skips_ref_when_fetch_fails(tmp_path, monkeypatch):
    _patch_credentials(monkeypatch, GITHUB_TOKEN="tok")
    repo_dir = _make_repo(tmp_path, "https://github.com/acme/app.git")

    monkeypatch.setattr(trackers.requests, "get", lambda url, headers=None, timeout=None: _FakeResponse(404))

    conn = store.connect(":memory:")
    commits = [{"hash": "c1", "message": "Migrate project to app router (#456)"}]

    trackers.link_commits_to_trackers(conn, commits, str(repo_dir))

    assert store.get_edges(conn, src_id="commit:c1", type="references") == []


def test_link_commits_resolves_bare_ref_that_is_actually_a_pr(tmp_path, monkeypatch):
    _patch_credentials(monkeypatch, GITHUB_TOKEN="tok")
    repo_dir = _make_repo(tmp_path, "https://github.com/acme/app.git")

    def _fake_get(url, headers=None, timeout=None):
        if "/pulls/" in url:
            return _FakeResponse(200, {"title": "Fix auth bug", "html_url": "u", "merged_at": "t"})
        return _FakeResponse(200, {"title": "Fix auth bug", "pull_request": {"url": "..."}})

    monkeypatch.setattr(trackers.requests, "get", _fake_get)

    conn = store.connect(":memory:")
    commits = [{"hash": "c1", "message": "fixes #42: broken auth flow"}]

    trackers.link_commits_to_trackers(conn, commits, str(repo_dir))

    assert store.get_node(conn, "pr:acme/app:42") is not None
    assert store.get_node(conn, "issue:acme/app:42") is None


def test_trackers_module_never_issues_write_http_requests():
    source = inspect.getsource(trackers)
    for verb in ("post", "put", "patch", "delete"):
        assert f"requests.{verb}(" not in source, f"trackers.py must never call requests.{verb}()"
