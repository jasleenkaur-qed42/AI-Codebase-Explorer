import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    path TEXT,
    start_line INTEGER,
    end_line INTEGER,
    docstring TEXT,
    attrs TEXT
);

CREATE TABLE IF NOT EXISTS edges (
    src_id TEXT NOT NULL,
    dst_id TEXT NOT NULL,
    type TEXT NOT NULL,
    attrs TEXT,
    PRIMARY KEY (src_id, dst_id, type)
);

CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src_id, type);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst_id, type);

CREATE TABLE IF NOT EXISTS commits (
    hash TEXT PRIMARY KEY,
    author_id TEXT,
    timestamp INTEGER,
    message TEXT,
    files_changed TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS docstrings_fts USING fts5(node_id UNINDEXED, text);
CREATE VIRTUAL TABLE IF NOT EXISTS commit_messages_fts USING fts5(node_id UNINDEXED, text);
CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(node_id UNINDEXED, text);
CREATE VIRTUAL TABLE IF NOT EXISTS trackers_fts USING fts5(node_id UNINDEXED, text);
"""

FTS_TABLES = {
    "docstrings": "docstrings_fts",
    "commit_messages": "commit_messages_fts",
    "docs": "docs_fts",
    "trackers": "trackers_fts",
}


def db_path(repo_path: str) -> str:
    explorer_dir = Path(repo_path) / ".explorer"
    explorer_dir.mkdir(parents=True, exist_ok=True)
    return str(explorer_dir / "graph.db")


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def upsert_node(conn, id, type, name, path=None, start_line=None,
                 end_line=None, docstring=None, attrs=None):
    conn.execute(
        """
        INSERT INTO nodes (id, type, name, path, start_line, end_line, docstring, attrs)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            type=excluded.type,
            name=excluded.name,
            path=excluded.path,
            start_line=excluded.start_line,
            end_line=excluded.end_line,
            docstring=excluded.docstring,
            attrs=excluded.attrs
        """,
        (id, type, name, path, start_line, end_line, docstring,
         json.dumps(attrs or {})),
    )
    conn.commit()


def get_node(conn, id):
    row = conn.execute(
        "SELECT id, type, name, path, start_line, end_line, docstring, attrs "
        "FROM nodes WHERE id = ?",
        (id,),
    ).fetchone()
    if row is None:
        return None
    keys = ["id", "type", "name", "path", "start_line", "end_line", "docstring", "attrs"]
    node = dict(zip(keys, row))
    node["attrs"] = json.loads(node["attrs"]) if node["attrs"] else {}
    return node


def upsert_edge(conn, src_id, dst_id, type, attrs=None):
    conn.execute(
        """
        INSERT INTO edges (src_id, dst_id, type, attrs)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(src_id, dst_id, type) DO UPDATE SET
            attrs=excluded.attrs
        """,
        (src_id, dst_id, type, json.dumps(attrs or {})),
    )
    conn.commit()


def get_edges(conn, src_id=None, dst_id=None, type=None):
    clauses = []
    params = []
    if src_id is not None:
        clauses.append("src_id = ?")
        params.append(src_id)
    if dst_id is not None:
        clauses.append("dst_id = ?")
        params.append(dst_id)
    if type is not None:
        clauses.append("type = ?")
        params.append(type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT src_id, dst_id, type, attrs FROM edges {where}", params
    ).fetchall()
    edges = []
    for src, dst, etype, attrs in rows:
        edges.append({
            "src_id": src,
            "dst_id": dst,
            "type": etype,
            "attrs": json.loads(attrs) if attrs else {},
        })
    return edges


def delete_edge(conn, src_id, dst_id, type):
    conn.execute(
        "DELETE FROM edges WHERE src_id = ? AND dst_id = ? AND type = ?",
        (src_id, dst_id, type),
    )
    conn.commit()


def upsert_commit(conn, hash, author_id, timestamp, message, files_changed):
    conn.execute(
        """
        INSERT INTO commits (hash, author_id, timestamp, message, files_changed)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(hash) DO UPDATE SET
            author_id=excluded.author_id,
            timestamp=excluded.timestamp,
            message=excluded.message,
            files_changed=excluded.files_changed
        """,
        (hash, author_id, timestamp, message, json.dumps(files_changed or [])),
    )
    conn.commit()


def get_commit(conn, hash):
    row = conn.execute(
        "SELECT hash, author_id, timestamp, message, files_changed "
        "FROM commits WHERE hash = ?",
        (hash,),
    ).fetchone()
    if row is None:
        return None
    keys = ["hash", "author_id", "timestamp", "message", "files_changed"]
    commit = dict(zip(keys, row))
    commit["files_changed"] = json.loads(commit["files_changed"]) if commit["files_changed"] else []
    return commit


def set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def get_meta(conn, key):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def index_text(conn, table, node_id, text):
    fts_table = FTS_TABLES[table]
    conn.execute(f"INSERT INTO {fts_table} (node_id, text) VALUES (?, ?)", (node_id, text))
    conn.commit()


def search_fts(conn, table, query, limit=20):
    fts_table = FTS_TABLES[table]
    rows = conn.execute(
        f"SELECT node_id, text FROM {fts_table} WHERE text MATCH ? "
        f"ORDER BY rank LIMIT ?",
        (query, limit),
    ).fetchall()
    return [{"node_id": node_id, "text": text} for node_id, text in rows]
