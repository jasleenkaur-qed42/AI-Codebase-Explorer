from explorer import store, risk


def _seed(conn):
    store.upsert_node(conn, id="file:foo.py", type="file", name="foo.py", path="foo.py")
    store.upsert_node(conn, id="file:bar.py", type="file", name="bar.py", path="bar.py")

    store.upsert_commit(conn, hash="c1", author_id="author:jane", timestamp=100,
                         message="add foo", files_changed=["foo.py"])
    store.upsert_commit(conn, hash="c2", author_id="author:bob", timestamp=200,
                         message="touch both", files_changed=["foo.py", "bar.py"])

    store.upsert_edge(conn, src_id="commit:c1", dst_id="file:foo.py", type="modifies")
    store.upsert_edge(conn, src_id="commit:c2", dst_id="file:foo.py", type="modifies")
    store.upsert_edge(conn, src_id="commit:c2", dst_id="file:bar.py", type="modifies")
    store.upsert_edge(conn, src_id="commit:c1", dst_id="author:jane", type="authored_by")
    store.upsert_edge(conn, src_id="commit:c2", dst_id="author:bob", type="authored_by")
    store.upsert_edge(conn, src_id="file:foo.py", dst_id="file:bar.py", type="co_changed_with",
                       attrs={"count": 1})


def test_compute_and_store_sets_churn_per_file():
    conn = store.connect(":memory:")
    _seed(conn)

    risk.compute_and_store(conn)

    foo = store.get_node(conn, "file:foo.py")
    bar = store.get_node(conn, "file:bar.py")
    assert foo["attrs"]["churn"] == 2
    assert bar["attrs"]["churn"] == 1


def test_compute_and_store_sets_bus_factor_per_file():
    conn = store.connect(":memory:")
    _seed(conn)

    risk.compute_and_store(conn)

    foo = store.get_node(conn, "file:foo.py")
    bar = store.get_node(conn, "file:bar.py")
    assert foo["attrs"]["bus_factor"] == 2
    assert bar["attrs"]["bus_factor"] == 1


def test_compute_and_store_sets_recency_per_file():
    conn = store.connect(":memory:")
    _seed(conn)

    risk.compute_and_store(conn)

    foo = store.get_node(conn, "file:foo.py")
    assert foo["attrs"]["last_modified"] == 200


def test_compute_and_store_sets_coupling_per_file():
    conn = store.connect(":memory:")
    _seed(conn)

    risk.compute_and_store(conn)

    foo = store.get_node(conn, "file:foo.py")
    assert foo["attrs"]["coupling"] == 1
