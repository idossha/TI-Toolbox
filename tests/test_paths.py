#!/usr/bin/env python3
"""
Unit tests for TI-Toolbox path management module (tit/paths.py)

Tests the PathManager singleton and all path resolution functions.
Critical for ensuring BIDS-compliant directory navigation works correctly.
"""

import pytest
import os
import pathlib
from unittest.mock import patch

from tit.paths import PathManager, get_path_manager, reset_path_manager
from tit import constants as const

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(tmp_path):
    """Create a minimal BIDS-compliant project directory."""
    root = tmp_path / "project"
    (root / "derivatives" / "SimNIBS").mkdir(parents=True)
    (root / "derivatives" / "freesurfer").mkdir(parents=True)
    (root / "derivatives" / "ti-toolbox").mkdir(parents=True)
    return str(root)


def _add_subject(project_dir, sid):
    """Add a subject with an m2m directory."""
    sub = pathlib.Path(project_dir) / "derivatives" / "SimNIBS" / f"sub-{sid}"
    (sub / f"m2m_{sid}").mkdir(parents=True, exist_ok=True)
    return sub


# ---------------------------------------------------------------------------
# Singleton behaviour
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_returns_same_instance(self):
        pm1 = get_path_manager()
        pm2 = get_path_manager()
        assert pm1 is pm2

    def test_reset_creates_new_instance(self):
        pm1 = get_path_manager()
        reset_path_manager()
        pm2 = get_path_manager()
        assert pm1 is not pm2


# ---------------------------------------------------------------------------
# __init__ with project_dir argument (line 30)
# ---------------------------------------------------------------------------


class TestInitWithProjectDir:
    def test_init_sets_project_dir(self, tmp_path):
        root = _make_project(tmp_path)
        pm = PathManager(project_dir=root)
        assert pm.project_dir == root

    def test_init_invalid_dir_raises(self):
        with pytest.raises(ValueError):
            PathManager(project_dir="/nonexistent/path/xyz")


# ---------------------------------------------------------------------------
# project_dir property — env-var auto-detection (lines 40-48)
# ---------------------------------------------------------------------------


class TestProjectDirAutoDetection:
    def test_detect_via_env_project_dir(self, tmp_path, monkeypatch):
        """Line 40-42: detect via ENV_PROJECT_DIR."""
        project = tmp_path / "myproject"
        project.mkdir()
        monkeypatch.setenv(const.ENV_PROJECT_DIR, str(project))
        monkeypatch.delenv(const.ENV_PROJECT_DIR_NAME, raising=False)
        pm = PathManager()
        assert pm.project_dir == str(project)

    def test_detect_via_env_project_dir_name(self, tmp_path, monkeypatch):
        """Lines 44-48: fallback to ENV_PROJECT_DIR_NAME + DOCKER_MOUNT_PREFIX."""
        monkeypatch.delenv(const.ENV_PROJECT_DIR, raising=False)
        project = tmp_path / "mnt" / "proj"
        project.mkdir(parents=True)
        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, "proj")
        monkeypatch.setattr(const, "DOCKER_MOUNT_PREFIX", str(tmp_path / "mnt"))
        pm = PathManager()
        assert pm.project_dir == str(project)

    def test_no_env_returns_none(self, monkeypatch):
        monkeypatch.delenv(const.ENV_PROJECT_DIR, raising=False)
        monkeypatch.delenv(const.ENV_PROJECT_DIR_NAME, raising=False)
        pm = PathManager()
        assert pm.project_dir is None


# ---------------------------------------------------------------------------
# project_dir_name property (lines 60-62)
# ---------------------------------------------------------------------------


class TestProjectDirName:
    def test_returns_basename_when_set(self, tmp_path):
        root = _make_project(tmp_path)
        pm = PathManager(project_dir=root)
        assert pm.project_dir_name == "project"

    def test_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv(const.ENV_PROJECT_DIR_NAME, "fallback_name")
        pm = PathManager()
        # _project_dir is None, so falls back
        assert pm.project_dir_name == "fallback_name"


# ---------------------------------------------------------------------------
# _root raises when unset (line 72)
# ---------------------------------------------------------------------------


class TestRootRaises:
    def test_root_raises_when_no_project(self, monkeypatch):
        monkeypatch.delenv(const.ENV_PROJECT_DIR, raising=False)
        monkeypatch.delenv(const.ENV_PROJECT_DIR_NAME, raising=False)
        pm = PathManager()
        with pytest.raises(RuntimeError, match="Project directory not set"):
            pm.derivatives()


# ---------------------------------------------------------------------------
# Project-level path methods (lines 83, 98, 101, 104, 107, 110, 113, 116, 119, 122)
# ---------------------------------------------------------------------------


class TestProjectLevelPaths:
    @pytest.fixture
    def pm(self, tmp_path):
        root = _make_project(tmp_path)
        return PathManager(project_dir=root), root

    def test_sourcedata(self, pm):
        p, root = pm
        assert p.sourcedata() == os.path.join(root, "sourcedata")

    def test_config_dir(self, pm):
        p, root = pm
        assert p.config_dir() == os.path.join(root, "code", "ti-toolbox", "config")

    def test_montage_config(self, pm):
        p, root = pm
        assert p.montage_config().endswith("montage_list.json")

    def test_project_status(self, pm):
        p, root = pm
        assert p.project_status().endswith("project_status.json")

    def test_extensions_config(self, pm):
        p, root = pm
        assert p.extensions_config().endswith("extensions.json")

    def test_reports(self, pm):
        p, root = pm
        assert p.reports() == os.path.join(root, "derivatives", "ti-toolbox", "reports")

    def test_stats_data(self, pm):
        p, root = pm
        assert p.stats_data() == os.path.join(
            root, "derivatives", "ti-toolbox", "stats", "data"
        )

    def test_stats_output(self, pm):
        p, root = pm
        result = p.stats_output("permutation", "run1")
        assert result == os.path.join(
            root, "derivatives", "ti-toolbox", "stats", "permutation", "run1"
        )

    def test_logs_group(self, pm):
        p, root = pm
        assert p.logs_group() == os.path.join(
            root, "derivatives", "ti-toolbox", "logs", "group_analysis"
        )

    def test_qsiprep(self, pm):
        p, root = pm
        assert p.qsiprep() == os.path.join(root, "derivatives", "qsiprep")

    def test_qsirecon(self, pm):
        p, root = pm
        assert p.qsirecon() == os.path.join(root, "derivatives", "qsirecon")


# ---------------------------------------------------------------------------
# Subject-level path methods
# (lines 138, 141, 144, 147, 150, 156, 159, 162, 165, 168, 171, 174, 177, 180, 183, 186, 189)
# ---------------------------------------------------------------------------


class TestSubjectLevelPaths:
    @pytest.fixture
    def pm(self, tmp_path):
        root = _make_project(tmp_path)
        _add_subject(root, "001")
        return PathManager(project_dir=root), root

    def test_rois(self, pm):
        p, root = pm
        assert p.rois("001").endswith("m2m_001/ROIs")

    def test_masks(self, pm):
        p, root = pm
        assert p.masks("001").endswith("m2m_001/masks")

    def test_t1(self, pm):
        p, root = pm
        assert p.t1("001").endswith("m2m_001/T1.nii.gz")

    def test_segmentation(self, pm):
        p, root = pm
        assert p.segmentation("001").endswith("m2m_001/segmentation")

    def test_tissue_labeling(self, pm):
        p, root = pm
        assert p.tissue_labeling("001").endswith("segmentation/labeling.nii.gz")

    def test_leadfields(self, pm):
        p, root = pm
        assert p.leadfields("001").endswith("sub-001/leadfields")

    def test_logs(self, pm):
        p, root = pm
        assert p.logs("001") == os.path.join(
            root, "derivatives", "ti-toolbox", "logs", "sub-001"
        )

    def test_tissue_analysis_output(self, pm):
        p, root = pm
        assert p.tissue_analysis_output("001") == os.path.join(
            root, "derivatives", "ti-toolbox", "tissue_analysis", "sub-001"
        )

    def test_bids_subject(self, pm):
        p, root = pm
        assert p.bids_subject("001") == os.path.join(root, "sub-001")

    def test_bids_anat(self, pm):
        p, root = pm
        assert p.bids_anat("001") == os.path.join(root, "sub-001", "anat")

    def test_bids_dwi(self, pm):
        p, root = pm
        assert p.bids_dwi("001") == os.path.join(root, "sub-001", "dwi")

    def test_sourcedata_subject(self, pm):
        p, root = pm
        assert p.sourcedata_subject("001") == os.path.join(
            root, "sourcedata", "sub-001"
        )

    def test_freesurfer_subject(self, pm):
        p, root = pm
        assert p.freesurfer_subject("001") == os.path.join(
            root, "derivatives", "freesurfer", "sub-001"
        )

    def test_freesurfer_mri(self, pm):
        p, root = pm
        assert p.freesurfer_mri("001") == os.path.join(
            root, "derivatives", "freesurfer", "sub-001", "mri"
        )

    def test_fastsurfer_subject(self, pm):
        p, root = pm
        assert p.fastsurfer_subject("001") == os.path.join(
            root, "derivatives", "fastsurfer", "sub-001"
        )

    def test_fastsurfer_mri(self, pm):
        p, root = pm
        assert p.fastsurfer_mri("001") == os.path.join(
            root, "derivatives", "fastsurfer", "sub-001", "mri"
        )

    def test_qsiprep_subject(self, pm):
        p, root = pm
        assert p.qsiprep_subject("001") == os.path.join(
            root, "derivatives", "qsiprep", "sub-001"
        )

    def test_qsirecon_subject(self, pm):
        p, root = pm
        assert p.qsirecon_subject("001") == os.path.join(
            root, "derivatives", "qsirecon", "sub-001"
        )

    def test_ex_search(self, pm):
        p, root = pm
        assert p.ex_search("001").endswith("sub-001/ex-search")

    def test_flex_search(self, pm):
        p, root = pm
        assert p.flex_search("001").endswith("sub-001/flex-search")


# ---------------------------------------------------------------------------
# Subject + simulation path methods
# (lines 199, 202, 205, 210)
# ---------------------------------------------------------------------------


class TestSimulationPaths:
    @pytest.fixture
    def pm(self, tmp_path):
        root = _make_project(tmp_path)
        _add_subject(root, "001")
        return PathManager(project_dir=root), root

    def test_ti_mesh(self, pm):
        p, _ = pm
        result = p.ti_mesh("001", "mont1")
        assert result.endswith("TI/mesh/mont1_TI.msh")

    def test_ti_mesh_dir(self, pm):
        p, _ = pm
        result = p.ti_mesh_dir("001", "mont1")
        assert result.endswith("TI/mesh")

    def test_ti_central_surface(self, pm):
        p, _ = pm
        result = p.ti_central_surface("001", "mont1")
        assert result.endswith("TI/mesh/surfaces/mont1_TI_central.msh")

    def test_mti_mesh_dir(self, pm):
        p, _ = pm
        result = p.mti_mesh_dir("001", "mont1")
        assert result.endswith("mTI/mesh")


# ---------------------------------------------------------------------------
# Subject + run/name paths (lines 221, 224, 227, 230, 233)
# ---------------------------------------------------------------------------


class TestRunNamePaths:
    @pytest.fixture
    def pm(self, tmp_path):
        root = _make_project(tmp_path)
        _add_subject(root, "001")
        return PathManager(project_dir=root), root

    def test_sourcedata_dicom(self, pm):
        p, root = pm
        result = p.sourcedata_dicom("001", "T1w")
        assert result == os.path.join(root, "sourcedata", "sub-001", "T1w", "dicom")

    def test_ex_search_run(self, pm):
        p, _ = pm
        result = p.ex_search_run("001", "run_01")
        assert result.endswith("ex-search/run_01")

    def test_flex_search_run(self, pm):
        p, _ = pm
        result = p.flex_search_run("001", "opt_A")
        assert result.endswith("flex-search/opt_A")

    def test_flex_electrode_positions(self, pm):
        p, _ = pm
        result = p.flex_electrode_positions("001", "opt_A")
        assert result.endswith("opt_A/electrode_positions.json")

    def test_flex_manifest(self, pm):
        p, _ = pm
        result = p.flex_manifest("001", "opt_A")
        assert result.endswith("opt_A/flex_meta.json")


# ---------------------------------------------------------------------------
# ensure() utility
# ---------------------------------------------------------------------------


class TestEnsure:
    def test_creates_directory_and_returns_path(self, tmp_path):
        root = _make_project(tmp_path)
        pm = PathManager(project_dir=root)
        new_dir = os.path.join(root, "a", "b", "c")
        result = pm.ensure(new_dir)
        assert result == new_dir
        assert os.path.isdir(new_dir)


# ---------------------------------------------------------------------------
# list_simnibs_subjects — natural sort + m2m filter
# ---------------------------------------------------------------------------


class TestUserConfigDir:
    def test_honors_tit_user_config_when_container_mount_unusable(
        self, tmp_path, monkeypatch
    ):
        blocked_container_path = tmp_path / "not_a_dir"
        blocked_container_path.write_text("file")
        env_config = tmp_path / "env_config"

        monkeypatch.setattr(
            const, "USER_CONFIG_CONTAINER_PATH", str(blocked_container_path)
        )
        monkeypatch.setenv("TIT_USER_CONFIG", str(env_config))

        assert PathManager.user_config_dir() == str(env_config)
        assert env_config.is_dir()


class TestListSubjects:
    def test_lists_subjects_with_m2m(self, tmp_path):
        root = _make_project(tmp_path)
        _add_subject(root, "002")
        _add_subject(root, "001")
        # sub-999 without m2m should be excluded
        (pathlib.Path(root) / "derivatives" / "SimNIBS" / "sub-999").mkdir()
        pm = PathManager(project_dir=root)
        assert pm.list_simnibs_subjects() == ["001", "002"]

    def test_empty_when_no_simnibs(self, tmp_path):
        root = tmp_path / "empty"
        root.mkdir()
        pm = PathManager()
        pm._project_dir = str(root)
        assert pm.list_simnibs_subjects() == []


# ---------------------------------------------------------------------------
# list_simulations — OSError branch (lines 313-316)
# ---------------------------------------------------------------------------


class TestListSimulations:
    def test_returns_simulation_dirs(self, tmp_path):
        root = _make_project(tmp_path)
        sub = _add_subject(root, "001")
        sims = sub / "Simulations"
        sims.mkdir()
        (sims / "montA").mkdir()
        (sims / "montB").mkdir()
        (sims / ".hidden").mkdir()  # should be excluded
        pm = PathManager(project_dir=root)
        assert pm.list_simulations("001") == ["montA", "montB"]

    def test_returns_empty_for_missing(self, tmp_path):
        root = _make_project(tmp_path)
        pm = PathManager(project_dir=root)
        assert pm.list_simulations("nonexistent") == []


# ---------------------------------------------------------------------------
# list_eeg_caps (lines 322-332)
# ---------------------------------------------------------------------------


class TestListEegCaps:
    def test_lists_csv_files(self, tmp_path):
        root = _make_project(tmp_path)
        sub = _add_subject(root, "001")
        eeg = sub / "m2m_001" / "eeg_positions"
        eeg.mkdir()
        (eeg / "GSN-256.csv").touch()
        (eeg / "10-10.csv").touch()
        (eeg / ".hidden.csv").touch()  # excluded
        (eeg / "readme.txt").touch()  # excluded
        pm = PathManager(project_dir=root)
        assert pm.list_eeg_caps("001") == ["10-10.csv", "GSN-256.csv"]

    def test_returns_empty_when_no_eeg_dir(self, tmp_path):
        root = _make_project(tmp_path)
        _add_subject(root, "001")
        pm = PathManager(project_dir=root)
        assert pm.list_eeg_caps("001") == []

    def test_returns_empty_no_project(self, monkeypatch):
        monkeypatch.delenv(const.ENV_PROJECT_DIR, raising=False)
        monkeypatch.delenv(const.ENV_PROJECT_DIR_NAME, raising=False)
        pm = PathManager()
        assert pm.list_eeg_caps("001") == []


# ---------------------------------------------------------------------------
# list_flex_search_runs (lines 336-355)
# ---------------------------------------------------------------------------


class TestListFlexSearchRuns:
    def test_lists_runs_with_meta(self, tmp_path):
        root = _make_project(tmp_path)
        sub = _add_subject(root, "001")
        flex = sub / "flex-search"
        flex.mkdir()
        # run with flex_meta.json
        run1 = flex / "run1"
        run1.mkdir()
        (run1 / "flex_meta.json").touch()
        # run with electrode_positions.json
        run2 = flex / "run2"
        run2.mkdir()
        (run2 / "electrode_positions.json").touch()
        # run without either — should be excluded
        (flex / "run3").mkdir()
        # hidden dir — should be excluded
        hidden = flex / ".hidden"
        hidden.mkdir()
        (hidden / "flex_meta.json").touch()
        pm = PathManager(project_dir=root)
        assert pm.list_flex_search_runs("001") == ["run1", "run2"]

    def test_returns_empty_when_no_flex_dir(self, tmp_path):
        root = _make_project(tmp_path)
        _add_subject(root, "001")
        pm = PathManager(project_dir=root)
        assert pm.list_flex_search_runs("001") == []

    def test_returns_empty_no_project(self, monkeypatch):
        monkeypatch.delenv(const.ENV_PROJECT_DIR, raising=False)
        monkeypatch.delenv(const.ENV_PROJECT_DIR_NAME, raising=False)
        pm = PathManager()
        assert pm.list_flex_search_runs("001") == []


# ---------------------------------------------------------------------------
# Analysis naming helpers (lines 377-378, already partially covered)
# ---------------------------------------------------------------------------


class TestAtlasNameClean:
    def test_strips_nii_gz(self):
        assert PathManager._atlas_name_clean("DK40.nii.gz") == "DK40"

    def test_strips_nii(self):
        assert PathManager._atlas_name_clean("atlas.nii") == "atlas"

    def test_strips_mgz(self):
        assert PathManager._atlas_name_clean("brain.mgz") == "brain"

    def test_replaces_plus_and_dot(self):
        assert PathManager._atlas_name_clean("aparc+aseg.nii.gz") == "aparc_aseg"

    def test_handles_full_path(self):
        result = PathManager._atlas_name_clean("/usr/share/atlases/DK40.nii.gz")
        assert result == "DK40"

    def test_none_becomes_unknown(self):
        assert PathManager._atlas_name_clean(None) == "unknown_atlas"


# ---------------------------------------------------------------------------
# analysis_output_dir (lines 417-438)
# ---------------------------------------------------------------------------


class TestAnalysisOutputDir:
    @pytest.fixture
    def pm(self, tmp_path):
        root = _make_project(tmp_path)
        _add_subject(root, "001")
        return PathManager(project_dir=root)

    def test_spherical_output_dir(self, pm):
        result = pm.analysis_output_dir(
            sid="001",
            sim="mont1",
            space="mesh",
            analysis_type="spherical",
            coordinates=[1.0, 2.0, 3.0],
            radius=5.0,
            coordinate_space="MNI",
        )
        assert "sphere_x1.00_y2.00_z3.00_r5.0_MNI" in result
        assert "Mesh" in result

    def test_spherical_missing_coords_raises(self, pm):
        with pytest.raises(ValueError, match="coordinates"):
            pm.analysis_output_dir(
                sid="001",
                sim="mont1",
                space="mesh",
                analysis_type="spherical",
                coordinates=[1.0, 2.0],  # only 2
                radius=5.0,
            )

    def test_spherical_missing_radius_raises(self, pm):
        with pytest.raises(ValueError, match="coordinates"):
            pm.analysis_output_dir(
                sid="001",
                sim="mont1",
                space="mesh",
                analysis_type="spherical",
                coordinates=[1.0, 2.0, 3.0],
                radius=None,
            )

    def test_cortical_whole_head(self, pm):
        result = pm.analysis_output_dir(
            sid="001",
            sim="mont1",
            space="voxel",
            analysis_type="cortical",
            whole_head=True,
            atlas_name="DK40",
        )
        assert "whole_head_DK40" in result
        assert "Voxel" in result

    def test_cortical_region(self, pm):
        result = pm.analysis_output_dir(
            sid="001",
            sim="mont1",
            space="mesh",
            analysis_type="cortical",
            region="precentral",
            atlas_path="/some/path/aparc+aseg.nii.gz",
        )
        assert "cortical_precentral_aparc_aseg" in result

    def test_cortical_multi_region(self, pm):
        result = pm.analysis_output_dir(
            sid="001",
            sim="mont1",
            space="mesh",
            analysis_type="cortical",
            region="lh.cuneus+rh.cuneus",
            atlas_name="DK40",
        )
        assert "cortical_2regions_DK40_" in result
        assert len(result.split("/")[-1]) < 60

    def test_cortical_multi_region_deterministic(self, pm):
        """Same regions produce the same hash."""
        r1 = pm.analysis_output_dir(
            sid="001",
            sim="mont1",
            space="mesh",
            analysis_type="cortical",
            region="lh.A+lh.B+lh.C",
            atlas_name="DK40",
        )
        r2 = pm.analysis_output_dir(
            sid="001",
            sim="mont1",
            space="mesh",
            analysis_type="cortical",
            region="lh.A+lh.B+lh.C",
            atlas_name="DK40",
        )
        assert r1 == r2

    def test_cortical_no_region_raises(self, pm):
        with pytest.raises(ValueError, match="region is required"):
            pm.analysis_output_dir(
                sid="001",
                sim="mont1",
                space="mesh",
                analysis_type="cortical",
                whole_head=False,
                region=None,
            )


# ---------------------------------------------------------------------------
# analysis_dir space branching
# ---------------------------------------------------------------------------


class TestAnalysisDir:
    @pytest.fixture
    def pm(self, tmp_path):
        root = _make_project(tmp_path)
        return PathManager(project_dir=root)

    def test_mesh_space(self, pm):
        result = pm.analysis_dir("001", "mont1", "mesh")
        assert result.endswith(os.path.join("Analyses", "Mesh"))

    def test_voxel_space(self, pm):
        result = pm.analysis_dir("001", "mont1", "voxel")
        assert result.endswith(os.path.join("Analyses", "Voxel"))

    def test_other_space_defaults_to_voxel(self, pm):
        result = pm.analysis_dir("001", "mont1", "nifti")
        assert result.endswith(os.path.join("Analyses", "Voxel"))


# ---------------------------------------------------------------------------
# get_path_manager with project_dir kwarg (line 454)
# ---------------------------------------------------------------------------


class TestGetPathManagerWithDir:
    def test_sets_project_dir_on_singleton(self, tmp_path):
        root = _make_project(tmp_path)
        reset_path_manager()
        pm = get_path_manager(project_dir=root)
        assert pm.project_dir == root


# ---------------------------------------------------------------------------
# OSError branches in list helpers (lines 315-316, 352-353)
# ---------------------------------------------------------------------------


class TestListOSErrorBranches:
    def test_list_simulations_oserror(self, tmp_path, monkeypatch):
        root = _make_project(tmp_path)
        sub = _add_subject(root, "001")
        sims = sub / "Simulations"
        sims.mkdir()
        pm = PathManager(project_dir=root)
        # Patch os.scandir to raise OSError
        original_scandir = os.scandir

        def broken_scandir(path):
            if "Simulations" in str(path):
                raise OSError("permission denied")
            return original_scandir(path)

        monkeypatch.setattr(os, "scandir", broken_scandir)
        assert pm.list_simulations("001") == []

    def test_list_flex_search_runs_oserror(self, tmp_path, monkeypatch):
        root = _make_project(tmp_path)
        sub = _add_subject(root, "001")
        flex = sub / "flex-search"
        flex.mkdir()
        pm = PathManager(project_dir=root)
        original_scandir = os.scandir

        def broken_scandir(path):
            if "flex-search" in str(path):
                raise OSError("permission denied")
            return original_scandir(path)

        monkeypatch.setattr(os, "scandir", broken_scandir)
        assert pm.list_flex_search_runs("001") == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ---------------------------------------------------------------------------
# list_bids_subjects / list_freesurfer_subjects — sub-* dirs, natural sort
# ---------------------------------------------------------------------------


class TestListBidsAndFreesurferSubjects:
    def test_bids_subjects_natural_sort_and_ignores_files(self, tmp_path):
        root = _make_project(tmp_path)
        for sid in ("10", "2", "1"):
            (pathlib.Path(root) / f"sub-{sid}" / "anat").mkdir(parents=True)
        (pathlib.Path(root) / "sub-file").write_text("not a dir")
        (pathlib.Path(root) / "dataset_description.json").write_text("{}")
        pm = PathManager(project_dir=root)
        assert pm.list_bids_subjects() == ["1", "2", "10"]

    def test_freesurfer_subjects_ignore_fsaverage(self, tmp_path):
        root = _make_project(tmp_path)
        fs = pathlib.Path(root) / "derivatives" / "freesurfer"
        (fs / "sub-002" / "mri").mkdir(parents=True)
        (fs / "sub-001").mkdir()
        (fs / "fsaverage").mkdir()
        pm = PathManager(project_dir=root)
        assert pm.list_freesurfer_subjects() == ["001", "002"]

    def test_fastsurfer_subjects_natural_sort(self, tmp_path):
        root = _make_project(tmp_path)
        fs = pathlib.Path(root) / "derivatives" / "fastsurfer"
        (fs / "sub-010" / "mri").mkdir(parents=True)
        (fs / "sub-2").mkdir()
        pm = PathManager(project_dir=root)
        assert pm.list_fastsurfer_subjects() == ["2", "010"]

    def test_fastsurfer_and_freesurfer_listings_are_independent(self, tmp_path):
        """A legacy recon-all project lists under freesurfer only, and vice versa."""
        root = _make_project(tmp_path)
        (pathlib.Path(root) / "derivatives" / "freesurfer" / "sub-old").mkdir(
            parents=True
        )
        (pathlib.Path(root) / "derivatives" / "fastsurfer" / "sub-new").mkdir(
            parents=True
        )
        pm = PathManager(project_dir=root)
        assert pm.list_freesurfer_subjects() == ["old"]
        assert pm.list_fastsurfer_subjects() == ["new"]

    def test_empty_when_dirs_missing_or_project_unset(self, tmp_path):
        root = tmp_path / "bare"
        root.mkdir()
        pm = PathManager(project_dir=str(root))
        assert pm.list_bids_subjects() == []
        assert pm.list_freesurfer_subjects() == []
        assert pm.list_fastsurfer_subjects() == []
        assert pm.list_simnibs_subjects() == []
        unset = PathManager()
        unset._project_dir = None
        assert unset.list_bids_subjects() == []
        assert unset.list_freesurfer_subjects() == []
        assert unset.list_fastsurfer_subjects() == []


# ---------------------------------------------------------------------------
# resolve_resources_dir / resolve_resource_path (N0.6 spike)
# ---------------------------------------------------------------------------

from tit import paths as _paths_module  # noqa: E402
from tit.paths import resolve_resource_path, resolve_resources_dir  # noqa: E402


class TestResolveResourcesDir:
    def test_checkout_relative_fallback_is_the_real_repo_resources_dir(self):
        """No env override, and /ti-toolbox doesn't exist on this dev host (r6/skeptic-3): the
        real, unmocked resolution must land on this checkout's own resources/ directory, which
        genuinely exists on disk -- not just a plausible-looking string."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TIT_RESOURCES_DIR", None)
            resolved = resolve_resources_dir()
        assert os.path.isdir(resolved)
        assert os.path.basename(resolved) == "resources"
        # Two levels above tit/paths.py is the repo root.
        repo_root = os.path.dirname(
            os.path.dirname(os.path.abspath(_paths_module.__file__))
        )
        assert resolved == os.path.join(repo_root, "resources")

    def test_env_override_wins_when_set_and_a_real_directory(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("TIT_RESOURCES_DIR", str(tmp_path))
        assert resolve_resources_dir() == str(tmp_path)

    def test_env_override_ignored_when_it_does_not_exist(self, tmp_path, monkeypatch):
        """A stale/typo'd TIT_RESOURCES_DIR must not silently win over a real directory --
        falls through to the next candidate instead of returning a nonexistent path."""
        monkeypatch.setenv("TIT_RESOURCES_DIR", str(tmp_path / "does-not-exist"))
        resolved = resolve_resources_dir()
        assert resolved != str(tmp_path / "does-not-exist")
        assert os.path.isdir(resolved)

    def test_container_layout_wins_over_checkout_when_present(
        self, tmp_path, monkeypatch
    ):
        """Simulates the Docker image's own /ti-toolbox/resources layout by monkeypatching
        os.path.isdir rather than requiring root to actually create /ti-toolbox on this host.
        """
        monkeypatch.delenv("TIT_RESOURCES_DIR", raising=False)
        real_isdir = os.path.isdir

        def fake_isdir(path):
            if path == "/ti-toolbox/resources":
                return True
            return real_isdir(path)

        monkeypatch.setattr(_paths_module.os.path, "isdir", fake_isdir)
        assert resolve_resources_dir() == "/ti-toolbox/resources"

    def test_resolve_resource_path_joins_onto_the_resources_dir(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("TIT_RESOURCES_DIR", str(tmp_path))
        assert resolve_resource_path("amv", "GSN-256.csv") == os.path.join(
            str(tmp_path), "amv", "GSN-256.csv"
        )


class TestSubjectIdGrammar:
    """RUN-05: one documented grammar, enforced wherever an id becomes a path component."""

    def test_accepts_the_ids_real_datasets_use(self, tmp_path):
        pm = PathManager(str(tmp_path))
        for sid in ("001", "01", "ernie", "sub-01", "P_01", "ernie_extended", "1a"):
            assert pm.sub(sid).endswith(f"sub-{sid}")
            assert pm.bids_anat(sid).endswith(os.path.join(f"sub-{sid}", "anat"))

    def test_rejects_separators_traversal_and_non_strings(self, tmp_path):
        pm = PathManager(str(tmp_path))
        for bad in ("../../../outside", "..", "a/b", "a\\b", "", " ", "001 ", ".hidden",
                    "a" * 65, None, 7, ["001"]):
            with pytest.raises(ValueError, match="subject id"):
                pm.sub(bad)

    def test_every_subject_path_helper_is_guarded(self, tmp_path):
        pm = PathManager(str(tmp_path))
        helpers = [
            pm.sub, pm.m2m, pm.bids_subject, pm.bids_anat, pm.bids_dwi,
            pm.sourcedata_subject, pm.fastsurfer_subject, pm.freesurfer_subject,
            pm.qsiprep_subject, pm.qsirecon_subject, pm.logs, pm.tissue_analysis_output,
        ]
        for helper in helpers:
            with pytest.raises(ValueError, match="subject id"):
                helper("../../evil")

    def test_a_guarded_path_can_never_leave_the_project(self, tmp_path):
        from tit.paths import is_within

        pm = PathManager(str(tmp_path))
        assert is_within(str(tmp_path), pm.bids_anat("001"))
        assert not is_within(str(tmp_path), str(tmp_path.parent / "outside"))
