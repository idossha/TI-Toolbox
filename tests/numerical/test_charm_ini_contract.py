"""charm.ini overrides land on keys the installed SimNIBS has, and read back as requested.

``tit.pre.charm._write_thread_settings`` copies ``SIMNIBSDIR/charm.ini`` and overrides the
thread count plus the validated options of ``tit.charm_options`` (denoise, final
segmentation resolution, skin facet size); charm then reads the copy through
``--usesettings``. The expected values come from the installed SimNIBS: its own
``charm.ini`` and its own reader (``simnibs.utils.settings_reader.read_ini``, the one
charm uses). charm itself is never run.

Run in the toolbox image (real SimNIBS)::

    simnibs_python -m pytest tests/numerical/test_charm_ini_contract.py -q -p no:cacheprovider
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest

#: (section, key) of every value _write_thread_settings may override.
OVERRIDDEN = {
    ("general", "threads"),
    ("preprocess", "denoise"),
    ("segment", "downsampling_targets"),
    ("mesh", "skin_facet_size"),
}


@pytest.fixture(scope="module", autouse=True)
def real_simnibs():
    """Swap the host conftest's ``simnibs`` mock for the real package, if any."""
    saved = {
        k: sys.modules.pop(k) for k in list(sys.modules) if k.split(".")[0] == "simnibs"
    }
    try:
        importlib.import_module("simnibs.utils.settings_reader")
    except Exception:
        sys.modules.update(saved)
        pytest.skip("real SimNIBS is unavailable; run in the toolbox container")
    yield
    for k in list(sys.modules):
        if k.split(".")[0] == "simnibs":
            del sys.modules[k]
    sys.modules.update(saved)


@pytest.fixture(scope="module")
def installed():
    from simnibs import SIMNIBSDIR
    from simnibs.utils.settings_reader import read_ini

    return read_ini(os.path.join(SIMNIBSDIR, "charm.ini"))


def _written(tmp_path, threads, options):
    from simnibs.utils.settings_reader import read_ini

    from tit.pre.charm import _write_thread_settings

    path = tmp_path / "charm.ini"
    _write_thread_settings(path, threads, options)
    return read_ini(str(path))


def test_installed_ini_has_every_key_the_toolbox_overrides(installed):
    for section, key in OVERRIDDEN:
        assert key in installed.get(section, {}), (section, key)
    assert type(installed["general"]["threads"]) is int
    assert type(installed["preprocess"]["denoise"]) is bool
    assert type(installed["mesh"]["skin_facet_size"]) in (int, float)
    targets = installed["segment"]["downsampling_targets"]
    # The coarse target bounds the final one: the 0.5-2.0 mm range the app offers
    # (tit.charm_options) is satisfiable only when the coarse target is >= 2.0 mm.
    assert isinstance(targets, list) and len(targets) >= 2
    assert targets[0] >= 2.0


def test_no_options_changes_only_the_thread_count(installed, tmp_path):
    written = _written(tmp_path, 3, None)

    assert written["general"]["threads"] == 3
    expected = {s: dict(v) for s, v in installed.items()}
    expected["general"]["threads"] = 3
    assert written == expected


@pytest.mark.parametrize(
    "options",
    [
        {"denoise": True, "segmentation_final_resolution": 0.5, "skin_facet_size": 4.5},
        {"denoise": False, "segmentation_final_resolution": 2.0, "skin_facet_size": 1},
        {"segmentation_final_resolution": 1.25},
        {"denoise": None, "skin_facet_size": 10.0},
    ],
)
def test_each_option_reads_back_as_requested_and_nothing_else_moves(
    installed, tmp_path, options
):
    written = _written(tmp_path, 5, options)

    expected = {s: dict(v) for s, v in installed.items()}
    expected["general"]["threads"] = 5
    if options.get("denoise") is not None:
        expected["preprocess"]["denoise"] = options["denoise"]
    if "segmentation_final_resolution" in options:
        coarse = installed["segment"]["downsampling_targets"][:-1]
        expected["segment"]["downsampling_targets"] = [
            *coarse,
            options["segmentation_final_resolution"],
        ]
    if "skin_facet_size" in options:
        expected["mesh"]["skin_facet_size"] = options["skin_facet_size"]

    # Same sections, same keys, the overridden values exactly, everything else as shipped.
    assert {s: set(v) for s, v in written.items()} == {
        s: set(v) for s, v in installed.items()
    }
    assert written == expected
    assert type(written["preprocess"]["denoise"]) is bool
    for value in written["segment"]["downsampling_targets"]:
        assert type(value) in (int, float)
