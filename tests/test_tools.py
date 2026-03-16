"""Tests for tit/tools modules added during TODO-cleanup phases."""

import pytest
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# check_for_update
# ---------------------------------------------------------------------------


class TestParseVersion:
    def test_basic_version(self):
        from tit.tools.check_for_update import parse_version

        assert parse_version("2.2.1") == (2, 2, 1)

    def test_strips_v_prefix(self):
        from tit.tools.check_for_update import parse_version

        assert parse_version("v2.2.1") == (2, 2, 1)

    def test_two_part_version(self):
        from tit.tools.check_for_update import parse_version

        assert parse_version("3.0") == (3, 0)

    def test_strips_whitespace(self):
        from tit.tools.check_for_update import parse_version

        assert parse_version("  v1.0.0  ") == (1, 0, 0)


class TestCheckForNewVersion:
    """Tests for check_for_new_version with mocked requests (lazy import)."""

    def _run_with_mocked_release(self, current: str, tag_name: str):
        """Helper: mock the requests module inside check_for_new_version."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"tag_name": tag_name}
        mock_resp.raise_for_status = MagicMock()

        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_resp

        # The function does `import requests` locally, so we patch
        # the builtins __import__ to intercept it.
        import builtins

        real_import = builtins.__import__

        def patched_import(name, *args, **kwargs):
            if name == "requests":
                return mock_requests
            return real_import(name, *args, **kwargs)

        from tit.tools.check_for_update import check_for_new_version

        with patch.object(builtins, "__import__", side_effect=patched_import):
            return check_for_new_version(current)

    def test_newer_version_returns_string(self):
        result = self._run_with_mocked_release("2.2.1", "v3.0.0")
        assert result == "3.0.0"

    def test_same_version_returns_none(self):
        result = self._run_with_mocked_release("2.2.1", "v2.2.1")
        assert result is None

    def test_older_version_returns_none(self):
        result = self._run_with_mocked_release("2.2.1", "v1.0.0")
        assert result is None


# ---------------------------------------------------------------------------
# gmsh_opt
# ---------------------------------------------------------------------------


class TestGmshOpt:
    def test_import_create_mesh_opt_file(self):
        from tit.tools.gmsh_opt import create_mesh_opt_file

        assert callable(create_mesh_opt_file)

    def test_creates_opt_file(self, tmp_path):
        from tit.tools.gmsh_opt import create_mesh_opt_file

        mesh_path = str(tmp_path / "test.msh")
        result = create_mesh_opt_file(mesh_path)
        assert result == f"{mesh_path}.opt"
        assert (tmp_path / "test.msh.opt").exists()

    def test_opt_file_contains_field_info(self, tmp_path):
        from tit.tools.gmsh_opt import create_mesh_opt_file

        mesh_path = str(tmp_path / "test.msh")
        field_info = {
            "fields": ["TI_max", "TI_normal"],
            "max_values": {"TI_max": 0.5, "TI_normal": 0.3},
        }
        result = create_mesh_opt_file(mesh_path, field_info=field_info)
        content = (tmp_path / "test.msh.opt").read_text()
        assert "TI_max" in content
        assert "TI_normal" in content
        assert "0.5" in content
