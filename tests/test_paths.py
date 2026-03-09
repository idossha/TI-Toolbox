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

    def test_t1(self, pm):
        p, root = pm
        assert p.t1("001").endswith("m2m_001/T1.nii.gz")

    def test_segmentation(self, pm):
        p, root = pm
        assert p.segmentation("001").endswith("m2m_001/segmentation")

    def test_tissue_labeling(self, pm):
        p, root = pm
        assert p.tissue_labeling("001").endswith("segmentation/Labeling.nii.gz")

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
# list_subjects — natural sort + m2m filter (lines 252, 257)
# ---------------------------------------------------------------------------

class TestListSubjects:
    def test_lists_subjects_with_m2m(self, tmp_path):
        root = _make_project(tmp_path)
        _add_subject(root, "002")
        _add_subject(root, "001")
        # sub-999 without m2m should be excluded
        (pathlib.Path(root) / "derivatives" / "SimNIBS" / "sub-999").mkdir()
        pm = PathManager(project_dir=root)
        assert pm.list_subjects() == ["001", "002"]

    def test_empty_when_no_simnibs(self, tmp_path):
        root = tmp_path / "empty"
        root.mkdir()
        pm = PathManager()
        pm._project_dir = str(root)
        assert pm.list_subjects() == []


# ---------------------------------------------------------------------------
# list_all_subjects (lines 280-296)
# ---------------------------------------------------------------------------

class TestListAllSubjects:
    def test_merges_all_sources(self, tmp_path):
        root = _make_project(tmp_path)
        _add_subject(root, "001")  # has m2m
        # sub-002 in project root only
        (pathlib.Path(root) / "sub-002").mkdir()
        # sub-003 in SimNIBS without m2m
        (pathlib.Path(root) / "derivatives" / "SimNIBS" / "sub-003").mkdir()
        pm = PathManager(project_dir=root)
        result = pm.list_all_subjects()
        assert result == ["001", "002", "003"]

    def test_deduplication(self, tmp_path):
        root = _make_project(tmp_path)
        _add_subject(root, "001")
        (pathlib.Path(root) / "sub-001").mkdir()
        pm = PathManager(project_dir=root)
        result = pm.list_all_subjects()
        assert result == ["001"]


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
        assert "region_precentral_aparc_aseg" in result

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
