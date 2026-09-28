import json
import posixpath
from pathlib import Path

from explorer import store

JS_EXTENSIONS = [".ts", ".tsx", ".js", ".jsx"]


IGNORED_CONFIG_DIRS = {"node_modules", ".git", ".next", "dist", "build", ".venv"}


def load_path_aliases(repo_path: str):
    """Find every tsconfig.json/jsconfig.json in the repo (handles monorepos
    where the config lives in a subdirectory, not the repo root) and return
    a list of (base_url, paths) each made root-relative, so alias resolution
    works regardless of which subtree the config was found in.

    `paths` maps an alias prefix (without the trailing "/*") to a
    root-relative target prefix (without the trailing "/*").
    """
    root = Path(repo_path)
    configs = []
    for filename in ("tsconfig.json", "jsconfig.json"):
        for config_path in root.rglob(filename):
            rel_dir = config_path.parent.relative_to(root)
            if any(part in IGNORED_CONFIG_DIRS for part in rel_dir.parts):
                continue
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

            compiler_options = config.get("compilerOptions", {})
            config_dir = rel_dir.as_posix()
            config_dir = "" if config_dir == "." else config_dir

            base_url = compiler_options.get("baseUrl", ".")
            base_url = _normalize(posixpath.join(config_dir, base_url)) if config_dir else base_url

            raw_paths = compiler_options.get("paths", {})
            paths = {}
            for alias, targets in raw_paths.items():
                if not targets:
                    continue
                alias_prefix = alias.removesuffix("/*")
                target_prefix = targets[0].removesuffix("/*")
                paths[alias_prefix] = _normalize(posixpath.join(base_url, target_prefix))

            configs.append((config_dir, base_url, paths))

    return configs


def _normalize(path: str) -> str:
    return posixpath.normpath(path)


def _config_for_path(configs, importing_path: str):
    """Pick the config whose directory most specifically contains importing_path."""
    best = None
    for config_dir, base_url, paths in configs:
        if config_dir and not importing_path.startswith(config_dir + "/"):
            continue
        if best is None or len(config_dir) > len(best[0]):
            best = (config_dir, base_url, paths)
    return best


def _js_candidate_bases(specifier: str, importing_path: str, configs):
    importing_dir = posixpath.dirname(importing_path)

    if specifier.startswith("."):
        return [_normalize(posixpath.join(importing_dir, specifier))]

    config = _config_for_path(configs, importing_path)
    if config is None:
        return []
    _, _base_url, paths = config

    for alias_prefix, target_prefix in paths.items():
        if specifier == alias_prefix or specifier.startswith(alias_prefix + "/"):
            rest = specifier[len(alias_prefix):].lstrip("/")
            base = posixpath.join(target_prefix, rest) if rest else target_prefix
            return [_normalize(base)]

    return []


def _py_candidate_bases(specifier: str, importing_path: str, level: int):
    importing_dir = posixpath.dirname(importing_path)

    if level and level > 0:
        base_dir = importing_dir
        for _ in range(level - 1):
            base_dir = posixpath.dirname(base_dir)
        rel = specifier.replace(".", "/") if specifier else ""
        base = posixpath.join(base_dir, rel) if rel else base_dir
        return [_normalize(base)]

    if specifier:
        return [_normalize(specifier.replace(".", "/"))]

    return []


def _find_module_node(conn, base_path: str):
    candidates = [base_path]
    for ext in JS_EXTENSIONS + [".py"]:
        candidates.append(f"{base_path}{ext}")
    for ext in JS_EXTENSIONS:
        candidates.append(f"{base_path}/index{ext}")
    candidates.append(f"{base_path}/__init__.py")

    for candidate in candidates:
        node = store.get_node(conn, f"module:{candidate}")
        if node is not None:
            return node
    return None


def _find_exported_node(conn, module_node, imported_name: str):
    module_edges = store.get_edges(conn, src_id=module_node["id"], type="contains")
    candidates = [store.get_node(conn, e["dst_id"]) for e in module_edges]
    candidates = [n for n in candidates if n is not None and n["type"] in ("function", "class")]

    if imported_name == "default":
        for n in candidates:
            if n["attrs"].get("export_kind") == "default":
                return n
        return None

    for n in candidates:
        if n["name"] == imported_name:
            return n
    return None


def resolve_imports_and_calls(conn, repo_path: str):
    configs = load_path_aliases(repo_path)

    bindings = {}
    import_src_ids = [row[0] for row in conn.execute(
        "SELECT DISTINCT src_id FROM edges WHERE type = 'imports'"
    ).fetchall()]
    for src_id in import_src_ids:
        edges = store.get_edges(conn, src_id=src_id, type="imports")
        src_node = store.get_node(conn, src_id)
        if src_node is None:
            continue
        importing_path = src_node["path"]
        if importing_path is None:
            continue

        for e in edges:
            attrs = e["attrs"]
            specifier = attrs.get("specifier")
            local_name = attrs.get("local_name")
            imported_name = attrs.get("imported_name")
            if specifier is None or local_name is None or imported_name in (None, "*"):
                continue

            if importing_path.endswith(".py"):
                candidate_bases = _py_candidate_bases(specifier, importing_path, attrs.get("level", 0))
            else:
                candidate_bases = _js_candidate_bases(specifier, importing_path, configs)

            module_node = None
            for base in candidate_bases:
                module_node = _find_module_node(conn, base)
                if module_node is not None:
                    break

            if module_node is not None:
                bindings[(importing_path, local_name)] = (module_node, imported_name)
                if e["dst_id"] != module_node["id"]:
                    store.delete_edge(conn, src_id, e["dst_id"], "imports")
                    store.upsert_edge(conn, src_id=src_id, dst_id=module_node["id"], type="imports", attrs=attrs)

    for edge_type in ("calls", "inherits"):
        prefix = f"unresolved:{'call' if edge_type == 'calls' else 'class'}:"
        rows = conn.execute(
            "SELECT src_id, dst_id, attrs FROM edges WHERE type = ? AND dst_id LIKE ?",
            (edge_type, f"{prefix}%"),
        ).fetchall()

        for src_id, dst_id, attrs_json in rows:
            name = dst_id[len(prefix):]
            src_node = store.get_node(conn, src_id)
            if src_node is None:
                continue
            binding = bindings.get((src_node["path"], name))
            if binding is None:
                continue
            module_node, imported_name = binding
            target_node = _find_exported_node(conn, module_node, imported_name)
            if target_node is None:
                continue

            attrs = json.loads(attrs_json) if attrs_json else {}
            store.delete_edge(conn, src_id, dst_id, edge_type)
            store.upsert_edge(conn, src_id=src_id, dst_id=target_node["id"], type=edge_type, attrs=attrs)
