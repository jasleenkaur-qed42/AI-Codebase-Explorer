from explorer import docs_walker


def test_find_doc_files_finds_readme_and_docs_markdown(tmp_path):
    (tmp_path / "README.md").write_text("# Project\nHello")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "architecture.md").write_text("# Architecture\nDetails")
    (tmp_path / "notes.txt").write_text("not a doc")

    found = {p.relative_to(tmp_path).as_posix() for p in docs_walker.find_doc_files(str(tmp_path))}

    assert found == {"README.md", "docs/architecture.md"}


def test_walk_returns_doc_nodes_with_content():
    docs = docs_walker.walk(
        repo_path=".",
        doc_paths=["README.md"],
        read_file=lambda p: "# Title\nSome content about installation.",
    )

    assert len(docs) == 1
    assert docs[0]["id"] == "doc:README.md"
    assert docs[0]["type"] == "doc"
    assert docs[0]["path"] == "README.md"
    assert "installation" in docs[0]["text"]
