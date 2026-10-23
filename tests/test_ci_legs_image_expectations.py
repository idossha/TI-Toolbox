"""The numerical and Dataset 000 legs are green on an old image and a rebuilt one, and nothing else.

What this pins
    One test depends on how the image was built, not on the numbers: the vector warp
    (``tests/numerical/test_simnibs_vector_warp.py``) fails on an image that still carries
    the removed ``nan_to_num`` patch. Before this, ``numerical_nightly`` on
    idossha/ti-toolbox:v3.1.1 was red every night (1 failure), for no regression. Now:

    * the warp test is a strict ``xfail`` for SimNIBS's ``ValueError`` exactly where the
      image's ``transformations.py`` has the patch's edit, and an ordinary test elsewhere;
    * ``dev/check_junit.py`` allows, on the leg that runs it, that outcome by its exact
      test id and its whole reason text -- an XPASS, another error, another reason, or the
      same reason on another test still fails the leg.

    The CI ``host-numerical`` leg (a venv without matplotlib) allows the tissue figure test's
    own "needs real matplotlib" skip, and only on that test.

    The numerical leg allows a skip that names ``TIT_DATASET_000`` in any module, so a new
    real-data module does not turn the nightly red (82eb1dde's leadfield module did, on
    2026-10-22, while the leg listed modules); a skip naming another variable still fails,
    the Dataset 000 leg refuses every such skip, and ``dev/run_realdata_tests.sh`` is shown
    to select every module whose skip names the variable. Every entry of the three legs must
    name a skip text its module carries, so a stale entry (a fixed xfail, a renamed reason)
    fails. (Up to v3.1.2 the Nilearn render module also skipped one of two tests depending on
    whether the image bundled ``/opt/nilearn_data``; its atlases now ship in ``resources/``,
    so it has no image-dependent outcome.)

Where the expectations come from
    The patch's own rule (``resources/patches/patch_nan_to_num.py`` before 7403910d replaced
    every ``copy=None`` with ``copy=False``; SimNIBS 4.6 passes ``copy=None`` at its three
    ``nan_to_num`` calls, and the v3.1.1 image shows ``copy=False`` there). The warp outcomes
    come from the **real** test module, run by pytest in a subprocess against a stand-in
    SimNIBS whose ``transformations.py`` has or lacks that edit and whose ``nifti_transform``
    raises NumPy 2's copy error, returns the mirrored field, or returns it unrotated -- so the
    shipped marker (``strict``, ``raises``, ``reason``) and its condition are what is checked,
    not a copy typed here. The other reason texts are read from the real test modules
    (``ast``), and every JUnit report is written by pytest itself, from modules that carry the
    real test ids, so ``check_junit`` is checked against the format the legs really produce.
    The runner's module list is its own output, run with a stub ``docker`` on an empty
    dataset.

How to run it
    ``python -m pytest tests/test_ci_legs_image_expectations.py -q -p no:cacheprovider``

Deliberately elsewhere
    The rules of ``check_junit`` itself: ``tests/test_check_junit.py``. The legs on the real
    image: ``docker run ... idossha/ti-toolbox:v3.1.1`` with ``check_junit --leg
    numerical-image`` and ``dev/run_realdata_tests.sh`` (docs/dev/TESTING.md).
"""

from __future__ import annotations

import ast
import fnmatch
import functools
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "check_junit", ROOT / "dev" / "check_junit.py"
)
check_junit = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("check_junit", check_junit)  # dataclasses resolve their module
_spec.loader.exec_module(check_junit)

WARP = ROOT / "tests" / "numerical" / "test_simnibs_vector_warp.py"
_warp_spec = importlib.util.spec_from_file_location("_vector_warp_under_test", WARP)
warp = importlib.util.module_from_spec(_warp_spec)
_warp_spec.loader.exec_module(warp)

WARP_ID = (
    "tests.numerical.test_simnibs_vector_warp."
    "test_vector_volume_is_mirrored_through_the_inverse_warp"
)
RENDER = ROOT / "tests" / "numerical" / "test_nilearn_render_realdata.py"
RUNNER = ROOT / "dev" / "run_realdata_tests.sh"
TISSUE = ROOT / "tests" / "numerical" / "test_tissue_geometry.py"
FIGURE_TEST = "test_figures_show_anatomical_views_whatever_the_storage_order"

#: SimNIBS 4.6's three ``nan_to_num`` lines (simnibs/utils/transformations.py:175, 394, 397
#: in the image, where they read ``copy=False``; 7403910d records the original ``copy=None``).
PRISTINE = (
    "    grad = np.nan_to_num(grad, copy=None)\n"
    "        im_data = np.nan_to_num(im_data, copy=None)\n"
    "        im_data = np.nan_to_num(im_data, copy=None)\n"
)


def _skip_call_text(path: Path, function: str) -> str:
    """The text of the ``pytest.skip(...)`` call inside *function*, read from the source."""
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.FunctionDef) and node.name == function:
            for call in ast.walk(node):
                if (
                    isinstance(call, ast.Call)
                    and ast.unparse(call.func) == "pytest.skip"
                ):
                    return ast.literal_eval(call.args[0])
    raise AssertionError(f"{function} in {path} calls no pytest.skip")


#: The calls whose text pytest records as a skip (an xfail is recorded as one too).
_SKIP_CALLS = {"skip", "skipif", "xfail", "importorskip"}


def _text(node: ast.AST, names: dict[str, str]) -> str | None:
    """A string expression's text: literals, ``+``, module-level names; f-string fields ``{}``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            v.value if isinstance(v, ast.Constant) else "{}" for v in node.values
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _text(node.left, names), _text(node.right, names)
        return None if left is None or right is None else left + right
    if isinstance(node, ast.Name):
        return names.get(node.id)
    return None


@functools.lru_cache(maxsize=None)
def _skip_texts(path: Path) -> tuple[str, ...]:
    """Every skip or xfail text *path* can report, read from its source.

    The ``reason=`` / ``msg=`` of a skip, skipif, xfail or importorskip call, the first
    argument of ``pytest.skip`` / ``pytest.xfail``, and a ``print("skipping: ...")`` -- how a
    check run in a subprocess hands its skip back (``tests/numerical/test_fsaverage_msh.py``).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            text = _text(node.value, names)
            for target in node.targets:
                if isinstance(target, ast.Name) and text is not None:
                    names[target.id] = text
    texts = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call = ast.unparse(node.func).rsplit(".", 1)[-1]
        if call == "print" and node.args:
            printed = _text(node.args[0], names)
            if printed is not None and printed.startswith("skipping:"):
                texts.append(printed)
            continue
        if call not in _SKIP_CALLS:
            continue
        values = [k.value for k in node.keywords if k.arg in {"reason", "msg"}]
        if call in {"skip", "xfail"} and node.args:
            values.append(node.args[0])
        texts += [t for t in (_text(v, names) for v in values) if t is not None]
    return tuple(texts)


def _module_id(path: Path) -> str:
    return ".".join(path.relative_to(ROOT).with_suffix("").parts)


def _modules_named_by(glob: str) -> list[Path]:
    """The test modules an allowlist id glob names: its module part, or all a wildcard covers."""
    parts = glob.split(".")
    for end in range(len(parts) - 1, 1, -1):
        if not any("*" in part for part in parts[:end]):
            path = ROOT.joinpath(*parts[:end]).with_suffix(".py")
            if path.is_file():
                return [path]
    return [
        path
        for path in sorted((ROOT / "tests").rglob("test_*.py"))
        if fnmatch.fnmatchcase(f"{_module_id(path)}.test_any", glob)
    ]


# ── which image carries the patch ────────────────────────────────────────────


def _install_fake_transformations(monkeypatch, tmp_path: Path, source: str) -> None:
    path = tmp_path / "transformations.py"
    path.write_text(source, encoding="utf-8")
    module = SimpleNamespace(__file__=str(path))
    utils = SimpleNamespace(transformations=module)
    monkeypatch.setitem(sys.modules, "simnibs", SimpleNamespace(utils=utils))
    monkeypatch.setitem(sys.modules, "simnibs.utils", utils)
    monkeypatch.setitem(sys.modules, "simnibs.utils.transformations", module)


def test_simnibs_own_transformations_is_not_the_patched_image(monkeypatch, tmp_path):
    _install_fake_transformations(monkeypatch, tmp_path, PRISTINE)
    assert warp._carries_the_nan_to_num_patch() is False


def test_the_patchs_edit_is_recognised(monkeypatch, tmp_path):
    # The patch script's whole edit: src.replace("copy=None", "copy=False").
    _install_fake_transformations(
        monkeypatch, tmp_path, PRISTINE.replace("copy=None", "copy=False")
    )
    assert warp._carries_the_nan_to_num_patch() is True


def test_copy_false_elsewhere_in_the_file_is_not_the_patch(monkeypatch, tmp_path):
    """Only a ``nan_to_num`` call with ``copy=False`` is the patch's edit."""
    _install_fake_transformations(
        monkeypatch, tmp_path, PRISTINE + "    out = np.array(x, copy=False)\n"
    )
    assert warp._carries_the_nan_to_num_patch() is False


# ── the legs' reports, written by pytest ─────────────────────────────────────

#: A stand-in ``simnibs/utils/transformations.py``: SimNIBS 4.6's ``nan_to_num`` call (which
#: the patch rewrote) and a ``nifti_transform`` that does what the case says.
_STAND_IN_TRANSFORMATIONS = """\
import numpy as np


class _Image:
    def __init__(self, data):
        self.dataobj = data


def _gradient(grad):
    return np.nan_to_num(grad, copy=None)


def nifti_transform(image, warp, reference, inverse_warp=None, **kwargs):
    data = np.asarray(image[0])
{body}
"""

#: What the stand-in ``nifti_transform`` does.
OUTCOMES = {
    # NumPy 2 refusing the patched call: what v3.1.1 really raises.
    "copy-error": "    raise ValueError("
    "'Unable to avoid copy while creating an array as requested.')",
    # The answer the test authors: x mirrored, y and z kept.
    "mirrored": "    return _Image(data * np.array([-1.0, 1.0, 1.0]))",
    # A wrong answer, failing the test's own assertion: the vectors not rotated.
    "unrotated": "    return _Image(data)",
}


def _real_warp_module(root: Path, *, patched: bool, outcome: str) -> str:
    """Install a stand-in SimNIBS under *root*; return the real warp test's source."""
    utils = root / "simnibs" / "utils"
    utils.mkdir(parents=True)
    for package in (root / "simnibs", utils):
        (package / "__init__.py").write_text("", encoding="utf-8")
    source = _STAND_IN_TRANSFORMATIONS.format(body=OUTCOMES[outcome])
    if patched:
        source = source.replace("copy=None", "copy=False")  # the patch script's edit
    (utils / "transformations.py").write_text(source, encoding="utf-8")
    return WARP.read_text(encoding="utf-8")


def _report(tmp_path: Path, modules: dict[str, str]) -> str:
    """Run *modules* as ``tests/numerical/<name>.py`` through pytest; return the JUnit path.

    pytest runs in *tmp_path*, which is first on its ``sys.path``, so a stand-in ``simnibs``
    there is the one the real warp module imports.
    """
    numerical = tmp_path / "tests" / "numerical"
    numerical.mkdir(parents=True)
    for package in (tmp_path / "tests", numerical):
        (package / "__init__.py").write_text("", encoding="utf-8")
    for name, text in modules.items():
        (numerical / f"{name}.py").write_text(text, encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    report = tmp_path / "out.xml"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests",
            "-q",
            "-p",
            "no:cacheprovider",
            "-c",
            str(tmp_path / "pytest.ini"),
            f"--junitxml={report}",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert report.is_file(), result.stdout + result.stderr
    return str(report)


def _case(report: str, test_id: str):
    (case,) = [
        c
        for c in check_junit.read_cases(Path(report).read_text(encoding="utf-8"))
        if c.test == test_id
    ]
    return case


def test_the_reasons_are_the_ones_the_test_modules_carry():
    """Guards the stubs: the warp reason read from source is the one the allowlist names."""
    numerical = check_junit.ALLOWLISTS["numerical-image"]
    warp_entries = [e for e in numerical if e["test"] == WARP_ID]
    assert [e["message"] for e in warp_entries] == [warp.PATCHED_IMAGE]


@pytest.mark.parametrize(
    "patched, warp_outcome",
    [
        # v3.1.1: the patch is in, SimNIBS raises the copy error.
        (True, "skipped"),
        # Rebuilt: no patch, the field is mirrored.
        (False, "passed"),
    ],
    ids=["v3.1.1", "rebuilt"],
)
def test_both_images_pass_the_numerical_leg(tmp_path, capsys, patched, warp_outcome):
    warp_module = _real_warp_module(
        tmp_path, patched=patched, outcome="copy-error" if patched else "mirrored"
    )
    report = _report(tmp_path, {"test_simnibs_vector_warp": warp_module})
    cases = check_junit.read_cases(Path(report).read_text(encoding="utf-8"))
    assert len(cases) == 1, cases
    case = _case(report, WARP_ID)
    assert case.outcome == warp_outcome, case
    if patched:
        assert case.message == warp.PATCHED_IMAGE  # the xfail, recorded with its reason
    assert (
        check_junit.main(["--leg", "numerical-image", report]) == 0
    ), capsys.readouterr()
    assert check_junit.main(["--leg", "no-skips", report]) == (1 if patched else 0)


@pytest.mark.parametrize(
    "patched, outcome, says",
    [
        # strict=True: the patch stopped mattering, or the check is wrong -- someone must look.
        (True, "mirrored", "XPASS(strict)"),
        # raises=ValueError: a wrong field on the old image is a real failure, not the xfail.
        (True, "unrotated", "Not equal to tolerance"),
        # The xfail is conditional: an image without the edit that raises is a failure.
        (False, "copy-error", "Unable to avoid copy"),
        # And one without the edit that computes the wrong field.
        (False, "unrotated", "Not equal to tolerance"),
    ],
    ids=[
        "xpass-on-patched",
        "wrong-field-on-patched",
        "copy-error-on-rebuilt",
        "wrong-field-on-rebuilt",
    ],
)
def test_the_warp_tests_real_marker_fails_the_leg_on_anything_but_its_case(
    tmp_path, capsys, patched, outcome, says
):
    warp_module = _real_warp_module(tmp_path, patched=patched, outcome=outcome)
    report = _report(tmp_path, {"test_simnibs_vector_warp": warp_module})
    case = _case(report, WARP_ID)
    assert case.outcome == "failed", case
    assert says in case.message, case
    assert check_junit.main(["--leg", "numerical-image", report]) == 1
    assert f"failed: {WARP_ID}" in capsys.readouterr().out


def test_the_warp_xfail_does_not_pass_the_dataset_000_leg(tmp_path, capsys):
    """The Dataset 000 leg never runs the warp test, so its xfail is not on that list."""
    warp_module = _real_warp_module(tmp_path, patched=True, outcome="copy-error")
    report = _report(tmp_path, {"test_simnibs_vector_warp": warp_module})
    assert check_junit.main(["--leg", "realdata", report]) == 1
    assert capsys.readouterr().out.count("skip not on the allowlist") == 1


def test_the_warp_reason_on_another_test_fails_the_numerical_leg(tmp_path, capsys):
    body = (
        "import pytest\n\n"
        f"@pytest.mark.xfail(strict=True, reason={warp.PATCHED_IMAGE!r})\n"
        "def test_vector_volume_is_mirrored_through_the_inverse_warp():\n"
        "    raise ValueError('copy')\n\n"
        f"@pytest.mark.xfail(strict=True, reason={warp.PATCHED_IMAGE!r})\n"
        "def test_scalar_volume_is_resampled():\n"
        "    raise ValueError('copy')\n"
    )
    report = _report(tmp_path, {"test_simnibs_vector_warp": body})
    assert check_junit.main(["--leg", "numerical-image", report]) == 1
    out = capsys.readouterr().out
    assert "test_simnibs_vector_warp.test_scalar_volume_is_resampled" in out
    assert out.count("skip not on the allowlist") == 1


# ── the host numerical leg's matplotlib skip ─────────────────────────────────


@pytest.mark.parametrize(
    "skipping_test, passes",
    [(FIGURE_TEST, True), ("test_bone_thickness_is_the_authored_shell", False)],
    ids=["figure-test", "another-tissue-test"],
)
def test_the_host_leg_allows_the_matplotlib_skip_on_the_figure_test_only(
    tmp_path, capsys, skipping_test, passes
):
    """The tissue figure test's own skip text, as pytest records it, and nowhere else."""
    text = _skip_call_text(TISSUE, FIGURE_TEST)
    other = "test_bone_thickness_is_the_authored_shell"
    module = "import pytest\n\n" + "".join(
        f"def {name}():\n"
        + (
            f"    pytest.skip({text!r})\n\n"
            if name == skipping_test
            else "    pass\n\n"
        )
        for name in (FIGURE_TEST, other)
    )
    report = _report(tmp_path, {"test_tissue_geometry": module})
    case = _case(report, f"tests.numerical.test_tissue_geometry.{skipping_test}")
    assert (case.outcome, case.message) == ("skipped", text)
    assert check_junit.main(["--leg", "host-numerical", report]) == (0 if passes else 1)
    out = capsys.readouterr().out
    assert out.count("skip not on the allowlist") == (0 if passes else 1), out
    assert check_junit.main(["--leg", "no-skips", report]) == 1


# ── Dataset 000 gates on the CI numerical leg ────────────────────────────────


def _dataset_000_gate_texts() -> list[str]:
    """The skip texts tests/numerical's real-data modules carry that name TIT_DATASET_000."""
    texts = sorted(
        {
            text
            for path in sorted((ROOT / "tests" / "numerical").glob("test_*.py"))
            for text in _skip_texts(path)
            if "TIT_DATASET_000" in text
        }
    )
    assert len(texts) >= 3, f"has Dataset 000 gates to check: {texts}"
    return texts


def _gated(texts: list[str]) -> str:
    """A module no allowlist names: one test skipping per text, and one that runs."""
    return (
        "import pytest\n\n"
        + "".join(
            f"@pytest.mark.skipif(True, reason={text!r})\n"
            f"def test_gate_{index}():\n    pass\n\n"
            for index, text in enumerate(texts)
        )
        + "def test_runs():\n    pass\n"
    )


def test_a_module_no_list_names_passes_the_numerical_leg_on_its_dataset_000_skip(
    tmp_path, capsys
):
    """CI has no Dataset 000, so a real-data module added later skips there in any wording.

    The nightly stays green without an allowlist edit (82eb1dde's leadfield module turned it
    red), and the Dataset 000 leg, which sets the variable, still refuses each skip.
    """
    texts = _dataset_000_gate_texts()
    report = _report(tmp_path, {"test_a_module_no_allowlist_names": _gated(texts)})
    cases = check_junit.read_cases(Path(report).read_text(encoding="utf-8"))
    assert sorted(c.message for c in cases if c.outcome == "skipped") == texts
    assert (
        check_junit.main(["--leg", "numerical-image", report]) == 0
    ), capsys.readouterr().out
    assert check_junit.main(["--leg", "realdata", report]) == 1
    assert capsys.readouterr().out.count("skip not on the allowlist") == len(texts)


def test_a_skip_that_does_not_name_tit_dataset_000_fails_the_numerical_leg(
    tmp_path, capsys
):
    texts = [
        # The retired spelling (TIT_DATASET000): the runner never sets it.
        "skipping: TIT_DATASET000 is unset (export TIT_DATASET000=/path/to/Dataset000)",
        # Another variable, which names Dataset 000 but is not the one CI lacks.
        "skipping: TIT_DTI_PROTO is unset; the prototype tensor is not part of Dataset 000",
    ]
    report = _report(tmp_path, {"test_a_module_no_allowlist_names": _gated(texts)})
    assert check_junit.main(["--leg", "numerical-image", report]) == 1
    out = capsys.readouterr().out
    assert out.count("skip not on the allowlist") == len(texts), out


def _runner_modules(tmp_path: Path) -> set[str]:
    """The modules dev/run_realdata_tests.sh selects, from its own output (docker stubbed)."""
    dataset = tmp_path / "000"
    (dataset / "derivatives" / "SimNIBS").mkdir(parents=True)
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "docker").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (stub / "docker").chmod(0o755)
    done = subprocess.run(
        [
            "bash",
            str(RUNNER),
            "--dataset",
            str(dataset),
            "--out",
            str(tmp_path / "out"),
        ],
        env={**os.environ, "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    prefix = "real-data modules ("
    (line,) = [l for l in done.stdout.splitlines() if l.startswith(prefix)] or [
        done.stdout + done.stderr
    ]
    count, _, names = line.removeprefix(prefix).partition("): ")
    modules = set(names.split())
    assert len(modules) == int(count), line
    return modules


def test_every_module_whose_skip_names_tit_dataset_000_is_run_by_the_dataset_000_leg(
    tmp_path,
):
    """The numerical leg may pass such a skip only because the Dataset 000 leg runs it."""
    named = {
        str(path.relative_to(ROOT))
        for path in sorted((ROOT / "tests").rglob("test_*.py"))
        if any("TIT_DATASET_000" in text for text in _skip_texts(path))
    }
    assert str(RENDER.relative_to(ROOT)) in named, "has gated modules to check"
    assert named - _runner_modules(tmp_path) == set()


# ── every allowlist entry is a skip the tree can report ──────────────────────


@pytest.mark.parametrize("leg", ["numerical-image", "realdata", "host-numerical"])
def test_every_allowlist_entry_names_a_skip_its_module_can_report(leg):
    """An entry whose text no module it names carries is stale (or mistyped): it allows nothing
    real and would allow the next skip that happens to share it."""
    entries = check_junit.ALLOWLISTS[leg]
    assert entries, f"{leg} has entries to check"
    stale = [
        f"{entry['test']}: {entry['message']!r}"
        for entry in entries
        if not any(
            entry["message"] in text
            for module in _modules_named_by(entry["test"])
            for text in _skip_texts(module)
        )
    ]
    assert stale == []
