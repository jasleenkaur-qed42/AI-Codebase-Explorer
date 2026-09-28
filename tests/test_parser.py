from explorer import parser


def test_parse_file_extracts_a_top_level_function():
    source = '''
def greet(name):
    """Say hello to someone."""
    return f"hello {name}"
'''
    result = parser.parse_source(source, path="greet.py")

    funcs = [n for n in result.nodes if n["type"] == "function"]
    assert len(funcs) == 1
    assert funcs[0]["name"] == "greet"
    assert funcs[0]["path"] == "greet.py"
    assert funcs[0]["docstring"] == "Say hello to someone."
    assert funcs[0]["start_line"] == 2


def test_parse_file_extracts_module_node_and_contains_edge_to_function():
    source = '''
def greet(name):
    return name
'''
    result = parser.parse_source(source, path="greet.py")

    modules = [n for n in result.nodes if n["type"] == "module"]
    assert len(modules) == 1
    module_id = modules[0]["id"]

    func_id = next(n["id"] for n in result.nodes if n["type"] == "function")
    contains = [e for e in result.edges if e["type"] == "contains"]
    assert {"src_id": module_id, "dst_id": func_id, "type": "contains", "attrs": {}} in contains


def test_parse_file_extracts_class_with_method_and_inheritance():
    source = '''
class Animal:
    pass


class Dog(Animal):
    def bark(self):
        """Make noise."""
        return "woof"
'''
    result = parser.parse_source(source, path="animals.py")

    classes = {n["name"]: n for n in result.nodes if n["type"] == "class"}
    assert set(classes.keys()) == {"Animal", "Dog"}

    dog_id = classes["Dog"]["id"]
    animal_id = classes["Animal"]["id"]
    inherits = [e for e in result.edges if e["type"] == "inherits"]
    assert {"src_id": dog_id, "dst_id": animal_id, "type": "inherits", "attrs": {}} in inherits

    bark = next(n for n in result.nodes if n["type"] == "function" and n["name"] == "bark")
    contains = [e for e in result.edges if e["type"] == "contains"]
    assert {"src_id": dog_id, "dst_id": bark["id"], "type": "contains", "attrs": {}} in contains


def test_parse_file_extracts_imports():
    source = '''
import os
from collections import OrderedDict
'''
    result = parser.parse_source(source, path="mod.py")

    imports = [e for e in result.edges if e["type"] == "imports"]
    by_dst = {e["dst_id"]: e for e in imports}
    assert "external:os" in by_dst
    assert "external:collections.OrderedDict" in by_dst

    os_import = by_dst["external:os"]
    assert os_import["attrs"]["local_name"] == "os"
    assert os_import["attrs"]["specifier"] == "os"
    assert os_import["attrs"]["level"] == 0

    od_import = by_dst["external:collections.OrderedDict"]
    assert od_import["attrs"]["local_name"] == "OrderedDict"
    assert od_import["attrs"]["imported_name"] == "OrderedDict"
    assert od_import["attrs"]["specifier"] == "collections"
    assert od_import["attrs"]["level"] == 0


def test_parse_file_extracts_relative_import_with_level():
    source = '''
from .utils import helper
'''
    result = parser.parse_source(source, path="pkg/mod.py")

    imports = [e for e in result.edges if e["type"] == "imports"]
    assert len(imports) == 1
    assert imports[0]["attrs"]["specifier"] == "utils"
    assert imports[0]["attrs"]["level"] == 1
    assert imports[0]["attrs"]["imported_name"] == "helper"
    assert imports[0]["attrs"]["local_name"] == "helper"


def test_parse_file_extracts_calls_within_function():
    source = '''
def helper():
    return 1


def main():
    return helper()
'''
    result = parser.parse_source(source, path="mod.py")

    main_id = next(n["id"] for n in result.nodes if n["name"] == "main")
    helper_id = next(n["id"] for n in result.nodes if n["name"] == "helper")
    calls = [e for e in result.edges if e["type"] == "calls"]
    assert {"src_id": main_id, "dst_id": helper_id, "type": "calls", "attrs": {}} in calls
