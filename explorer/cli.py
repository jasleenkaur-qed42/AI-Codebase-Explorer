import atexit
import json
import os
import time
import webbrowser
from pathlib import Path

import click

from explorer import docs_walker, history_miner, js_ts_parser, linker, parser, queries, risk, store, trackers

IGNORED_DIRS = {
    ".git", ".venv", "__pycache__", ".explorer", "node_modules",
    "dist", "build", ".next",
}

SOURCE_EXTENSIONS = {
    ".py": parser,
    ".js": js_ts_parser,
    ".jsx": js_ts_parser,
    ".ts": js_ts_parser,
    ".tsx": js_ts_parser,
}


_db_path = store.db_path


def _find_source_files(repo_path: str):
    root = Path(repo_path)
    for ext in SOURCE_EXTENSIONS:
        for path in root.rglob(f"*{ext}"):
            if any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
                continue
            yield path


def ingest(repo_path: str):
    conn = store.connect(_db_path(repo_path))
    root = Path(repo_path)

    for file_path in _find_source_files(repo_path):
        rel_path = file_path.relative_to(root).as_posix()
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        module_for_ext = SOURCE_EXTENSIONS["." + rel_path.rsplit(".", 1)[-1]]
        try:
            result = module_for_ext.parse_source(source, path=rel_path)
        except (SyntaxError, ValueError) as exc:
            click.echo(f"warning: skipping unparseable file {rel_path}: {exc}", err=True)
            continue

        for node in result.nodes:
            store.upsert_node(conn, **node)
            if node.get("docstring"):
                store.index_text(conn, "docstrings", node_id=node["id"], text=node["docstring"])
        for edge in result.edges:
            store.upsert_edge(conn, **edge)

        store.upsert_node(conn, id=f"file:{rel_path}", type="file", name=rel_path, path=rel_path)

    linker.resolve_imports_and_calls(conn, repo_path)

    since_commit = store.get_meta(conn, "last_commit")
    try:
        history = history_miner.mine(repo_path, since_commit=since_commit)
    except Exception as exc:  # not a git repo, or no commits yet
        click.echo(f"warning: skipping git history: {exc}", err=True)
        history = None

    if history is not None:
        for author in history.authors:
            store.upsert_node(conn, id=author["id"], type="author", name=author["name"])
        for commit in history.commits:
            store.upsert_node(
                conn, id=commit["id"], type="commit", name=commit["hash"],
                docstring=commit["message"],
            )
            store.upsert_commit(
                conn, hash=commit["hash"], author_id=commit["author_id"],
                timestamp=commit["timestamp"], message=commit["message"],
                files_changed=commit["files_changed"],
            )
            store.index_text(conn, "commit_messages", node_id=commit["id"], text=commit["message"])
            for path in commit["files_changed"]:
                store.upsert_node(conn, id=f"file:{path}", type="file", name=path, path=path)
        for edge in history.edges:
            store.upsert_edge(conn, **edge)
        if history.commits:
            store.set_meta(conn, "last_commit", history.commits[-1]["hash"])

        try:
            trackers.link_commits_to_trackers(conn, history.commits, repo_path)
        except Exception as exc:
            click.echo(f"warning: skipping issue-tracker linking: {exc}", err=True)

    for doc_path in docs_walker.find_doc_files(repo_path):
        rel_path = doc_path.relative_to(root).as_posix()
        text = doc_path.read_text(encoding="utf-8", errors="ignore")
        doc_id = f"doc:{rel_path}"
        store.upsert_node(conn, id=doc_id, type="doc", name=rel_path, path=rel_path)
        store.index_text(conn, "docs", node_id=doc_id, text=text)

    risk.compute_and_store(conn)
    conn.close()


@click.group()
def main():
    pass


@main.command()
@click.argument("repo_path")
def ingest_cmd(repo_path):
    ingest(repo_path)


main.add_command(ingest_cmd, name="ingest")


@main.command()
@click.argument("repo_path")
def stats(repo_path):
    conn = store.connect(_db_path(repo_path))
    click.echo(json.dumps(queries.repo_stats(conn)))


@main.command()
@click.argument("repo_path")
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8420, type=int)
@click.option("--no-browser", is_flag=True, default=False)
def serve(repo_path, host, port, no_browser):
    import uvicorn

    from explorer.web.api import create_app

    app = create_app(repo_path)

    marker_path = Path(_db_path(repo_path)).parent / "serve.json"
    marker_path.write_text(json.dumps({
        "host": host, "port": port, "pid": os.getpid(), "started_at": time.time(),
    }))
    atexit.register(lambda: marker_path.unlink(missing_ok=True))

    if not no_browser:
        webbrowser.open(f"http://{host}:{port}")

    uvicorn.run(app, host=host, port=port)


main.add_command(serve, name="serve")


@main.group()
def query():
    pass


@query.command("callers")
@click.argument("repo_path")
@click.argument("function_id")
@click.option("--max-depth", default=1)
def query_callers(repo_path, function_id, max_depth):
    conn = store.connect(_db_path(repo_path))
    click.echo(json.dumps(queries.callers(conn, function_id, max_depth=max_depth)))


@query.command("callees")
@click.argument("repo_path")
@click.argument("function_id")
@click.option("--max-depth", default=1)
def query_callees(repo_path, function_id, max_depth):
    conn = store.connect(_db_path(repo_path))
    click.echo(json.dumps(queries.callees(conn, function_id, max_depth=max_depth)))


@query.command("churn-hotspots")
@click.argument("repo_path")
@click.option("--top", default=10)
def query_churn_hotspots(repo_path, top):
    conn = store.connect(_db_path(repo_path))
    click.echo(json.dumps(queries.churn_hotspots(conn, top=top)))


@query.command("bus-factor-risk")
@click.argument("repo_path")
@click.option("--top", default=10)
def query_bus_factor_risk(repo_path, top):
    conn = store.connect(_db_path(repo_path))
    click.echo(json.dumps(queries.bus_factor_risk(conn, top=top)))


@query.command("co-change")
@click.argument("repo_path")
@click.argument("file_id")
def query_co_change(repo_path, file_id):
    conn = store.connect(_db_path(repo_path))
    click.echo(json.dumps(queries.co_change(conn, file_id)))


@query.command("authors")
@click.argument("repo_path")
@click.argument("file_id")
def query_authors(repo_path, file_id):
    conn = store.connect(_db_path(repo_path))
    click.echo(json.dumps(queries.authors(conn, file_id)))


@query.command("imports")
@click.argument("repo_path")
@click.argument("module_id")
def query_imports(repo_path, module_id):
    conn = store.connect(_db_path(repo_path))
    click.echo(json.dumps(queries.imports(conn, module_id)))


@query.command("commit-for-ref")
@click.argument("repo_path")
@click.argument("tracker_node_id")
def query_commit_for_ref(repo_path, tracker_node_id):
    conn = store.connect(_db_path(repo_path))
    click.echo(json.dumps(queries.referencing_commits(conn, tracker_node_id)))


@query.command("search")
@click.argument("repo_path")
@click.argument("table")
@click.argument("query_text")
def query_search(repo_path, table, query_text):
    conn = store.connect(_db_path(repo_path))
    click.echo(json.dumps(queries.search(conn, table, query_text)))


if __name__ == "__main__":
    main()
