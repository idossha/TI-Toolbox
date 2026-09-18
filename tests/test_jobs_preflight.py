"""``tit.jobs.preflight``: a job's required inputs are checked on disk before it is queued.

The regression: an analyzer job in voxel space with a cortical DK40 target on a subject with no
FastSurfer/recon-all parcellation was accepted and only failed minutes later inside the runner
(``FileNotFoundError: Atlas 'DK40' not found in .../fastsurfer/sub-101/mri, ...``). Every test
here builds a project tree from the PathManager's own paths, proves "all present" is ``[]``,
then removes one input and expects the one :class:`MissingInput` naming its path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tit.jobs.preflight import MissingInput, preflight
from tit.paths import get_path_manager

SID = "101"
SIM = "L_Insula"
NET = "GSN-HydroCel-185.csv"


def touch(path: str | Path, text: str = "") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """A subject with a head model, an EEG net and a finished 2-pair TI simulation."""
    pm = get_path_manager(str(tmp_path))
    touch(Path(pm.m2m(SID)) / f"{SID}.msh")
    touch(
        Path(pm.eeg_positions(SID)) / NET,
        "Electrode,1,0,0,E1\nElectrode,2,0,0,E2\nElectrode,3,0,0,E3\nElectrode,4,0,0,E4\n",
    )
    touch(pm.ti_mesh(SID, SIM))
    touch(pm.ti_central_surface(SID, SIM))
    niftis = Path(pm.simulation(SID, SIM)) / "TI" / "niftis"
    touch(niftis / f"grey_{SIM}_TI_TI_max.nii.gz")
    touch(niftis / f"grey_{SIM}_TI_MNI_MNI_TI_max.nii.gz")
    return tmp_path


def missing_paths(found: list[MissingInput]) -> list[str]:
    return [m.expected_path for m in found]


# -- analyzer ---------------------------------------------------------------------------------


def analyzer_config(space: str, **overrides) -> dict:
    return {
        "mode": "single",
        "subject_id": SID,
        "simulation": SIM,
        "space": space,
        "analysis_type": "cortical",
        "atlas": "DK40",
        "region": "lh.insula",
        **overrides,
    }


def test_analyzer_voxel_cortical_dk40_needs_a_volume_parcellation(
    project: Path,
) -> None:
    """The real case: the surface atlas id resolves to FastSurfer's DKT volume in voxel space."""
    found = preflight("analyzer", analyzer_config("voxel"), str(project))
    assert len(found) == 1
    item = found[0]
    pm = get_path_manager()
    assert item.expected_path == str(
        Path(pm.fastsurfer_mri(SID)) / "aparc.DKTatlas+aseg.deep.mgz"
    )
    assert "DK40" in item.what and SID in item.what
    assert "FastSurfer" in item.how_to_fix and "mesh space" in item.how_to_fix


def test_analyzer_voxel_cortical_passes_once_fastsurfer_or_recon_all_exists(
    project: Path,
) -> None:
    pm = get_path_manager()
    touch(Path(pm.freesurfer_mri(SID)) / "aparc.DKTatlas+aseg.mgz")
    assert preflight("analyzer", analyzer_config("voxel"), str(project)) == []


def test_analyzer_mesh_cortical_dk40_needs_no_parcellation(project: Path) -> None:
    """Same target in mesh space: the SimNIBS built-in atlas comes from the m2m itself."""
    assert preflight("analyzer", analyzer_config("mesh"), str(project)) == []


def test_analyzer_missing_simulation_names_the_folder_and_the_simulation(
    project: Path,
) -> None:
    found = preflight(
        "analyzer", analyzer_config("mesh", simulation="R_Insula"), str(project)
    )
    pm = get_path_manager()
    assert missing_paths(found) == [pm.simulation(SID, "R_Insula")]
    assert "R_Insula" in found[0].how_to_fix


def test_analyzer_mesh_needs_the_field_mesh_and_the_central_surface(
    project: Path,
) -> None:
    pm = get_path_manager()
    Path(pm.ti_central_surface(SID, SIM)).unlink()
    found = preflight("analyzer", analyzer_config("mesh"), str(project))
    assert missing_paths(found) == [pm.ti_central_surface(SID, SIM)]
    Path(pm.ti_mesh(SID, SIM)).unlink()
    found = preflight("analyzer", analyzer_config("mesh"), str(project))
    assert missing_paths(found) == [pm.ti_mesh(SID, SIM)]


def test_analyzer_voxel_needs_the_tissue_nifti(project: Path) -> None:
    pm = get_path_manager()
    niftis = Path(pm.simulation(SID, SIM)) / "TI" / "niftis"
    (niftis / f"grey_{SIM}_TI_TI_max.nii.gz").unlink()
    found = preflight(
        "analyzer",
        analyzer_config("voxel", analysis_type="spherical", atlas=None),
        str(project),
    )
    assert missing_paths(found) == [str(niftis)]


def test_analyzer_mask_and_head_model(project: Path) -> None:
    cfg = analyzer_config(
        "mesh", analysis_type="mask", atlas=None, mask_path="/nope/mask.nii.gz"
    )
    found = preflight("analyzer", cfg, str(project))
    assert missing_paths(found) == ["/nope/mask.nii.gz"]
    pm = get_path_manager()
    Path(pm.m2m(SID), f"{SID}.msh").unlink()
    found = preflight("analyzer", analyzer_config("mesh"), str(project))
    assert str(Path(pm.m2m(SID)) / f"{SID}.msh") in missing_paths(found)


def test_analyzer_group_checks_every_subject(project: Path) -> None:
    cfg = analyzer_config(
        "mesh", mode="group", subject_id=None, subject_ids=[SID, "102"]
    )
    found = preflight("analyzer", cfg, str(project))
    pm = get_path_manager()
    assert missing_paths(found) == [pm.m2m("102")]


# -- sim --------------------------------------------------------------------------------------


def sim_config(**montage) -> dict:
    return {
        "subject_id": SID,
        "montages": [
            {
                "_type": "Montage",
                "name": "m1",
                "mode": "net",
                "electrode_pairs": [["E1", "E2"], ["E3", "E4"]],
                "eeg_net": NET,
                **montage,
            }
        ],
    }


def test_sim_all_present(project: Path) -> None:
    assert preflight("sim", sim_config(), str(project)) == []


def test_sim_missing_head_model(project: Path) -> None:
    pm = get_path_manager()
    Path(pm.m2m(SID), f"{SID}.msh").unlink()
    cfg = sim_config()
    assert missing_paths(preflight("sim", cfg, str(project))) == [
        str(Path(pm.m2m(SID)) / f"{SID}.msh")
    ]


def test_sim_missing_eeg_net_and_unknown_electrode(project: Path) -> None:
    pm = get_path_manager()
    found = preflight("sim", sim_config(eeg_net="EEG10-10.csv"), str(project))
    assert missing_paths(found) == [str(Path(pm.eeg_positions(SID)) / "EEG10-10.csv")]
    found = preflight(
        "sim", sim_config(electrode_pairs=[["E1", "E99"], ["E3", "E4"]]), str(project)
    )
    assert len(found) == 1 and "E99" in found[0].what


def test_sim_xyz_montages_need_no_net(project: Path) -> None:
    cfg = sim_config(
        mode="freehand", eeg_net=None, electrode_pairs=[[[0, 0, 0], [1, 1, 1]]]
    )
    assert preflight("sim", cfg, str(project)) == []


# -- flex / ex / mex / leadfield ----------------------------------------------------------------


def test_flex_mapping_net_and_atlas_paths(project: Path) -> None:
    pm = get_path_manager()
    cfg = {
        "subject_id": SID,
        "enable_mapping": True,
        "eeg_net": "GSN-HydroCel-185",
        "roi": {"_type": "SphericalROI", "center": [0, 0, 0], "radius": 5},
    }
    for kind in ("flex", "flex_adaptive", "flex_pareto"):
        assert preflight(kind, cfg, str(project)) == []
    cfg["eeg_net"] = "EGI256"
    found = preflight("flex", cfg, str(project))
    assert missing_paths(found) == [str(Path(pm.eeg_positions(SID)) / "EGI256.csv")]
    cfg["eeg_net"] = "GSN-HydroCel-185"
    cfg["roi"] = {
        "_type": "SubcorticalROI",
        "atlas_path": ["/a.mgz", "/a.mgz", "/b.mgz"],
        "label": [1, 2, 3],
    }
    found = preflight("flex", cfg, str(project))
    assert missing_paths(found) == ["/a.mgz", "/b.mgz"]


def test_ex_and_mex_leadfield_and_roi_csvs(project: Path) -> None:
    pm = get_path_manager()
    touch(Path(pm.leadfields(SID)) / "lf.hdf5")
    touch(Path(pm.rois(SID)) / "target.csv")
    cfg = {"subject_id": SID, "leadfield_hdf": "lf.hdf5", "roi_name": "target"}
    for kind in ("ex", "mex"):
        assert preflight(kind, cfg, str(project)) == []
    cfg = {
        "subject_id": SID,
        "leadfield_hdf": "other.hdf5",
        "roi_names": ["target", "second.csv"],
    }
    found = preflight("ex", cfg, str(project))
    assert missing_paths(found) == [
        str(Path(pm.leadfields(SID)) / "other.hdf5"),
        str(Path(pm.rois(SID)) / "second.csv"),
    ]
    assert "leadfield" in found[0].how_to_fix.lower()


def test_leadfield_needs_the_cap(project: Path) -> None:
    pm = get_path_manager()
    assert (
        preflight(
            "leadfield",
            {"subject_id": SID, "eeg_net": "GSN-HydroCel-185"},
            str(project),
        )
        == []
    )
    found = preflight(
        "leadfield", {"subject_id": SID, "eeg_net": "EEG10-10"}, str(project)
    )
    assert missing_paths(found) == [str(Path(pm.eeg_positions(SID)) / "EEG10-10.csv")]


# -- source / stats / nifti_average / nilearn / blender / pre -------------------------------------


def test_source_forward_and_fsavg_map(project: Path) -> None:
    pm = get_path_manager()
    cfg = {
        "mode": "forward",
        "subject_ids": [SID],
        "forward": {"eeg_net": "GSN-HydroCel-185"},
    }
    assert preflight("source", cfg, str(project)) == []
    cfg["forward"]["eeg_net"] = "EEG10-10"
    assert missing_paths(preflight("source", cfg, str(project))) == [
        str(Path(pm.eeg_positions(SID)) / "EEG10-10.csv")
    ]
    cfg = {"mode": "fsavg_map", "pairs": [{"subject_id": SID, "simulation": SIM}]}
    assert preflight("source", cfg, str(project)) == []
    Path(pm.ti_central_surface(SID, SIM)).unlink()
    assert missing_paths(preflight("source", cfg, str(project))) == [
        pm.ti_central_surface(SID, SIM)
    ]


def test_group_tools_need_the_mni_nifti(project: Path) -> None:
    pm = get_path_manager()
    subjects = [{"subject_id": SID, "simulation_name": SIM, "response": 1}]
    assert preflight("stats", {"subjects": subjects}, str(project)) == []
    assert preflight("nifti_average", {"subjects": subjects}, str(project)) == []
    pairs = [{"subject_id": SID, "simulation_name": SIM}]
    assert preflight("nilearn", {"subject_simulation_pairs": pairs}, str(project)) == []
    mni = (
        Path(pm.simulation(SID, SIM))
        / "TI"
        / "niftis"
        / f"grey_{SIM}_TI_MNI_MNI_TI_max.nii.gz"
    )
    mni.unlink()
    for kind, cfg in (
        ("stats", {"subjects": subjects}),
        ("nifti_average", {"subjects": subjects}),
        ("nilearn", {"subject_simulation_pairs": pairs}),
    ):
        found = preflight(kind, cfg, str(project))
        assert missing_paths(found) == [str(mni)], kind
        assert "map_to_mni" in found[0].how_to_fix
    # white matter is a different file, resolved through the stats config's own default.
    found = preflight(
        "stats", {"subjects": subjects, "tissue_type": "white"}, str(project)
    )
    assert missing_paths(found) == [
        str(mni.with_name(f"white_{SIM}_TI_MNI_MNI_TI_max.nii.gz"))
    ]


def test_stats_fsaverage_space_needs_the_projection(project: Path) -> None:
    pm = get_path_manager()
    subjects = [{"subject_id": SID, "simulation_name": SIM, "response": 1}]
    cfg = {"subjects": subjects, "space": "fsaverage", "fsaverage_spacing": 5}
    npz = (
        Path(pm.sim_fsaverage(SID, SIM))
        / f"sub-{SID}_sim-{SIM}_space-fsaverage5_fields.npz"
    )
    assert missing_paths(preflight("stats", cfg, str(project))) == [str(npz)]
    touch(npz)
    assert preflight("stats", cfg, str(project)) == []


def test_blender_needs_the_simulation(project: Path) -> None:
    pm = get_path_manager()
    assert (
        preflight("blender", {"subject_id": SID, "simulation_name": SIM}, str(project))
        == []
    )
    found = preflight(
        "blender", {"subject_id": SID, "simulation_name": "nope"}, str(project)
    )
    assert missing_paths(found) == [pm.simulation(SID, "nope")]


def test_pre_charm_needs_a_bids_t1(project: Path) -> None:
    pm = get_path_manager()
    cfg = {"subject_ids": ["102"], "create_m2m": True}
    found = preflight("pre", cfg, str(project))
    assert missing_paths(found) == [pm.bids_anat("102")]
    assert "T1w" in found[0].how_to_fix
    # DICOM conversion in the same run supplies the T1w, so nothing is missing yet.
    assert preflight("pre", {**cfg, "convert_dicom": True}, str(project)) == []


def test_unknown_or_uncheckable_kinds_and_configs_are_silent(project: Path) -> None:
    assert preflight("project_init", {}, str(project)) == []
    assert preflight("tools", {"module": "tit.tools.x"}, str(project)) == []
    assert preflight("analyzer", {"simulation": SIM}, str(project)) == []
    assert preflight("sim", {"montages": "not-a-list"}, str(project)) == []
