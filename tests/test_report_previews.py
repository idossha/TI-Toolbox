"""Fast report-preview tests for manual visualization.

These tests exercise the HTML report generators with deterministic synthetic data
so developers can inspect report layout without running SimNIBS or flex-search.
Set ``TI_TOOLBOX_WRITE_REPORT_PREVIEWS=1`` to copy the generated reports to a
stable ignored directory (``.cache/report-previews`` by default).
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import zlib
from pathlib import Path
from unittest.mock import patch

import pytest

PREVIEW_ENV = "TI_TOOLBOX_WRITE_REPORT_PREVIEWS"
PREVIEW_DIR_ENV = "TI_TOOLBOX_REPORT_PREVIEW_DIR"
DEFAULT_PREVIEW_DIR = Path(".cache/report-previews")


def _png_base64(width: int, height: int, palette: str = "montage") -> str:
    """Return a small deterministic PNG as base64 without external deps."""

    def pixel(x: int, y: int) -> tuple[int, int, int]:
        if palette == "field":
            return (
                min(255, 40 + x * 3),
                min(255, 20 + y * 3),
                max(0, 220 - (x + y)),
            )
        if (x // 8 + y // 8) % 2 == 0:
            return (42, 92, 170)
        return (239, 148, 56)

    raw = bytearray()
    for y in range(height):
        raw.append(0)  # PNG filter type 0 for each scanline
        for x in range(width):
            raw.extend(pixel(x, y))

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(kind + data) & 0xFFFFFFFF
        return len(data).to_bytes(4, "big") + kind + data + crc.to_bytes(4, "big")

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(
        b"IHDR",
        width.to_bytes(4, "big") + height.to_bytes(4, "big") + bytes([8, 2, 0, 0, 0]),
    )
    png += chunk(b"IDAT", zlib.compress(bytes(raw), level=9))
    png += chunk(b"IEND", b"")
    return base64.b64encode(png).decode("ascii")


def _maybe_copy_preview(report_path: Path) -> Path | None:
    """Copy *report_path* to a stable ignored preview directory when enabled."""
    if not os.environ.get(PREVIEW_ENV):
        return None

    preview_dir = Path(os.environ.get(PREVIEW_DIR_ENV, DEFAULT_PREVIEW_DIR))
    preview_dir.mkdir(parents=True, exist_ok=True)
    destination = preview_dir / report_path.name
    shutil.copy2(report_path, destination)
    print(f"Report preview written to: {destination.resolve()}")
    return destination


def _write_ernie_simulation_config(project_dir: Path) -> Path:
    """Create an ernie/BU_eg2 config snapshot matching the report loader."""
    config_dir = (
        project_dir
        / "derivatives"
        / "SimNIBS"
        / "sub-ernie"
        / "Simulations"
        / "BU_eg2"
        / "documentation"
    )
    config_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "subject_id": "ernie",
        "simulation_name": "BU_eg2",
        "simulation_mode": "TI",
        "montage_mode": "net",
        "eeg_net": "EEG10-10_Cutini_2011.csv",
        "conductivity": "scalar",
        "electrode_pairs": [["AF3", "AF4"], ["C5", "C6"]],
        "is_xyz_montage": False,
        "intensities": [1.0, 1.0],
        "electrode_geometry": {
            "shape": "ellipse",
            "dimensions": [8.0, 8.0],
            "gel_thickness": 4.0,
            "rubber_thickness": 2.0,
        },
        "mapping_options": {
            "map_to_surf": True,
            "map_to_vol": True,
            "map_to_mni": True,
            "map_to_fsavg": False,
        },
        "created_at": "2026-05-05T19:20:12",
    }
    path = config_dir / "config.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


@pytest.mark.unit
def test_generate_visualizable_simulation_report_preview(tmp_path):
    """Generate a complete simulation report quickly from synthetic provenance."""
    with patch("subprocess.run", side_effect=FileNotFoundError):
        from tit.reporting.generators.simulation import SimulationReportGenerator

        project_dir = tmp_path / "ernie_project"
        _write_ernie_simulation_config(project_dir)

        generator = SimulationReportGenerator(
            project_dir=project_dir,
            subject_id="ernie",
            simulation_session_id="preview_simulation",
        )
        generator.add_simulation_parameters(
            simulation_mode="TI",
            conductivity_type="scalar",
            eeg_net="placeholder-runtime-net",
            command="ti-toolbox preview simulation report (synthetic)",
        )
        generator.add_subject(
            "ernie",
            m2m_path=str(
                project_dir / "derivatives" / "SimNIBS" / "sub-ernie" / "m2m_ernie"
            ),
            status="completed",
        )
        # Intentionally stale runtime pair; the report should rehydrate AF3-AF4/C5-C6.
        generator.add_montage("BU_eg2", [["E1", "E2"]])
        generator.add_simulation_result(
            "ernie",
            "BU_eg2",
            output_files={
                "mesh": ["BU_eg2_TI_max.msh", "BU_eg2_TI_normal.msh"],
                "nifti": ["grey_BU_eg2_TI_max_MNI.nii.gz"],
            },
            duration=42.0,
            status="completed",
        )
        generator.add_visualization(
            "ernie",
            "BU_eg2",
            "montage",
            _png_base64(96, 64, "montage"),
            title="Synthetic Montage Preview",
            caption="Synthetic embedded image for report layout inspection.",
        )
        generator.add_visualization(
            "ernie",
            "BU_eg2",
            "field",
            _png_base64(96, 64, "field"),
            title="Synthetic Field Preview",
            caption="Synthetic field-map placeholder; no simulation was run.",
        )

        output = generator.generate(
            output_path=tmp_path / "simulation_report_ernie_preview.html"
        )

    html = output.read_text(encoding="utf-8")
    assert output.exists()
    assert "AF3" in html and "C5" in html
    assert "E1</td>" not in html
    assert "Simulation Overview" in html
    assert "Machine-Readable Provenance" in html
    assert "https://doi.org/10.1016/j.cell.2017.05.024" in html
    assert not list(tmp_path.glob("*_METHODS.md"))
    assert not list(tmp_path.glob("*_CITATION*"))
    assert not list(tmp_path.glob("*_provenance.json"))

    _maybe_copy_preview(output)


@pytest.mark.unit
def test_generate_visualizable_flex_search_report_preview(tmp_path):
    """Generate a complete flex-search report quickly from synthetic results."""
    with patch("subprocess.run", side_effect=FileNotFoundError):
        from tit.reporting.generators.flex_search import FlexSearchReportGenerator

        project_dir = tmp_path / "ernie_project"
        generator = FlexSearchReportGenerator(
            project_dir=project_dir,
            subject_id="ernie",
            session_id="preview_flex_search",
        )
        generator.set_configuration(
            electrode_net="EEG10-10_Cutini_2011.csv",
            optimization_target="maximize TI_max in target ROI",
            optimization_goal="target_focality",
            n_candidates=128,
            n_starts=8,
            selection_method="best_score",
            intensity_ch1=1.0,
            intensity_ch2=1.0,
            electrode_shape="ellipse",
            electrode_dimensions_mm=[8.0, 8.0],
            electrode_thickness_mm=2.0,
            min_electrode_distance_mm=20.0,
            mapping_enabled=True,
            run_final_electrode_simulation=False,
        )
        generator.set_roi_info(
            roi_name="left insula synthetic sphere",
            roi_type="sphere",
            coordinates=[-31.3, 24.0, -37.0],
            coordinate_space="MNI",
            radius=10.0,
            volume_mm3=4188.8,
            n_voxels=524,
        )
        for rank, (pair1, pair2, score) in enumerate(
            [
                (("AF3", "AF4"), ("C5", "C6"), 0.8123),
                (("F3", "F4"), ("CP5", "CP6"), 0.7641),
                (("FC5", "FC6"), ("P3", "P4"), 0.7210),
            ],
            start=1,
        ):
            generator.add_search_result(
                rank=rank,
                electrode_1a=pair1[0],
                electrode_1b=pair1[1],
                electrode_2a=pair2[0],
                electrode_2b=pair2[1],
                score=score,
                mean_field_roi=0.22 / rank,
                max_field_roi=0.51 / rank,
                focality=0.73 / rank,
            )
        generator.set_best_solution(
            electrode_pairs=[
                {"electrode1": "AF3", "electrode2": "AF4"},
                {"electrode1": "C5", "electrode2": "C6"},
            ],
            score=0.8123,
            metrics={
                "mean_field_roi": 0.22,
                "max_field_roi": 0.51,
                "focality": 0.73,
                "off_target_mean": 0.04,
            },
            montage_image_base64=_png_base64(96, 64, "montage"),
            field_map_base64=_png_base64(96, 64, "field"),
            electrode_coordinates=[
                [-42.1, 45.2, 70.0],
                [41.8, 44.9, 70.5],
                [-58.0, -12.5, 42.0],
                [57.6, -12.2, 42.5],
            ],
            channel_array_indices=[[0, 0], [0, 1], [1, 0], [1, 1]],
            mapped_labels=["AF3", "AF4", "C5", "C6"],
            mapped_positions=[
                [-41.9, 45.0, 70.1],
                [41.5, 44.5, 70.2],
                [-57.8, -12.1, 42.2],
                [57.2, -12.0, 42.1],
            ],
        )

        output = generator.generate(
            output_path=tmp_path / "flex_search_report_ernie_preview.html"
        )

    html = output.read_text(encoding="utf-8")
    assert output.exists()
    assert "Flex-Search Optimization Report" in html
    assert "left insula synthetic sphere" in html
    assert "AF3-AF4" in html
    assert "Search Results" in html
    assert "Optimal Solution" in html
    assert "Computer-Friendly Output" in html
    assert "Haber2026" in html
    assert "Weise2024" in html
    assert "max-width: 520px" in html
    assert "https://doi.org/10.1016/j.brs.2025.103016" in html
    assert "https://doi.org/10.1088/1741-2552/ab41ba" in html
    assert not list(tmp_path.glob("*_METHODS.md"))
    assert not list(tmp_path.glob("*_CITATION*"))
    assert not list(tmp_path.glob("*_provenance.json"))

    _maybe_copy_preview(output)
