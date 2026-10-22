"""Every Blender export writes into the directory the Plan card names, explicit or default.

What this pins (2026-10-22): ``tit.server.routes.plan._blender_output_dir`` tells the user where
a ``blender`` job will write -- an ``output_dir`` already on the config "always wins", otherwise
``derivatives/ti-toolbox/visual_exports/sub-<id>/...``. The region and vector runners used to
overwrite an explicit ``output_dir`` unconditionally in ``_resolve_paths``, so the plan said
``<project>/x`` and the job wrote ``visual_exports/sub-<id>/<sim>/vectors``. Montage and
sub-cortical already honoured it; they are pinned here so the four modes stay one rule.

Where the expected values come from: the directory each runner itself resolves (its own
``_resolve_paths``, ``run_subcortical`` with meshing replaced, ``build_montage_publication_blend``
up to its Blender call), compared with the plan route's answer and with the default layout
spelled out from the plan docstring's table -- never from either function alone.

Host leg. Reproduce: ``.venv/bin/python -m pytest tests/test_blender_output_dir.py -q -p no:cacheprovider``
Deliberately elsewhere: the Nilearn half of the output-dir contract (another package).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("fastapi")

from tit.blender import (
    montage_publication,
    region_exporter,
    vector_field_exporter,
)  # noqa: E402
from tit.blender.config import (  # noqa: E402
    MontageConfig,
    RegionConfig,
    SubcorticalConfig,
    VectorConfig,
)
from tit.server.routes.plan import _blender_output_dir  # noqa: E402

pytestmark = pytest.mark.unit

SID, SIM = "001", "L_Insula"


class _BlenderCalled(Exception):
    """The montage build reached its Blender subprocess: every directory is decided."""


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


@pytest.fixture
def project(init_pm, tmp_project):
    sim = tmp_project / "derivatives" / "SimNIBS" / f"sub-{SID}" / "Simulations" / SIM
    for name in (
        f"TI/mesh/{SIM}_TI.msh",
        f"TI/mesh/surfaces/{SIM}_TI_central.msh",
        f"high_Frequency/mesh/{SID}_TDCS_1_scalar.msh",
        f"high_Frequency/mesh/{SID}_TDCS_2_scalar.msh",
    ):
        _touch(sim / name)
    (sim / "documentation").mkdir(parents=True)
    (sim / "documentation" / "config.json").write_text(
        json.dumps(
            {
                "conductivity": "scalar",
                "eeg_net": "GSN-HydroCel-185.csv",
                "electrode_pairs": [["E1", "E2"], ["E3", "E4"]],
            }
        )
    )
    _touch(Path(init_pm.m2m(SID)) / f"{SID}.msh")
    _touch(tmp_project / "labeling.nii.gz")
    return tmp_project


def _default(project: Path, *parts: str) -> str:
    return str(
        project
        / "derivatives"
        / "ti-toolbox"
        / "visual_exports"
        / f"sub-{SID}"
        / Path(*parts)
    )


def _region_dir(cfg: RegionConfig) -> str:
    region_exporter._resolve_paths(cfg)
    return cfg.output_dir


def _vector_dir(cfg: VectorConfig) -> str:
    vector_field_exporter._resolve_paths(cfg)
    return cfg.output_dir


def _subcortical_dir(cfg: SubcorticalConfig, monkeypatch) -> str:
    import tit.tools.nifti_to_mesh as n2m
    from tit.blender.subcortical_exporter import run_subcortical

    def mesh(input_file, output_file, **kwargs):
        return {
            "output_file": output_file,
            "vertices": 3,
            "faces": 1,
            "removed_components": 0,
        }

    monkeypatch.setattr(n2m, "nifti_to_mesh", mesh)
    return run_subcortical(cfg)


def _montage_dir(cfg: MontageConfig, monkeypatch) -> str:
    mp = montage_publication
    seen: dict[str, str] = {}

    def blender(args, **kwargs):
        seen["output_dir"] = json.loads(Path(args[-1]).read_text())["output_dir"]
        raise _BlenderCalled

    monkeypatch.setattr(mp, "export_scalp_stl_from_sim", lambda *a, **k: None)
    monkeypatch.setattr(mp, "export_gm_stl_from_sim", lambda *a, **k: None)
    monkeypatch.setattr(mp, "_resolve_eeg_net_csv", lambda **k: "net.csv")
    monkeypatch.setattr(mp, "read_electrodes", lambda path: iter([]))
    monkeypatch.setattr(
        mp.be_utils,
        "extract_scalp_from_msh",
        lambda path, tag: (np.eye(3), np.array([[0, 1, 2]])),
    )
    monkeypatch.setattr(mp.subprocess, "run", blender)
    with pytest.raises(_BlenderCalled):
        mp.run_montage(cfg)
    return seen["output_dir"]


@pytest.mark.parametrize("fmt", ["stl", "ply"])
def test_region_runner_writes_where_the_plan_says(project, fmt):
    default = RegionConfig(subject_id=SID, simulation_name=SIM, format=fmt)
    assert _blender_output_dir(_pm(), default) == _default(project, SIM, fmt)
    assert _region_dir(default) == _default(project, SIM, fmt)

    explicit = RegionConfig(subject_id=SID, simulation_name=SIM, format=fmt)
    explicit.output_dir = str(project / "exports" / f"regions_{fmt}")
    planned = _blender_output_dir(_pm(), explicit)
    assert planned == str(project / "exports" / f"regions_{fmt}")
    assert _region_dir(explicit) == planned


def test_vector_runner_writes_where_the_plan_says(project):
    default = VectorConfig(subject_id=SID, simulation_name=SIM)
    assert _blender_output_dir(_pm(), default) == _default(project, SIM, "vectors")
    assert _vector_dir(default) == _default(project, SIM, "vectors")

    explicit = VectorConfig(subject_id=SID, simulation_name=SIM)
    explicit.output_dir = str(project / "exports" / "arrows")
    planned = _blender_output_dir(_pm(), explicit)
    assert planned == str(project / "exports" / "arrows")
    assert _vector_dir(explicit) == planned


def test_subcortical_runner_writes_where_the_plan_says(project, monkeypatch):
    nifti = str(project / "labeling.nii.gz")
    default = SubcorticalConfig(subject_id=SID, nifti_path=nifti)
    assert _blender_output_dir(_pm(), default) == _default(project, "sub-cortical")
    assert _subcortical_dir(default, monkeypatch) == _default(project, "sub-cortical")

    explicit = SubcorticalConfig(subject_id=SID, nifti_path=nifti)
    explicit.output_dir = str(project / "exports" / "deep")
    planned = _blender_output_dir(_pm(), explicit)
    assert _subcortical_dir(explicit, monkeypatch) == planned == explicit.output_dir


def test_montage_runner_writes_where_the_plan_says(project, monkeypatch):
    default = MontageConfig(subject_id=SID, simulation_name=SIM)
    assert _blender_output_dir(_pm(), default) == _default(
        project, "montage_publication"
    )
    assert _montage_dir(default, monkeypatch) == _default(
        project, "montage_publication"
    )

    explicit = MontageConfig(
        subject_id=SID, simulation_name=SIM, output_dir=str(project / "exports" / "m")
    )
    planned = _blender_output_dir(_pm(), explicit)
    assert (
        _montage_dir(explicit, monkeypatch) == planned == str(project / "exports" / "m")
    )


def _pm():
    from tit.paths import get_path_manager

    return get_path_manager()
