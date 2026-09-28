from dataclasses import dataclass, field

import tree_sitter_javascript as tsjs
import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser

_LANGUAGES = {
    ".js": Language(tsjs.language()),
    ".jsx": Language(tsjs.language()),
    ".ts": Language(tsts.language_typescript()),
    ".tsx": Language(tsts.language_tsx()),
}


@dataclass
class ParseResult:
    nodes: list = field(default_factory=list)
    edges: list = field(default_factory=list)


def _edge(src_id, dst_id, type, attrs=None):
    return {"src_id": src_id, "dst_id": dst_id, "type": type, "attrs": attrs or {}}


def _text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")


def _child_by_type(node, type_name):
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def parse_source(source: str, path: str) -> ParseResult:
    ext = "." + path.rsplit(".", 1)[-1]
    language = _LANGUAGES[ext]
    source_bytes = source.encode("utf-8")
    parser = Parser(language)
    tree = parser.parse(source_bytes)

    result = ParseResult()
    module_id = f"module:{path}"
    result.nodes.append({
        "id": module_id,
        "type": "module",
        "name": path,
        "path": path,
        "start_line": 1,
        "end_line": tree.root_node.end_point[0] + 1,
        "docstring": None,
        "attrs": {},
    })

    _Visitor(result, path, source_bytes, module_id).visit(tree.root_node)

    class_ids_by_name = {n["name"]: n["id"] for n in result.nodes if n["type"] == "class"}
    resolved_edges = []
    for e in result.edges:
        if e["type"] == "inherits" and e["dst_id"].startswith("unresolved:class:"):
            base_name = e["dst_id"].removeprefix("unresolved:class:")
            e = dict(e, dst_id=class_ids_by_name.get(base_name, e["dst_id"]))
        resolved_edges.append(e)
    result.edges = resolved_edges

    return result


class _Visitor:
    def __init__(self, result: ParseResult, path: str, source: bytes, module_id: str):
        self.result = result
        self.path = path
        self.source = source
        self.scope_stack = [(module_id, "scope")]
        self.function_ids_by_name = {}
        self.pending_export_kind = None

    def _current_scope_id(self):
        return self.scope_stack[-1][0]

    def visit(self, node):
        handler = getattr(self, f"visit_{node.type}", None)
        if handler:
            handler(node)
        else:
            self.visit_children(node)

    def visit_children(self, node):
        for child in node.children:
            self.visit(child)

    def _line(self, node):
        return node.start_point[0] + 1

    def _end_line(self, node):
        return node.end_point[0] + 1

    def _docstring_for(self, node):
        prev = node.prev_sibling
        if prev is not None and prev.type == "comment":
            text = _text(prev, self.source).strip()
            if text.startswith("/**"):
                text = text[3:]
                if text.endswith("*/"):
                    text = text[:-2]
                lines = [ln.strip().lstrip("*").strip() for ln in text.splitlines()]
                return "\n".join(ln for ln in lines if ln).strip() or None
        return None

    def _add_function(self, name, name_node, body_node):
        func_id = f"function:{self.path}:{name}:{self._line(name_node)}"
        attrs = {}
        if self.pending_export_kind is not None:
            attrs["export_kind"] = self.pending_export_kind
        self.result.nodes.append({
            "id": func_id,
            "type": "function",
            "name": name,
            "path": self.path,
            "start_line": self._line(name_node),
            "end_line": self._end_line(body_node) if body_node is not None else self._line(name_node),
            "docstring": self._docstring_for(name_node),
            "attrs": attrs,
        })
        self.result.edges.append(_edge(self._current_scope_id(), func_id, "contains"))
        self.function_ids_by_name.setdefault(name, func_id)
        return func_id

    def visit_function_declaration(self, node):
        name_node = _child_by_type(node, "identifier")
        if name_node is None:
            self.visit_children(node)
            return
        name = _text(name_node, self.source)
        func_id = self._add_function(name, node, node)
        self.scope_stack.append((func_id, "function"))
        self.visit_children(node)
        self.scope_stack.pop()

    def visit_lexical_declaration(self, node):
        for declarator in node.children:
            if declarator.type != "variable_declarator":
                continue
            name_node = _child_by_type(declarator, "identifier")
            value_node = declarator.child_by_field_name("value")
            if name_node is None or value_node is None:
                continue
            if value_node.type in ("arrow_function", "function_expression"):
                name = _text(name_node, self.source)
                func_id = self._add_function(name, node, value_node)
                self.scope_stack.append((func_id, "function"))
                self.visit_children(value_node)
                self.scope_stack.pop()
            else:
                self.visit_children(value_node)

    def visit_class_declaration(self, node):
        name_node = _child_by_type(node, "identifier") or _child_by_type(node, "type_identifier")
        if name_node is None:
            self.visit_children(node)
            return
        name = _text(name_node, self.source)
        class_id = f"class:{self.path}:{name}:{self._line(node)}"
        class_attrs = {}
        if self.pending_export_kind is not None:
            class_attrs["export_kind"] = self.pending_export_kind
        self.result.nodes.append({
            "id": class_id,
            "type": "class",
            "name": name,
            "path": self.path,
            "start_line": self._line(node),
            "end_line": self._end_line(node),
            "docstring": self._docstring_for(node),
            "attrs": class_attrs,
        })
        self.result.edges.append(_edge(self._current_scope_id(), class_id, "contains"))

        heritage = _child_by_type(node, "class_heritage")
        if heritage is not None:
            extends_clause = _child_by_type(heritage, "extends_clause")
            search_node = extends_clause if extends_clause is not None else heritage
            base_name_node = _child_by_type(search_node, "identifier")
            if base_name_node is not None:
                base_name = _text(base_name_node, self.source)
                self.result.edges.append(
                    _edge(class_id, f"unresolved:class:{base_name}", "inherits")
                )

        self.scope_stack.append((class_id, "class"))
        self.visit_children(node)
        self.scope_stack.pop()

    def visit_method_definition(self, node):
        name_node = _child_by_type(node, "property_identifier")
        if name_node is None:
            self.visit_children(node)
            return
        name = _text(name_node, self.source)
        func_id = self._add_function(name, name_node, node)
        self.scope_stack.append((func_id, "function"))
        self.visit_children(node)
        self.scope_stack.pop()

    def visit_export_statement(self, node):
        has_default = _child_by_type(node, "default") is not None
        prev = self.pending_export_kind
        self.pending_export_kind = "default" if has_default else "named"
        self.visit_children(node)
        self.pending_export_kind = prev

    def visit_import_statement(self, node):
        source_node = _child_by_type(node, "string")
        if source_node is None:
            self.visit_children(node)
            return
        module_specifier = _text(_child_by_type(source_node, "string_fragment") or source_node, self.source)

        clause = _child_by_type(node, "import_clause")
        bindings = []
        if clause is not None:
            default_name_node = _child_by_type(clause, "identifier")
            if default_name_node is not None:
                bindings.append((_text(default_name_node, self.source), "default"))

            named_imports = _child_by_type(clause, "named_imports")
            if named_imports is not None:
                for specifier in named_imports.children:
                    if specifier.type != "import_specifier":
                        continue
                    identifiers = [c for c in specifier.children if c.type == "identifier"]
                    if not identifiers:
                        continue
                    imported_name = _text(identifiers[0], self.source)
                    local_name = _text(identifiers[1], self.source) if len(identifiers) > 1 else imported_name
                    bindings.append((local_name, imported_name))

            namespace_import = _child_by_type(clause, "namespace_import")
            if namespace_import is not None:
                ns_name_node = _child_by_type(namespace_import, "identifier")
                if ns_name_node is not None:
                    bindings.append((_text(ns_name_node, self.source), "*"))

        for local_name, imported_name in bindings:
            self.result.edges.append(
                _edge(self._current_scope_id(), f"external:{module_specifier}", "imports", {
                    "specifier": module_specifier,
                    "local_name": local_name,
                    "imported_name": imported_name,
                })
            )
        self.visit_children(node)

    def _call_target_name(self, callee_node):
        if callee_node.type == "identifier":
            return _text(callee_node, self.source)
        if callee_node.type == "member_expression":
            obj = callee_node.child_by_field_name("object")
            prop = callee_node.child_by_field_name("property")
            if obj is not None and prop is not None:
                return f"{self._call_target_name(obj) or _text(obj, self.source)}.{_text(prop, self.source)}"
        return None

    def visit_call_expression(self, node):
        scope_id, scope_kind = self.scope_stack[-1]
        if scope_kind == "function":
            callee = node.child_by_field_name("function")
            if callee is not None:
                name = self._call_target_name(callee)
                if name:
                    dst = self.function_ids_by_name.get(name, f"unresolved:call:{name}")
                    self.result.edges.append(_edge(scope_id, dst, "calls"))
        self.visit_children(node)

    def _visit_jsx(self, node):
        scope_id, scope_kind = self.scope_stack[-1]
        if scope_kind == "function":
            name_node = _child_by_type(node, "identifier")
            if name_node is not None:
                name = _text(name_node, self.source)
                if name and name[0].isupper():
                    dst = self.function_ids_by_name.get(name, f"unresolved:call:{name}")
                    self.result.edges.append(_edge(scope_id, dst, "calls"))
        self.visit_children(node)

    def visit_jsx_self_closing_element(self, node):
        self._visit_jsx(node)

    def visit_jsx_opening_element(self, node):
        self._visit_jsx(node)
