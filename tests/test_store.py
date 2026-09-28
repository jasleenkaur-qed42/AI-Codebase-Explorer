from explorer import store


def test_init_schema_creates_empty_nodes_table():
    conn = store.connect(":memory:")
    cur = conn.execute("SELECT COUNT(*) FROM nodes")
    assert cur.fetchone()[0] == 0


def test_upsert_node_then_get_node_returns_it():
    conn = store.connect(":memory:")
    store.upsert_node(
        conn,
        id="function:foo.py:bar:1",
        type="function",
        name="bar",
        path="foo.py",
        start_line=1,
        end_line=3,
        docstring="does bar things",
        attrs={"churn": 2},
    )

    node = store.get_node(conn, "function:foo.py:bar:1")

    assert node["type"] == "function"
    assert node["name"] == "bar"
    assert node["path"] == "foo.py"
    assert node["start_line"] == 1
    assert node["end_line"] == 3
    assert node["docstring"] == "does bar things"
    assert node["attrs"] == {"churn": 2}


def test_upsert_node_twice_updates_instead_of_duplicating():
    conn = store.connect(":memory:")
    store.upsert_node(conn, id="n1", type="function", name="bar", path="foo.py",
                       start_line=1, end_line=3, docstring=None, attrs={"churn": 1})
    store.upsert_node(conn, id="n1", type="function", name="bar", path="foo.py",
                       start_line=1, end_line=3, docstring=None, attrs={"churn": 2})

    count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    node = store.get_node(conn, "n1")

    assert count == 1
    assert node["attrs"] == {"churn": 2}


def test_upsert_edge_then_list_edges_returns_it():
    conn = store.connect(":memory:")
    store.upsert_edge(conn, src_id="a", dst_id="b", type="calls", attrs={"count": 1})

    edges = store.get_edges(conn, src_id="a", type="calls")

    assert len(edges) == 1
    assert edges[0]["src_id"] == "a"
    assert edges[0]["dst_id"] == "b"
    assert edges[0]["type"] == "calls"
    assert edges[0]["attrs"] == {"count": 1}


def test_upsert_edge_twice_merges_attrs_instead_of_duplicating():
    conn = store.connect(":memory:")
    store.upsert_edge(conn, src_id="a", dst_id="b", type="co_changed_with", attrs={"count": 1})
    store.upsert_edge(conn, src_id="a", dst_id="b", type="co_changed_with", attrs={"count": 2})

    edges = store.get_edges(conn, src_id="a", type="co_changed_with")

    assert len(edges) == 1
    assert edges[0]["attrs"] == {"count": 2}


def test_delete_edge_removes_it():
    conn = store.connect(":memory:")
    store.upsert_edge(conn, src_id="a", dst_id="b", type="calls", attrs={"count": 1})

    store.delete_edge(conn, src_id="a", dst_id="b", type="calls")

    assert store.get_edges(conn, src_id="a", type="calls") == []


def test_upsert_commit_then_get_commit_returns_it():
    conn = store.connect(":memory:")
    store.upsert_commit(
        conn,
        hash="abc123",
        author_id="author:jane",
        timestamp=1700000000,
        message="fix bug",
        files_changed=["foo.py", "bar.py"],
    )

    commit = store.get_commit(conn, "abc123")

    assert commit["author_id"] == "author:jane"
    assert commit["timestamp"] == 1700000000
    assert commit["message"] == "fix bug"
    assert commit["files_changed"] == ["foo.py", "bar.py"]


def test_meta_set_and_get_roundtrip():
    conn = store.connect(":memory:")
    assert store.get_meta(conn, "last_commit") is None

    store.set_meta(conn, "last_commit", "abc123")

    assert store.get_meta(conn, "last_commit") == "abc123"


def test_fts_index_and_search_finds_matching_text():
    conn = store.connect(":memory:")
    store.index_text(conn, "docstrings", node_id="function:foo.py:bar:1",
                      text="parses configuration files from disk")
    store.index_text(conn, "docstrings", node_id="function:foo.py:baz:1",
                      text="sends an email notification")

    results = store.search_fts(conn, "docstrings", "configuration")

    assert len(results) == 1
    assert results[0]["node_id"] == "function:foo.py:bar:1"
