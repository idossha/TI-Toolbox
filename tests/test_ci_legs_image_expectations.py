"""The numerical and Dataset 000 legs are green on an old image and a rebuilt one, and nothing else.

What this pins
    Two tests depend on how the image was built, not on the numbers: the vector warp
    (``tests/numerical/test_simnibs_vector_warp.py``) fails on an image that still carries
    the removed ``nan_to_num`` patch, and the Nilearn render module
    (``tests/numerical/test_nilearn_render_realdata.py``) skips one of two tests depending on
    whether the image bundles ``/opt/nilearn_data``. Before this, ``numerical_nightly`` on
    idossha/ti-toolbox:v3.1.1 was red every night (1 failure) and the Dataset 000 leg red on an
    unlisted skip, for no regression. Now:

    * the warp test is a strict ``xfail`` exactly where the image's ``transformations.py`` has
      the patch's edit, and an ordinary test elsewhere;
    * ``dev/check_junit.py`` allows, on the legs that run them, those outcomes by their exact
      test id and their whole reason text -- an XPASS, another reason, or the same reason on
      another test still fails the leg.

Where the expectations come from
    The patch's own rule (``resources/patches/patch_nan_to_num.py`` before 7403910d replaced
    every ``copy=None`` with ``copy=False``; SimNIBS 4.6 passes ``copy=None`` at its three
    ``nan_to_num`` calls, and the v3.1.1 image shows ``copy=False`` there). The reason texts
    are read from the real test modules (``ast``, or the module's own constant), and the
    JUnit reports are written by pytest itself in a subprocess, from stubs that carry the real
    test ids, so ``check_junit`` is checked against the format the legs really produce.

How to run it
    ``python -m pytest tests/test_ci_legs_image_expectations.py -q -p no:cacheprovider``

Deliberately elsewhere
    The rules of ``check_junit`` itself: ``tests/test_check_junit.py``. The legs on the real
    image: ``docker run ... idossha/ti-toolbox:v3.1.1`` with ``check_junit --leg
    numerical-image`` and ``dev/run_realdata_tests.sh`` (docs/dev/TESTING.md).
"""

from __future__ import annotations

import ast
import importlib.util
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

_warp_spec = importlib.util.spec_from_file_location(
    "_vector_warp_under_test",
    ROOT / "tests" / "numerical" / "test_simnibs_vector_warp.py",
)
warp = importlib.util.module_from_spec(_warp_spec)
_warp_spec.loader.exec_module(warp)

WARP_ID = (
    "tests.numerical.test_simnibs_vector_warp."
    "test_vector_volume_is_mirrored_through_the_inverse_warp"
)
RENDER = ROOT / "tests" / "numerical" / "test_nilearn_render_realdata.py"
BUNDLED_TEST = "test_the_atlas_outlines_load_offline_from_the_bundled_cache"
FALLBACK_TEST = "test_without_the_bundled_atlases_the_job_still_draws_and_says_why"

#: SimNIBS 4.6's three ``nan_to_num`` lines (simnibs/utils/transformations.py:175, 394, 397
#: in the image, where they read ``copy=False``; 7403910d records the original ``copy=None``).
PRISTINE = (
    "    grad = np.nan_to_num(grad, copy=None)\n"
    "        im_data = np.nan_to_num(im_data, copy=None)\n"
    "        im_data = np.nan_to_num(im_data, copy=None)\n"
)


def _skipif_reason(path: Path, function: str) -> str:
    """The ``reason=`` of *function*'s ``pytest.mark.skipif``, read from the source."""
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.FunctionDef) and node.name == function:
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and ast.unparse(
                    decorator.func
                ).endswith("skipif"):
                    for keyword in decorator.keywords:
                        if keyword.arg == "reason":
                            return ast.literal_eval(keyword.value)
    raise AssertionError(f"{function} in {path} has no skipif reason")


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


def _stub_report(tmp_path: Path, warp_body: str, render_tests: str) -> str:
    """Run stubs carrying the real test ids through pytest; return the JUnit path."""
    numerical = tmp_path / "tests" / "numerical"
    numerical.mkdir(parents=True)
    for package in (tmp_path / "tests", numerical):
        (package / "__init__.py").write_text("", encoding="utf-8")
    (numerical / "test_simnibs_vector_warp.py").write_text(
        "import pytest\n\n" + warp_body, encoding="utf-8"
    )
    (numerical / "test_nilearn_render_realdata.py").write_text(
        "import pytest\n\n" + render_tests, encoding="utf-8"
    )
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


def _skipping(name: str, reason: str) -> str:
    return (
        f"@pytest.mark.skipif(True, reason={reason!r})\n" f"def {name}():\n    pass\n\n"
    )


def _old_image_warp() -> str:
    """The real outcome on v3.1.1: the strict xfail, with SimNIBS's ValueError."""
    return (
        "@pytest.mark.xfail(strict=True, raises=ValueError, "
        f"reason={warp.PATCHED_IMAGE!r})\n"
        "def test_vector_volume_is_mirrored_through_the_inverse_warp():\n"
        "    raise ValueError('Unable to avoid copy while creating an array as requested.')\n"
    )


NEW_IMAGE_WARP = (
    "def test_vector_volume_is_mirrored_through_the_inverse_warp():\n    pass\n"
)


def _old_image_render() -> str:
    return _skipping(BUNDLED_TEST, _skipif_reason(RENDER, BUNDLED_TEST)) + (
        f"def {FALLBACK_TEST}():\n    pass\n"
    )


def _new_image_render() -> str:
    return f"def {BUNDLED_TEST}():\n    pass\n\n" + _skipping(
        FALLBACK_TEST, _skipif_reason(RENDER, FALLBACK_TEST)
    )


def test_the_reasons_are_the_ones_the_test_modules_carry():
    """Guards the stubs: each reason read from source is the one the allowlists name."""
    numerical = check_junit.ALLOWLISTS["numerical-image"]
    realdata = check_junit.ALLOWLISTS["realdata"]
    warp_entries = [e for e in numerical if e["test"] == WARP_ID]
    assert [e["message"] for e in warp_entries] == [warp.PATCHED_IMAGE]
    for leg in (numerical, realdata):
        fallback = [e for e in leg if e["test"].endswith(f".{FALLBACK_TEST}")]
        assert [e["message"] for e in fallback] == [
            _skipif_reason(RENDER, FALLBACK_TEST)
        ]
    bundled = [e for e in realdata if e["test"].endswith(f".{BUNDLED_TEST}")]
    assert [e["message"] for e in bundled] == [_skipif_reason(RENDER, BUNDLED_TEST)]


@pytest.mark.parametrize(
    "image, warp_body, render",
    [
        ("v3.1.1", _old_image_warp(), _old_image_render()),
        ("rebuilt", NEW_IMAGE_WARP, _new_image_render()),
    ],
    ids=["v3.1.1", "rebuilt"],
)
def test_both_images_pass_the_numerical_leg(tmp_path, capsys, image, warp_body, render):
    report = _stub_report(tmp_path, warp_body, render)
    cases = check_junit.read_cases(Path(report).read_text(encoding="utf-8"))
    assert len(cases) == 3, cases
    assert sum(c.outcome == "skipped" for c in cases) == (2 if image == "v3.1.1" else 1)
    assert (
        check_junit.main(["--leg", "numerical-image", report]) == 0
    ), capsys.readouterr()
    assert check_junit.main(["--leg", "no-skips", report]) == 1


@pytest.mark.parametrize(
    "render", [_old_image_render(), _new_image_render()], ids=["v3.1.1", "rebuilt"]
)
def test_both_images_pass_the_dataset_000_leg(tmp_path, capsys, render):
    report = _stub_report(tmp_path, NEW_IMAGE_WARP, render)
    assert check_junit.main(["--leg", "realdata", report]) == 0, capsys.readouterr()


def test_an_xpass_on_the_patched_image_fails_the_leg(tmp_path, capsys):
    """The patch stopped mattering, or the check is wrong: someone must look."""
    xpass = _old_image_warp().replace(
        "    raise ValueError('Unable to avoid copy while creating an array as requested.')\n",
        "    pass\n",
    )
    report = _stub_report(tmp_path, xpass, _new_image_render())
    assert check_junit.main(["--leg", "numerical-image", report]) == 1
    assert f"failed: {WARP_ID}" in capsys.readouterr().out


def test_the_warp_failing_another_way_on_the_patched_image_fails_the_leg(
    tmp_path, capsys
):
    """``raises=ValueError``: a different error on the old image is a real failure."""
    other = _old_image_warp().replace(
        "raise ValueError('Unable to avoid copy while creating an array as requested.')",
        "assert False, 'the mirrored vector is wrong'",
    )
    report = _stub_report(tmp_path, other, _new_image_render())
    assert check_junit.main(["--leg", "numerical-image", report]) == 1
    assert "the mirrored vector is wrong" in capsys.readouterr().out


@pytest.mark.parametrize(
    "warp_body, render",
    [
        # The xfail reason on the dataset leg, which never runs the warp test.
        (_old_image_warp(), _new_image_render()),
        # The fallback's skip text on the bundled-cache test.
        (
            NEW_IMAGE_WARP,
            _skipping(BUNDLED_TEST, _skipif_reason(RENDER, FALLBACK_TEST))
            + f"def {FALLBACK_TEST}():\n    pass\n",
        ),
        # The fallback test skipping for another reason.
        (
            NEW_IMAGE_WARP,
            f"def {BUNDLED_TEST}():\n    pass\n\n"
            + _skipping(FALLBACK_TEST, "real nilearn is not importable here"),
        ),
    ],
    ids=["xfail-on-realdata", "text-on-other-test", "other-reason"],
)
def test_nothing_broader_passes_the_dataset_000_leg(
    tmp_path, capsys, warp_body, render
):
    report = _stub_report(tmp_path, warp_body, render)
    assert check_junit.main(["--leg", "realdata", report]) == 1
    assert capsys.readouterr().out.count("skip not on the allowlist") == 1


def test_the_warp_reason_on_another_test_fails_the_numerical_leg(tmp_path, capsys):
    body = (
        f"@pytest.mark.xfail(strict=True, reason={warp.PATCHED_IMAGE!r})\n"
        "def test_vector_volume_is_mirrored_through_the_inverse_warp():\n"
        "    raise ValueError('copy')\n\n"
        f"@pytest.mark.xfail(strict=True, reason={warp.PATCHED_IMAGE!r})\n"
        "def test_scalar_volume_is_resampled():\n"
        "    raise ValueError('copy')\n"
    )
    report = _stub_report(tmp_path, body, _new_image_render())
    assert check_junit.main(["--leg", "numerical-image", report]) == 1
    out = capsys.readouterr().out
    assert "test_simnibs_vector_warp.test_scalar_volume_is_resampled" in out
    assert out.count("skip not on the allowlist") == 1
