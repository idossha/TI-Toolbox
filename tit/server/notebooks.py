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
"""

from __future__ import annotations

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
#: but a wider jail to defend — ``examples/getting-started.ipynb`` is a real
#: path the maintainer named, not the first of an open set.
EXAMPLES_DIR = "examples"

#: The example notebook's own name, seeded on first listing.
EXAMPLE_NAME = f"{EXAMPLES_DIR}/getting-started{NOTEBOOK_SUFFIX}"


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
    ``examples/getting-started.ipynb`` are all fine; ``../escape``, ``a/b`` and
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


def seed_example(project_root: str | Path) -> bool:
    """Write the example notebook if it is not there. True when it was written.

    Seeded on first listing rather than shipped in the image, because it names
    *this* project: the cells resolve the project's own subjects and plot the
    first TI field it actually has. A user who deletes it is not given it back
    — it reappears only in a project that has never had one.
    """
    path = notebook_path(project_root, EXAMPLE_NAME)
    if path.exists() or _example_was_deleted(project_root):
        return False
    write_notebook(project_root, EXAMPLE_NAME, example_notebook())
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


def example_notebook() -> dict[str, Any]:
    """The worked example: `examples/getting-started.ipynb`.

    Four code cells, each proving something the previous one could not. It ends
    on a matplotlib figure and two DataFrames deliberately: a notebook whose
    only output is printed text has not shown that rich outputs work, and rich
    outputs are half of why a notebook beats a script.

    Every cell is asserted to run green in the container by
    ``tests/e2e/real/notebooks.spec.ts``.
    """
    import nbformat

    notebook = nbformat.v4.new_notebook()
    notebook["metadata"] = _METADATA
    notebook["cells"] = [
        nbformat.v4.new_markdown_cell(EXAMPLE_INTRO),
        nbformat.v4.new_code_cell(EXAMPLE_ENV),
        nbformat.v4.new_code_cell(EXAMPLE_TABLE),
        nbformat.v4.new_code_cell(EXAMPLE_CALC),
        nbformat.v4.new_code_cell(EXAMPLE_PLOT),
    ]
    return dict(notebook)


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
            "plotted and tabulated — open `examples/getting-started.ipynb`."
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
        _atomic_text_write(
            stamp, "the example notebook was deleted; do not seed it again\n"
        )


# ---------------------------------------------------------------------------
# The example notebook's cells.
#
# They live here as plain strings rather than as a committed .ipynb because the
# notebook is *written into the user's project*, and a file the app writes is
# better generated from one source than copied from a fixture that then drifts
# from the API it calls. Every name they use is exercised by
# ``tests/test_notebook_files.py`` and run for real by the container e2e.
# ---------------------------------------------------------------------------

_METADATA = {
    "kernelspec": {
        "name": "simnibs",
        "display_name": "SimNIBS + TI-Toolbox",
        "language": "python",
    },
    "language_info": {"name": "python"},
}

EXAMPLE_INTRO = """# Getting started with TI-Toolbox notebooks

This notebook runs on the container's **SimNIBS Python**, so `tit`, `simnibs`, `numpy`,
`nibabel`, `pandas` and `matplotlib` are all importable with *nothing to install*.

## What it shows

1. The environment — the project this kernel is bound to, and the SimNIBS it runs.
2. This project's subjects and simulations, as a `pandas` table.
3. A real `tit` computation: the temporal-interference envelope, `tit.calc.get_TI_vectors`.
4. A real field from disk, summarised and plotted with `matplotlib`.

## The maths it computes

Two carriers at nearby frequencies produce an envelope whose amplitude at a point is

$$
|\\vec{E}_{\\mathrm{TI}}| = 2\\,\\bigl|\\,\\vec{E}_2\\,\\bigr| \\quad\\text{when}\\quad
|\\vec{E}_2| < |\\vec{E}_1|\\cos\\theta,
$$

and $2\\,|\\vec{E}_1 \\times \\vec{E}_2| / |\\vec{E}_1 - \\vec{E}_2|$ otherwise — which is what
`get_TI_vectors` evaluates per voxel.

| step | module | cost |
| --- | --- | --- |
| environment | `tit`, `simnibs` | instant |
| catalogue | `tit.catalog` | instant |
| envelope | `tit.calc` | instant |
| field summary | `nibabel`, `matplotlib` | a second or two |

See the [TI-Toolbox wiki](https://idossha.github.io/TI-Toolbox/) for the full scripting API.
Press **⇧↵** in a cell to run it; **A**/**B** insert, **DD** deletes, **M** makes a cell markdown.
"""

EXAMPLE_ENV = """# 1 — the environment. Nothing was installed for this: the kernel IS the
# container's SimNIBS Python, the same interpreter every TI-Toolbox job runs on.
import sys

import simnibs

from tit import catalog, get_path_manager

pm = get_path_manager()
print("project    ", pm.project_dir)
print("python     ", ".".join(str(n) for n in sys.version_info[:3]))
print("simnibs    ", simnibs.__version__)
print("subjects   ", catalog.subject_ids(pm))
"""

EXAMPLE_TABLE = """# 2 — what this project holds, as a table. A DataFrame's HTML repr renders as a
# real table here, which is why a notebook beats a printed dict.
import os

import pandas as pd

rows = [
    {
        "subject": sid,
        "head model": os.path.isdir(pm.m2m(sid)),
        "simulations": len(pm.list_simulations(sid)),
        "names": ", ".join(pm.list_simulations(sid)) or "—",
    }
    for sid in catalog.subject_ids(pm)
]
pd.DataFrame(rows).set_index("subject")
"""

EXAMPLE_CALC = """# 3 — a real TI-Toolbox computation. `tit.calc.get_TI_vectors` is the toolbox's
# own envelope maths: the carrier's two channel fields in, the temporal-interference
# envelope out, per voxel.
import numpy as np

from tit import calc

# One carrier's two channels: orthogonal 1 V/m, then rotated towards each other,
# then exactly aligned.
E1 = np.array([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
E2 = np.array([[0.0, 1.0, 0.0], [0.5, 0.5, 0.0], [1.0, 0.0, 0.0]])

# `fields` is a LIST — [E_1a, E_1b, ...], two consecutive entries per carrier.
# Passing them as two positional arguments makes the second one `psi`.
envelope = calc.get_TI_vectors([E1, E2])
pd.DataFrame(
    {
        "|E1|": np.linalg.norm(E1, axis=1),
        "|E2|": np.linalg.norm(E2, axis=1),
        "|TI envelope|": np.linalg.norm(envelope, axis=1),
    }
)
"""

EXAMPLE_PLOT = """# 4 — a real field on disk, summarised and drawn.
#
# `%matplotlib inline` is not decoration. Without it this kernel's display
# formatter offers a Figure only as `text/plain` — the cell prints
# `<Figure size 900x340>` and no picture is ever produced. The magic registers
# matplotlib_inline, which is what makes `image/png` part of the bundle.
%matplotlib inline

import glob

import matplotlib.pyplot as plt
import nibabel as nib

subject = next((s for s in catalog.subject_ids(pm) if pm.list_simulations(s)), None)
simulation = pm.list_simulations(subject)[0] if subject else None
pattern = os.path.join(pm.simulations(subject), simulation, "TI", "niftis", "*TI_max.nii.gz")
candidates = sorted(glob.glob(pattern))
print(f"{subject} / {simulation}:", os.path.basename(candidates[0]) if candidates else "no TI volume")

volume = nib.load(candidates[0])
field = np.asarray(volume.dataobj, dtype=np.float32)
inside = field[field > 0]
print(f"{inside.size:,} non-zero voxels   mean {inside.mean():.4f}   p99 {np.percentile(inside, 99):.4f} V/m")

figure, (left, right) = plt.subplots(1, 2, figsize=(9, 3.4))
left.hist(inside, bins=80, color="#1f5bd7")
left.set(title="TI field, non-zero voxels", xlabel="|TI| (V/m)", ylabel="voxels")
slice_index = field.shape[2] // 2
right.imshow(np.rot90(field[:, :, slice_index]), cmap="magma")
right.set(title=f"axial slice z={slice_index}")
right.axis("off")
figure.tight_layout()
# No trailing `figure` here: the inline backend already draws it at the end of
# the cell, and returning it as well puts the SAME picture in the notebook
# twice — once as display_data, once as the execute_result.
plt.show()
"""
