from explorer import linker, store


def _seed_module_with_function(conn, path, func_name, line=1, export_kind=None):
    module_id = f"module:{path}"
    store.upsert_node(conn, id=module_id, type="module", name=path, path=path)
    attrs = {"export_kind": export_kind} if export_kind else {}
    func_id = f"function:{path}:{func_name}:{line}"
    store.upsert_node(conn, id=func_id, type="function", name=func_name, path=path, attrs=attrs)
    store.upsert_edge(conn, src_id=module_id, dst_id=func_id, type="contains")
    return func_id


def test_resolves_named_import_call_across_js_files(tmp_path):
    conn = store.connect(":memory:")
    helper_id = _seed_module_with_function(conn, "a.ts", "helper", export_kind="named")

    caller_id = _seed_module_with_function(conn, "b.ts", "caller")
    store.upsert_edge(conn, src_id="module:b.ts", dst_id="external:./a", type="imports", attrs={
        "specifier": "./a", "local_name": "helper", "imported_name": "helper",
    })
    store.upsert_edge(conn, src_id=caller_id, dst_id="unresolved:call:helper", type="calls")

    linker.resolve_imports_and_calls(conn, str(tmp_path))

    calls = store.get_edges(conn, src_id=caller_id, type="calls")
    assert len(calls) == 1
    assert calls[0]["dst_id"] == helper_id


def test_resolves_default_import_jsx_usage_across_files(tmp_path):
    conn = store.connect(":memory:")
    foo_id = _seed_module_with_function(conn, "components/Foo.tsx", "Foo", export_kind="default")

    page_id = _seed_module_with_function(conn, "pages/Page.tsx", "Page")
    store.upsert_edge(conn, src_id="module:pages/Page.tsx", dst_id="external:../components/Foo",
                       type="imports", attrs={
                           "specifier": "../components/Foo", "local_name": "Foo", "imported_name": "default",
                       })
    store.upsert_edge(conn, src_id=page_id, dst_id="unresolved:call:Foo", type="calls")

    linker.resolve_imports_and_calls(conn, str(tmp_path))

    calls = store.get_edges(conn, src_id=page_id, type="calls")
    assert calls[0]["dst_id"] == foo_id


def test_resolves_alias_import_using_tsconfig_paths(tmp_path):
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["./*"]}}}'
    )
    conn = store.connect(":memory:")
    button_id = _seed_module_with_function(conn, "components/Button.tsx", "Button", export_kind="default")

    home_id = _seed_module_with_function(conn, "pages/Home.tsx", "Home")
    store.upsert_edge(conn, src_id="module:pages/Home.tsx", dst_id="external:@/components/Button",
                       type="imports", attrs={
                           "specifier": "@/components/Button", "local_name": "Button", "imported_name": "default",
                       })
    store.upsert_edge(conn, src_id=home_id, dst_id="unresolved:call:Button", type="calls")

    linker.resolve_imports_and_calls(conn, str(tmp_path))

    calls = store.get_edges(conn, src_id=home_id, type="calls")
    assert calls[0]["dst_id"] == button_id


def test_resolves_alias_import_using_nested_tsconfig_in_monorepo(tmp_path):
    (tmp_path / "nextjs").mkdir()
    (tmp_path / "nextjs" / "tsconfig.json").write_text(
        '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["./*"]}}}'
    )
    conn = store.connect(":memory:")
    button_id = _seed_module_with_function(
        conn, "nextjs/components/Button.tsx", "Button", export_kind="default"
    )

    home_id = _seed_module_with_function(conn, "nextjs/pages/Home.tsx", "Home")
    store.upsert_edge(conn, src_id="module:nextjs/pages/Home.tsx", dst_id="external:@/components/Button",
                       type="imports", attrs={
                           "specifier": "@/components/Button", "local_name": "Button", "imported_name": "default",
                       })
    store.upsert_edge(conn, src_id=home_id, dst_id="unresolved:call:Button", type="calls")

    linker.resolve_imports_and_calls(conn, str(tmp_path))

    calls = store.get_edges(conn, src_id=home_id, type="calls")
    assert calls[0]["dst_id"] == button_id


def test_resolves_python_relative_import_call_across_files(tmp_path):
    conn = store.connect(":memory:")
    helper_id = _seed_module_with_function(conn, "pkg/utils.py", "helper")

    run_id = _seed_module_with_function(conn, "pkg/main.py", "run")
    store.upsert_edge(conn, src_id="module:pkg/main.py", dst_id="external:utils.helper",
                       type="imports", attrs={
                           "specifier": "utils", "local_name": "helper", "imported_name": "helper", "level": 1,
                       })
    store.upsert_edge(conn, src_id=run_id, dst_id="unresolved:call:helper", type="calls")

    linker.resolve_imports_and_calls(conn, str(tmp_path))

    calls = store.get_edges(conn, src_id=run_id, type="calls")
    assert calls[0]["dst_id"] == helper_id


def test_leaves_edge_unresolved_when_no_local_binding_found(tmp_path):
    conn = store.connect(":memory:")
    caller_id = _seed_module_with_function(conn, "b.ts", "caller")
    store.upsert_edge(conn, src_id="module:b.ts", dst_id="external:react", type="imports", attrs={
        "specifier": "react", "local_name": "useState", "imported_name": "useState",
    })
    store.upsert_edge(conn, src_id=caller_id, dst_id="unresolved:call:useState", type="calls")

    linker.resolve_imports_and_calls(conn, str(tmp_path))

    calls = store.get_edges(conn, src_id=caller_id, type="calls")
    assert calls[0]["dst_id"] == "unresolved:call:useState"


def test_rewrites_import_edge_to_point_at_resolved_local_module(tmp_path):
    conn = store.connect(":memory:")
    store.upsert_node(conn, id="module:src/ReservationForm.tsx", type="module",
                       name="src/ReservationForm.tsx", path="src/ReservationForm.tsx")
    store.upsert_node(conn, id="module:src/ReservationPage.tsx", type="module",
                       name="src/ReservationPage.tsx", path="src/ReservationPage.tsx")
    store.upsert_edge(
        conn, src_id="module:src/ReservationPage.tsx", dst_id="external:./ReservationForm",
        type="imports", attrs={
            "specifier": "./ReservationForm", "local_name": "ReservationForm", "imported_name": "default",
        },
    )

    linker.resolve_imports_and_calls(conn, str(tmp_path))

    imports = store.get_edges(conn, src_id="module:src/ReservationPage.tsx", type="imports")
    assert imports[0]["dst_id"] == "module:src/ReservationForm.tsx"


def test_leaves_import_edge_pointing_at_external_when_unresolved(tmp_path):
    conn = store.connect(":memory:")
    store.upsert_node(conn, id="module:src/Page.tsx", type="module",
                       name="src/Page.tsx", path="src/Page.tsx")
    store.upsert_edge(
        conn, src_id="module:src/Page.tsx", dst_id="external:react",
        type="imports", attrs={"specifier": "react", "local_name": "useState", "imported_name": "useState"},
    )

    linker.resolve_imports_and_calls(conn, str(tmp_path))

    imports = store.get_edges(conn, src_id="module:src/Page.tsx", type="imports")
    assert imports[0]["dst_id"] == "external:react"
