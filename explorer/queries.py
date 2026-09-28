from explorer import store


def _traverse(conn, start_id, max_depth, direction):
    """direction: 'out' follows src->dst (callees), 'in' follows dst->src (callers)."""
    src_col, dst_col = ("src_id", "dst_id") if direction == "out" else ("dst_id", "src_id")
    query = f"""
        WITH RECURSIVE reach(id, depth) AS (
            SELECT ?, 0
            UNION
            SELECT e.{dst_col}, r.depth + 1
            FROM edges e
            JOIN reach r ON e.{src_col} = r.id
            WHERE e.type = 'calls' AND r.depth < ?
        )
        SELECT DISTINCT id FROM reach WHERE depth > 0
    """
    rows = conn.execute(query, (start_id, max_depth)).fetchall()
    return [store.get_node(conn, row[0]) for row in rows if store.get_node(conn, row[0])]


def callees(conn, function_id, max_depth=1):
    return _traverse(conn, function_id, max_depth, direction="out")


def callers(conn, function_id, max_depth=1):
    return _traverse(conn, function_id, max_depth, direction="in")


def churn_hotspots(conn, top=10):
    rows = conn.execute(
        "SELECT id FROM nodes WHERE type = 'file' "
        "ORDER BY CAST(json_extract(attrs, '$.churn') AS INTEGER) DESC "
        "LIMIT ?",
        (top,),
    ).fetchall()
    return [store.get_node(conn, row[0]) for row in rows]


def bus_factor_risk(conn, top=10):
    rows = conn.execute(
        "SELECT id FROM nodes WHERE type = 'file' "
        "ORDER BY CAST(json_extract(attrs, '$.bus_factor') AS INTEGER) ASC, "
        "CAST(json_extract(attrs, '$.churn') AS INTEGER) DESC "
        "LIMIT ?",
        (top,),
    ).fetchall()
    return [store.get_node(conn, row[0]) for row in rows]


def co_change(conn, file_id):
    edges = store.get_edges(conn, src_id=file_id, type="co_changed_with")
    edges += store.get_edges(conn, dst_id=file_id, type="co_changed_with")
    results = []
    for edge in edges:
        other_id = edge["dst_id"] if edge["src_id"] == file_id else edge["src_id"]
        results.append({"node": store.get_node(conn, other_id), "count": edge["attrs"].get("count", 0)})
    return results


def authors(conn, file_id):
    modifies = store.get_edges(conn, dst_id=file_id, type="modifies")
    author_ids = []
    seen = set()
    for edge in modifies:
        commit_hash = edge["src_id"].removeprefix("commit:")
        commit = store.get_commit(conn, commit_hash)
        if commit and commit["author_id"] not in seen:
            seen.add(commit["author_id"])
            author_ids.append(commit["author_id"])
    return [store.get_node(conn, author_id) for author_id in author_ids]


def referencing_commits(conn, tracker_id):
    edges = store.get_edges(conn, dst_id=tracker_id, type="references")
    commits = []
    for edge in edges:
        commit_hash = edge["src_id"].removeprefix("commit:")
        commit = store.get_commit(conn, commit_hash)
        if commit:
            commits.append(commit)
    return commits


def imports(conn, module_id):
    edges = store.get_edges(conn, src_id=module_id, type="imports")
    return [store.get_node(conn, e["dst_id"]) or {"id": e["dst_id"], "type": "external"} for e in edges]


def search(conn, table, query_text, limit=20):
    fts_results = store.search_fts(conn, table, query_text, limit=limit)
    results = []
    for hit in fts_results:
        node = store.get_node(conn, hit["node_id"])
        results.append({"node": node, "text": hit["text"]})
    return results


def search_nodes(conn, query_text, limit=20):
    pattern = f"%{query_text.replace('%', '\\%').replace('_', '\\_')}%"
    rows = conn.execute(
        "SELECT id FROM nodes WHERE name LIKE ? ESCAPE '\\' OR id LIKE ? ESCAPE '\\' "
        "ORDER BY name LIMIT ?",
        (pattern, pattern, limit),
    ).fetchall()
    return [store.get_node(conn, row[0]) for row in rows]


def _file_id_for_node(node):
    if node["type"] == "file":
        return node["id"]
    return f"file:{node['path']}" if node.get("path") else None


def node_detail(conn, node_id):
    node = store.get_node(conn, node_id)
    if node is None:
        return None

    file_id = _file_id_for_node(node)
    modifies_edges = store.get_edges(conn, dst_id=file_id, type="modifies") if file_id else []
    commits = []
    for edge in modifies_edges:
        commit_hash = edge["src_id"].removeprefix("commit:")
        commit = store.get_commit(conn, commit_hash)
        if commit:
            commits.append(commit)

    return {
        "node": node,
        "calls": callees(conn, node_id, max_depth=1),
        "called_by": callers(conn, node_id, max_depth=1),
        "modified_by": {"commit_count": len(commits), "commits": commits},
        "authors": authors(conn, file_id) if file_id else [],
    }


# A commit whose diff is mostly unrelated files (e.g. a broad merge that
# happens to touch one cited file among a dozen others) is weak evidence for
# the cited topic -- require a minimum share of its files to be cited.
RELATED_COMMIT_MIN_OVERLAP_RATIO = 0.3

# Caps how many commits a single cited file can contribute, so a high-churn
# file (e.g. README.md) can't flood "related commits" with its entire history
# -- only its most recent, still keeping the signal per file bounded.
RELATED_COMMITS_PER_FILE_CAP = 5


def _normalize_citation(entry):
    """A citation is either a bare node id string (treated as "primary", for
    backward compatibility) or a {"id", "role"} dict, where role is "primary"
    (the actual subject of the answer -- gets full commit surfacing) or
    "supporting" (cited only as context, e.g. a config file or a doc that
    merely documents something -- shown as a node but never contributes its
    unrelated commit history)."""
    if isinstance(entry, str):
        return {"id": entry, "role": "primary"}
    return {"id": entry["id"], "role": entry.get("role", "primary")}


def session_graph(conn, node_ids):
    """Induced subgraph for a set of cited node ids: the nodes themselves,
    structural edges directly between two of them, and -- per cited
    file/symbol with role "primary" -- the commits whose `modifies` edge
    targets that specific file (plus each commit's author), filtered to
    commits where cited files make up a meaningful share of what changed and
    capped per file to the most recent few. A commit that also touched other,
    uncited files never pulls those files in. Nodes cited only as
    "supporting" context are included as nodes but never contribute commits."""
    nodes = {}
    edges = []
    edge_keys = set()

    def add_node(node):
        if node is not None:
            nodes[node["id"]] = node

    def add_edge(src_id, dst_id, type_, attrs=None):
        key = (src_id, dst_id, type_)
        if key not in edge_keys:
            edge_keys.add(key)
            edges.append({"src_id": src_id, "dst_id": dst_id, "type": type_, "attrs": attrs or {}})

    citations = [_normalize_citation(entry) for entry in node_ids]
    role_by_id = {c["id"]: c["role"] for c in citations}
    cited = [store.get_node(conn, c["id"]) for c in citations]
    cited = [node for node in cited if node is not None]
    for node in cited:
        add_node(node)
    cited_ids = {node["id"] for node in cited}

    for node in cited:
        for edge in store.get_edges(conn, src_id=node["id"]):
            if edge["dst_id"] in cited_ids:
                add_edge(edge["src_id"], edge["dst_id"], edge["type"], edge["attrs"])

    # A commit cited directly (rather than discovered via a primary file's
    # modifies edges below) has no path for _file_id_for_node to resolve, so
    # it would otherwise never get its own author attached.
    for node in cited:
        if node["type"] != "commit":
            continue
        for author_edge in store.get_edges(conn, src_id=node["id"], type="authored_by"):
            author_node = store.get_node(conn, author_edge["dst_id"])
            if author_node is None:
                continue
            add_node(author_node)
            add_edge(author_edge["src_id"], author_edge["dst_id"], "authored_by", author_edge["attrs"])

    primary_ids = {node_id for node_id, role in role_by_id.items() if role == "primary"}
    cited_file_paths = {
        file_id.removeprefix("file:")
        for file_id in (_file_id_for_node(node) for node in cited if node["id"] in primary_ids)
        if file_id
    }

    for node in cited:
        file_id = _file_id_for_node(node)
        if not file_id:
            continue
        # A "module" node already represents this same path for display
        # purposes (import graph); a source file also gets a separately
        # persisted "file:" node (git history/churn) at ingest time. Adding
        # both would show the same path twice, so only surface the derived
        # file: node when the cited node isn't already that same file.
        if node["type"] != "module":
            add_node(store.get_node(conn, file_id))

        if node["id"] not in primary_ids:
            continue

        candidates = []
        for edge in store.get_edges(conn, dst_id=file_id, type="modifies"):
            commit_node = store.get_node(conn, edge["src_id"])
            if commit_node is None:
                continue
            commit_hash = edge["src_id"].removeprefix("commit:")
            commit = store.get_commit(conn, commit_hash)
            if commit and commit["files_changed"]:
                overlap = sum(1 for f in commit["files_changed"] if f in cited_file_paths)
                ratio = overlap / len(commit["files_changed"])
                if ratio < RELATED_COMMIT_MIN_OVERLAP_RATIO:
                    continue
                timestamp = commit["timestamp"]
            else:
                # No file-list data to score against -- fail open rather than
                # silently dropping a commit we can't evaluate.
                timestamp = 0
            candidates.append((timestamp, edge, commit_node))

        candidates.sort(key=lambda c: c[0], reverse=True)
        for _, edge, commit_node in candidates[:RELATED_COMMITS_PER_FILE_CAP]:
            add_node(commit_node)
            add_edge(edge["src_id"], file_id, "modifies", edge["attrs"])
            for author_edge in store.get_edges(conn, src_id=edge["src_id"], type="authored_by"):
                author_node = store.get_node(conn, author_edge["dst_id"])
                if author_node is None:
                    continue
                add_node(author_node)
                add_edge(author_edge["src_id"], author_edge["dst_id"], "authored_by", author_edge["attrs"])

    return {"nodes": list(nodes.values()), "edges": edges}


def repo_stats(conn):
    node_counts = dict(conn.execute("SELECT type, COUNT(*) FROM nodes GROUP BY type").fetchall())
    edge_counts = dict(conn.execute("SELECT type, COUNT(*) FROM edges GROUP BY type").fetchall())
    commit_count = conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
    return {
        "node_counts": node_counts,
        "edge_counts": edge_counts,
        "commit_count": commit_count,
        "author_count": node_counts.get("author", 0),
        "top_churn": churn_hotspots(conn, top=5),
        "top_bus_factor_risk": bus_factor_risk(conn, top=5),
    }


def graph_around(conn, node_id, depth=1, edge_types=None, direction="both"):
    """BFS outward from node_id up to `depth` hops, following edges of any
    type in `edge_types` (None = all types). Returns nodes and edges (not
    just reachable ids) so the result can be rendered as a graph."""
    seen_nodes = {node_id}
    edges_by_key = {}
    frontier = {node_id}

    for _ in range(depth):
        next_frontier = set()
        for nid in frontier:
            candidate_edges = []
            if direction in ("out", "both"):
                candidate_edges += store.get_edges(conn, src_id=nid)
            if direction in ("in", "both"):
                candidate_edges += store.get_edges(conn, dst_id=nid)
            for edge in candidate_edges:
                if edge_types and edge["type"] not in edge_types:
                    continue
                edges_by_key[(edge["src_id"], edge["dst_id"], edge["type"])] = edge
                other = edge["dst_id"] if edge["src_id"] == nid else edge["src_id"]
                if other not in seen_nodes:
                    seen_nodes.add(other)
                    next_frontier.add(other)
        frontier = next_frontier

    return {
        "nodes": [n for n in (store.get_node(conn, nid) for nid in seen_nodes) if n],
        "edges": list(edges_by_key.values()),
    }


def shortest_path(conn, from_id, to_id, edge_types=None):
    """BFS over edges treated as undirected, for highlighting a dependency
    path between two nodes regardless of edge direction."""
    if from_id == to_id:
        node = store.get_node(conn, from_id)
        return {"nodes": [node] if node else [], "edges": []} if node else None

    came_from = {from_id: None}
    edge_used = {}
    queue = [from_id]

    while queue:
        current = queue.pop(0)
        if current == to_id:
            break
        candidate_edges = store.get_edges(conn, src_id=current) + store.get_edges(conn, dst_id=current)
        for edge in candidate_edges:
            if edge_types and edge["type"] not in edge_types:
                continue
            other = edge["dst_id"] if edge["src_id"] == current else edge["src_id"]
            if other not in came_from:
                came_from[other] = current
                edge_used[other] = edge
                queue.append(other)

    if to_id not in came_from:
        return None

    path_ids = []
    node_id = to_id
    while node_id is not None:
        path_ids.append(node_id)
        node_id = came_from[node_id]
    path_ids.reverse()

    return {
        "nodes": [store.get_node(conn, nid) for nid in path_ids],
        "edges": [edge_used[nid] for nid in path_ids if nid in edge_used],
    }


def _functions_and_classes_in(conn, paths):
    if not paths:
        return []
    placeholders = ",".join("?" for _ in paths)
    rows = conn.execute(
        f"SELECT id FROM nodes WHERE type IN ('function', 'class') AND path IN ({placeholders})",
        list(paths),
    ).fetchall()
    return [row[0] for row in rows]


def graph_overview(conn, seed_limit=15, depth=1, edge_types=None, max_nodes=200):
    top_files = churn_hotspots(conn, top=seed_limit)
    seeds = [n["id"] for n in top_files]
    seeds += _functions_and_classes_in(conn, [n["path"] for n in top_files if n.get("path")])

    nodes = {}
    edges = {}
    for seed_id in seeds:
        sub = graph_around(conn, seed_id, depth=depth, edge_types=edge_types)
        for n in sub["nodes"]:
            nodes[n["id"]] = n
        for e in sub["edges"]:
            edges[(e["src_id"], e["dst_id"], e["type"])] = e

    truncated = len(nodes) > max_nodes
    node_list = list(nodes.values())[:max_nodes]
    kept_ids = {n["id"] for n in node_list}
    edge_list = [e for e in edges.values() if e["src_id"] in kept_ids and e["dst_id"] in kept_ids]

    return {"nodes": node_list, "edges": edge_list, "truncated": truncated}
