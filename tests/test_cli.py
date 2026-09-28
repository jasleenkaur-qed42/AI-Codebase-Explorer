import json
import subprocess

from click.testing import CliRunner

from explorer import store
from explorer.cli import main


def _run(repo_dir, *args):
    subprocess.run(["git", *args], cwd=repo_dir, check=True, capture_output=True)


def _make_repo(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _run(repo_dir, "init", "-q")
    _run(repo_dir, "config", "user.email", "jane@example.com")
    _run(repo_dir, "config", "user.name", "Jane")

    (repo_dir / "README.md").write_text("# Demo\nA demo project for testing.")
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


def test_ingest_then_query_churn_hotspots(tmp_path):
    repo_dir = _make_repo(tmp_path)
    runner = CliRunner()

    ingest_result = runner.invoke(main, ["ingest", str(repo_dir)])
    assert ingest_result.exit_code == 0, ingest_result.output

    query_result = runner.invoke(main, ["query", "churn-hotspots", str(repo_dir)])
    assert query_result.exit_code == 0, query_result.output
    data = json.loads(query_result.output)
    assert any(node["path"] == "foo.py" for node in data)


def test_ingest_then_query_callees(tmp_path):
    repo_dir = _make_repo(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["ingest", str(repo_dir)])

    stats = runner.invoke(main, ["query", "search", str(repo_dir), "docstrings", "configuration"])
    assert stats.exit_code == 0, stats.output
    data = json.loads(stats.output)
    assert any(hit["node"]["name"] == "helper" for hit in data)


def test_ingest_parses_tsx_files_and_traces_jsx_composition(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _run(repo_dir, "init", "-q")
    _run(repo_dir, "config", "user.email", "jane@example.com")
    _run(repo_dir, "config", "user.name", "Jane")

    (repo_dir / "page.tsx").write_text(
        "const ReservationForm = () => {\n"
        "  return <div>form</div>;\n"
        "};\n"
        "const Page = () => {\n"
        "  return <ReservationForm />;\n"
        "};\n"
    )
    _run(repo_dir, "add", ".")
    _run(repo_dir, "commit", "-q", "-m", "add page")

    runner = CliRunner()
    ingest_result = runner.invoke(main, ["ingest", str(repo_dir)])
    assert ingest_result.exit_code == 0, ingest_result.output

    db_path = repo_dir / ".explorer" / "graph.db"
    conn = store.connect(str(db_path))
    page_node = store.get_node(conn, "function:page.tsx:Page:4")
    assert page_node is not None
    assert page_node["type"] == "function"

    callees_result = runner.invoke(
        main, ["query", "callees", str(repo_dir), "function:page.tsx:Page:4"]
    )
    assert callees_result.exit_code == 0, callees_result.output
    data = json.loads(callees_result.output)
    assert any(n["name"] == "ReservationForm" for n in data)


def test_ingest_resolves_cross_file_jsx_component_usage(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _run(repo_dir, "init", "-q")
    _run(repo_dir, "config", "user.email", "jane@example.com")
    _run(repo_dir, "config", "user.name", "Jane")

    components_dir = repo_dir / "components"
    components_dir.mkdir()
    (components_dir / "Foo.tsx").write_text(
        "export default function Foo() {\n"
        "  return <div>foo</div>;\n"
        "}\n"
    )
    (repo_dir / "Page.tsx").write_text(
        "import Foo from './components/Foo';\n\n"
        "const Page = () => {\n"
        "  return <Foo />;\n"
        "};\n"
    )
    _run(repo_dir, "add", ".")
    _run(repo_dir, "commit", "-q", "-m", "add page and component")

    runner = CliRunner()
    ingest_result = runner.invoke(main, ["ingest", str(repo_dir)])
    assert ingest_result.exit_code == 0, ingest_result.output

    conn = store.connect(str(repo_dir / ".explorer" / "graph.db"))
    page_id = "function:Page.tsx:Page:3"
    foo_id = "function:components/Foo.tsx:Foo:1"
    calls = store.get_edges(conn, src_id=page_id, type="calls")
    assert calls == [{"src_id": page_id, "dst_id": foo_id, "type": "calls", "attrs": {}}]


def test_ingest_resolves_import_edge_to_local_module_and_query_imports_reports_it(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _run(repo_dir, "init", "-q")
    _run(repo_dir, "config", "user.email", "jane@example.com")
    _run(repo_dir, "config", "user.name", "Jane")

    (repo_dir / "ReservationForm.tsx").write_text(
        "export default function ReservationForm() {\n"
        "  return <div>form</div>;\n"
        "}\n"
    )
    (repo_dir / "ReservationPage.tsx").write_text(
        "import ReservationForm from './ReservationForm';\n\n"
        "const Page = () => {\n"
        "  return <ReservationForm />;\n"
        "};\n"
    )
    _run(repo_dir, "add", ".")
    _run(repo_dir, "commit", "-q", "-m", "add form and page")

    runner = CliRunner()
    ingest_result = runner.invoke(main, ["ingest", str(repo_dir)])
    assert ingest_result.exit_code == 0, ingest_result.output

    result = runner.invoke(main, ["query", "imports", str(repo_dir), "module:ReservationPage.tsx"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert any(n["id"] == "module:ReservationForm.tsx" for n in data)


def test_ingest_links_commit_to_github_pr_and_query_commit_for_ref_reports_it(tmp_path, monkeypatch):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _run(repo_dir, "init", "-q")
    _run(repo_dir, "config", "user.email", "jane@example.com")
    _run(repo_dir, "config", "user.name", "Jane")
    _run(repo_dir, "remote", "add", "origin", "https://github.com/acme/app.git")

    (repo_dir / "app.py").write_text("def route():\n    return 'app router'\n")
    _run(repo_dir, "add", ".")
    _run(repo_dir, "commit", "-q", "-m", "Migrate project to app router (#456)")

    monkeypatch.setattr(
        "explorer.trackers.config.load_tracker_credentials",
        lambda: {"GITHUB_TOKEN": "tok", "JIRA_BASE_URL": None, "JIRA_EMAIL": None, "JIRA_API_TOKEN": None},
    )

    class _FakeResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json_data = json_data

        def json(self):
            return self._json_data

    pr_payload = {
        "title": "Migrate project to app router", "body": "",
        "state": "closed", "html_url": "https://github.com/acme/app/pull/456",
        "merged_at": "2026-01-05T10:00:00Z", "assignee": None,
    }
    monkeypatch.setattr(
        "explorer.trackers.requests.get",
        lambda url, headers=None, timeout=None: _FakeResponse(200, pr_payload),
    )

    runner = CliRunner()
    ingest_result = runner.invoke(main, ["ingest", str(repo_dir)])
    assert ingest_result.exit_code == 0, ingest_result.output

    result = runner.invoke(main, ["query", "commit-for-ref", str(repo_dir), "pr:acme/app:456"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert any("app router" in c["message"] for c in data)

    search_result = runner.invoke(main, ["query", "search", str(repo_dir), "trackers", "router"])
    assert search_result.exit_code == 0, search_result.output
    assert json.loads(search_result.output)


def test_stats_reports_repo_stats_shape(tmp_path):
    repo_dir = _make_repo(tmp_path)
    runner = CliRunner()
    ingest_result = runner.invoke(main, ["ingest", str(repo_dir)])
    assert ingest_result.exit_code == 0, ingest_result.output

    result = runner.invoke(main, ["stats", str(repo_dir)])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["node_counts"]["file"] >= 1
    assert "commit_count" in data
    assert "author_count" in data
    assert any(n["path"] == "foo.py" for n in data["top_churn"])


def test_serve_starts_uvicorn_with_the_app_for_the_repo(tmp_path, monkeypatch):
    repo_dir = _make_repo(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["ingest", str(repo_dir)])

    captured = {}

    def fake_run(app, host, port):
        captured["app"] = app
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr("uvicorn.run", fake_run)
    monkeypatch.setattr("webbrowser.open", lambda url: None)

    result = runner.invoke(main, ["serve", str(repo_dir), "--port", "8888"])

    assert result.exit_code == 0, result.output
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8888
    assert captured["app"].state.repo_path == str(repo_dir)

    marker = repo_dir / ".explorer" / "serve.json"
    assert marker.exists()


def test_ingest_is_idempotent(tmp_path):
    repo_dir = _make_repo(tmp_path)
    runner = CliRunner()

    first = runner.invoke(main, ["ingest", str(repo_dir)])
    second = runner.invoke(main, ["ingest", str(repo_dir)])

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
