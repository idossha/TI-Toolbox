"""Notebook files under ``code/ti-toolbox/notebooks/`` — read, write, list.

The ``.ipynb`` on disk **is** the document (SUNA docs/dev/ARCHITECTURE.md §16.3).
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

The worked example
------------------
``examples/example_workflow.ipynb`` is a byte-for-byte copy of the packaged
``tit/server/examples/example_workflow.ipynb`` (the repository's
``examples/notebooks/example_workflow.ipynb`` is a symlink to that same file, so
there is exactly one source). :func:`seed_example` writes it on the first
listing and records the packaged file's sha256 in ``examples/.seeded``. On later
listings it re-copies the notebook only when the packaged file has changed
*and* the project's copy still matches the hash that was recorded — a copy the
user edited is theirs and is never overwritten. A deleted example is not given
back: deleting it writes ``deleted`` into the stamp instead of a hash.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
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

#: The one subdirectory a name may carry. There is exactly one because the UI
#: shows a flat list and because a general subdirectory grammar buys nothing
#: but a wider jail to defend — ``examples/example_workflow.ipynb`` is a real
#: path the maintainer named, not the first of an open set.
EXAMPLES_DIR = "examples"

#: The example notebook's own name, seeded on first listing.
EXAMPLE_NAME = f"{EXAMPLES_DIR}/example_workflow{NOTEBOOK_SUFFIX}"

#: The packaged source of the example (``pyproject.toml`` package-data).
EXAMPLE_SOURCE = Path(__file__).resolve().parent / "examples" / "example_workflow.ipynb"

#: Stamp content meaning "the user deleted the example; never seed it again".
_DELETED = "deleted"


class NotebookError(ValueError):
    """A notebook could not be named, found, read or written."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def notebooks_dir(project_root: str | Path) -> Path:
    """The notebook directory for a project (not created)."""
    root = os.path.realpath(project_root)
    directory = os.path.realpath(os.path.join(root, NOTEBOOK_SUBDIR))
    if directory == root or directory.startswith(root.rstrip(os.sep) + os.sep):
        return Path(directory)
    raise NotebookError("bad-name", "Notebook directory resolves outside the project.")


def ensure_notebooks_dir(project_root: str | Path) -> Path:
    directory = notebooks_dir(project_root)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def normalise_name(name: str) -> str:
    """A caller's name as the file name it maps to, or raise.

    ``analysis``, ``analysis.ipynb``, ``Analysis 2.ipynb`` and
    ``examples/example_workflow.ipynb`` are all fine; ``../escape``, ``a/b`` and
    ``.hidden`` are not. The ``examples/`` prefix is the only directory a name
    may carry (:data:`EXAMPLES_DIR`).
    """
    candidate = (name or "").strip()
    prefix = ""
    if candidate.startswith(f"{EXAMPLES_DIR}/"):
        prefix = f"{EXAMPLES_DIR}/"
        candidate = candidate[len(prefix) :]
    if candidate.endswith(NOTEBOOK_SUFFIX):
        candidate = candidate[: -len(NOTEBOOK_SUFFIX)]
    if not _SAFE_NAME.match(candidate):
        raise NotebookError(
            "bad-name",
            f"{name!r} is not a usable notebook name. Use letters, digits, spaces, "
            f"'.', '_' or '-', and no directory separators.",
        )
    return prefix + candidate + NOTEBOOK_SUFFIX


def notebook_path(project_root: str | Path, name: str) -> Path:
    """Where a notebook of this name lives. Never outside the directory."""
    return _checked_notebook_entry(project_root, normalise_name(name))


def _checked_notebook_entry(project_root: str | Path, name: str) -> Path:
    """Check a trusted relative entry, preserving its leaf for replace/unlink."""
    directory = os.path.realpath(notebooks_dir(project_root))
    named_path = os.path.join(directory, name)
    # Resolve parent symlinks, but retain the leaf: save/delete must replace or
    # unlink a notebook alias, not mutate the file that alias points to.
    parent = os.path.realpath(os.path.dirname(named_path))
    entry = os.path.abspath(os.path.join(parent, os.path.basename(named_path)))
    if entry == directory or entry.startswith(directory.rstrip(os.sep) + os.sep):
        target = os.path.realpath(entry)
        # Reads follow the leaf, so its target must independently stay jailed.
        if target == directory or target.startswith(directory.rstrip(os.sep) + os.sep):
            return Path(entry)
    raise NotebookError(
        "bad-name", f"{name!r} resolves outside the notebook directory."
    )


@dataclass(frozen=True)
class NotebookEntry:
    """One notebook as the list shows it."""

    name: str
    size: int
    modified: float
    #: Lives under ``examples/``. The list sorts these last and labels them.
    example: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "size": self.size,
            "modified": self.modified,
            "example": self.example,
        }


def seed_example(project_root: str | Path, source: Path = EXAMPLE_SOURCE) -> bool:
    """Copy the packaged example into the project. True when it was written.

    Written when absent, and re-written when *source* has changed since the
    hash recorded in ``examples/.seeded`` **and** the project's copy is still
    byte-identical to that recorded hash (i.e. the user never edited it). A
    copy the user edited, or one seeded before the stamp carried a hash, is
    left alone; a deleted example stays deleted (see the module docstring).
    """
    path = notebook_path(project_root, EXAMPLE_NAME)
    stamp = _example_stamp(project_root)
    recorded = stamp.read_text(encoding="utf-8").strip() if stamp.is_file() else None
    if recorded == _DELETED:
        return False
    packaged = source.read_bytes()
    digest = hashlib.sha256(packaged).hexdigest()
    if path.exists():
        if recorded is None or recorded == digest:
            return False
        if hashlib.sha256(path.read_bytes()).hexdigest() != recorded:
            return False  # the user edited their copy
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_text_write(path, packaged.decode("utf-8"))
    _atomic_text_write(stamp, digest + "\n")
    return True


def _example_stamp(project_root: str | Path) -> Path:
    return _checked_notebook_entry(project_root, f"{EXAMPLES_DIR}/.seeded")


def _example_was_deleted(project_root: str | Path) -> bool:
    return _example_stamp(project_root).exists()


def list_notebooks(project_root: str | Path) -> list[NotebookEntry]:
    """Every notebook, newest first. Missing dir → empty.

    Two levels: the flat directory the user writes into, and ``examples/``.
    Nothing recurses further, because :func:`normalise_name` cannot name
    anything deeper and a listing that shows what cannot be opened is a lie.
    """
    directory = notebooks_dir(project_root)
    if not directory.is_dir():
        return []
    paths = sorted(directory.glob(f"*{NOTEBOOK_SUFFIX}"))
    paths += sorted((directory / EXAMPLES_DIR).glob(f"*{NOTEBOOK_SUFFIX}"))
    entries: list[NotebookEntry] = []
    for path in paths:
        name = (
            path.name if path.parent == directory else f"{path.parent.name}/{path.name}"
        )
        try:
            info = notebook_path(project_root, name).stat()
        except (OSError, NotebookError):  # stale file or outward leaf/parent link
            continue
        entries.append(
            NotebookEntry(
                name=name,
                size=info.st_size,
                modified=info.st_mtime,
                example=name.startswith(f"{EXAMPLES_DIR}/"),
            )
        )
    entries.sort(key=lambda entry: (entry.example, -entry.modified))
    return entries


def starter_source() -> str:
    """The first cell of a new notebook.

    The maintainer's ask was that "the TI-Toolbox environment is automatically
    loaded". It is — the kernel is SimNIBS Python with ``tit`` importable — but
    a blank first cell would leave the author to discover that. So a new
    notebook opens holding a cell that *demonstrates* it and runs green: the
    path manager, the project's subjects, the SimNIBS version, and the two
    module imports every scripted workflow starts from.

    Every name in here is checked by ``tests/test_notebook_files.py`` against
    the real ``tit`` API, because the first version of this cell called
    ``pm.project_root``, which does not exist — a starter cell that raises on
    its first run is worse than no starter cell at all.
    """
    return (
        "# TI-Toolbox is already on this kernel's path — this cell proves it,\n"
        "# and it is the block every scripted workflow starts from.\n"
        "import simnibs\n"
        "\n"
        "from tit import catalog, get_path_manager\n"
        "from tit.analyzer import Analyzer\n"
        "from tit.sim import SimulationConfig\n"
        "\n"
        "pm = get_path_manager()\n"
        "subjects = catalog.subject_ids(pm)\n"
        "\n"
        "print('project ', pm.project_dir)\n"
        "print('simnibs ', simnibs.__version__)\n"
        "print('subjects', subjects)\n"
        "for sid in subjects:\n"
        "    print(f'  {sid}: {pm.list_simulations(sid)}')\n"
    )


def new_notebook(project_root: str | Path | None = None) -> dict[str, Any]:
    """An empty nbformat v4 notebook with the starter cell already in it."""
    import nbformat

    notebook = nbformat.v4.new_notebook()
    notebook["metadata"] = _METADATA
    notebook["cells"] = [
        nbformat.v4.new_markdown_cell(
            "# New TI-Toolbox notebook\n\n"
            "This kernel is the container's **SimNIBS Python**, so `tit`, `simnibs`, `numpy`, "
            "`nibabel`, `pandas` and `matplotlib` are all importable with nothing to install.\n\n"
            "Run the cell below with **⇧↵**. For a worked example — a real field summarised, "
            "plotted and tabulated — open `examples/example_workflow.ipynb`."
        ),
        nbformat.v4.new_code_cell(starter_source()),
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
    # `examples/` is a real directory the write may be the first to need.
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        notebook = nbformat.from_dict(content)
        nbformat.validate(notebook)
    except Exception as error:
        raise NotebookError(
            "invalid", f"That is not a valid notebook: {error}"
        ) from error
    # Match nbformat.write's trailing newline without opening an untrusted temp path.
    content = nbformat.writes(notebook, version=4)
    if not content.endswith("\n"):
        content += "\n"
    _atomic_text_write(path, content)
    return path


def _atomic_text_write(path: Path, content: str) -> None:
    """Create our own temporary file exclusively; never follow a planted .tmp link."""
    temporary = None
    try:
        candidate = path.with_name(f".notebook-{secrets.token_hex(16)}.tmp")
        # 'x' refuses collisions and retains the ordinary process umask.
        with candidate.open("x", encoding="utf-8") as handle:
            temporary = candidate
            handle.write(content)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def delete_notebook(project_root: str | Path, name: str) -> None:
    path = notebook_path(project_root, name)
    if not path.is_file():
        raise NotebookError("not-found", f"No notebook named {name!r}.")
    # Validate the stamp before deleting anything, so an outward stamp cannot
    # turn a refused request into a partially completed deletion.
    stamp = (
        _example_stamp(project_root) if normalise_name(name) == EXAMPLE_NAME else None
    )
    path.unlink()
    # Deleting the example is a decision, not an accident to be undone by the
    # next listing. The stamp is what makes "seed once" mean once.
    if stamp is not None:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        _atomic_text_write(stamp, _DELETED + "\n")


_METADATA = {
    "kernelspec": {
        "name": "simnibs",
        "display_name": "SimNIBS + TI-Toolbox",
        "language": "python",
    },
    "language_info": {"name": "python"},
}
