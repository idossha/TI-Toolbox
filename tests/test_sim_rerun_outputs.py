"""A re-run of a montage leaves only what its own ``config.json`` says, and the Python API keeps
its overwrite promise.

What this pins (p15, 2026-10-22)
--------------------------------
Dataset 000 ``sub-101/Simulations/L_Insula``: ``config.json`` (2026-09-23, ``map_to_mni`` false,
``output_fields`` ``["TI_max"]``) sits beside ``*_MNI_MNI_TI_max.nii.gz`` from 2026-09-09 and
``*_hf_peak``/``*_hf_sar`` NIfTIs from 2026-07-20: nothing cleared the earlier run's outputs, so a
group MNI analysis read a volume the config never asked for. And SimNIBS's own existence guard
(``simnibs_simulation*.mat`` in ``pathfem``) never fires after a completed run, because
``_organize_files`` moves that file into ``documentation/`` -- so ``run_simulation(cfg)`` from
Python silently overwrote, though its docstring promised an ``OSError``.

The spec: the outputs in a simulation folder are exactly what its ``config.json`` says.
* Without ``overwrite`` a folder that already holds a result mesh is refused before anything is
  written (``config.json`` included), with an ``OSError``.
* With ``overwrite`` the derived outputs of earlier runs (``TI/``, ``mTI/``, ``fsaverage/`` and
  the contents of ``high_Frequency/``) are removed before solving; the run history
  (``documentation/`` session records, any ``simnibs_simulation_*`` record a crashed run left in
  ``high_Frequency/``) and ``Analyses/`` are kept.

Where the expected values come from: the file names of the real folder above (listed by hand,
read-only) and the layout ``setup_montage_directories`` documents; the expected file set after a
re-run is written out here, not read back from the code.

SimNIBS is mocked (tests/conftest.py); a fake session writes what SimNIBS writes into
``pathfem`` (two carrier meshes, ``fields_summary.txt`` and a session record), and the real
``TISimulation._organize_files`` moves them. The real-SimNIBS half of the guard is
``tests/numerical/test_sim_overwrite.py``.

Reproduce: ``.venv/bin/python -m pytest tests/test_sim_rerun_outputs.py -q -p no:cacheprovider``
"""

from __future__ import annotations

import json
import os
import shutil
import string
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import tit.sim.base as base_mod
import tit.sim.TI as ti_mod
from tit.sim.config import Montage, MontageMode, SimulationConfig
from tit.sim.TI import TISimulation

SID = "001"
NAME = "L_Insula"
NET = "GSN-HydroCel-185.csv"

#: What an earlier run with map_to_mni and hf_peak/hf_sar left (real names, sub-101/L_Insula).
STALE = [
    "TI/mesh/L_Insula_TI.msh",
    "TI/mesh/grey_L_Insula_TI.msh",
    "TI/mesh/L_Insula_normal.msh",
    "TI/niftis/L_Insula_TI_subject_TI_max.nii.gz",
    "TI/niftis/L_Insula_TI_MNI_MNI_TI_max.nii.gz",
    "TI/niftis/grey_L_Insula_TI_MNI_MNI_TI_max.nii.gz",
    "TI/niftis/L_Insula_TI_subject_hf_peak.nii.gz",
    "TI/niftis/L_Insula_TI_MNI_MNI_hf_sar.nii.gz",
    "TI/montage_imgs/L_Insula_highlighted_visualization.png",
    "TI/surface_overlays/lh.001_TDCS_1_scalar.central.E.magn",
    "mTI/niftis/L_Insula_mTI_MNI_MNI_mTI_max.nii.gz",
    "high_Frequency/mesh/001_TDCS_1_scalar.msh",
    "high_Frequency/niftis/001_TDCS_1_scalar_MNI_MNI_magnE.nii.gz",
    "high_Frequency/analysis/fields_summary.txt",
    "fsaverage/sub-001_sim-L_Insula_space-fsaverage5_fields.npz",
]
#: The run history and the user's analyses: never removed.
KEPT = [
    "documentation/simnibs_simulation_20260720-232821.mat",
    "documentation/simnibs_simulation_20260720-232821.log",
    "Analyses/Mesh/thalamus/results.csv",
]
#: A crashed run's session record left in pathfem; a re-run moves it into documentation/.
CRASHED_RECORD = "high_Frequency/simnibs_simulation_20260909-030809.mat"
OLD_CONFIG = {"simulation_name": NAME, "mapping_options": {"map_to_mni": True}}


def _listing(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }


@pytest.fixture()
def montage_dir(init_pm) -> Path:
    os.makedirs(init_pm.eeg_positions(SID))
    Path(init_pm.eeg_positions(SID), NET).write_text("Electrode,1,2,3,E010\n")
    root = Path(init_pm.simulation(SID, NAME))
    for rel in STALE + KEPT + [CRASHED_RECORD]:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(f"old {rel}".encode())
    (root / "documentation" / "config.json").write_text(json.dumps(OLD_CONFIG))
    return root


def _config(**overrides) -> SimulationConfig:
    montage = Montage(
        name=NAME,
        mode=MontageMode.NET,
        electrode_pairs=[("E010", "E011"), ("E012", "E013")],
        eeg_net=NET,
    )
    kwargs = dict(
        subject_id=SID,
        montages=[montage],
        map_to_mni=False,
        map_to_fsavg=False,
        output_fields=["TI_max"],
    )
    kwargs.update(overrides)
    return SimulationConfig(**kwargs)


class _SimnibsSession:
    """Writes into ``pathfem`` what a SimNIBS TI session writes there."""

    def __init__(self, pathfem: str):
        self.pathfem = pathfem
        self.runs = []

    def run(self, **kwargs):
        self.runs.append(kwargs)
        for i in (1, 2):
            Path(self.pathfem, f"{SID}_TDCS_{i}_scalar.msh").write_bytes(b"new")
        Path(self.pathfem, "fields_summary.txt").write_bytes(b"new")
        Path(self.pathfem, "simnibs_simulation_20261022-010101.mat").write_bytes(b"new")


@contextmanager
def _fake_simnibs(sessions: list):
    """Every TI montage run in this block solves with a :class:`_SimnibsSession` appended to
    *sessions*; the real ``run``/``_organize_files`` do the rest."""

    def build(self, output_dir):
        sessions.append(_SimnibsSession(output_dir))
        return sessions[-1]

    mesh_io = MagicMock()
    mesh_io.read_msh.return_value.crop_mesh.return_value.field.__getitem__.return_value.value = np.zeros(
        (8, 3)
    )
    with (
        patch.object(TISimulation, "_build_session", build),
        patch.object(base_mod, "run_simnibs", side_effect=lambda s: s.run()),
        patch.object(base_mod, "run_montage_visualization"),
        patch.object(base_mod, "subprocess"),
        patch.object(base_mod.BaseSimulation, "_write_report"),
        patch.object(ti_mod, "mesh_io", mesh_io),
        patch.object(ti_mod, "envelope_max"),
        patch.object(ti_mod, "envelope"),
        patch.object(ti_mod, "extract_fields"),
        patch.object(ti_mod, "transform_dirs_to_nifti"),
    ):
        yield


def _run(overwrite: bool, sessions: list | None = None) -> _SimnibsSession:
    """One ``TISimulation.run``; every session it builds is appended to *sessions*."""
    sim = TISimulation(_config(), _config().montages[0], logger=MagicMock())
    sessions = [] if sessions is None else sessions
    with _fake_simnibs(sessions):
        sim.run("/unused", overwrite=overwrite)
    return sessions[0] if sessions else None


@pytest.mark.parametrize(
    "mesh", ["TI/mesh/L_Insula_TI.msh", "mTI/mesh/L_Insula_mTI.msh"]
)
def test_without_overwrite_a_folder_with_a_result_mesh_is_refused_untouched(
    init_pm, mesh: str
):
    root = Path(init_pm.simulation(SID, NAME))
    (root / mesh).parent.mkdir(parents=True)
    (root / mesh).write_bytes(b"old result")
    (root / "documentation").mkdir()
    (root / "documentation" / "config.json").write_text(json.dumps(OLD_CONFIG))
    before = _listing(root)
    sessions: list = []
    with pytest.raises(OSError, match=f"{NAME}.*overwrite"):
        _run(overwrite=False, sessions=sessions)
    assert sessions == []  # no SimNIBS session was even built, let alone solved
    assert (
        _listing(root) == before
    )  # config.json too: it still describes the old result


def test_run_simulation_from_python_refuses_instead_of_silently_overwriting(
    montage_dir: Path,
):
    from tit.sim.utils import run_simulation

    before = _listing(montage_dir)
    with patch.object(base_mod, "run_simnibs") as solve:
        with pytest.raises(OSError):
            run_simulation(_config(), logger=MagicMock())
    solve.assert_not_called()
    assert _listing(montage_dir) == before


def test_a_later_montage_with_a_result_refuses_the_whole_run_before_any_solve(
    montage_dir: Path,
):
    """[First, L_Insula] where only L_Insula has a result: without overwrite the run is refused
    up front, so First is not solved either (it used to be solved, then L_Insula refused).
    """
    from tit.sim.utils import run_simulation

    first = Montage(
        name="First",
        mode=MontageMode.NET,
        electrode_pairs=[("E020", "E021"), ("E022", "E023")],
        eeg_net=NET,
    )
    config = _config(montages=[first, _config().montages[0]])
    before = _listing(montage_dir)
    sessions: list = []
    with _fake_simnibs(sessions):
        with pytest.raises(FileExistsError, match=f"'{NAME}'.*overwrite"):
            run_simulation(config, logger=MagicMock())
    assert sessions == []  # no montage was solved
    assert not Path(montage_dir.parent, "First").exists()
    assert _listing(montage_dir) == before


def test_a_folder_without_a_result_mesh_runs_without_overwrite(init_pm):
    """A crash before any mesh was written leaves nothing to protect (the guard is the mesh,
    not "the folder exists")."""
    root = Path(init_pm.simulation(SID, NAME))
    (root / "documentation").mkdir(parents=True)
    (root / "documentation" / "simnibs_simulation_20260720-232821.log").write_text("x")
    session = _run(overwrite=False)
    assert session.runs == [{}]  # run_simnibs(session): SimNIBS's own guard stays on


def test_a_confirmed_rerun_leaves_exactly_what_the_new_config_says(montage_dir: Path):
    session = _run(overwrite=True)
    assert session.runs == [{"allow_multiple_runs": True}]

    after = _listing(montage_dir)
    # Nothing of the earlier run's derived outputs survives: no MNI volume, no carrier-safety
    # field, no fsaverage projection, no stale mesh or picture.
    assert not [rel for rel in after if "_MNI" in rel or "hf_" in rel]
    assert not (montage_dir / "fsaverage").exists()
    assert not (montage_dir / "mTI").exists()
    for rel in STALE:
        assert after.get(rel, b"").decode() != f"old {rel}", rel

    # The run history and the analyses are kept byte for byte; the crashed run's record and the
    # new session record join the history.
    for rel in KEPT:
        assert after[rel] == f"old {rel}".encode()
    assert (
        after["documentation/simnibs_simulation_20260909-030809.mat"]
        == f"old {CRASHED_RECORD}".encode()
    )
    assert after["documentation/simnibs_simulation_20261022-010101.mat"] == b"new"

    written = json.loads(after["documentation/config.json"])
    assert written["mapping_options"]["map_to_mni"] is False
    assert written["output_fields"] == ["TI_max"]

    # The whole folder: the history, the analyses, the new config and this run's carriers.
    assert set(after) == set(KEPT) | {
        "documentation/simnibs_simulation_20260909-030809.mat",
        "documentation/simnibs_simulation_20261022-010101.mat",
        "documentation/config.json",
        f"high_Frequency/mesh/{SID}_TDCS_1_scalar.msh",
        f"high_Frequency/mesh/{SID}_TDCS_2_scalar.msh",
        "high_Frequency/analysis/fields_summary.txt",
    }
    assert after[f"high_Frequency/mesh/{SID}_TDCS_1_scalar.msh"] == b"new"


def test_a_confirmed_rerun_keeps_files_the_simulator_does_not_write(montage_dir: Path):
    """Only the simulator's own output folders are cleared: a file someone put at the top of
    the montage folder is not the simulator's to delete."""
    (montage_dir / "notes.txt").write_text("mine")
    _run(overwrite=True)
    assert (montage_dir / "notes.txt").read_text() == "mine"


@pytest.mark.parametrize("folder", ["TI", "mTI", "fsaverage", "high_Frequency"])
def test_a_linked_output_folder_is_left_alone_and_its_target_untouched(
    montage_dir: Path, tmp_path_factory, folder: str
):
    """A derived-output folder that is a link (to another disk, say) is not followed: what it
    points at is not this montage's to delete. The link and its target stay as they were.
    """
    from tit.sim.utils import clear_previous_outputs

    target = tmp_path_factory.mktemp("elsewhere")
    (target / "simnibs_simulation_20260101-000000.mat").write_bytes(b"theirs")
    (target / "mesh").mkdir()
    (target / "mesh" / "L_Insula_TI.msh").write_bytes(b"theirs")
    link = montage_dir / folder
    if link.exists():
        shutil.rmtree(link)
    link.symlink_to(target, target_is_directory=True)
    outside = _listing(target)

    clear_previous_outputs(str(montage_dir))

    assert link.is_symlink() and link.resolve() == target.resolve()
    assert _listing(target) == outside
    # The real folders around it are still cleared.
    for other in {"TI", "mTI", "fsaverage"} - {folder}:
        assert not (montage_dir / other).exists(), other


# ── mTI names carriers A..Z: the tenth is J, not A0 ──────────────────────────────────────────


def test_mti_with_more_than_nine_channels_names_each_carrier_by_its_own_letter(init_pm):
    """SimNIBS numbers carriers 1..N; ``mTISimulation._organize_files`` renames them A..Z
    (``tests/test_sim_output_naming_contract.py``). The glob ``*TDCS_1*`` also matched
    TDCS_10..12, which became ``TDCS_A0``..``TDCS_A2`` and left J..L missing.

    Expected names: channel i is letter ``string.ascii_uppercase[i - 1]``; each file holds its
    own channel number, so a swapped mapping is caught as well as a wrong name. The three
    suffixes are what SimNIBS writes per carrier (Dataset 000
    ``sub-101/Simulations/L_Insula/high_Frequency/mesh``: ``101_TDCS_1_el_currents.geo``,
    ``101_TDCS_1_scalar.msh``, ``101_TDCS_1_scalar.msh.opt``).
    """
    from tit.sim.config import SimulationMode
    from tit.sim.mTI import mTISimulation
    from tit.sim.utils import setup_montage_directories

    n = 12
    labels = [f"E{i:03d}" for i in range(2 * n)]
    montage = Montage(
        name="Twelve",
        mode=MontageMode.NET,
        electrode_pairs=[(labels[2 * i], labels[2 * i + 1]) for i in range(n)],
        eeg_net=NET,
    )
    config = _config(montages=[montage], intensities=[1.0] * n)
    dirs = setup_montage_directories(
        init_pm.simulation(SID, "Twelve"), SimulationMode.MTI
    )
    hf = Path(dirs["hf_dir"])
    suffixes = ("scalar.msh", "scalar.msh.opt", "el_currents.geo")
    for i in range(1, n + 1):
        for suffix in suffixes:
            (hf / f"{SID}_TDCS_{i}_{suffix}").write_text(f"channel {i}")
    (hf / "fields_summary.txt").write_text("summary")

    mTISimulation(config, montage, logger=MagicMock())._organize_files(dirs)

    moved = {p.name: p.read_text() for p in Path(dirs["hf_mesh"]).iterdir()}
    assert moved == {
        f"{SID}_TDCS_{string.ascii_uppercase[i - 1]}_{suffix}": f"channel {i}"
        for i in range(1, n + 1)
        for suffix in suffixes
    }
    assert not [p.name for p in hf.iterdir() if "TDCS" in p.name]


# ── real data: the stale folder the bug was found in ─────────────────────────────────────────

_DATASET = os.environ.get("TIT_DATASET_000", "")
_REAL = Path(_DATASET, "derivatives/SimNIBS/sub-101/Simulations/L_Insula")


@pytest.mark.skipif(
    not _DATASET or not _REAL.is_dir(),
    reason="skipping: TIT_DATASET_000 is unset or has no sub-101/Simulations/L_Insula",
)
def test_clearing_the_real_stale_folder_leaves_only_its_history_and_analyses(tmp_path):
    """Dataset 000 sub-101/L_Insula holds outputs of three runs (2026-07-20 hf fields,
    2026-09-09 MNI volumes, 2026-09-23 TI_max). Its file names are mirrored as empty files
    (2.3 GB is not copied; the dataset is only listed), and clearing them must leave the
    session records, config.json and Analyses/ -- and nothing with _MNI or hf_ in its name.
    """
    from tit.sim.utils import clear_previous_outputs, existing_result_meshes

    real = sorted(p for p in _REAL.rglob("*") if p.is_file())
    stamps = {p: p.stat().st_mtime_ns for p in real}
    mirror = tmp_path / "L_Insula"
    for p in real:
        (mirror / p.relative_to(_REAL)).parent.mkdir(parents=True, exist_ok=True)
        (mirror / p.relative_to(_REAL)).touch()
    names = {str(p.relative_to(_REAL)) for p in real}
    assert any("_MNI_MNI_TI_max" in n for n in names), "has the stale MNI volume"
    assert any("hf_peak" in n for n in names), "has the stale hf_peak volume"
    # The guard sees the run's result meshes: the .msh files directly in TI/mesh.
    meshes = {n for n in names if n.startswith("TI/mesh/") and n.count("/") == 2} - {
        n for n in names if not n.endswith(".msh")
    }
    assert "TI/mesh/L_Insula_TI.msh" in meshes
    found = existing_result_meshes(str(mirror))
    assert {str(Path(m).relative_to(mirror)) for m in found} == meshes

    clear_previous_outputs(str(mirror))

    left = {str(p.relative_to(mirror)) for p in mirror.rglob("*") if p.is_file()}
    expected = {
        n
        for n in names
        if n.startswith(("documentation/", "Analyses/")) or "/" not in n
    }
    assert left == expected
    assert existing_result_meshes(str(mirror)) == []
    # Analyses/ may name an MNI sphere; nothing else may carry an MNI or carrier field.
    outputs = [n for n in left if not n.startswith("Analyses/")]
    assert not [n for n in outputs if "_MNI" in n or "hf_" in n]
    assert {
        p: p.stat().st_mtime_ns for p in real
    } == stamps  # the dataset was only read
