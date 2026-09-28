import ast
from dataclasses import dataclass, field


@dataclass
class ParseResult:
    nodes: list = field(default_factory=list)
    edges: list = field(default_factory=list)


def _edge(src_id, dst_id, type, attrs=None):
    return {"src_id": src_id, "dst_id": dst_id, "type": type, "attrs": attrs or {}}


class _Visitor(ast.NodeVisitor):
    def __init__(self, result: ParseResult, path: str, module_id: str):
        self.result = result
        self.path = path
        # stack of (node_id, kind) for the containing scope: module/class/function
        self.scope_stack = [(module_id, "module")]
        # local name -> function node id, for best-effort call resolution
        self.function_ids_by_name = {}

    def _current_scope_id(self):
        return self.scope_stack[-1][0]

    def visit_ClassDef(self, node: ast.ClassDef):
        class_id = f"class:{self.path}:{node.name}:{node.lineno}"
        self.result.nodes.append({
            "id": class_id,
            "type": "class",
            "name": node.name,
            "path": self.path,
            "start_line": node.lineno,
            "end_line": getattr(node, "end_lineno", node.lineno),
            "docstring": ast.get_docstring(node),
            "attrs": {},
        })
        self.result.edges.append(_edge(self._current_scope_id(), class_id, "contains"))

        for base in node.bases:
            base_name = _name_of(base)
            if base_name:
                # Resolved against known classes in a later linking pass if needed;
                # for now we record by best-effort id guess using name only.
                self.result.edges.append(_edge(class_id, f"unresolved:class:{base_name}", "inherits"))

        self.scope_stack.append((class_id, "class"))
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node):
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node):
        self._visit_function(node)

    def _visit_function(self, node):
        func_id = f"function:{self.path}:{node.name}:{node.lineno}"
        self.result.nodes.append({
            "id": func_id,
            "type": "function",
            "name": node.name,
            "path": self.path,
            "start_line": node.lineno,
            "end_line": getattr(node, "end_lineno", node.lineno),
            "docstring": ast.get_docstring(node),
            "attrs": {},
        })
        self.result.edges.append(_edge(self._current_scope_id(), func_id, "contains"))
        self.function_ids_by_name.setdefault(node.name, func_id)

        self.scope_stack.append((func_id, "function"))
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            local_name = alias.asname or alias.name.split(".")[0]
            self.result.edges.append(
                _edge(self._current_scope_id(), f"external:{alias.name}", "imports", {
                    "specifier": alias.name,
                    "local_name": local_name,
                    "imported_name": None,
                    "level": 0,
                })
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        for alias in node.names:
            target = f"{module}.{alias.name}" if module else alias.name
            local_name = alias.asname or alias.name
            self.result.edges.append(
                _edge(self._current_scope_id(), f"external:{target}", "imports", {
                    "specifier": module,
                    "local_name": local_name,
                    "imported_name": alias.name,
                    "level": node.level,
                })
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        scope_id, scope_kind = self.scope_stack[-1]
        if scope_kind == "function":
            name = _name_of(node.func)
            if name:
                dst = self.function_ids_by_name.get(name, f"unresolved:call:{name}")
                self.result.edges.append(_edge(scope_id, dst, "calls"))
        self.generic_visit(node)


def _name_of(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _name_of(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return None


def parse_source(source: str, path: str) -> ParseResult:
    result = ParseResult()
    tree = ast.parse(source)

    module_id = f"module:{path}"
    result.nodes.append({
        "id": module_id,
        "type": "module",
        "name": path,
        "path": path,
        "start_line": 1,
        "end_line": getattr(tree, "end_lineno", 1),
        "docstring": ast.get_docstring(tree),
        "attrs": {},
    })

    visitor = _Visitor(result, path, module_id)
    visitor.visit(tree)

    # Resolve same-file class inheritance ids now that all classes are known.
    class_ids_by_name = {n["name"]: n["id"] for n in result.nodes if n["type"] == "class"}
    resolved_edges = []
    for e in result.edges:
        if e["type"] == "inherits" and e["dst_id"].startswith("unresolved:class:"):
            base_name = e["dst_id"].removeprefix("unresolved:class:")
            e = dict(e, dst_id=class_ids_by_name.get(base_name, e["dst_id"]))
        resolved_edges.append(e)
    result.edges = resolved_edges

    return result
