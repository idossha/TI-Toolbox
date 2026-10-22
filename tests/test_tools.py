"""Tests for tit/tools modules added during TODO-cleanup phases."""

import os

import pytest
from unittest.mock import patch

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


class TestMontageVisualizerResources:
    """_RESOURCES_DIR used to be a hard-coded "/ti-toolbox/resources/amv" -- only ever real
    inside the Docker image (N0.6 spike). These exercise the real (unmocked) resolved path end
    to end on this dev host, and confirm the template-copy step no longer shells out to the
    POSIX-only ``cp`` binary (replaced with shutil.copy2)."""

    def test_resources_dir_points_at_a_real_directory_with_expected_files(self):
        from tit.tools.montage_visualizer import _RESOURCES_DIR

        assert os.path.isdir(_RESOURCES_DIR)
        assert os.path.isfile(os.path.join(_RESOURCES_DIR, "GSN-256.csv"))
        assert os.path.isfile(os.path.join(_RESOURCES_DIR, "GSN-256.png"))

    def test_visualize_montage_copies_template_without_shelling_out_to_cp(
        self, tmp_path
    ):
        """Template copying is native; only drawing invokes ImageMagick."""
        from tit.tools.montage_visualizer import (
            get_expected_output_filename,
            visualize_montage,
        )

        with patch("tit.tools.montage_visualizer.subprocess.run") as mock_run:
            visualize_montage(
                montage_name="combined",
                electrode_pairs=[["E022", "E015"], ["E006", "E005"]],
                eeg_net="GSN-HydroCel-185.csv",
                output_dir=str(tmp_path),
                sim_mode="U",
            )

        assert mock_run.call_count > 0
        assert all(call.args[0][0] == "convert" for call in mock_run.call_args_list)
        out_path = tmp_path / get_expected_output_filename("combined", "U")
        assert out_path.exists()
        assert out_path.stat().st_size > 0


@pytest.mark.parametrize("existing", [False, True])
def test_montage_failure_does_not_publish_a_bare_template(tmp_path, existing):
    from tit.tools.montage_visualizer import visualize_montage

    output = tmp_path / "test_highlighted_visualization.png"
    if existing:
        output.write_bytes(b"previous annotated image")
    with patch(
        "tit.tools.montage_visualizer.subprocess.run",
        side_effect=FileNotFoundError("convert"),
    ):
        with pytest.raises(FileNotFoundError):
            visualize_montage(
                "test", [["E022", "E015"]], "GSN-HydroCel-185.csv", str(tmp_path)
            )
    if existing:
        assert output.read_bytes() == b"previous annotated image"
    else:
        assert not output.exists()
    assert not list(tmp_path.glob(".montage-*"))


@pytest.mark.parametrize("pairs", [[], [["not-an-electrode", "E015"]]])
def test_montage_rejects_unrenderable_pairs_before_writing(tmp_path, pairs):
    from tit.tools.montage_visualizer import visualize_montage

    with pytest.raises(ValueError):
        visualize_montage("test", pairs, "GSN-HydroCel-185.csv", str(tmp_path))
    assert not list(tmp_path.iterdir())


def test_montage_png_contains_colored_pixels_at_each_electrode(tmp_path):
    """Read the real PNG independently; a template-only output cannot satisfy these checks."""
    import csv
    import shutil
    import subprocess
    from pathlib import Path

    image_module = pytest.importorskip(
        "PIL.Image", reason="Pillow needed to inspect rendered pixels"
    )
    if not shutil.which("convert"):
        pytest.skip("ImageMagick is required for the real montage rendering check")
    fonts = subprocess.run(
        ["convert", "-list", "font"], capture_output=True, text=True, check=True
    )
    if "DejaVu-Sans" not in fonts.stdout:
        pytest.skip("DejaVu font is required for the real montage rendering check")
    from tit.tools.montage_visualizer import _RESOURCES_DIR, visualize_montage

    with open(Path(_RESOURCES_DIR) / "GSN-256.csv") as source:
        coordinates = {
            row["electrode_name"]: (int(row["x"]), int(row["y"]))
            for row in csv.DictReader(source)
        }
    pairs = [["E022", "E015"], ["E006", "E005"]]
    visualize_montage("pixels", pairs, "GSN-HydroCel-185.csv", str(tmp_path))
    with image_module.open(
        tmp_path / "pixels_highlighted_visualization.png"
    ) as rendered:
        image = rendered.convert("RGB")
    for channel, pair in enumerate(pairs):
        for label in pair:
            x, y = coordinates[label]
            pixels = image.crop((x - 55, y - 55, x + 55, y + 55)).getdata()
            colored = sum(
                (
                    (blue > 120 and blue > red * 1.5 and blue > green * 1.5)
                    if channel == 0
                    else (red > 120 and red > green * 1.5 and red > blue * 1.5)
                )
                for red, green, blue in pixels
            )
            assert colored > 50, f"Missing channel overlay at {label}: {colored} pixels"
