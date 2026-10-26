"""Every third-party module tit imports is installed by the ``test`` extra, mocked, or image-only.

What this pins
    CircleCI ``build-and-run-tests`` builds its venv with ``pip install -e '.[test]'``; the
    developer ``.venv`` carries much more. From 1cc4bc3a to 45f47171 (CircleCI #1246-#1265)
    every main build failed 99 tests and errored 3 while the local gate was green:
    ``tit/tools/nifti_to_mesh.py`` imported ``skimage`` at module level and the flex report
    imported ``PIL`` inside a function, and the extra had neither. This guard reads the source
    instead of waiting for CI: every import of a non-stdlib, non-``tit`` module anywhere under
    ``tit/`` must be

    (a) installed by the ``test`` extra of ``pyproject.toml`` (directly, or as a dependency of
        one of its distributions listed in ``_BROUGHT_BY``), or
    (b) one of the packages ``tests/conftest.py`` replaces with a mock (``_MOCK_PACKAGES``), or
    (c) only for an import that does not run when its module is imported -- inside a function,
        under an ``ImportError``/``Exception`` guard, ``TYPE_CHECKING`` or ``__main__`` -- a
        module the image provides and the host suite never imports for real
        (``_IMAGE_ONLY``, each with its reason).

Where the expectations come from
    ``pyproject.toml`` read with ``tomllib``, ``tests/conftest.py`` and every ``tit/**/*.py``
    read with ``ast``; nothing is imported from tit or the conftest. The red cases plant a
    module in a temporary tree, or hand the guard the ``test`` extra CircleCI #1265 installed
    (copied from ``pyproject.toml`` at ce506e0b), whose offending lines are located by plain
    text search, not by the scanner under test.

How to run it
    ``python -m pytest tests/test_test_extra_imports.py -q -p no:cacheprovider``

Deliberately elsewhere
    Whether a mocked package's *submodules* resolve (the conftest's business), and the
    image's own dependency set (``container/blueprint/Dockerfile.ti-toolbox``).
"""

from __future__ import annotations

import ast
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Import name -> distribution name, where the two differ.
_DISTRIBUTION_OF = {
    "PIL": "pillow",
    "skimage": "scikit-image",
}

#: Modules a ``test``-extra distribution installs as its own dependency -> that distribution.
_BROUGHT_BY = {
    "starlette": "fastapi",
    "pydantic": "fastapi",
    "certifi": "requests",
}

#: Modules the image provides that tit imports only lazily, and why the host never needs them.
_IMAGE_ONLY = {
    "bpy": "Blender's own module; the Blender exporters run inside Blender's Python",
    "mathutils": "Blender's own module; the Blender exporters run inside Blender's Python",
    "dipy": "QSIRecon's DTI extraction (tit/pre/qsi) runs in the image",
    "jupyter_client": "notebook kernels are started by the server in the image",
    "numba": "optional JIT kernel; tit falls back to NumPy when it is not importable",
    "seaborn": "statistics figures are drawn in the image; host tests stub the plot",
    "stl": "numpy-stl writes nifti_to_mesh's STL output in the image",
    "threadpoolctl": "caps BLAS threads in ex-search workers, under an import guard",
}

#: The ``test`` extra CircleCI #1265 (45f47171) installed, from ``git show
#: ce506e0b:pyproject.toml``: no Pillow, no scikit-image.
_EXTRA_OF_CI_1265 = """
[project.optional-dependencies]
test = [
  "pytest>=8", "pytest-cov>=5", "numpy>=1.26", "scipy>=1.11", "nibabel>=5",
  "fastapi>=0.110", "uvicorn>=0.30", "httpx>=0.27", "PyYAML>=6", "requests>=2.31",
  "psutil>=5.9", "nbformat>=5.1.4", "jsonschema>=4", "websocket-client>=1.7",
]
"""

_IMPORT_GUARDS = {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}


@dataclass(frozen=True)
class Import:
    """One import statement of a third-party top-level module."""

    module: str
    path: str  # relative to the scanned root, POSIX separators
    line: int
    eager: bool  # runs when its module is imported


class _Visitor(ast.NodeVisitor):
    """Collect imports, marking those that do not run at import time."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.deferred = 0
        self.found: list[Import] = []

    def _deferred(self, nodes) -> None:  # noqa: ANN001 - a list of statements
        self.deferred += 1
        for node in nodes:
            self.visit(node)
        self.deferred -= 1

    def visit_FunctionDef(self, node: ast.AST) -> None:
        self._deferred(node.body)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Try(self, node: ast.Try) -> None:
        guarded = any(
            handler.type is None
            or any(
                isinstance(name, ast.Name) and name.id in _IMPORT_GUARDS
                for name in ast.walk(handler.type)
            )
            for handler in node.handlers
        )
        if guarded:
            self._deferred(node.body)
        else:
            for stmt in node.body:
                self.visit(stmt)
        for stmt in [*node.handlers, *node.orelse, *node.finalbody]:
            self.visit(stmt)

    def visit_If(self, node: ast.If) -> None:
        test = ast.unparse(node.test)
        if "TYPE_CHECKING" in test or ("__name__" in test and "__main__" in test):
            self._deferred(node.body)
            for stmt in node.orelse:
                self.visit(stmt)
        else:
            self.generic_visit(node)

    def _record(self, dotted: str, node: ast.stmt) -> None:
        top = dotted.split(".")[0]
        if top in sys.stdlib_module_names or top in {"tit", "__future__"}:
            return
        self.found.append(Import(top, self.path, node.lineno, self.deferred == 0))

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._record(alias.name, node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level == 0 and node.module:
            self._record(node.module, node)


def imports_in(source: str, path: str) -> list[Import]:
    """Every third-party import in one file's source."""
    visitor = _Visitor(path)
    visitor.visit(ast.parse(source, path))
    return visitor.found


def scan(root: Path) -> tuple[int, list[Import]]:
    """``(files scanned, imports)`` over ``root/tit/**/*.py``."""
    files = sorted((root / "tit").rglob("*.py"))
    found: list[Import] = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        found.extend(imports_in(path.read_text(encoding="utf-8"), rel))
    return len(files), found


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def extra_distributions(pyproject_text: str) -> set[str]:
    """The normalised distribution names of ``[project.optional-dependencies].test``."""
    requirements = tomllib.loads(pyproject_text)["project"]["optional-dependencies"][
        "test"
    ]
    names = set()
    for requirement in requirements:
        match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", requirement)
        if match is None:
            raise ValueError(f"cannot read the requirement {requirement!r}")
        names.add(_normalise(match.group(0)))
    return names


def mocked(conftest_text: str) -> set[str]:
    """Top-level names of the conftest's ``_MOCK_PACKAGES``.

    Raises:
        ValueError: If the conftest no longer assigns a literal ``_MOCK_PACKAGES`` list.
    """
    for node in ast.parse(conftest_text).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "_MOCK_PACKAGES"
            for target in node.targets
        ):
            return {name.split(".")[0] for name in ast.literal_eval(node.value)}
    raise ValueError("tests/conftest.py assigns no literal _MOCK_PACKAGES list")


@functools.cache
def _installed_names() -> dict[str, list[str]]:
    return metadata.packages_distributions()


def _installed_by(module: str, extra: set[str]) -> bool:
    candidates = {
        _DISTRIBUTION_OF.get(module, module),
        *_installed_names().get(module, []),
    }
    if module in _BROUGHT_BY:
        candidates.add(_BROUGHT_BY[module])
    return any(_normalise(name) in extra for name in candidates)


def violations(imports: list[Import], extra: set[str], mocks: set[str]) -> list[str]:
    """``path:line`` lines for every import the host suite could not satisfy."""
    found = []
    for imp in imports:
        if imp.module in mocks or _installed_by(imp.module, extra):
            continue
        if imp.module in _IMAGE_ONLY and not imp.eager:
            continue
        where = "module-level" if imp.eager else "deferred"
        found.append(
            f"{imp.path}:{imp.line}: {where} import of {imp.module!r} is not in the test "
            "extra, not mocked by tests/conftest.py"
            + (
                ""
                if imp.module not in _IMAGE_ONLY
                else ", and image-only modules must be deferred"
            )
        )
    return found


@functools.cache
def _repo_scan() -> tuple[int, list[Import]]:
    """One scan of this checkout, shared by the tests that read it (about 0.5 s)."""
    return scan(ROOT)


def _real_lists() -> tuple[set[str], set[str]]:
    return (
        extra_distributions((ROOT / "pyproject.toml").read_text(encoding="utf-8")),
        mocked((ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")),
    )


def _line_of(path: Path, text: str) -> int:
    """1-based number of the first line containing *text*, by plain search."""
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if text in line:
            return number
    raise AssertionError(f"{text!r} is not in {path}")


def _tree(tmp_path: Path, planted: str) -> Path:
    """A root holding only ``tit/__init__.py`` and ``tit/planted.py``."""
    (tmp_path / "tit").mkdir(parents=True)
    (tmp_path / "tit" / "__init__.py").write_text("")
    (tmp_path / "tit" / "planted.py").write_text(planted)
    return tmp_path


# ── the repository ───────────────────────────────────────────────────────────


def test_every_import_in_tit_is_satisfied_on_the_host() -> None:
    extra, mocks = _real_lists()
    files, imports = _repo_scan()
    # It checked something: the package, its server and its science core.
    assert files > 200, files
    modules = {imp.module for imp in imports}
    assert {"numpy", "fastapi", "psutil", "simnibs", "PIL", "skimage"} <= modules
    assert violations(imports, extra, mocks) == []


def test_every_allowance_is_still_used() -> None:
    """An allowance nothing needs is a hole waiting for the next import."""
    _, imports = _repo_scan()
    modules = {imp.module for imp in imports}
    for table in (_DISTRIBUTION_OF, _BROUGHT_BY, _IMAGE_ONLY):
        assert set(table) <= modules, set(table) - modules


# ── red cases ────────────────────────────────────────────────────────────────


def test_the_extra_ci_1265_installed_names_the_lines_that_failed_there() -> None:
    """With the extra before Pillow and scikit-image, the guard names their imports."""
    _, mocks = _real_lists()
    _, imports = _repo_scan()
    found = violations(imports, extra_distributions(_EXTRA_OF_CI_1265), mocks)
    skimage_line = _line_of(ROOT / "tit/tools/nifti_to_mesh.py", "from skimage")
    pil_line = _line_of(ROOT / "tit/reporting/generators/flex_search.py", "from PIL")
    assert any(
        line.startswith(f"tit/tools/nifti_to_mesh.py:{skimage_line}: ")
        and "'skimage'" in line
        for line in found
    ), found
    assert any(
        line.startswith(f"tit/reporting/generators/flex_search.py:{pil_line}: ")
        and "'PIL'" in line
        for line in found
    ), found
    # Only those two modules are missing from that extra.
    assert {re.search(r"import of '(\w+)'", line).group(1) for line in found} == {
        "PIL",
        "skimage",
    }


def test_a_module_level_import_nobody_installs_is_named_with_file_and_line(
    tmp_path: Path,
) -> None:
    extra, mocks = _real_lists()
    root = _tree(tmp_path, '"""Planted."""\n\nimport os\nimport sklearn.cluster\n')
    _, imports = scan(root)
    assert violations(imports, extra, mocks) == [
        "tit/planted.py:4: module-level import of 'sklearn' is not in the test extra, "
        "not mocked by tests/conftest.py"
    ]


def test_the_planted_import_is_the_only_finding_in_a_copy_of_the_tree(
    tmp_path: Path,
) -> None:
    extra, mocks = _real_lists()
    shutil.copytree(
        ROOT / "tit",
        tmp_path / "tit",
        ignore=lambda folder, names: [
            name
            for name in names
            if not name.endswith(".py") and not (Path(folder) / name).is_dir()
        ],
    )
    (tmp_path / "tit" / "tools" / "planted.py").write_text(
        "import numpy as np\nfrom skimage import measure\n"
    )
    _, imports = scan(tmp_path)
    found = violations(imports, extra_distributions(_EXTRA_OF_CI_1265), mocks)
    assert "tit/tools/planted.py:2: module-level import of 'skimage'" in "\n".join(
        found
    )
    assert violations(imports, extra, mocks) == []


def test_an_image_only_module_is_allowed_deferred_and_refused_at_module_level(
    tmp_path: Path,
) -> None:
    extra, mocks = _real_lists()
    deferred = (
        "def kernel():\n"
        "    import numba\n"
        "\n"
        "try:\n"
        "    import threadpoolctl\n"
        "except ImportError:\n"
        "    threadpoolctl = None\n"
    )
    _, imports = scan(_tree(tmp_path / "a", deferred))
    assert [imp.eager for imp in imports] == [False, False]
    assert violations(imports, extra, mocks) == []

    _, imports = scan(_tree(tmp_path / "b", "import numba\n"))
    assert violations(imports, extra, mocks) == [
        "tit/planted.py:1: module-level import of 'numba' is not in the test extra, "
        "not mocked by tests/conftest.py, and image-only modules must be deferred"
    ]


def test_an_unguarded_try_does_not_defer_an_import(tmp_path: Path) -> None:
    """Only a handler that catches the import's failure makes the import optional."""
    source = "try:\n    import numba\nexcept KeyError:\n    pass\n"
    _, imports = scan(_tree(tmp_path, source))
    assert [imp.eager for imp in imports] == [True]


def test_import_names_map_to_their_distributions(tmp_path: Path) -> None:
    """``PIL`` is Pillow, ``skimage`` scikit-image, ``starlette`` comes with fastapi.

    The extra spells the names the ways pip accepts them (case, ``_`` for ``-``).
    """
    _, mocks = _real_lists()
    source = (
        "import PIL\nfrom skimage import measure\nimport nbformat\nimport starlette\n"
    )
    _, imports = scan(_tree(tmp_path, source))
    extra = extra_distributions(
        '[project.optional-dependencies]\ntest = ["Pillow>=12", "scikit_image", '
        '"NBFormat==5.1.4", "FastAPI>=0.110"]\n'
    )
    assert violations(imports, extra, mocks) == []
    assert [line.split(": ")[0] for line in violations(imports, set(), mocks)] == [
        "tit/planted.py:1",
        "tit/planted.py:2",
        "tit/planted.py:3",
        "tit/planted.py:4",
    ]


def test_a_mocked_package_needs_nothing_else(tmp_path: Path) -> None:
    _, imports = scan(_tree(tmp_path, "import trimesh\nfrom simnibs import mesh_io\n"))
    assert violations(imports, set(), {"trimesh", "simnibs"}) == []
    assert len(violations(imports, set(), set())) == 2


def test_a_conftest_without_the_mock_list_cannot_be_checked() -> None:
    with pytest.raises(ValueError, match="_MOCK_PACKAGES"):
        mocked("MOCKS = ['simnibs']\n")
    assert mocked("_MOCK_PACKAGES = ['simnibs.mesh_tools', 'bpy']\n") == {
        "simnibs",
        "bpy",
    }


# ── tit.tools.nifti_to_mesh, the module CircleCI #1265 could not import ──────

#: Runs in a fresh interpreter (real numpy, scipy, nibabel; no conftest mocks): argv is the
#: NIfTI to write, whether to hide scikit-image, and the affine as JSON; prints JSON facts.
_N2M_SCRIPT = r"""
import json, sys
import numpy as np
import nibabel as nib

path, hide, affine = sys.argv[1], sys.argv[2] == "hide", np.array(json.loads(sys.argv[3]))
if hide:
    sys.modules["skimage"] = None
    sys.modules["skimage.measure"] = None
import tit.tools.nifti_to_mesh as n2m

mask = np.zeros((8, 9, 10))
mask[2:5, 1:3, 3:8] = 1.0
nib.save(nib.Nifti1Image(mask, affine), path)
try:
    verts, faces, removed = n2m.mask_to_surface(path)
except ImportError as exc:
    print(json.dumps({"imported": True, "mesh_error": str(exc)}))
else:
    print(json.dumps({"imported": True, "min": verts.min(axis=0).tolist(),
                      "max": verts.max(axis=0).tolist(), "faces": len(faces),
                      "removed": removed}))
"""


def _n2m(tmp_path: Path, hide: str, affine: np.ndarray) -> dict:
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            _N2M_SCRIPT,
            str(tmp_path / "seg.nii"),
            hide,
            json.dumps(affine.tolist()),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_nifti_to_mesh_imports_without_scikit_image(tmp_path: Path) -> None:
    """The tools job's argument jail imports the module; only meshing needs scikit-image."""
    facts = _n2m(tmp_path, "hide", np.eye(4))
    assert facts["imported"] is True
    assert "skimage" in facts["mesh_error"]


def test_nifti_to_mesh_meshes_a_box_where_its_voxels_are(tmp_path: Path) -> None:
    """Real marching cubes through the deferred import, on a 3 x 2 x 5-voxel box.

    The box (voxels 2..4, 1..2, 3..7 of an 8 x 9 x 10 grid) has a different extent and
    offset on each axis, and the affine a different scale, so meshing a transposed or
    axis-swapped mask moves the bounds. At level 0.5 the surface crosses each axis half a
    voxel outside the box: at 1.5..4.5, 0.5..2.5 and 2.5..7.5.
    """
    affine = np.diag([2.0, 3.0, 4.0, 1.0])
    affine[:3, 3] = [10.0, -20.0, 30.0]
    facts = _n2m(tmp_path, "keep", affine)
    # 10 + 2 * [1.5, 4.5] = [13, 19]; -20 + 3 * [0.5, 2.5] = [-18.5, -12.5];
    # 30 + 4 * [2.5, 7.5] = [40, 60].
    np.testing.assert_allclose(facts["min"], [13.0, -18.5, 40.0], atol=1e-6)
    np.testing.assert_allclose(facts["max"], [19.0, -12.5, 60.0], atol=1e-6)
    assert facts["faces"] > 0 and facts["removed"] == 0
