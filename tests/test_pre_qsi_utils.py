"""Tests for tit.pre.qsi.utils — QSI utility functions."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

from tit.pre.qsi.utils import (
    _get_total_mem_bytes_from_proc,
    _parse_cpuset,
    _read_first_line,
    check_image_exists,
    format_memory_limit,
    get_container_resource_limits,
    get_freesurfer_license_path,
    get_host_project_dir,
    get_inherited_dood_resources,
    pull_image_if_needed,
    resolve_host_project_path,
    validate_bids_dwi,
    validate_qsiprep_output,
)

MODULE = "tit.pre.qsi.utils"


class TestResolveHostProjectPath:
    """Tests for resolve_host_project_path."""

    @patch.dict(os.environ, {"LOCAL_PROJECT_DIR": "/host/myproject"})
    def test_replaces_mnt_path(self):
        result = resolve_host_project_path("/mnt/myproject/sub-001/anat")
        assert result == "/host/myproject/sub-001/anat"

    @patch.dict(os.environ, {"LOCAL_PROJECT_DIR": "/host/myproject"})
    def test_short_mnt_path(self):
        result = resolve_host_project_path("/mnt/myproject")
        assert result == "/host/myproject"

    @patch.dict(os.environ, {"LOCAL_PROJECT_DIR": "/host/myproject"})
    def test_non_mnt_path_unchanged(self):
        result = resolve_host_project_path("/some/other/path")
        assert result == "/some/other/path"

    @patch.dict(os.environ, {}, clear=True)
    def test_no_env_var_raises(self):
        # Remove the env var if it exists
        os.environ.pop("LOCAL_PROJECT_DIR", None)
        with pytest.raises(ValueError, match="LOCAL_PROJECT_DIR"):
            resolve_host_project_path("/mnt/proj")


class TestGetHostProjectDir:
    """Tests for get_host_project_dir."""

    @patch.dict(os.environ, {"LOCAL_PROJECT_DIR": "/host/proj"})
    def test_returns_env_var(self):
        assert get_host_project_dir() == "/host/proj"

    @patch.dict(os.environ, {}, clear=True)
    def test_no_env_raises(self):
        os.environ.pop("LOCAL_PROJECT_DIR", None)
        with pytest.raises(ValueError, match="LOCAL_PROJECT_DIR"):
            get_host_project_dir()


class TestCheckImageExists:
    """Tests for check_image_exists."""

    @patch(f"{MODULE}.subprocess.run")
    def test_image_exists(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        assert check_image_exists("pennlinc/qsiprep", "1.1.1") is True

    @patch(f"{MODULE}.subprocess.run")
    def test_image_not_exists(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        assert check_image_exists("pennlinc/qsiprep", "1.1.1") is False

    @patch(f"{MODULE}.subprocess.run", side_effect=FileNotFoundError("docker not found"))
    def test_exception_returns_false(self, mock_run):
        assert check_image_exists("pennlinc/qsiprep", "1.1.1") is False


class TestPullImageIfNeeded:
    """Tests for pull_image_if_needed."""

    @patch(f"{MODULE}.check_image_exists", return_value=True)
    def test_already_exists(self, mock_check):
        logger = MagicMock()
        assert pull_image_if_needed("img", "tag", logger) is True

    @patch(f"{MODULE}.subprocess.run")
    @patch(f"{MODULE}.check_image_exists", return_value=False)
    def test_pull_success(self, mock_check, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        logger = MagicMock()
        assert pull_image_if_needed("img", "tag", logger) is True

    @patch(f"{MODULE}.subprocess.run")
    @patch(f"{MODULE}.check_image_exists", return_value=False)
    def test_pull_failure(self, mock_check, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        logger = MagicMock()
        assert pull_image_if_needed("img", "tag", logger) is False

    @patch(f"{MODULE}.subprocess.run", side_effect=OSError("network error"))
    @patch(f"{MODULE}.check_image_exists", return_value=False)
    def test_pull_exception(self, mock_check, mock_run):
        logger = MagicMock()
        assert pull_image_if_needed("img", "tag", logger) is False

    @patch(f"{MODULE}.subprocess.run")
    @patch(f"{MODULE}.check_image_exists", return_value=False)
    def test_pull_timeout(self, mock_check, mock_run):
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=1800)
        logger = MagicMock()
        assert pull_image_if_needed("img", "tag", logger) is False


class TestValidateBidsDwi:
    """Tests for validate_bids_dwi."""

    def test_no_dwi_dir(self, tmp_path):
        valid, msg = validate_bids_dwi(str(tmp_path), "001", MagicMock())
        assert valid is False
        assert "not found" in msg

    def test_no_dwi_files(self, tmp_path):
        dwi = tmp_path / "sub-001" / "dwi"
        dwi.mkdir(parents=True)
        valid, msg = validate_bids_dwi(str(tmp_path), "001", MagicMock())
        assert valid is False
        assert "No DWI NIfTI" in msg

    def test_no_bval(self, tmp_path):
        dwi = tmp_path / "sub-001" / "dwi"
        dwi.mkdir(parents=True)
        (dwi / "sub-001_dwi.nii.gz").touch()
        valid, msg = validate_bids_dwi(str(tmp_path), "001", MagicMock())
        assert valid is False
        assert "bval" in msg

    def test_no_bvec(self, tmp_path):
        dwi = tmp_path / "sub-001" / "dwi"
        dwi.mkdir(parents=True)
        (dwi / "sub-001_dwi.nii.gz").touch()
        (dwi / "sub-001_dwi.bval").touch()
        valid, msg = validate_bids_dwi(str(tmp_path), "001", MagicMock())
        assert valid is False
        assert "bvec" in msg

    def test_valid(self, tmp_path):
        dwi = tmp_path / "sub-001" / "dwi"
        dwi.mkdir(parents=True)
        (dwi / "sub-001_dwi.nii.gz").touch()
        (dwi / "sub-001_dwi.bval").touch()
        (dwi / "sub-001_dwi.bvec").touch()
        valid, msg = validate_bids_dwi(str(tmp_path), "001", MagicMock())
        assert valid is True
        assert msg is None


class TestValidateQsiprepOutput:
    """Tests for validate_qsiprep_output."""

    def test_no_dir(self, tmp_path):
        valid, msg = validate_qsiprep_output(str(tmp_path), "001")
        assert valid is False

    def test_no_dwi_dir(self, tmp_path):
        d = tmp_path / "derivatives" / "qsiprep" / "sub-001"
        d.mkdir(parents=True)
        valid, msg = validate_qsiprep_output(str(tmp_path), "001")
        assert valid is False

    def test_no_preproc_files(self, tmp_path):
        d = tmp_path / "derivatives" / "qsiprep" / "sub-001" / "dwi"
        d.mkdir(parents=True)
        valid, msg = validate_qsiprep_output(str(tmp_path), "001")
        assert valid is False

    def test_valid(self, tmp_path):
        d = tmp_path / "derivatives" / "qsiprep" / "sub-001" / "dwi"
        d.mkdir(parents=True)
        (d / "sub-001_space-T1w_desc-preproc_dwi.nii.gz").touch()
        valid, msg = validate_qsiprep_output(str(tmp_path), "001")
        assert valid is True


class TestGetFreesurferLicensePath:
    """Tests for get_freesurfer_license_path."""

    @patch.dict(os.environ, {"FS_LICENSE": "/opt/fs/license.txt"})
    def test_env_set(self):
        assert get_freesurfer_license_path() == "/opt/fs/license.txt"

    @patch.dict(os.environ, {}, clear=True)
    def test_env_not_set(self):
        os.environ.pop("FS_LICENSE", None)
        assert get_freesurfer_license_path() is None


class TestFormatMemoryLimit:
    """Tests for format_memory_limit."""

    def test_format(self):
        assert format_memory_limit(32) == "32g"
        assert format_memory_limit(4) == "4g"


class TestParseCpuset:
    """Tests for _parse_cpuset."""

    def test_range(self):
        assert _parse_cpuset("0-3") == 4

    def test_individual(self):
        assert _parse_cpuset("0,1,2") == 3

    def test_mixed(self):
        assert _parse_cpuset("0-3,6,8-9") == 7

    def test_empty(self):
        assert _parse_cpuset("") is None

    def test_none(self):
        assert _parse_cpuset(None) is None

    def test_invalid_range(self):
        assert _parse_cpuset("3-1") is None

    def test_invalid_value(self):
        assert _parse_cpuset("abc") is None

    def test_invalid_range_value(self):
        assert _parse_cpuset("a-b") is None


class TestReadFirstLine:
    """Tests for _read_first_line."""

    def test_reads_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello\nworld\n")
        assert _read_first_line(str(f)) == "hello"

    def test_nonexistent_file(self):
        assert _read_first_line("/nonexistent/file") is None


class TestGetTotalMemBytesFromProc:
    """Tests for _get_total_mem_bytes_from_proc."""

    @patch(
        "builtins.open",
        mock_open(read_data="MemTotal:      154457636 kB\nMemFree:      100000 kB\n"),
    )
    def test_reads_meminfo(self):
        result = _get_total_mem_bytes_from_proc()
        assert result == 154457636 * 1024

    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_file_not_found(self, mock_f):
        assert _get_total_mem_bytes_from_proc() is None


class TestGetContainerResourceLimits:
    """Tests for get_container_resource_limits."""

    @patch(f"{MODULE}._read_first_line")
    def test_cgroup_v2(self, mock_read):
        def side_effect(path):
            if "memory.max" in path:
                return "34359738368"  # 32 GB
            if "cpuset.cpus.effective" in path:
                return "0-7"
            return None

        mock_read.side_effect = side_effect

        cpus, mem = get_container_resource_limits()
        assert cpus == 8
        assert mem == 34359738368

    @patch(f"{MODULE}._read_first_line")
    def test_unlimited_memory(self, mock_read):
        def side_effect(path):
            if "memory.max" in path:
                return "max"
            return None

        mock_read.side_effect = side_effect

        cpus, mem = get_container_resource_limits()
        assert mem is None

    @patch(f"{MODULE}._read_first_line")
    def test_very_large_memory_treated_as_unlimited(self, mock_read):
        def side_effect(path):
            if "memory.max" in path:
                return str(2**62)
            return None

        mock_read.side_effect = side_effect

        cpus, mem = get_container_resource_limits()
        assert mem is None

    @patch(f"{MODULE}._read_first_line")
    def test_cpu_max_quota(self, mock_read):
        def side_effect(path):
            if path == "/sys/fs/cgroup/cpu.max":
                return "400000 100000"  # 4 CPUs
            return None

        mock_read.side_effect = side_effect

        cpus, mem = get_container_resource_limits()
        assert cpus == 4

    @patch(f"{MODULE}._read_first_line", return_value=None)
    def test_no_cgroup_info(self, mock_read):
        cpus, mem = get_container_resource_limits()
        assert cpus is None
        assert mem is None

    @patch(f"{MODULE}._read_first_line")
    def test_cgroup_v1_memory(self, mock_read):
        """Tests cgroup v1 memory limit path."""

        def side_effect(path):
            if path == "/sys/fs/cgroup/memory.max":
                return None  # No v2
            if path == "/sys/fs/cgroup/memory/memory.limit_in_bytes":
                return str(16 * 1024**3)  # 16 GB
            return None

        mock_read.side_effect = side_effect

        cpus, mem = get_container_resource_limits()
        assert mem == 16 * 1024**3

    @patch(f"{MODULE}._read_first_line")
    def test_cgroup_v1_cpu_quota(self, mock_read):
        """Tests cgroup v1 CPU quota path."""

        def side_effect(path):
            if path == "/sys/fs/cgroup/cpu.max":
                return None  # No v2 cpu.max
            if path == "/sys/fs/cgroup/cpu/cpu.cfs_quota_us":
                return "200000"
            if path == "/sys/fs/cgroup/cpu/cpu.cfs_period_us":
                return "100000"
            return None

        mock_read.side_effect = side_effect

        cpus, mem = get_container_resource_limits()
        assert cpus == 2

    @patch(f"{MODULE}._read_first_line")
    def test_cgroup_v1_large_memory_unlimited(self, mock_read):
        """Very large v1 memory treated as unlimited."""

        def side_effect(path):
            if path == "/sys/fs/cgroup/memory/memory.limit_in_bytes":
                return str(2**62)
            return None

        mock_read.side_effect = side_effect

        cpus, mem = get_container_resource_limits()
        assert mem is None

    @patch(f"{MODULE}._read_first_line")
    def test_cpu_max_with_max_value(self, mock_read):
        """cpu.max with 'max' quota (unlimited) is skipped."""

        def side_effect(path):
            if path == "/sys/fs/cgroup/cpu.max":
                return "max 100000"
            return None

        mock_read.side_effect = side_effect

        cpus, mem = get_container_resource_limits()
        assert cpus is None

    @patch(f"{MODULE}._read_first_line")
    def test_cpuset_and_cpu_quota_uses_minimum(self, mock_read):
        """Uses minimum of cpuset and quota-derived count."""

        def side_effect(path):
            if "cpuset.cpus.effective" in path:
                return "0-7"  # 8 CPUs
            if path == "/sys/fs/cgroup/cpu.max":
                return "400000 100000"  # 4 CPUs
            return None

        mock_read.side_effect = side_effect

        cpus, mem = get_container_resource_limits()
        assert cpus == 4


class TestGetInheritedDoodResources:
    """Tests for get_inherited_dood_resources."""

    @patch(f"{MODULE}.get_container_resource_limits", return_value=(8, 34359738368))
    @patch(f"{MODULE}._get_total_mem_bytes_from_proc")
    def test_with_limits(self, mock_proc, mock_limits):
        cpus, mem = get_inherited_dood_resources()
        assert cpus == 8
        assert mem == 32  # 34359738368 / 1024^3 = 32

    @patch(f"{MODULE}.get_container_resource_limits", return_value=(None, None))
    @patch(f"{MODULE}._get_total_mem_bytes_from_proc", return_value=None)
    @patch(f"{MODULE}.os.cpu_count", return_value=4)
    def test_fallback_defaults(self, mock_cpu, mock_proc, mock_limits):
        cpus, mem = get_inherited_dood_resources()
        assert cpus == 4

    @patch(f"{MODULE}.get_container_resource_limits", return_value=(None, None))
    @patch(f"{MODULE}._get_total_mem_bytes_from_proc", return_value=8 * 1024**3)
    @patch(f"{MODULE}.os.cpu_count", return_value=2)
    def test_proc_memory(self, mock_cpu, mock_proc, mock_limits):
        cpus, mem = get_inherited_dood_resources()
        assert cpus == 2
        assert mem == 8

    @patch(f"{MODULE}.get_container_resource_limits", return_value=(None, None))
    @patch(f"{MODULE}._get_total_mem_bytes_from_proc", return_value=2 * 1024**3)
    @patch(f"{MODULE}.os.cpu_count", return_value=1)
    def test_minimum_memory(self, mock_cpu, mock_proc, mock_limits):
        cpus, mem = get_inherited_dood_resources()
        assert mem >= 4  # Minimum 4GB
