"""Nilearn Visuals reads each run's own field file, and a missing atlas costs only the outlines.

Pins, 2026-10-21:

1. :func:`field_nifti` picks the folder and file per mode. The expected names are the ones
   the simulators write: ``TI/niftis/grey_<sim>_TI_MNI_MNI_TI_max.nii.gz`` (the real file
   in Dataset 000, e.g. ``sub-LA/Simulations/L_Insula``), and for an mTI run, which
   :func:`tit.analyzer.field_selector.is_mti_simulation` recognises by ``mTI/mesh/``,
   ``mTI/niftis/grey_<sim>_mTI_MNI_MNI_mTI_max.nii.gz`` (``tit/sim/mTI.py`` names the mesh
   ``<sim>_mTI.msh`` and its field ``mTI_max``; ``tit/tools/mesh2nii.py`` adds ``_MNI``).
   The runner used to read ``TI/niftis`` only, so an mTI run could not be visualised.
2. ``_load_atlas`` never raises: offline without the bundled atlases, the job log says in
   plain words that the outlines were skipped and why, and the figure is drawn anyway.
3. The panel offers exactly the atlases the image bundles (``atlases.ATLASES``), so no
   choice in the UI needs the network.

The real averaging over those files runs in ``tests/numerical/test_nilearn_group_average.py``.
Reproduce: ``.venv/bin/python -m pytest tests/test_nilearn_visuals.py -q``
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.unit
class TestFieldNifti:
    def test_a_two_pair_run_reads_TI_max_from_TI_niftis(self, init_pm, tmp_project):
        from tit.plotting.nilearn.visualizer import field_nifti

        sim = Path(init_pm.simulation("001", "L_Insula"))
        (sim / "TI" / "mesh").mkdir(parents=True)
        assert field_nifti("001", "L_Insula") == os.path.join(
            sim, "TI", "niftis", "grey_L_Insula_TI_MNI_MNI_TI_max.nii.gz"
        )

    def test_an_mti_run_reads_mTI_max_from_mTI_niftis(self, init_pm, tmp_project):
        from tit.plotting.nilearn.visualizer import field_nifti

        sim = Path(init_pm.simulation("001", "Deep"))
        (sim / "mTI" / "mesh").mkdir(parents=True)
        assert field_nifti("001", "Deep") == os.path.join(
            sim, "mTI", "niftis", "grey_Deep_mTI_MNI_MNI_mTI_max.nii.gz"
        )


@pytest.mark.unit
class TestAtlasFallback:
    def test_an_atlas_that_cannot_load_is_skipped_in_plain_words(
        self, init_pm, monkeypatch, capsys
    ):
        from tit.plotting.nilearn import visualizer

        def offline(key):
            raise ConnectionError("Failed to resolve 'www.nitrc.org'")

        monkeypatch.setattr(visualizer, "atlas_path", offline)
        img, name = visualizer.NilearnVisualizer()._load_atlas("harvard_oxford_sub")

        assert (img, name) == (None, "")
        out = capsys.readouterr().out
        assert "Atlas contours skipped" in out
        assert "Harvard-Oxford subcortical atlas" in out
        assert "www.nitrc.org" in out
        assert "drawn without region outlines" in out

    def test_an_unknown_atlas_is_skipped_not_raised(self, init_pm, capsys):
        from tit.plotting.nilearn.visualizer import NilearnVisualizer

        assert NilearnVisualizer()._load_atlas("juelich") == (None, "")
        assert "unknown atlas 'juelich'" in capsys.readouterr().out


@pytest.mark.unit
def test_the_panel_offers_exactly_the_bundled_atlases():
    from tit.plotting.nilearn.atlases import ATLASES

    src = (
        REPO / "desktop/src/renderer/pages/panels/nilearn-visuals/index.tsx"
    ).read_text()
    block = src.split("const ATLAS_OPTIONS = [", 1)[1].split("];", 1)[0]
    offered = re.findall(r'value: "(\w+)"', block)
    assert offered, "found no atlas options in the panel source"
    assert set(offered) == set(ATLASES)
