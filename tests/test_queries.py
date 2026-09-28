from explorer import store, queries


def _seed_call_chain(conn):
    # a -> b -> c
    for name in ("a", "b", "c"):
        store.upsert_node(conn, id=f"function:{name}", type="function", name=name, path="mod.py")
    store.upsert_edge(conn, src_id="function:a", dst_id="function:b", type="calls")
    store.upsert_edge(conn, src_id="function:b", dst_id="function:c", type="calls")


def test_callees_returns_direct_callees():
    conn = store.connect(":memory:")
    _seed_call_chain(conn)

    result = queries.callees(conn, "function:a", max_depth=1)

    assert [n["id"] for n in result] == ["function:b"]


def test_callees_respects_max_depth_for_transitive_calls():
    conn = store.connect(":memory:")
    _seed_call_chain(conn)

    result = queries.callees(conn, "function:a", max_depth=2)

    assert {n["id"] for n in result} == {"function:b", "function:c"}


def test_callers_returns_functions_that_call_the_target():
    conn = store.connect(":memory:")
    _seed_call_chain(conn)

    result = queries.callers(conn, "function:c", max_depth=2)

    assert {n["id"] for n in result} == {"function:a", "function:b"}


def test_churn_hotspots_ranks_files_by_churn_descending():
    conn = store.connect(":memory:")
    store.upsert_node(conn, id="file:hot.py", type="file", name="hot.py", path="hot.py",
                       attrs={"churn": 10})
    store.upsert_node(conn, id="file:cold.py", type="file", name="cold.py", path="cold.py",
                       attrs={"churn": 1})

    result = queries.churn_hotspots(conn, top=10)

    assert [n["id"] for n in result] == ["file:hot.py", "file:cold.py"]


def test_bus_factor_risk_ranks_low_bus_factor_high_churn_first():
    conn = store.connect(":memory:")
    store.upsert_node(conn, id="file:risky.py", type="file", name="risky.py", path="risky.py",
                       attrs={"churn": 10, "bus_factor": 1})
    store.upsert_node(conn, id="file:safe.py", type="file", name="safe.py", path="safe.py",
                       attrs={"churn": 10, "bus_factor": 5})

    result = queries.bus_factor_risk(conn, top=10)

    assert [n["id"] for n in result] == ["file:risky.py", "file:safe.py"]


def test_co_change_returns_coupled_files():
    conn = store.connect(":memory:")
    store.upsert_node(conn, id="file:a.py", type="file", name="a.py", path="a.py")
    store.upsert_node(conn, id="file:b.py", type="file", name="b.py", path="b.py")
    store.upsert_edge(conn, src_id="file:a.py", dst_id="file:b.py", type="co_changed_with",
                       attrs={"count": 3})

    result = queries.co_change(conn, "file:a.py")

    assert len(result) == 1
    assert result[0]["node"]["id"] == "file:b.py"
    assert result[0]["count"] == 3


def test_authors_returns_distinct_authors_of_a_file():
    conn = store.connect(":memory:")
    store.upsert_node(conn, id="author:jane", type="author", name="Jane")
    store.upsert_commit(conn, hash="c1", author_id="author:jane", timestamp=100,
                         message="add", files_changed=["a.py"])
    store.upsert_edge(conn, src_id="commit:c1", dst_id="file:a.py", type="modifies")

    result = queries.authors(conn, "file:a.py")

    assert [a["id"] for a in result] == ["author:jane"]


def test_referencing_commits_returns_commits_that_reference_a_tracker_node():
    conn = store.connect(":memory:")
    store.upsert_node(conn, id="author:jane", type="author", name="Jane")
    store.upsert_node(conn, id="pr:acme/app:456", type="pr", name="Migrate project to app router",
                       attrs={"merged_at": "2026-01-05T10:00:00Z", "state": "merged"})
    store.upsert_commit(conn, hash="c1", author_id="author:jane", timestamp=1000,
                         message="Migrate project to app router (#456)", files_changed=["a.py"])
    store.upsert_edge(conn, src_id="commit:c1", dst_id="pr:acme/app:456", type="references")

    result = queries.referencing_commits(conn, "pr:acme/app:456")

    assert len(result) == 1
    assert result[0]["hash"] == "c1"
    assert result[0]["message"] == "Migrate project to app router (#456)"


def test_referencing_commits_returns_empty_when_nothing_references_the_tracker_node():
    conn = store.connect(":memory:")
    store.upsert_node(conn, id="ticket:DESIGN-77", type="ticket", name="Design change request")

    result = queries.referencing_commits(conn, "ticket:DESIGN-77")

    assert result == []


def test_imports_returns_resolved_local_module_nodes():
    conn = store.connect(":memory:")
    store.upsert_node(conn, id="module:page.tsx", type="module", name="page.tsx", path="page.tsx")
    store.upsert_node(conn, id="module:form.tsx", type="module", name="form.tsx", path="form.tsx")
    store.upsert_edge(conn, src_id="module:page.tsx", dst_id="module:form.tsx", type="imports")

    result = queries.imports(conn, "module:page.tsx")

    assert [n["id"] for n in result] == ["module:form.tsx"]


def test_imports_reports_unresolved_external_packages_as_external_placeholder():
    conn = store.connect(":memory:")
    store.upsert_node(conn, id="module:page.tsx", type="module", name="page.tsx", path="page.tsx")
    store.upsert_edge(conn, src_id="module:page.tsx", dst_id="external:react", type="imports")

    result = queries.imports(conn, "module:page.tsx")

    assert result == [{"id": "external:react", "type": "external"}]


def test_search_joins_fts_results_with_node_metadata():
    conn = store.connect(":memory:")
    store.upsert_node(conn, id="function:foo", type="function", name="foo", path="foo.py")
    store.index_text(conn, "docstrings", node_id="function:foo", text="parses configuration files")

    result = queries.search(conn, "docstrings", "configuration")

    assert len(result) == 1
    assert result[0]["node"]["id"] == "function:foo"
    assert result[0]["text"] == "parses configuration files"


def _seed_node_detail_fixture(conn):
    store.upsert_node(conn, id="function:foo", type="function", name="foo", path="mod.py",
                       start_line=1, end_line=5)
    store.upsert_node(conn, id="function:bar", type="function", name="bar", path="mod.py",
                       start_line=7, end_line=9)
    store.upsert_edge(conn, src_id="function:foo", dst_id="function:bar", type="calls")
    store.upsert_node(conn, id="file:mod.py", type="file", name="mod.py", path="mod.py")
    store.upsert_node(conn, id="author:jane", type="author", name="Jane")
    store.upsert_commit(conn, hash="c1", author_id="author:jane", timestamp=100,
                         message="add mod", files_changed=["mod.py"])
    store.upsert_edge(conn, src_id="commit:c1", dst_id="file:mod.py", type="modifies")


def test_node_detail_returns_none_for_unknown_node():
    conn = store.connect(":memory:")

    assert queries.node_detail(conn, "function:missing") is None


def test_node_detail_bundles_node_calls_called_by_modified_by_and_authors():
    conn = store.connect(":memory:")
    _seed_node_detail_fixture(conn)

    result = queries.node_detail(conn, "function:foo")

    assert result["node"]["id"] == "function:foo"
    assert [n["id"] for n in result["calls"]] == ["function:bar"]
    assert result["called_by"] == []
    assert result["modified_by"]["commit_count"] == 1
    assert result["modified_by"]["commits"][0]["hash"] == "c1"
    assert [a["id"] for a in result["authors"]] == ["author:jane"]


def test_node_detail_for_a_file_node_uses_its_own_id_for_modifies_and_authors():
    conn = store.connect(":memory:")
    _seed_node_detail_fixture(conn)

    result = queries.node_detail(conn, "file:mod.py")

    assert result["modified_by"]["commit_count"] == 1
    assert [a["id"] for a in result["authors"]] == ["author:jane"]


def test_repo_stats_reports_counts_and_top_risk_lists():
    conn = store.connect(":memory:")
    store.upsert_node(conn, id="file:hot.py", type="file", name="hot.py", path="hot.py",
                       attrs={"churn": 10, "bus_factor": 1})
    store.upsert_node(conn, id="function:foo", type="function", name="foo", path="hot.py")
    store.upsert_node(conn, id="author:jane", type="author", name="Jane")
    store.upsert_commit(conn, hash="c1", author_id="author:jane", timestamp=100,
                         message="add", files_changed=["hot.py"])
    store.upsert_edge(conn, src_id="function:foo", dst_id="function:foo", type="calls")

    result = queries.repo_stats(conn)

    assert result["node_counts"]["file"] == 1
    assert result["node_counts"]["function"] == 1
    assert result["node_counts"]["author"] == 1
    assert result["edge_counts"]["calls"] == 1
    assert result["commit_count"] == 1
    assert result["author_count"] == 1
    assert [n["id"] for n in result["top_churn"]] == ["file:hot.py"]
    assert [n["id"] for n in result["top_bus_factor_risk"]] == ["file:hot.py"]


def _seed_mixed_edge_graph(conn):
    for name in ("a", "b", "c", "d"):
        store.upsert_node(conn, id=f"function:{name}", type="function", name=name, path="mod.py")
    store.upsert_edge(conn, src_id="function:a", dst_id="function:b", type="calls")
    store.upsert_edge(conn, src_id="function:b", dst_id="function:c", type="calls")
    store.upsert_edge(conn, src_id="function:a", dst_id="function:d", type="imports")


def test_graph_around_returns_nodes_and_edges_within_depth():
    conn = store.connect(":memory:")
    _seed_mixed_edge_graph(conn)

    result = queries.graph_around(conn, "function:a", depth=1)

    assert {n["id"] for n in result["nodes"]} == {"function:a", "function:b", "function:d"}
    assert {(e["src_id"], e["dst_id"], e["type"]) for e in result["edges"]} == {
        ("function:a", "function:b", "calls"),
        ("function:a", "function:d", "imports"),
    }


def test_graph_around_expands_to_further_depth():
    conn = store.connect(":memory:")
    _seed_mixed_edge_graph(conn)

    result = queries.graph_around(conn, "function:a", depth=2)

    assert {n["id"] for n in result["nodes"]} == {
        "function:a", "function:b", "function:c", "function:d",
    }


def test_graph_around_filters_by_edge_type():
    conn = store.connect(":memory:")
    _seed_mixed_edge_graph(conn)

    result = queries.graph_around(conn, "function:a", depth=1, edge_types=["calls"])

    assert {n["id"] for n in result["nodes"]} == {"function:a", "function:b"}


def _seed_session_graph_fixture(conn):
    # two files, each touched by its own commit -- plus one commit that
    # touches BOTH files, to prove unrelated files from a shared commit
    # don't leak into a single-file query.
    store.upsert_node(conn, id="file:auth.py", type="file", name="auth.py", path="auth.py")
    store.upsert_node(conn, id="file:unrelated.py", type="file", name="unrelated.py",
                       path="unrelated.py")
    store.upsert_node(conn, id="function:login", type="function", name="login", path="auth.py")
    store.upsert_edge(conn, src_id="function:login", dst_id="file:auth.py", type="contains")

    store.upsert_node(conn, id="author:jane", type="author", name="Jane")
    store.upsert_commit(conn, hash="c1", author_id="author:jane", timestamp=100,
                         message="add auth", files_changed=["auth.py"])
    store.upsert_node(conn, id="commit:c1", type="commit", name="c1", docstring="add auth")
    store.upsert_edge(conn, src_id="commit:c1", dst_id="author:jane", type="authored_by")
    store.upsert_edge(conn, src_id="commit:c1", dst_id="file:auth.py", type="modifies")

    store.upsert_node(conn, id="author:bob", type="author", name="Bob")
    store.upsert_commit(conn, hash="c2", author_id="author:bob", timestamp=200,
                         message="auth + unrelated cleanup",
                         files_changed=["auth.py", "unrelated.py"])
    store.upsert_node(conn, id="commit:c2", type="commit", name="c2",
                       docstring="auth + unrelated cleanup")
    store.upsert_edge(conn, src_id="commit:c2", dst_id="author:bob", type="authored_by")
    store.upsert_edge(conn, src_id="commit:c2", dst_id="file:auth.py", type="modifies")
    store.upsert_edge(conn, src_id="commit:c2", dst_id="file:unrelated.py", type="modifies")


def test_session_graph_includes_cited_nodes_and_their_commits_and_authors():
    conn = store.connect(":memory:")
    _seed_session_graph_fixture(conn)

    result = queries.session_graph(conn, ["file:auth.py"])

    node_ids = {n["id"] for n in result["nodes"]}
    assert node_ids == {"file:auth.py", "commit:c1", "commit:c2", "author:jane", "author:bob"}


def test_session_graph_excludes_files_from_a_shared_commit_that_were_not_cited():
    conn = store.connect(":memory:")
    _seed_session_graph_fixture(conn)

    result = queries.session_graph(conn, ["file:auth.py"])

    node_ids = {n["id"] for n in result["nodes"]}
    assert "file:unrelated.py" not in node_ids
    edge_dsts = {(e["src_id"], e["dst_id"], e["type"]) for e in result["edges"]}
    assert ("commit:c2", "file:unrelated.py", "modifies") not in edge_dsts


def test_session_graph_includes_structural_edges_between_two_cited_nodes():
    conn = store.connect(":memory:")
    _seed_session_graph_fixture(conn)

    result = queries.session_graph(conn, ["function:login", "file:auth.py"])

    edge_tuples = {(e["src_id"], e["dst_id"], e["type"]) for e in result["edges"]}
    assert ("function:login", "file:auth.py", "contains") in edge_tuples


def test_session_graph_resolves_a_symbol_node_to_its_containing_files_commits():
    conn = store.connect(":memory:")
    _seed_session_graph_fixture(conn)

    result = queries.session_graph(conn, ["function:login"])

    node_ids = {n["id"] for n in result["nodes"]}
    assert {"commit:c1", "commit:c2", "author:jane", "author:bob"} <= node_ids


def test_session_graph_skips_unknown_node_ids():
    conn = store.connect(":memory:")
    _seed_session_graph_fixture(conn)

    result = queries.session_graph(conn, ["file:auth.py", "file:does-not-exist"])

    assert {n["id"] for n in result["nodes"]} >= {"file:auth.py"}
    assert not any(n["id"] == "file:does-not-exist" for n in result["nodes"])


def test_session_graph_does_not_duplicate_a_cited_module_as_a_separate_file_node():
    # A source file gets both a "module:" node (import graph) and a "file:"
    # node (git history/churn) at ingest time -- see explorer/cli.py. Citing
    # the module must not also surface the file: node as a second,
    # visually-identical entry for the same path.
    conn = store.connect(":memory:")
    store.upsert_node(conn, id="module:app.py", type="module", name="app.py", path="app.py")
    store.upsert_node(conn, id="file:app.py", type="file", name="app.py", path="app.py")

    result = queries.session_graph(conn, ["module:app.py"])

    app_py_nodes = [n for n in result["nodes"] if n.get("path") == "app.py"]
    assert len(app_py_nodes) == 1
    assert app_py_nodes[0]["id"] == "module:app.py"


def test_session_graph_returns_empty_for_no_node_ids():
    conn = store.connect(":memory:")
    _seed_session_graph_fixture(conn)

    result = queries.session_graph(conn, [])

    assert result == {"nodes": [], "edges": []}


def test_session_graph_excludes_commits_with_low_cited_file_overlap_ratio():
    # A broad commit that happens to touch the cited file among many unrelated
    # ones (e.g. a big merge) should not be surfaced as "related" -- only 1 of
    # its 10 files is cited, well below the relevance threshold.
    conn = store.connect(":memory:")
    store.upsert_node(conn, id="file:auth.py", type="file", name="auth.py", path="auth.py")
    store.upsert_node(conn, id="author:jane", type="author", name="Jane")
    files = ["auth.py"] + [f"other{i}.py" for i in range(9)]
    store.upsert_commit(conn, hash="broad", author_id="author:jane", timestamp=100,
                         message="broad merge", files_changed=files)
    store.upsert_node(conn, id="commit:broad", type="commit", name="broad")
    store.upsert_edge(conn, src_id="commit:broad", dst_id="author:jane", type="authored_by")
    store.upsert_edge(conn, src_id="commit:broad", dst_id="file:auth.py", type="modifies")

    result = queries.session_graph(conn, ["file:auth.py"])

    assert "commit:broad" not in {n["id"] for n in result["nodes"]}


def test_session_graph_keeps_commits_with_high_cited_file_overlap_ratio():
    conn = store.connect(":memory:")
    store.upsert_node(conn, id="file:auth.py", type="file", name="auth.py", path="auth.py")
    store.upsert_node(conn, id="author:jane", type="author", name="Jane")
    store.upsert_commit(conn, hash="focused", author_id="author:jane", timestamp=100,
                         message="auth fix", files_changed=["auth.py"])
    store.upsert_node(conn, id="commit:focused", type="commit", name="focused")
    store.upsert_edge(conn, src_id="commit:focused", dst_id="author:jane", type="authored_by")
    store.upsert_edge(conn, src_id="commit:focused", dst_id="file:auth.py", type="modifies")

    result = queries.session_graph(conn, ["file:auth.py"])

    assert "commit:focused" in {n["id"] for n in result["nodes"]}


def test_session_graph_excludes_commit_history_for_supporting_nodes():
    # A node cited only as supporting context (e.g. README.md documenting an
    # env var, not the actual subject of the question) should still appear as
    # a node, but its commit history shouldn't be pulled in at all.
    conn = store.connect(":memory:")
    _seed_session_graph_fixture(conn)

    result = queries.session_graph(conn, [{"id": "file:auth.py", "role": "supporting"}])

    node_ids = {n["id"] for n in result["nodes"]}
    assert "file:auth.py" in node_ids
    assert "commit:c1" not in node_ids
    assert "commit:c2" not in node_ids


def test_session_graph_keeps_commit_surfacing_for_primary_nodes_in_mixed_citation():
    conn = store.connect(":memory:")
    _seed_session_graph_fixture(conn)

    result = queries.session_graph(
        conn,
        [
            {"id": "file:auth.py", "role": "primary"},
            {"id": "file:unrelated.py", "role": "supporting"},
        ],
    )

    node_ids = {n["id"] for n in result["nodes"]}
    assert "commit:c1" in node_ids
    assert "file:unrelated.py" in node_ids


def test_session_graph_treats_plain_string_ids_as_primary_for_backward_compatibility():
    conn = store.connect(":memory:")
    _seed_session_graph_fixture(conn)

    result = queries.session_graph(conn, ["file:auth.py"])

    assert "commit:c1" in {n["id"] for n in result["nodes"]}


def test_session_graph_caps_related_commits_per_cited_file_to_most_recent():
    # A high-churn cited file (e.g. README.md) shouldn't flood the result with
    # every commit it ever received -- only the most recent few per file.
    conn = store.connect(":memory:")
    store.upsert_node(conn, id="file:readme.md", type="file", name="readme.md", path="readme.md")
    store.upsert_node(conn, id="author:jane", type="author", name="Jane")
    for i in range(8):
        h = f"c{i}"
        store.upsert_commit(conn, hash=h, author_id="author:jane", timestamp=i,
                             message=f"edit {i}", files_changed=["readme.md"])
        store.upsert_node(conn, id=f"commit:{h}", type="commit", name=h)
        store.upsert_edge(conn, src_id=f"commit:{h}", dst_id="author:jane", type="authored_by")
        store.upsert_edge(conn, src_id=f"commit:{h}", dst_id="file:readme.md", type="modifies")

    result = queries.session_graph(conn, ["file:readme.md"])

    commit_ids = {n["id"] for n in result["nodes"] if n["type"] == "commit"}
    assert commit_ids == {"commit:c3", "commit:c4", "commit:c5", "commit:c6", "commit:c7"}


def test_session_graph_includes_author_of_a_directly_cited_commit():
    # A commit can itself be cited as evidence in an answer (e.g. "the merge
    # commit that implemented X"), not just discovered via a primary file's
    # modifies edges. Its author should still be surfaced -- commit nodes
    # have no path, so they were falling through the file-based
    # author-attachment loop entirely.
    conn = store.connect(":memory:")
    _seed_session_graph_fixture(conn)

    result = queries.session_graph(conn, ["commit:c1"])

    node_ids = {n["id"] for n in result["nodes"]}
    assert "author:jane" in node_ids
    edge_tuples = {(e["src_id"], e["dst_id"], e["type"]) for e in result["edges"]}
    assert ("commit:c1", "author:jane", "authored_by") in edge_tuples


def test_graph_overview_seeds_from_top_churn_files():
    conn = store.connect(":memory:")
    store.upsert_node(conn, id="file:hot.py", type="file", name="hot.py", path="hot.py",
                       attrs={"churn": 10})
    store.upsert_node(conn, id="file:cold.py", type="file", name="cold.py", path="cold.py",
                       attrs={"churn": 0})
    store.upsert_edge(conn, src_id="file:hot.py", dst_id="file:cold.py", type="co_changed_with",
                       attrs={"count": 1})

    result = queries.graph_overview(conn, seed_limit=1, depth=1)

    assert {n["id"] for n in result["nodes"]} == {"file:hot.py", "file:cold.py"}
    assert result["truncated"] is False


def test_graph_overview_includes_functions_and_classes_defined_in_seed_files():
    conn = store.connect(":memory:")
    store.upsert_node(conn, id="file:hot.py", type="file", name="hot.py", path="hot.py",
                       attrs={"churn": 10})
    store.upsert_node(conn, id="function:hot.py:foo:1", type="function", name="foo", path="hot.py")
    store.upsert_node(conn, id="class:hot.py:Bar:5", type="class", name="Bar", path="hot.py")
    store.upsert_edge(conn, src_id="function:hot.py:foo:1", dst_id="class:hot.py:Bar:5", type="calls")

    result = queries.graph_overview(conn, seed_limit=1, depth=1)

    node_ids = {n["id"] for n in result["nodes"]}
    assert "function:hot.py:foo:1" in node_ids
    assert "class:hot.py:Bar:5" in node_ids


def test_graph_overview_truncates_when_over_max_nodes():
    conn = store.connect(":memory:")
    for i in range(5):
        store.upsert_node(conn, id=f"file:f{i}.py", type="file", name=f"f{i}.py", path=f"f{i}.py",
                           attrs={"churn": 5 - i})

    result = queries.graph_overview(conn, seed_limit=5, depth=0, max_nodes=2)

    assert len(result["nodes"]) == 2
    assert result["truncated"] is True


def _seed_path_chain(conn):
    # a -calls-> b -imports-> c, plus an unrelated d
    for name in ("a", "b", "c", "d"):
        store.upsert_node(conn, id=f"function:{name}", type="function", name=name, path="mod.py")
    store.upsert_edge(conn, src_id="function:a", dst_id="function:b", type="calls")
    store.upsert_edge(conn, src_id="function:b", dst_id="function:c", type="imports")


def test_shortest_path_returns_ordered_nodes_and_connecting_edges():
    conn = store.connect(":memory:")
    _seed_path_chain(conn)

    result = queries.shortest_path(conn, "function:a", "function:c")

    assert [n["id"] for n in result["nodes"]] == ["function:a", "function:b", "function:c"]
    assert {(e["src_id"], e["dst_id"], e["type"]) for e in result["edges"]} == {
        ("function:a", "function:b", "calls"),
        ("function:b", "function:c", "imports"),
    }


def test_shortest_path_is_undirected():
    conn = store.connect(":memory:")
    _seed_path_chain(conn)

    result = queries.shortest_path(conn, "function:c", "function:a")

    assert [n["id"] for n in result["nodes"]] == ["function:c", "function:b", "function:a"]


def test_shortest_path_respects_edge_type_filter():
    conn = store.connect(":memory:")
    _seed_path_chain(conn)

    result = queries.shortest_path(conn, "function:a", "function:c", edge_types=["calls"])

    assert result is None


def test_shortest_path_returns_none_when_unreachable():
    conn = store.connect(":memory:")
    _seed_path_chain(conn)

    assert queries.shortest_path(conn, "function:a", "function:d") is None


def test_search_nodes_matches_by_name_case_insensitively():
    conn = store.connect(":memory:")
    store.upsert_node(conn, id="function:AuthService.login", type="function",
                       name="login", path="auth.py")
    store.upsert_node(conn, id="class:AuthService", type="class",
                       name="AuthService", path="auth.py")
    store.upsert_node(conn, id="function:other", type="function", name="unrelated", path="x.py")

    result = queries.search_nodes(conn, "auth")

    assert {n["id"] for n in result} == {"function:AuthService.login", "class:AuthService"}


def test_search_nodes_respects_limit():
    conn = store.connect(":memory:")
    for i in range(5):
        store.upsert_node(conn, id=f"function:foo{i}", type="function", name=f"foo{i}", path="x.py")

    result = queries.search_nodes(conn, "foo", limit=2)

    assert len(result) == 2
