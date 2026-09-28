from explorer import js_ts_parser


def test_parse_source_extracts_a_named_function_declaration():
    source = "function greet(name) {\n  return name;\n}\n"

    result = js_ts_parser.parse_source(source, path="greet.js")

    funcs = [n for n in result.nodes if n["type"] == "function"]
    assert len(funcs) == 1
    assert funcs[0]["name"] == "greet"
    assert funcs[0]["path"] == "greet.js"
    assert funcs[0]["start_line"] == 1


def test_parse_source_extracts_arrow_function_assigned_to_const():
    source = "const handleSubmit = () => {\n  return true;\n};\n"

    result = js_ts_parser.parse_source(source, path="form.js")

    funcs = [n for n in result.nodes if n["type"] == "function"]
    assert len(funcs) == 1
    assert funcs[0]["name"] == "handleSubmit"


def test_parse_source_extracts_jsdoc_comment_as_docstring():
    source = (
        "/**\n"
        " * Greets a person by name.\n"
        " */\n"
        "function greet(name) {\n"
        "  return name;\n"
        "}\n"
    )

    result = js_ts_parser.parse_source(source, path="greet.js")

    func = next(n for n in result.nodes if n["type"] == "function")
    assert func["docstring"] == "Greets a person by name."


def test_parse_source_extracts_class_with_method_and_inheritance():
    source = (
        "class Animal {}\n"
        "class Dog extends Animal {\n"
        "  bark() {\n"
        "    return 'woof';\n"
        "  }\n"
        "}\n"
    )

    result = js_ts_parser.parse_source(source, path="animals.ts")

    classes = {n["name"]: n for n in result.nodes if n["type"] == "class"}
    assert set(classes.keys()) == {"Animal", "Dog"}

    dog_id = classes["Dog"]["id"]
    animal_id = classes["Animal"]["id"]
    inherits = [e for e in result.edges if e["type"] == "inherits"]
    assert {"src_id": dog_id, "dst_id": animal_id, "type": "inherits", "attrs": {}} in inherits

    bark = next(n for n in result.nodes if n["type"] == "function" and n["name"] == "bark")
    contains = [e for e in result.edges if e["type"] == "contains"]
    assert {"src_id": dog_id, "dst_id": bark["id"], "type": "contains", "attrs": {}} in contains


def test_parse_source_extracts_named_import_attrs():
    source = "import { useState } from 'react';\n"

    result = js_ts_parser.parse_source(source, path="mod.ts")

    imports = [e for e in result.edges if e["type"] == "imports"]
    assert imports[0]["dst_id"] == "external:react"
    assert imports[0]["attrs"] == {
        "specifier": "react",
        "local_name": "useState",
        "imported_name": "useState",
    }


def test_parse_source_extracts_named_import_with_alias():
    source = "import { bar as baz } from './bar';\n"

    result = js_ts_parser.parse_source(source, path="mod.ts")

    imports = [e for e in result.edges if e["type"] == "imports"]
    assert imports[0]["attrs"]["local_name"] == "baz"
    assert imports[0]["attrs"]["imported_name"] == "bar"
    assert imports[0]["attrs"]["specifier"] == "./bar"


def test_parse_source_extracts_default_import():
    source = "import Foo from './foo';\n"

    result = js_ts_parser.parse_source(source, path="mod.ts")

    imports = [e for e in result.edges if e["type"] == "imports"]
    assert imports[0]["attrs"]["local_name"] == "Foo"
    assert imports[0]["attrs"]["imported_name"] == "default"


def test_parse_source_extracts_namespace_import():
    source = "import * as ns from './ns';\n"

    result = js_ts_parser.parse_source(source, path="mod.ts")

    imports = [e for e in result.edges if e["type"] == "imports"]
    assert imports[0]["attrs"]["local_name"] == "ns"
    assert imports[0]["attrs"]["imported_name"] == "*"


def test_parse_source_marks_default_export_kind():
    source = "export default function Foo() {}\n"

    result = js_ts_parser.parse_source(source, path="mod.ts")

    func = next(n for n in result.nodes if n["type"] == "function")
    assert func["attrs"]["export_kind"] == "default"


def test_parse_source_marks_named_export_kind():
    source = "export const Bar = () => {};\n"

    result = js_ts_parser.parse_source(source, path="mod.ts")

    func = next(n for n in result.nodes if n["type"] == "function")
    assert func["attrs"]["export_kind"] == "named"


def test_parse_source_non_exported_function_has_no_export_kind():
    source = "function helper() {}\n"

    result = js_ts_parser.parse_source(source, path="mod.ts")

    func = next(n for n in result.nodes if n["type"] == "function")
    assert "export_kind" not in func["attrs"]


def test_parse_source_extracts_calls_within_function():
    source = (
        "function helper() {\n"
        "  return 1;\n"
        "}\n"
        "function main() {\n"
        "  return helper();\n"
        "}\n"
    )

    result = js_ts_parser.parse_source(source, path="mod.js")

    main_id = next(n["id"] for n in result.nodes if n["name"] == "main")
    helper_id = next(n["id"] for n in result.nodes if n["name"] == "helper")
    calls = [e for e in result.edges if e["type"] == "calls"]
    assert {"src_id": main_id, "dst_id": helper_id, "type": "calls", "attrs": {}} in calls


def test_parse_source_extracts_jsx_component_usage_as_calls():
    source = (
        "const ReservationForm = () => {\n"
        "  return <div>form</div>;\n"
        "};\n"
        "const Page = () => {\n"
        "  return <ReservationForm />;\n"
        "};\n"
    )

    result = js_ts_parser.parse_source(source, path="page.tsx")

    page_id = next(n["id"] for n in result.nodes if n["name"] == "Page")
    form_id = next(n["id"] for n in result.nodes if n["name"] == "ReservationForm")
    calls = [e for e in result.edges if e["type"] == "calls"]
    assert {"src_id": page_id, "dst_id": form_id, "type": "calls", "attrs": {}} in calls
