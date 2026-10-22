"""Every picture an analysis folder holds reaches the catalog, and its scene is named (2026-10-22).

What this pins
    ``catalog._analysis_entry`` reported one ``pdf`` and nothing else, but the analyzer writes
    ``histogram.png`` (``tit.analyzer.visualizer.save_histogram``) and the desktop renders
    ``scene.png`` beside ``scene.tetravox.json`` (``desktop/src/main/roiPlates.ts``). On
    Dataset 000, 5 of the 10 analyses held only PNGs, so their Results pane had no figure at
    all. An analysis now carries ``figures`` (every PNG and PDF in its folder, ``image`` /
    ``pdf`` kinds) and ``scene`` (its ``scene.tetravox.json``, the "Open in viewer" target).

Where the expectations come from
    ``os.listdir`` of the folder the analyzer produced: the synthetic case runs the analyzer's
    own ``visualize=True`` path (``Analyzer.analyze_sphere`` -> ``save_histogram`` names
    ``histogram.png``; ``tit.analyzer.scene._write`` names the scene from ``SCENE_NAME``), with
    only the drawing replaced -- matplotlib is mocked on the host, so ``savefig_close`` writes
    placeholder bytes at the path the visualizer chose. The real-data case reads Dataset 000.

Run: .venv/bin/python -m pytest tests/test_catalog_analysis_figures.py -q -p no:cacheprovider
Real data: TIT_DATASET_000=/Users/idohaber/datasets/000 (read-only; mtimes compared).
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from tit import catalog
from tit.paths import PathManager, get_path_manager

SID = "101"
SIM = "M1"
#: The desktop's own suffix rule for the rendered scene (``roiPlates.ts`` SCENE_SUFFIX).
DESKTOP_SCENE_SUFFIX = ".tetravox.json"
FIGURE_EXTS = (".png", ".pdf")


def _touch(path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    pm = get_path_manager(str(tmp_path))
    _touch(Path(pm.m2m(SID)) / f"{SID}.msh")
    _touch(pm.ti_mesh(SID, SIM))
    _touch(
        Path(pm.simulation(SID, SIM))
        / "TI"
        / "niftis"
        / f"grey_{SIM}_TI_subject_TI_max.nii.gz"
    )
    return tmp_path


def _fake_nib_load(arr: np.ndarray):
    def load(path):
        return SimpleNamespace(
            get_fdata=lambda: arr.astype(float),
            dataobj=arr,
            affine=np.eye(4),
            shape=arr.shape,
        )

    return load


def _write_placeholder(fig, output_file, **_kwargs) -> str:
    """``savefig_close`` without matplotlib: bytes at exactly the path the caller chose."""
    Path(output_file).write_bytes(b"\x89PNG placeholder")
    return output_file


def _visualized_voxel_analysis(project: Path) -> Path:
    """Run the analyzer's own visualize path and return the folder it wrote."""
    from tit.analyzer.analyzer import Analyzer
    from tit.analyzer import scene

    with patch("tit.analyzer.analyzer.add_file_handler"):
        analyzer = Analyzer(SID, SIM, space="voxel")
    grid = np.linspace(0.1, 1.0, 4 * 5 * 6).reshape(4, 5, 6)
    with (
        patch("nibabel.load", _fake_nib_load(grid)),
        patch("matplotlib.pyplot.subplots", return_value=(MagicMock(), MagicMock())),
        patch("tit.plotting._common.savefig_close", _write_placeholder),
    ):
        analyzer.analyze_sphere((2.0, 2.0, 2.0), 1.5, visualize=True)
    run_dirs = sorted(p.parent for p in project.rglob("results.csv"))
    assert len(run_dirs) == 1, run_dirs
    run_dir = run_dirs[0]
    # The scene writer's own file name (its framing needs real scipy; the name does not).
    scene_path = Path(scene._write(str(run_dir), {"cursor": [2.0, 2.0, 2.0]}, "test"))
    # What the desktop renders beside it once the job finishes.
    (run_dir / (scene_path.name[: -len(DESKTOP_SCENE_SUFFIX)] + ".png")).write_bytes(
        b"png"
    )
    return run_dir


def test_every_png_and_pdf_the_analysis_wrote_is_a_figure(project: Path) -> None:
    run_dir = _visualized_voxel_analysis(project)
    on_disk = sorted(
        str(run_dir / name)
        for name in os.listdir(run_dir)
        if name.endswith(FIGURE_EXTS)
    )
    assert len(on_disk) == 2, on_disk  # histogram.png (analyzer) + scene.png (desktop)

    (entry,) = catalog.analyses(get_path_manager(str(project)), SID, SIM)
    assert sorted(f["path"] for f in entry["figures"]) == on_disk
    for figure in entry["figures"]:
        assert (
            figure["kind"]
            == {".png": "image", ".pdf": "pdf"}[Path(figure["path"]).suffix]
        )
        assert figure["label"]
    # Nothing that is not a picture rides along as one.
    assert not any(f["path"].endswith((".csv", ".json")) for f in entry["figures"])


def test_the_scene_the_analysis_wrote_is_its_viewer_target(project: Path) -> None:
    from tit.analyzer.scene import SCENE_NAME

    run_dir = _visualized_voxel_analysis(project)
    (entry,) = catalog.analyses(get_path_manager(str(project)), SID, SIM)
    assert entry["scene"] == str(run_dir / SCENE_NAME)
    assert catalog._ANALYSIS_SCENE_NAME == SCENE_NAME


def test_an_analysis_without_pictures_lists_none(project: Path) -> None:
    """visualize=False: no picture, no scene -- empty, not invented."""
    pm = get_path_manager(str(project))
    run_dir = Path(pm.simulation(SID, SIM)) / "Analyses" / "Voxel" / "bare"
    run_dir.mkdir(parents=True)
    (run_dir / "analysis.json").write_text('{"field_name": "TI_max", "space": "voxel"}')
    (run_dir / "results.csv").write_text("Metric,Value\nroi_mean,0.1\n")
    (entry,) = catalog.analyses(pm, SID, SIM)
    assert entry["figures"] == [] and entry["scene"] is None and entry["pdf"] is None


def test_a_legacy_pdf_stays_listed_as_pdf_and_as_a_figure(project: Path) -> None:
    pm = get_path_manager(str(project))
    run_dir = Path(pm.simulation(SID, SIM)) / "Analyses" / "Mesh" / "legacy"
    run_dir.mkdir(parents=True)
    (run_dir / "analysis.json").write_text('{"field_name": "TI_max"}')
    (run_dir / "results.csv").write_text("Metric,Value\nroi_mean,0.1\n")
    (run_dir / "histogram_histogram.pdf").write_bytes(b"%PDF")
    (entry,) = catalog.analyses(pm, SID, SIM)
    assert entry["pdf"] == str(run_dir / "histogram_histogram.pdf")
    assert entry["figures"] == [
        {"path": entry["pdf"], "kind": "pdf", "label": "histogram histogram"}
    ]


# -- real data ----------------------------------------------------------------------------------

_DATASET = os.environ.get("TIT_DATASET_000", "")


def _mtimes(root: Path) -> dict[str, int]:
    return {str(p): p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}


@pytest.mark.skipif(
    not _DATASET or not os.path.isdir(_DATASET),
    reason="skipping: TIT_DATASET_000 is unset or not a directory (Dataset 000 copy)",
)
def test_dataset_000_every_analysis_lists_the_pictures_its_folder_holds() -> None:
    root = Path(_DATASET)
    pm = PathManager(project_dir=str(root))
    simnibs = root / "derivatives" / "SimNIBS"
    before = _mtimes(simnibs)

    checked = png_only = 0
    for sid in catalog.subject_ids(pm):
        for sim in catalog.list_simulations(pm, sid) or []:
            for entry in catalog.analyses(pm, sid, sim["name"]) or []:
                folder = Path(entry["csv"]).parent
                expected = sorted(
                    str(folder / n)
                    for n in os.listdir(folder)
                    if n.lower().endswith(FIGURE_EXTS)
                )
                assert sorted(f["path"] for f in entry["figures"]) == expected, folder
                scene = folder / "scene.tetravox.json"
                assert entry["scene"] == (
                    str(scene) if scene.is_file() else None
                ), folder
                checked += 1
                if expected and not any(p.endswith(".pdf") for p in expected):
                    png_only += 1
    assert checked > 0, "no analysis found in Dataset 000"
    # The audit's case: analyses whose only pictures are PNGs (they showed no figure before).
    assert png_only > 0
    assert _mtimes(simnibs) == before
