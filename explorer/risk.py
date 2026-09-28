from explorer import store


def compute_and_store(conn):
    file_ids = [
        row[0] for row in conn.execute("SELECT id FROM nodes WHERE type = 'file'")
    ]

    for file_id in file_ids:
        modifies = store.get_edges(conn, dst_id=file_id, type="modifies")
        commit_hashes = [e["src_id"].removeprefix("commit:") for e in modifies]

        churn = len(commit_hashes)

        author_ids = set()
        last_modified = None
        for hash_ in commit_hashes:
            commit = store.get_commit(conn, hash_)
            if commit is None:
                continue
            author_ids.add(commit["author_id"])
            if last_modified is None or commit["timestamp"] > last_modified:
                last_modified = commit["timestamp"]

        coupling_edges = store.get_edges(conn, src_id=file_id, type="co_changed_with")
        coupling_edges += store.get_edges(conn, dst_id=file_id, type="co_changed_with")
        coupling = sum(e["attrs"].get("count", 0) for e in coupling_edges)

        node = store.get_node(conn, file_id)
        attrs = dict(node["attrs"])
        attrs["churn"] = churn
        attrs["bus_factor"] = len(author_ids)
        attrs["last_modified"] = last_modified
        attrs["coupling"] = coupling

        store.upsert_node(
            conn,
            id=node["id"],
            type=node["type"],
            name=node["name"],
            path=node["path"],
            start_line=node["start_line"],
            end_line=node["end_line"],
            docstring=node["docstring"],
            attrs=attrs,
        )
