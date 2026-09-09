"""Canonical jail boundaries, 2026-09-09.

Run: python3 -m pytest tests/test_path_jails.py -q
Authored temp-file bytes distinguish the allowed target from a sibling escape;
real filesystem symlinks exercise containment without mocking normalization.
HTTP route integration and notebook serialization remain in their existing suites.
"""

from pathlib import Path

import pytest
from fastapi import HTTPException

from tit import viewspec
from tit.server import notebooks
from tit.server.routes.files import _resolve_jailed
from tit.server.static import resolve_static_file, resolve_tetravox_file


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "project"
    nested = root / "nested"
    nested.mkdir(parents=True)
    inside = nested / "target.txt"
    inside.write_text("inside")
    sibling = tmp_path / "project-copy"
    sibling.mkdir()
    outside = sibling / "target.txt"
    outside.write_text("outside")
    (root / "inside-link").symlink_to(inside)
    (root / "outside-link").symlink_to(outside)
    return root, inside, outside


@pytest.mark.parametrize("surface", ["files", "viewspec", "static", "tetravox"])
@pytest.mark.parametrize(
    "case",
    [
        "normal",
        "absolute",
        "inside-link",
        "outside",
        "parent",
        "outside-link",
        "missing",
        "directory",
    ],
)
def test_file_jail_returns_only_canonical_inside_files(
    tree, monkeypatch, surface, case
):
    root, inside, outside = tree
    monkeypatch.setattr(viewspec, "jail_roots", lambda: [root])
    paths = {
        "normal": root / "nested" / ".." / "nested" / "target.txt",
        "absolute": inside,
        "inside-link": root / "inside-link",
        "outside": outside,
        "parent": root / ".." / "project-copy" / "target.txt",
        "outside-link": root / "outside-link",
        "missing": root / "missing.txt",
        "directory": root,
    }
    raw = str(paths[case])
    allowed = case in {"normal", "absolute", "inside-link"}
    if surface == "files":
        if not allowed:
            with pytest.raises(HTTPException) as exc:
                _resolve_jailed(raw, roots=[root])
            assert exc.value.status_code == (
                404 if case in {"missing", "directory"} else 403
            )
            return
        result = _resolve_jailed(raw, roots=[root])
    elif surface == "viewspec":
        result = viewspec.resolve_jailed(raw)
    else:
        resolver = resolve_static_file if surface == "static" else resolve_tetravox_file
        result = resolver(str(root), raw)
    if allowed:
        assert result == inside.resolve()
        assert result.read_text() == "inside"
    else:
        assert result is None


@pytest.mark.parametrize("surface", ["files", "viewspec", "static", "tetravox"])
def test_filesystem_root_jail_accepts_a_real_nested_file(tree, monkeypatch, surface):
    _, inside, _ = tree
    root = Path(inside.anchor)
    monkeypatch.setattr(viewspec, "jail_roots", lambda: [root])
    if surface == "files":
        result = _resolve_jailed(str(inside), roots=[root])
    elif surface == "viewspec":
        result = viewspec.resolve_jailed(str(inside))
    else:
        resolver = resolve_static_file if surface == "static" else resolve_tetravox_file
        result = resolver(str(root), str(inside))
    assert result == inside.resolve()


@pytest.mark.parametrize("name", ["analysis", "examples/getting-started"])
def test_notebook_jail_permits_new_files_without_creating_them(tmp_path, name):
    result = notebooks.notebook_path(tmp_path, name)
    expected = tmp_path / "code" / "ti-toolbox" / "notebooks" / (name + ".ipynb")
    assert result == expected.resolve()
    assert not result.exists()


@pytest.mark.parametrize(
    "name", ["/tmp/outside.ipynb", "../outside", "examples/../../outside"]
)
def test_notebook_jail_rejects_absolute_and_parent_names(tmp_path, name):
    with pytest.raises(notebooks.NotebookError) as exc:
        notebooks.notebook_path(tmp_path, name)
    assert exc.value.code == "bad-name"


@pytest.mark.parametrize("inside", [True, False])
def test_notebook_symlink_keeps_checked_alias_or_rejects_sibling(tmp_path, inside):
    directory = notebooks.ensure_notebooks_dir(tmp_path)
    target_dir = directory if inside else directory.with_name("notebooks-copy")
    target_dir.mkdir(exist_ok=True)
    target = target_dir / "target.ipynb"
    target.write_text("notebook bytes")
    (directory / "linked.ipynb").symlink_to(target)
    if inside:
        result = notebooks.notebook_path(tmp_path, "linked")
        assert result == directory.resolve() / "linked.ipynb"
        assert result.read_text() == "notebook bytes"
    else:
        with pytest.raises(notebooks.NotebookError) as exc:
            notebooks.notebook_path(tmp_path, "linked")
        assert exc.value.code == "bad-name"


@pytest.mark.parametrize("resolver", [resolve_static_file, resolve_tetravox_file])
def test_asset_jail_accepts_nested_relative_path(tree, resolver):
    root, inside, _ = tree
    assert resolver(str(root), "nested/target.txt") == inside.resolve()


@pytest.mark.parametrize("inside", [True, False])
def test_notebook_examples_directory_symlink_stays_jailed(tmp_path, inside):
    directory = notebooks.ensure_notebooks_dir(tmp_path)
    target_dir = directory / "actual-examples" if inside else tmp_path / "outside"
    target_dir.mkdir()
    target = target_dir / "demo.ipynb"
    target.write_text("example bytes")
    (directory / "examples").symlink_to(target_dir, target_is_directory=True)
    if inside:
        assert notebooks.notebook_path(tmp_path, "examples/demo") == target.resolve()
    else:
        with pytest.raises(notebooks.NotebookError) as exc:
            notebooks.notebook_path(tmp_path, "examples/demo")
        assert exc.value.code == "bad-name"


@pytest.mark.parametrize("action", ["read", "save", "delete"])
@pytest.mark.parametrize("inside", [True, False])
def test_notebook_alias_io_preserves_target_and_rejects_outward_links(
    tmp_path, action, inside
):
    import nbformat

    directory = notebooks.ensure_notebooks_dir(tmp_path)
    target_dir = directory if inside else tmp_path / "outside"
    target_dir.mkdir(exist_ok=True)
    target = target_dir / "original.ipynb"
    original = nbformat.v4.new_notebook(
        cells=[nbformat.v4.new_markdown_cell("original")]
    )
    nbformat.write(original, target)
    original_bytes = target.read_bytes()
    alias = directory / "alias.ipynb"
    alias.symlink_to(target)
    replacement = nbformat.v4.new_notebook(
        cells=[nbformat.v4.new_markdown_cell("replacement")]
    )

    def operate():
        if action == "read":
            return notebooks.read_notebook(tmp_path, "alias")
        if action == "save":
            return notebooks.write_notebook(tmp_path, "alias", dict(replacement))
        return notebooks.delete_notebook(tmp_path, "alias")

    if not inside:
        with pytest.raises(notebooks.NotebookError) as exc:
            operate()
        assert exc.value.code == "bad-name"
        assert alias.is_symlink()
    elif action == "read":
        assert operate()["cells"][0]["source"] == "original"
        assert alias.is_symlink()
    elif action == "save":
        assert operate() == directory.resolve() / "alias.ipynb"
        assert not alias.is_symlink()
        assert nbformat.read(alias, as_version=4).cells[0].source == "replacement"
    else:
        operate()
        assert not alias.is_symlink()
        assert not alias.exists()
    assert target.read_bytes() == original_bytes


@pytest.mark.parametrize(
    "operation", ["ensure", "list", "seed", "read", "write", "delete"]
)
def test_notebook_directory_cannot_redirect_outside_project(tmp_path, operation):
    import nbformat

    project = tmp_path / "project"
    directory = project / "code/ti-toolbox/notebooks"
    directory.parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    original = outside / "existing.ipynb"
    nbformat.write(nbformat.v4.new_notebook(), original)
    original_bytes = original.read_bytes()
    directory.symlink_to(outside, target_is_directory=True)
    actions = {
        "ensure": lambda: notebooks.ensure_notebooks_dir(project),
        "list": lambda: notebooks.list_notebooks(project),
        "seed": lambda: notebooks.seed_example(project),
        "read": lambda: notebooks.read_notebook(project, "existing"),
        "write": lambda: notebooks.write_notebook(
            project, "new", dict(nbformat.v4.new_notebook())
        ),
        "delete": lambda: notebooks.delete_notebook(project, "existing"),
    }
    with pytest.raises(notebooks.NotebookError) as exc:
        actions[operation]()
    assert exc.value.code == "bad-name"
    assert original.read_bytes() == original_bytes
    assert sorted(p.name for p in outside.iterdir()) == ["existing.ipynb"]


def test_notebook_predictable_temp_symlink_is_untouched(tmp_path):
    import nbformat

    directory = notebooks.ensure_notebooks_dir(tmp_path)
    outside = tmp_path / "outside-sentinel"
    outside.write_bytes(b"untouched")
    temporary = directory / "new.ipynb.tmp"
    temporary.symlink_to(outside)
    notebooks.write_notebook(tmp_path, "new", dict(nbformat.v4.new_notebook()))
    assert outside.read_bytes() == b"untouched"
    assert temporary.is_symlink()
    assert (directory / "new.ipynb").is_file()


@pytest.mark.parametrize("exists", [True, False])
def test_example_stamp_outward_symlink_blocks_delete_before_mutation(tmp_path, exists):
    notebooks.seed_example(tmp_path)
    directory = notebooks.notebooks_dir(tmp_path)
    example = directory / notebooks.EXAMPLE_NAME
    original = example.read_bytes()
    outside = tmp_path / "outside-stamp"
    if exists:
        outside.write_bytes(b"untouched")
    (directory / "examples/.seeded").symlink_to(outside)
    with pytest.raises(notebooks.NotebookError) as exc:
        notebooks.delete_notebook(tmp_path, notebooks.EXAMPLE_NAME)
    assert exc.value.code == "bad-name"
    assert example.read_bytes() == original
    assert outside.read_bytes() == b"untouched" if exists else not outside.exists()


@pytest.mark.parametrize("failure", ["collision", "replace"])
def test_notebook_atomic_failure_removes_only_owned_temp(
    tmp_path, monkeypatch, failure
):
    import nbformat

    directory = notebooks.ensure_notebooks_dir(tmp_path)
    target = notebooks.write_notebook(
        tmp_path, "original", dict(nbformat.v4.new_notebook())
    )
    original = target.read_bytes()
    monkeypatch.setattr(notebooks.secrets, "token_hex", lambda _: "fixed")
    temporary = directory / ".notebook-fixed.tmp"
    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"untouched")
    if failure == "collision":
        temporary.symlink_to(sentinel)
    else:

        def fail_replace(*args):
            raise OSError("authored replace failure")

        monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError):
        notebooks.write_notebook(tmp_path, "original", dict(nbformat.v4.new_notebook()))
    assert target.read_bytes() == original
    assert sentinel.read_bytes() == b"untouched"
    assert temporary.is_symlink() if failure == "collision" else not temporary.exists()


def test_inside_project_notebook_directory_link_preserves_example_lifecycle(tmp_path):
    project = tmp_path / "project"
    directory = project / "code/ti-toolbox/notebooks"
    directory.parent.mkdir(parents=True)
    actual = project / "actual-notebooks"
    actual.mkdir()
    directory.symlink_to(actual, target_is_directory=True)
    assert notebooks.seed_example(project)
    assert notebooks.read_notebook(project, notebooks.EXAMPLE_NAME)["cells"]
    assert any(
        entry.name == notebooks.EXAMPLE_NAME
        for entry in notebooks.list_notebooks(project)
    )
    notebooks.delete_notebook(project, notebooks.EXAMPLE_NAME)
    assert not notebooks.seed_example(project)
    assert (actual / "examples/.seeded").is_file()


def test_notebook_listing_skips_outward_examples_and_leaf_links(tmp_path):
    directory = notebooks.ensure_notebooks_dir(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.ipynb").write_text("private")
    (directory / "examples").symlink_to(outside, target_is_directory=True)
    (directory / "private.ipynb").symlink_to(outside / "private.ipynb")
    assert notebooks.list_notebooks(tmp_path) == []
