import subprocess

import pytest
from fastapi.testclient import TestClient

from explorer import store
from explorer.web.api import create_app


def _run(repo_dir, *args):
    subprocess.run(["git", *args], cwd=repo_dir, check=True, capture_output=True)


def _make_repo(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _run(repo_dir, "init", "-q")
    _run(repo_dir, "config", "user.email", "jane@example.com")
    _run(repo_dir, "config", "user.name", "Jane")
    (repo_dir / "foo.py").write_text(
        'def helper():\n'
        '    """Parses configuration files."""\n'
        '    return 1\n\n'
        'def main():\n'
        '    return helper()\n'
    )
    _run(repo_dir, "add", ".")
    _run(repo_dir, "commit", "-q", "-m", "initial commit")
    return repo_dir


@pytest.fixture
def client(tmp_path):
    from explorer.cli import ingest
    repo_dir = _make_repo(tmp_path)
    ingest(str(repo_dir))
    app = create_app(str(repo_dir))
    return TestClient(app)


def test_repo_stats_endpoint_returns_repo_stats_shape(client):
    response = client.get("/api/repo/stats")

    assert response.status_code == 200
    data = response.json()
    assert "node_counts" in data
    assert "top_churn" in data


def test_node_endpoint_returns_node_detail_for_known_node(client):
    response = client.get("/api/node", params={"id": "function:foo.py:helper:1"})

    assert response.status_code == 200
    data = response.json()
    assert data["node"]["id"] == "function:foo.py:helper:1"
    assert "calls" in data
    assert "called_by" in data
    assert "modified_by" in data
    assert "authors" in data


def test_node_endpoint_404s_for_unknown_node(client):
    response = client.get("/api/node", params={"id": "function:does-not-exist"})

    assert response.status_code == 404


def test_graph_overview_endpoint_returns_nodes_and_edges(client):
    response = client.get("/api/graph/overview")

    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data
    assert "truncated" in data


def test_graph_endpoint_expands_around_a_node(client):
    response = client.get(
        "/api/graph", params={"node_id": "function:foo.py:main:5", "depth": 1}
    )

    assert response.status_code == 200
    data = response.json()
    assert any(n["id"] == "function:foo.py:helper:1" for n in data["nodes"])


def test_search_endpoint_returns_matches(client):
    response = client.get(
        "/api/search", params={"table": "docstrings", "q": "configuration"}
    )

    assert response.status_code == 200
    data = response.json()
    assert any(hit["node"]["name"] == "helper" for hit in data)


def test_session_explain_endpoint_publishes_event_and_stream_receives_it(client):
    payload = {
        "question": "What does helper do?",
        "answer_markdown": "It parses configuration files.",
        "node_ids": ["function:foo.py:helper:1"],
        "tools_invoked": [
            {"command": "query search", "args": ["docstrings", "configuration"], "summary": "1 hit"}
        ],
    }

    response = client.post("/api/session/explain", json=payload)

    assert response.status_code == 200
    events = client.app.state.events.recent()
    assert events[-1]["question"] == "What does helper do?"
    assert events[-1]["tools_invoked"][0]["command"] == "query search"


def test_search_symbols_endpoint_matches_node_names(client):
    response = client.get("/api/search/symbols", params={"q": "helper"})

    assert response.status_code == 200
    data = response.json()
    assert any(n["name"] == "helper" for n in data)


def test_path_endpoint_returns_shortest_path_between_two_nodes(client):
    response = client.get(
        "/api/path",
        params={"from": "function:foo.py:main:5", "to": "function:foo.py:helper:1"},
    )

    assert response.status_code == 200
    data = response.json()
    assert [n["id"] for n in data["nodes"]] == [
        "function:foo.py:main:5", "function:foo.py:helper:1",
    ]


def test_path_endpoint_404s_when_unreachable(client):
    response = client.get(
        "/api/path",
        params={"from": "function:foo.py:main:5", "to": "function:does-not-exist"},
    )

    assert response.status_code == 404


def test_session_explain_endpoint_rejects_malformed_body(client):
    response = client.post("/api/session/explain", json={"question": "missing fields"})

    assert response.status_code == 422


def test_graph_session_endpoint_returns_subgraph_for_cited_nodes(client):
    response = client.get(
        "/api/graph/session", params={"node_ids": "function:foo.py:helper:1"}
    )

    assert response.status_code == 200
    data = response.json()
    assert any(n["id"] == "function:foo.py:helper:1" for n in data["nodes"])
    assert "edges" in data


def test_session_explain_endpoint_accepts_node_citations_with_role(client):
    payload = {
        "question": "What does helper do?",
        "answer_markdown": "It parses configuration files.",
        "node_ids": [
            {"id": "function:foo.py:helper:1", "role": "primary"},
            {"id": "file:foo.py", "role": "supporting"},
        ],
    }

    response = client.post("/api/session/explain", json=payload)

    assert response.status_code == 200
    event = client.app.state.events.recent()[-1]
    assert {"id": "function:foo.py:helper:1", "role": "primary"} in event["node_ids"]
    assert {"id": "file:foo.py", "role": "supporting"} in event["node_ids"]


def test_session_explain_endpoint_normalizes_plain_string_node_ids_to_primary(client):
    payload = {
        "question": "What does helper do?",
        "answer_markdown": "It parses configuration files.",
        "node_ids": ["function:foo.py:helper:1"],
    }

    response = client.post("/api/session/explain", json=payload)

    assert response.status_code == 200
    event = client.app.state.events.recent()[-1]
    assert event["node_ids"] == [{"id": "function:foo.py:helper:1", "role": "primary"}]


def test_graph_session_endpoint_excludes_commits_for_supporting_ids(client):
    response = client.get(
        "/api/graph/session", params={"supporting_ids": "file:foo.py"}
    )

    assert response.status_code == 200
    data = response.json()
    node_ids = {n["id"] for n in data["nodes"]}
    assert "file:foo.py" in node_ids
    assert not any(n["type"] == "commit" for n in data["nodes"])


def test_graph_session_endpoint_returns_empty_for_no_node_ids(client):
    response = client.get("/api/graph/session", params={"node_ids": ""})

    assert response.status_code == 200
    assert response.json() == {"nodes": [], "edges": []}


def test_repo_remote_endpoint_returns_github_base_for_github_remote(tmp_path):
    from explorer.cli import ingest

    repo_dir = _make_repo(tmp_path)
    _run(repo_dir, "remote", "add", "origin", "https://github.com/acme/app.git")
    ingest(str(repo_dir))
    app = create_app(str(repo_dir))
    local_client = TestClient(app)

    response = local_client.get("/api/repo/remote")

    assert response.status_code == 200
    assert response.json() == {"github_base": "https://github.com/acme/app"}


def test_repo_remote_endpoint_returns_null_when_no_github_remote(client):
    response = client.get("/api/repo/remote")

    assert response.status_code == 200
    assert response.json() == {"github_base": None}
