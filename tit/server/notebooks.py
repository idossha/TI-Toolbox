"""Notebook files under ``code/ti-toolbox/notebooks/`` — read, write, list.

The ``.ipynb`` on disk **is** the document (SUNA docs/ARCHITECTURE.md §16.3).
A notebook the app opens and saves untouched must produce an empty git diff,
or every notebook in a project becomes a merge conflict the moment two tools
disagree about whitespace. SUNA reimplements nbformat's serializer in
TypeScript because its notebook model lives in the renderer; here the file
never leaves the container, so ``nbformat`` itself does the reading and
writing and the question does not arise.

Everything lives in one directory, ``<project>/code/ti-toolbox/notebooks``,
which is also where the pipeline's exported notebooks land. Names are a
single path segment: there are no subdirectories, because a flat list is what
the UI shows and a traversal is the only thing a name could otherwise buy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Relative to the project root. The pipeline exports here too.
NOTEBOOK_SUBDIR = Path("code") / "ti-toolbox" / "notebooks"

NOTEBOOK_SUFFIX = ".ipynb"

#: A notebook name is one path segment of ordinary characters. Anything with a
#: separator, a leading dot or a ``..`` in it is refused rather than sanitised
#: — silently rewriting a name is how a save lands somewhere the author never
#: looked.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,127}$")


class NotebookError(ValueError):
    """A notebook could not be named, found, read or written."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def notebooks_dir(project_root: str | Path) -> Path:
    """The notebook directory for a project (not created)."""
    return Path(project_root) / NOTEBOOK_SUBDIR


def ensure_notebooks_dir(project_root: str | Path) -> Path:
    directory = notebooks_dir(project_root)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def normalise_name(name: str) -> str:
    """A caller's name as the file name it maps to, or raise.

    ``analysis``, ``analysis.ipynb`` and ``Analysis 2.ipynb`` are all fine;
    ``../escape``, ``a/b`` and ``.hidden`` are not.
    """
    candidate = (name or "").strip()
    if candidate.endswith(NOTEBOOK_SUFFIX):
        candidate = candidate[: -len(NOTEBOOK_SUFFIX)]
    if not _SAFE_NAME.match(candidate):
        raise NotebookError(
            "bad-name",
            f"{name!r} is not a usable notebook name. Use letters, digits, spaces, "
            f"'.', '_' or '-', and no directory separators.",
        )
    return candidate + NOTEBOOK_SUFFIX


def notebook_path(project_root: str | Path, name: str) -> Path:
    """Where a notebook of this name lives. Never outside the directory."""
    directory = notebooks_dir(project_root)
    path = directory / normalise_name(name)
    # Belt and braces: the name regex already forbids a separator, but the
    # jail is the thing that must hold, so it is checked rather than assumed.
    try:
        path.resolve().relative_to(directory.resolve(strict=False))
    except ValueError:
        raise NotebookError("bad-name", f"{name!r} resolves outside the notebook directory.") from None
    return path


@dataclass(frozen=True)
class NotebookEntry:
    """One notebook as the list shows it."""

    name: str
    size: int
    modified: float

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "size": self.size, "modified": self.modified}


def list_notebooks(project_root: str | Path) -> list[NotebookEntry]:
    """Every notebook in the directory, newest first. Missing dir → empty."""
    directory = notebooks_dir(project_root)
    if not directory.is_dir():
        return []
    entries: list[NotebookEntry] = []
    for path in sorted(directory.glob(f"*{NOTEBOOK_SUFFIX}")):
        try:
            info = path.stat()
        except OSError:  # pragma: no cover - raced with a delete
            continue
        entries.append(NotebookEntry(name=path.name, size=info.st_size, modified=info.st_mtime))
    entries.sort(key=lambda entry: entry.modified, reverse=True)
    return entries


def starter_source(project_root: str | Path) -> str:
    """The first cell of a new notebook.

    The maintainer's ask was that "the TI-Toolbox environment is automatically
    loaded". It is — the kernel is SimNIBS Python with ``tit`` importable — but
    a blank first cell would leave the author to discover that. So a new
    notebook opens already holding the two lines that prove it, against *this*
    project rather than a generic example.
    """
    return (
        "# TI-Toolbox is already on this kernel's path — this cell proves it.\n"
        "from tit import get_path_manager\n"
        "\n"
        "pm = get_path_manager()\n"
        f"print('project:', pm.project_dir)  # {project_root}\n"
        "print('subjects:', pm.list_all_subjects())\n"
    )


def new_notebook(project_root: str | Path, kernel_name: str = "simnibs") -> dict[str, Any]:
    """An empty nbformat v4 notebook with the starter cell already in it."""
    import nbformat

    notebook = nbformat.v4.new_notebook()
    notebook["metadata"] = {
        "kernelspec": {
            "name": kernel_name,
            "display_name": "SimNIBS + TI-Toolbox",
            "language": "python",
        },
        "language_info": {"name": "python"},
    }
    notebook["cells"] = [
        nbformat.v4.new_markdown_cell(
            "# New TI-Toolbox notebook\n\n"
            "This kernel is the container's SimNIBS Python, so `tit`, `simnibs`, "
            "`numpy` and `nibabel` are all importable with nothing to install."
        ),
        nbformat.v4.new_code_cell(starter_source(project_root)),
    ]
    return dict(notebook)


def read_notebook(project_root: str | Path, name: str) -> dict[str, Any]:
    """Read one notebook as plain JSON-able nbformat v4."""
    import nbformat

    path = notebook_path(project_root, name)
    if not path.is_file():
        raise NotebookError("not-found", f"No notebook named {name!r}.")
    try:
        notebook = nbformat.read(str(path), as_version=4)
    except Exception as error:
        raise NotebookError("bad-notebook", f"{path.name} is not a readable notebook: {error}") from error
    return dict(notebook)


def write_notebook(project_root: str | Path, name: str, content: dict[str, Any]) -> Path:
    """Write one notebook, validating it first.

    Validation is not ceremony: what arrives here came from a browser, and a
    notebook that fails ``nbformat.validate`` is one every other tool in the
    project — Jupyter, nbconvert, git's diff driver — will then refuse to open.
    Better to reject the save than to write the file that breaks them.
    """
    import nbformat

    path = notebook_path(project_root, name)
    ensure_notebooks_dir(project_root)
    try:
        notebook = nbformat.from_dict(content)
        nbformat.validate(notebook)
    except Exception as error:
        raise NotebookError("invalid", f"That is not a valid notebook: {error}") from error
    # Written whole through a temporary file in the same directory: a save
    # interrupted halfway must not leave the author with a truncated .ipynb.
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            nbformat.write(notebook, handle, version=4)
        temporary.replace(path)
    finally:
        if temporary.exists():  # pragma: no cover - only on a failed write
            temporary.unlink(missing_ok=True)
    return path


def delete_notebook(project_root: str | Path, name: str) -> None:
    path = notebook_path(project_root, name)
    if not path.is_file():
        raise NotebookError("not-found", f"No notebook named {name!r}.")
    path.unlink()
