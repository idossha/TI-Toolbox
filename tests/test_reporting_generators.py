#!/usr/bin/env python3
"""
Unit tests for TI-Toolbox reporting generators and deeper reportlet code.

Covers:
- generators/base_generator.py
- generators/flex_search.py
- generators/simulation.py
- reportlets/metadata.py
- reportlets/images.py
- reportlets/text.py
- reportlets/references.py
- core/base.py (remaining gaps)
- core/templates.py (remaining gaps)
"""

import json
import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Reportlets — metadata.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConductivityTableReportlet:
    """Tests for ConductivityTableReportlet."""

    def test_defaults_loaded_when_no_conductivities_given(self):
        from tit.reporting.reportlets.metadata import (
            ConductivityTableReportlet,
            DEFAULT_CONDUCTIVITIES,
        )

        r = ConductivityTableReportlet()
        assert len(r.conductivities) == len(DEFAULT_CONDUCTIVITIES)

    def test_custom_conductivities(self):
        from tit.reporting.reportlets.metadata import ConductivityTableReportlet

        conds = {
            "white_matter": {"value": 0.15, "unit": "S/m", "source": "Custom"},
        }
        r = ConductivityTableReportlet(conductivities=conds)
        assert len(r.conductivities) == 1
        html = r.render_html()
        assert "White Matter" in html
        assert "0.1500" in html
        assert "Custom" in html

    def test_show_sources_false_hides_source_column(self):
        from tit.reporting.reportlets.metadata import ConductivityTableReportlet

        conds = {"gm": {"value": 0.275, "unit": "S/m", "source": "SimNIBS"}}
        r = ConductivityTableReportlet(conductivities=conds, show_sources=False)
        html = r.render_html()
        assert "Source" not in html
        assert "source-cell" not in html

    def test_show_sources_true_shows_source_column(self):
        from tit.reporting.reportlets.metadata import ConductivityTableReportlet

        conds = {"gm": {"value": 0.275, "unit": "S/m", "source": "SimNIBS"}}
        r = ConductivityTableReportlet(conductivities=conds, show_sources=True)
        html = r.render_html()
        assert "Source" in html
        assert "source-cell" in html

    def test_integer_tissue_key(self):
        from tit.reporting.reportlets.metadata import ConductivityTableReportlet

        conds = {1: {"value": 0.126, "unit": "S/m", "name": "Brain Tissue"}}
        r = ConductivityTableReportlet(conductivities=conds)
        html = r.render_html()
        assert "Brain Tissue" in html

    def test_integer_tissue_key_without_name(self):
        from tit.reporting.reportlets.metadata import ConductivityTableReportlet

        conds = {2: {"value": 0.5, "unit": "S/m"}}
        r = ConductivityTableReportlet(conductivities=conds)
        html = r.render_html()
        assert "Tissue 2" in html

    def test_conductivity_field_name_fallback(self):
        from tit.reporting.reportlets.metadata import ConductivityTableReportlet

        conds = {"wm": {"conductivity": 0.126, "unit": "S/m"}}
        r = ConductivityTableReportlet(conductivities=conds)
        html = r.render_html()
        assert "0.1260" in html

    def test_reference_field_name_fallback(self):
        from tit.reporting.reportlets.metadata import ConductivityTableReportlet

        conds = {"wm": {"value": 0.1, "unit": "S/m", "reference": "Ref2024"}}
        r = ConductivityTableReportlet(conductivities=conds)
        html = r.render_html()
        assert "Ref2024" in html

    def test_title_rendered(self):
        from tit.reporting.reportlets.metadata import ConductivityTableReportlet

        r = ConductivityTableReportlet(title="My Conductivities")
        html = r.render_html()
        assert "<h3>My Conductivities</h3>" in html

    def test_conductivity_type_badge(self):
        from tit.reporting.reportlets.metadata import ConductivityTableReportlet

        r = ConductivityTableReportlet(conductivity_type="anisotropic")
        html = r.render_html()
        assert "anisotropic" in html
        assert "conductivity-type-badge" in html

    def test_set_conductivity(self):
        from tit.reporting.reportlets.metadata import ConductivityTableReportlet

        r = ConductivityTableReportlet(conductivities={})
        r.set_conductivity("new_tissue", 0.999, "S/m", "My Source")
        assert r.conductivities["new_tissue"]["value"] == 0.999
        assert r.conductivities["new_tissue"]["source"] == "My Source"

    def test_set_conductivity_default_source(self):
        from tit.reporting.reportlets.metadata import ConductivityTableReportlet

        r = ConductivityTableReportlet(conductivities={})
        r.set_conductivity("tissue_x", 0.5)
        assert r.conductivities["tissue_x"]["source"] == "User-defined"

    def test_to_dict(self):
        from tit.reporting.reportlets.metadata import ConductivityTableReportlet

        r = ConductivityTableReportlet(
            conductivities={"wm": {"value": 0.1}},
            conductivity_type="scalar",
            show_sources=True,
        )
        d = r.to_dict()
        assert d["conductivity_type"] == "scalar"
        assert d["show_sources"] is True
        assert "conductivities" in d

    def test_reportlet_type(self):
        from tit.reporting.reportlets.metadata import ConductivityTableReportlet
        from tit.reporting.core.protocols import ReportletType

        r = ConductivityTableReportlet()
        assert r.reportlet_type == ReportletType.TABLE


@pytest.mark.unit
class TestSummaryCardsReportlet:
    """Tests for SummaryCardsReportlet."""

    def test_empty_cards_returns_empty_string(self):
        from tit.reporting.reportlets.metadata import SummaryCardsReportlet

        r = SummaryCardsReportlet()
        assert r.render_html() == ""

    def test_add_card_and_render(self):
        from tit.reporting.reportlets.metadata import SummaryCardsReportlet

        r = SummaryCardsReportlet(columns=3)
        r.add_card(label="Subject", value="sub-01")
        r.add_card(label="Mode", value="TI", color="#28a745")
        html = r.render_html()
        assert "Subject" in html
        assert "sub-01" in html
        assert "columns-3" in html
        assert "#28a745" in html

    def test_card_with_icon(self):
        from tit.reporting.reportlets.metadata import SummaryCardsReportlet

        r = SummaryCardsReportlet()
        r.add_card(label="Test", value="val", icon="*")
        html = r.render_html()
        assert "card-icon" in html
        assert "*" in html

    def test_card_with_subtitle(self):
        from tit.reporting.reportlets.metadata import SummaryCardsReportlet

        r = SummaryCardsReportlet()
        r.add_card(label="Test", value="val", subtitle="extra info")
        html = r.render_html()
        assert "card-subtitle" in html
        assert "extra info" in html

    def test_title_rendered(self):
        from tit.reporting.reportlets.metadata import SummaryCardsReportlet

        r = SummaryCardsReportlet(title="Summary")
        r.add_card(label="X", value="Y")
        html = r.render_html()
        assert "<h3>Summary</h3>" in html

    def test_to_dict(self):
        from tit.reporting.reportlets.metadata import SummaryCardsReportlet

        r = SummaryCardsReportlet(columns=2)
        r.add_card(label="A", value=1)
        d = r.to_dict()
        assert d["columns"] == 2
        assert len(d["cards"]) == 1


@pytest.mark.unit
class TestParameterListReportlet:
    """Tests for ParameterListReportlet."""

    def test_empty_parameters_returns_empty_string(self):
        from tit.reporting.reportlets.metadata import ParameterListReportlet

        r = ParameterListReportlet()
        assert r.render_html() == ""

    def test_add_category_and_render(self):
        from tit.reporting.reportlets.metadata import ParameterListReportlet

        r = ParameterListReportlet(title="Config")
        r.add_category("Simulation", {"mode": "TI", "intensity": 1.0})
        html = r.render_html()
        assert "Simulation" in html
        assert "Mode" in html
        assert "TI" in html

    def test_add_parameter(self):
        from tit.reporting.reportlets.metadata import ParameterListReportlet

        r = ParameterListReportlet()
        r.add_parameter("General", "n_threads", 4)
        assert r.parameters["General"]["n_threads"] == 4

    def test_add_parameter_creates_category(self):
        from tit.reporting.reportlets.metadata import ParameterListReportlet

        r = ParameterListReportlet()
        r.add_parameter("NewCat", "key", "val")
        assert "NewCat" in r.parameters

    def test_format_value_types(self):
        from tit.reporting.reportlets.metadata import ParameterListReportlet

        r = ParameterListReportlet()
        assert r._format_value(None) == "<em>N/A</em>"
        assert r._format_value(True) == "Yes"
        assert r._format_value(False) == "No"
        assert r._format_value([1, 2, 3]) == "1, 2, 3"
        assert "x: 1" in r._format_value({"x": 1})
        assert r._format_value(3.14159) == "3.142"
        assert r._format_value("hello") == "hello"

    def test_to_dict(self):
        from tit.reporting.reportlets.metadata import ParameterListReportlet

        r = ParameterListReportlet(title="Params")
        r.add_category("Cat1", {"a": 1})
        d = r.to_dict()
        assert d["title"] == "Params"
        assert "Cat1" in d["parameters"]


# ---------------------------------------------------------------------------
# Reportlets — images.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSliceSeriesReportlet:
    """Tests for SliceSeriesReportlet."""

    def test_empty_slices_shows_placeholder(self):
        from tit.reporting.reportlets.images import SliceSeriesReportlet

        r = SliceSeriesReportlet()
        html = r.render_html()
        assert "No slices available" in html

    def test_add_slice_with_base64_string(self):
        from tit.reporting.reportlets.images import SliceSeriesReportlet

        r = SliceSeriesReportlet(orientation="sagittal")
        r.add_slice("AAAA", label="Slice 1")
        html = r.render_html()
        assert "sagittal" in html
        assert "AAAA" in html
        assert "Slice 1" in html

    def test_add_slice_with_bytes(self):
        from tit.reporting.reportlets.images import SliceSeriesReportlet

        r = SliceSeriesReportlet()
        r.add_slice(b"\x89PNG", label="Raw")
        assert len(r.slices) == 1
        assert r.slices[0]["base64"] == base64.b64encode(b"\x89PNG").decode("utf-8")

    def test_add_slice_with_path(self, tmp_path):
        from tit.reporting.reportlets.images import SliceSeriesReportlet

        img_file = tmp_path / "slice.png"
        img_file.write_bytes(b"fake_png_data")
        r = SliceSeriesReportlet()
        r.add_slice(img_file, label="From file")
        assert len(r.slices) == 1

    def test_add_slice_with_pil_image(self):
        from tit.reporting.reportlets.images import SliceSeriesReportlet

        mock_image = MagicMock()
        mock_image.save = MagicMock(
            side_effect=lambda buf, format: buf.write(b"image_data")
        )
        r = SliceSeriesReportlet()
        r.add_slice(mock_image, label="PIL")
        assert len(r.slices) == 1
        assert r.slices[0]["base64"] != ""

    def test_process_image_pil_failure(self):
        from tit.reporting.reportlets.images import SliceSeriesReportlet

        r = SliceSeriesReportlet()
        bad_obj = MagicMock()
        bad_obj.save = MagicMock(side_effect=AttributeError)
        r.add_slice(bad_obj)
        assert r.slices[0]["base64"] == ""

    def test_load_from_files(self, tmp_path):
        from tit.reporting.reportlets.images import SliceSeriesReportlet

        for i in range(3):
            (tmp_path / f"slice_{i}.png").write_bytes(b"data")
        files = [tmp_path / f"slice_{i}.png" for i in range(3)]
        r = SliceSeriesReportlet()
        r.load_from_files(files)
        assert len(r.slices) == 3

    def test_load_from_files_skips_missing(self, tmp_path):
        from tit.reporting.reportlets.images import SliceSeriesReportlet

        existing = tmp_path / "exists.png"
        existing.write_bytes(b"data")
        r = SliceSeriesReportlet()
        r.load_from_files([existing, tmp_path / "missing.png"])
        assert len(r.slices) == 1

    def test_caption_rendered(self):
        from tit.reporting.reportlets.images import SliceSeriesReportlet

        r = SliceSeriesReportlet(caption="Test caption")
        r.add_slice("data")
        html = r.render_html()
        assert "Test caption" in html
        assert "series-caption" in html

    def test_to_dict(self):
        from tit.reporting.reportlets.images import SliceSeriesReportlet

        r = SliceSeriesReportlet(title="Slices", orientation="coronal", caption="Cap")
        r.add_slice("data")
        d = r.to_dict()
        assert d["orientation"] == "coronal"
        assert d["slice_count"] == 1
        assert d["caption"] == "Cap"


@pytest.mark.unit
class TestMontageImageReportlet:
    """Tests for MontageImageReportlet."""

    def test_no_image_shows_placeholder(self):
        from tit.reporting.reportlets.images import MontageImageReportlet

        r = MontageImageReportlet(montage_name="TestMontage")
        html = r.render_html()
        assert "Montage visualization unavailable" in html
        assert "expected montage visualization PNG" in html
        assert "TestMontage" in html

    def test_set_base64_data(self):
        from tit.reporting.reportlets.images import MontageImageReportlet

        r = MontageImageReportlet()
        r.set_base64_data("ABCDEF", mime_type="image/jpeg")
        html = r.render_html()
        assert "ABCDEF" in html
        assert "image/jpeg" in html

    def test_add_electrode_pair(self):
        from tit.reporting.reportlets.images import MontageImageReportlet

        r = MontageImageReportlet()
        r.add_electrode_pair("Pair 1", "E001", "E002", intensity=1.5)
        assert len(r.electrode_pairs) == 1
        assert r.electrode_pairs[0]["electrode1"] == "E001"

    def test_electrode_pairs_table_rendered(self):
        from tit.reporting.reportlets.images import MontageImageReportlet

        r = MontageImageReportlet()
        r.add_electrode_pair("Pair 1", "E001", "E002", intensity=1.5)
        html = r.render_html()
        assert "E001" in html
        assert "E002" in html
        assert "1.50 mA" in html

    def test_electrode_pairs_no_intensity(self):
        from tit.reporting.reportlets.images import MontageImageReportlet

        r = MontageImageReportlet()
        r.add_electrode_pair("Pair 1", "A", "B", intensity=None)
        html = r.render_html()
        # Intensity should show em-dash when None

    def test_electrode_pairs_empty_intensity(self):
        from tit.reporting.reportlets.images import MontageImageReportlet

        r = MontageImageReportlet()
        r.add_electrode_pair("Pair 1", "A", "B", intensity=None)
        r.electrode_pairs[0]["intensity"] = ""
        html = r.render_html()
        # Should not crash

    def test_electrode_pairs_invalid_intensity(self):
        from tit.reporting.reportlets.images import MontageImageReportlet

        r = MontageImageReportlet()
        r.add_electrode_pair("Pair 1", "A", "B")
        r.electrode_pairs[0]["intensity"] = "not_a_number"
        html = r.render_html()
        assert "not_a_number" in html

    def test_load_image_from_path(self, tmp_path):
        from tit.reporting.reportlets.images import MontageImageReportlet

        img = tmp_path / "montage.png"
        img.write_bytes(b"fake_png")
        r = MontageImageReportlet(image_source=img)
        assert r._base64_data is not None

    def test_load_image_from_jpeg(self, tmp_path):
        from tit.reporting.reportlets.images import MontageImageReportlet

        img = tmp_path / "montage.jpg"
        img.write_bytes(b"fake_jpg")
        r = MontageImageReportlet(image_source=img)
        assert r._mime_type == "image/jpeg"

    def test_load_image_from_bytes(self):
        from tit.reporting.reportlets.images import MontageImageReportlet

        r = MontageImageReportlet(image_source=b"raw_image_data")
        assert r._base64_data is not None

    def test_load_image_pil_fallback(self):
        from tit.reporting.reportlets.images import MontageImageReportlet

        mock_img = MagicMock()
        mock_img.save = MagicMock(side_effect=lambda buf, format: buf.write(b"data"))
        r = MontageImageReportlet(image_source=mock_img)
        assert r._base64_data is not None

    def test_load_image_pil_failure(self):
        from tit.reporting.reportlets.images import MontageImageReportlet

        bad_obj = MagicMock()
        bad_obj.save = MagicMock(side_effect=AttributeError)
        r = MontageImageReportlet(image_source=bad_obj)
        assert r._base64_data is None

    def test_to_dict(self):
        from tit.reporting.reportlets.images import MontageImageReportlet

        r = MontageImageReportlet(montage_name="M1")
        r.set_base64_data("data")
        d = r.to_dict()
        assert d["montage_name"] == "M1"
        assert d["has_image"] is True

    def test_to_dict_no_image(self):
        from tit.reporting.reportlets.images import MontageImageReportlet

        r = MontageImageReportlet(montage_name="M2")
        d = r.to_dict()
        assert d["has_image"] is False


@pytest.mark.unit
class TestMethodsBoilerplateReportlet:
    """Tests for MethodsBoilerplateReportlet."""

    def test_custom_boilerplate_text(self):
        from tit.reporting.reportlets.text import MethodsBoilerplateReportlet

        r = MethodsBoilerplateReportlet(boilerplate_text="Custom boilerplate text.")
        assert r.generate_boilerplate() == "Custom boilerplate text."

    def test_set_boilerplate(self):
        from tit.reporting.reportlets.text import MethodsBoilerplateReportlet

        r = MethodsBoilerplateReportlet()
        r.set_boilerplate("Overridden text.")
        assert r.generate_boilerplate() == "Overridden text."

    def test_simulation_boilerplate(self):
        from tit.reporting.reportlets.text import MethodsBoilerplateReportlet

        r = MethodsBoilerplateReportlet(pipeline_type="simulation")
        text = r.generate_boilerplate()
        assert "Temporal interference" in text
        assert "TI-Toolbox" in text
        assert "SimNIBS" in text

    def test_simulation_boilerplate_with_electrode_params(self):
        from tit.reporting.reportlets.text import MethodsBoilerplateReportlet

        r = MethodsBoilerplateReportlet(
            pipeline_type="simulation",
            parameters={"electrode_shape": "circular", "electrode_size": "10mm"},
        )
        text = r.generate_boilerplate()
        assert "circular" in text
        assert "10 mm" in text

    def test_simulation_boilerplate_minimal_electrode_fallback_is_publication_safe(
        self,
    ):
        from tit.reporting.reportlets.text import MethodsBoilerplateReportlet

        r = MethodsBoilerplateReportlet(pipeline_type="simulation")
        text = r.generate_boilerplate()
        assert "electrode recorded-size electrodes" not in text
        assert "recorded layer" not in text
        assert "Electrode geometry was modeled" in text
        assert "available simulation metadata" in text

    def test_simulation_boilerplate_with_intensity(self):
        from tit.reporting.reportlets.text import MethodsBoilerplateReportlet

        r = MethodsBoilerplateReportlet(
            pipeline_type="simulation",
            parameters={"intensity": 2.0},
        )
        text = r.generate_boilerplate()
        assert "2.0 mA" in text

    def test_simulation_boilerplate_from_config_provenance(self):
        from tit.reporting.reportlets.text import MethodsBoilerplateReportlet

        r = MethodsBoilerplateReportlet(
            pipeline_type="simulation",
            parameters={
                "subject_id": "ernie",
                "simulation_mode": "TI",
                "conductivity_type": "scalar",
                "mapping_options": {"map_to_surf": True, "map_to_mni": False},
                "software_versions": {"ti_toolbox": "2.3.1", "simnibs": "4.5"},
                "electrode_geometry": {
                    "shape": "ellipse",
                    "dimensions": [8.0, 8.0],
                    "gel_thickness": 4.0,
                    "rubber_thickness": 2.0,
                },
                "montages": [
                    {
                        "name": "BU_eg2",
                        "type": "TI",
                        "montage_mode": "net",
                        "eeg_net": "EEG10-10_Cutini_2011.csv",
                        "electrode_pairs": [
                            {
                                "name": "Pair 1",
                                "electrode1": "AF3",
                                "electrode2": "AF4",
                                "intensity": 1.0,
                            },
                            {
                                "name": "Pair 2",
                                "electrode1": "C5",
                                "electrode2": "C6",
                                "intensity": 1.0,
                            },
                        ],
                    }
                ],
            },
        )
        text = r.generate_boilerplate()
        assert "subject ernie" in text
        assert "montage BU_eg2" in text
        assert "AF3-AF4" in text
        assert "C5-C6" in text
        assert "1.0 mA per pair" in text
        assert "scalar conductivity" in text
        assert "ellipse 8x8 mm electrodes" in text
        assert "4 mm conductive gel" in text
        assert "2 mm rubber" in text
        assert "TI_max and TI_normal" in text
        assert "NIfTI derivatives" in text
        assert "[Grossman2017]" in text
        assert "TI-Toolbox" in text
        assert "SimNIBS" in text

    def test_optimization_boilerplate(self):
        from tit.reporting.reportlets.text import MethodsBoilerplateReportlet

        r = MethodsBoilerplateReportlet(pipeline_type="optimization")
        text = r.generate_boilerplate()
        assert "optimization" in text.lower()
        assert "flex-search" in text
        assert "Haber2026" in text
        assert "Weise2024" in text

    def test_flex_search_boilerplate_uses_optimization_text(self):
        from tit.reporting.reportlets.text import MethodsBoilerplateReportlet

        r = MethodsBoilerplateReportlet(
            pipeline_type="flex-search",
            parameters={"target_region": "hippocampus", "n_candidates": 42},
        )
        text = r.generate_boilerplate()
        assert "hippocampus" in text
        assert "42" in text
        assert "leadfield-free" in text
        assert "Haber2026" in text
        assert "Weise2024" in text

    def test_optimization_boilerplate_with_method(self):
        from tit.reporting.reportlets.text import MethodsBoilerplateReportlet

        r = MethodsBoilerplateReportlet(
            pipeline_type="optimization",
            parameters={"optimization_method": "differential evolution"},
        )
        text = r.generate_boilerplate()
        assert "flex-search" in text

    def test_optimization_boilerplate_with_target(self):
        from tit.reporting.reportlets.text import MethodsBoilerplateReportlet

        r = MethodsBoilerplateReportlet(
            pipeline_type="optimization",
            parameters={"target_region": "hippocampus"},
        )
        text = r.generate_boilerplate()
        assert "hippocampus" in text

    def test_generic_boilerplate(self):
        from tit.reporting.reportlets.text import MethodsBoilerplateReportlet

        r = MethodsBoilerplateReportlet(pipeline_type="unknown_type")
        text = r.generate_boilerplate()
        assert "TI-Toolbox" in text
        assert "SimNIBS" in text

    def test_render_html(self):
        from tit.reporting.reportlets.text import MethodsBoilerplateReportlet

        r = MethodsBoilerplateReportlet(title="Methods")
        html = r.render_html()
        assert "Methods" in html
        assert "copy-btn" in html
        assert "boilerplate-intro" in html
        assert "methods-boilerplate-reportlet" in html
        assert "methods-text" in html
        assert "monospace" not in html

    def test_to_dict(self):
        from tit.reporting.reportlets.text import MethodsBoilerplateReportlet

        r = MethodsBoilerplateReportlet(pipeline_type="simulation")
        d = r.to_dict()
        assert d["pipeline_type"] == "simulation"
        assert "boilerplate" in d


@pytest.mark.unit
class TestTIToolboxReferencesReportlet:
    """Tests for TIToolboxReferencesReportlet."""

    def test_include_defaults_no_components_uses_core_references(self):
        from tit.reporting.reportlets.references import TIToolboxReferencesReportlet

        r = TIToolboxReferencesReportlet(include_defaults=True)
        keys = {ref["key"] for ref in r.references}
        assert "haber2026_titoolbox" in keys
        assert "grossman2017_ti" in keys
        assert "saturnino2019_simnibs_fem" in keys
        assert "puonti2020_charm" in keys

    def test_no_defaults_is_empty(self):
        from tit.reporting.reportlets.references import TIToolboxReferencesReportlet

        r = TIToolboxReferencesReportlet(include_defaults=False)
        assert len(r.references) == 0

    def test_simulation_components_sets_pipeline(self):
        from tit.reporting.reportlets.references import TIToolboxReferencesReportlet

        r = TIToolboxReferencesReportlet(
            include_defaults=True, pipeline_components=["simulation"]
        )
        assert r.pipeline_components == ["simulation"]
        keys = {ref["key"] for ref in r.references}
        assert "haber2026_titoolbox" in keys
        assert "grossman2017_ti" in keys
        assert "saturnino2019_simnibs_fem" in keys
        assert "saturnino2015_electrodes" in keys
        assert "puonti2020_charm" in keys
        assert "jurcak2007_eeg_positions" in keys
        html = r.render_html()
        assert "https://doi.org/10.1016/j.brs.2025.103016" in html
        assert "https://doi.org/10.1016/j.cell.2017.05.024" in html
        assert "https://doi.org/10.1088/1741-2552/ab41ba" in html

    def test_flex_search_components_sets_pipeline(self):
        from tit.reporting.reportlets.references import TIToolboxReferencesReportlet

        r = TIToolboxReferencesReportlet(
            include_defaults=True, pipeline_components=["flex-search"]
        )
        assert r.pipeline_components == ["flex-search"]
        keys = {ref["key"] for ref in r.references}
        assert "haber2026_titoolbox" in keys
        assert "grossman2017_ti" in keys
        assert "weise2024_leadfield_free" in keys

    def test_component_specific_refs_dti_keys_match(self):
        from tit.reporting.reportlets.references import TIToolboxReferencesReportlet

        r = TIToolboxReferencesReportlet(
            include_defaults=True, pipeline_components=["dti"]
        )
        keys = {ref["key"] for ref in r.references}
        assert "assaf2005_charmed" in keys
        assert "rullmann2009_dti_conductivity" in keys

    def test_unknown_component_falls_back_to_core(self):
        from tit.reporting.reportlets.references import TIToolboxReferencesReportlet

        r = TIToolboxReferencesReportlet(
            include_defaults=True, pipeline_components=["totally_unknown"]
        )
        keys = {ref["key"] for ref in r.references}
        assert "haber2026_titoolbox" in keys
        assert "grossman2017_ti" in keys
        assert "saturnino2019_simnibs_fem" in keys

    def test_nilearn_component_adds_visualization_citation(self):
        from tit.reporting.reportlets.references import TIToolboxReferencesReportlet

        r = TIToolboxReferencesReportlet(
            include_defaults=True, pipeline_components=["simulation", "nilearn"]
        )
        keys = {ref["key"] for ref in r.references}
        assert "abraham2014_nilearn" in keys
        assert "10.3389/fninf.2014.00014" in r.render_html()

    def test_add_default_reference_found(self):
        from tit.reporting.reportlets.references import TIToolboxReferencesReportlet

        r = TIToolboxReferencesReportlet(include_defaults=False)
        result = r.add_default_reference("FreeSurfer")
        assert result is True
        assert len(r.references) == 1
        assert r.references[0]["key"] == "fischl2012_freesurfer"

    def test_add_default_reference_not_found(self):
        from tit.reporting.reportlets.references import TIToolboxReferencesReportlet

        r = TIToolboxReferencesReportlet(include_defaults=False)
        result = r.add_default_reference("NonexistentReference")
        assert result is False
        assert len(r.references) == 0

    def test_add_default_reference_no_duplicate(self):
        from tit.reporting.reportlets.references import TIToolboxReferencesReportlet

        r = TIToolboxReferencesReportlet(include_defaults=False)
        r.add_default_reference("FreeSurfer")
        r.add_default_reference("fischl2012_freesurfer")
        count = sum(1 for ref in r.references if ref["key"] == "fischl2012_freesurfer")
        assert count == 1

    def test_render_html_with_manual_refs(self):
        """Use add_default_reference to add refs that actually work."""
        from tit.reporting.reportlets.references import TIToolboxReferencesReportlet

        r = TIToolboxReferencesReportlet(include_defaults=False)
        r.add_default_reference("FreeSurfer")
        r.add_default_reference("Gmsh")
        html = r.render_html()
        assert "references-list" in html
        assert "DOI" in html


@pytest.mark.unit
class TestReferenceHelperFunctions:
    """Tests for module-level helper functions."""

    def test_get_default_references(self):
        from tit.reporting.reportlets.references import get_default_references

        refs = get_default_references()
        assert isinstance(refs, list)
        assert len(refs) > 0
        assert "key" in refs[0]
        assert "citation" in refs[0]

    def test_get_reference_by_key_found(self):
        from tit.reporting.reportlets.references import get_reference_by_key

        ref = get_reference_by_key("FreeSurfer")
        assert ref is not None
        assert ref["key"] == "fischl2012_freesurfer"

    def test_get_reference_by_key_supports_legacy_display_keys(self):
        from tit.reporting.reportlets.references import get_reference_by_key

        expected_keys = {
            "TI Theory": "grossman2017_ti",
            "SimNIBS": "saturnino2019_simnibs_fem",
            "CHARM Segmentation": "puonti2020_charm",
            "Multipolar TI": "botzanowski2025_mti",
            "Electrode Parameters": "saturnino2015_electrodes",
            "Quasi-static Approximation": "gaugain2023_quasistatic",
            "Electric Field Determinants": "opitz2015_tdcs_determinants",
            "International Consortium for Brain Mapping (ICBM)": "mazziotta2001_icbm",
            "Glasser Atlas": "glasser2016_hcp_mmp",
            "Destrieux Atlas": "destrieux2010_atlas",
            "Desikan-Killiany-Tourville Atlas": "alexander2019_dkt",
            "EEG Positions": "jurcak2007_eeg_positions",
            "EGI Sensor Nets": "egi_sensor_nets",
            "FreeSurfer": "fischl2012_freesurfer",
            "Brain Imaging Data Structure (BIDS)": "bids2016",
            "BIDS Apps": "gorgolewski2017_bids_apps",
            "QSIprep": "cieslak2021_qsiprep",
            "DICOM to NIfTI Converter (dcm2niix)": "li2016_dcm2niix",
            "Leadfield-free Optimization Framework": "weise2024_leadfield_free",
            "charmed": "assaf2005_charmed",
            "dti_conductivity": "rullmann2009_dti_conductivity",
            "Gmsh": "geuzaine2009_gmsh",
            "Blender": "blender",
        }

        for legacy_key, expected_key in expected_keys.items():
            ref = get_reference_by_key(legacy_key)
            assert ref is not None, legacy_key
            assert ref["key"] == expected_key

    def test_get_reference_by_key_not_found(self):
        from tit.reporting.reportlets.references import get_reference_by_key

        ref = get_reference_by_key("NonexistentRef")
        assert ref is None


# ---------------------------------------------------------------------------
# core/base.py — fill remaining coverage gaps
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestImageReportletBase:
    """Tests for ImageReportlet from core/base.py."""

    def test_no_image_placeholder(self):
        from tit.reporting.core.base import ImageReportlet

        r = ImageReportlet(title="Empty Image")
        html = r.render_html()
        assert "No image available" in html

    def test_set_base64_data(self):
        from tit.reporting.core.base import ImageReportlet

        r = ImageReportlet(title="Test")
        r.set_base64_data("ABC123", mime_type="image/jpeg")
        html = r.render_html()
        assert "ABC123" in html
        assert "image/jpeg" in html

    def test_load_image_from_path(self, tmp_path):
        from tit.reporting.core.base import ImageReportlet

        img = tmp_path / "test.png"
        img.write_bytes(b"fake_png")
        r = ImageReportlet(image_source=img)
        assert r._base64_data is not None

    def test_load_image_from_bytes(self):
        from tit.reporting.core.base import ImageReportlet

        r = ImageReportlet(image_source=b"\x89PNG")
        assert r._base64_data is not None

    def test_load_image_pil(self):
        from tit.reporting.core.base import ImageReportlet

        mock_img = MagicMock()
        mock_img.save = MagicMock(side_effect=lambda buf, format: buf.write(b"data"))
        r = ImageReportlet(image_source=mock_img)
        assert r._base64_data is not None

    def test_load_image_pil_failure(self):
        from tit.reporting.core.base import ImageReportlet

        bad = MagicMock()
        bad.save = MagicMock(side_effect=AttributeError)
        r = ImageReportlet(image_source=bad)
        assert r._base64_data is None

    def test_get_mime_type_extensions(self):
        from tit.reporting.core.base import ImageReportlet

        r = ImageReportlet()
        assert r._get_mime_type(Path("test.png")) == "image/png"
        assert r._get_mime_type(Path("test.jpg")) == "image/jpeg"
        assert r._get_mime_type(Path("test.jpeg")) == "image/jpeg"
        assert r._get_mime_type(Path("test.gif")) == "image/gif"
        assert r._get_mime_type(Path("test.svg")) == "image/svg+xml"
        assert r._get_mime_type(Path("test.webp")) == "image/webp"
        assert r._get_mime_type(Path("test.bmp")) == "image/png"  # fallback

    def test_width_and_height_in_style(self):
        from tit.reporting.core.base import ImageReportlet

        r = ImageReportlet(title="Sized", width="500px", height="300px")
        r.set_base64_data("data")
        html = r.render_html()
        assert "max-width: 500px" in html
        assert "max-height: 300px" in html

    def test_caption_rendered(self):
        from tit.reporting.core.base import ImageReportlet

        r = ImageReportlet(title="Img", caption="My caption")
        r.set_base64_data("data")
        html = r.render_html()
        assert "My caption" in html
        assert "image-caption" in html

    def test_to_dict(self):
        from tit.reporting.core.base import ImageReportlet

        r = ImageReportlet(title="T", caption="C", alt_text="alt")
        d = r.to_dict()
        assert d["caption"] == "C"
        assert d["alt_text"] == "alt"
        assert d["has_image"] is False


@pytest.mark.unit
class TestTableReportletBase:
    """Fill coverage gaps in TableReportlet from core/base.py."""

    def test_format_cell_bool_true(self):
        from tit.reporting.core.base import TableReportlet

        r = TableReportlet([[True]])
        html = r.render_html()
        assert "Yes" in html

    def test_format_cell_bool_false(self):
        from tit.reporting.core.base import TableReportlet

        r = TableReportlet([[False]])
        html = r.render_html()
        assert "No" in html

    def test_compact_class(self):
        from tit.reporting.core.base import TableReportlet

        r = TableReportlet([{"a": 1}], compact=True)
        html = r.render_html()
        assert "compact" in html

    def test_sortable_class(self):
        from tit.reporting.core.base import TableReportlet

        r = TableReportlet([{"a": 1}], sortable=True)
        html = r.render_html()
        assert "sortable" in html

    def test_dataframe_like_input(self):
        """Test DataFrame-like object with to_dict and columns attributes."""
        from tit.reporting.core.base import TableReportlet

        df_mock = MagicMock()
        df_mock.columns = ["col1", "col2"]
        df_mock.values.tolist.return_value = [[1, 2], [3, 4]]
        r = TableReportlet(df_mock)
        assert r.headers == ["col1", "col2"]
        assert r.rows == [[1, 2], [3, 4]]


# ---------------------------------------------------------------------------
# core/templates.py — fill remaining coverage gaps
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTemplates:
    """Tests for get_html_template function."""

    def test_basic_template(self):
        from tit.reporting.core.templates import get_html_template

        html = get_html_template(title="Test Report", content="<p>Hello</p>")
        assert "<!DOCTYPE html>" in html
        assert "<title>Test Report</title>" in html
        assert "<p>Hello</p>" in html

    def test_toc_included(self):
        from tit.reporting.core.templates import get_html_template

        html = get_html_template(
            title="Test", content="body", toc_html="<ul><li>Section</li></ul>"
        )
        assert "report-nav" in html
        assert "Contents" in html
        assert "Section" in html

    def test_no_toc(self):
        from tit.reporting.core.templates import get_html_template

        html = get_html_template(title="Test", content="body", toc_html="")
        # The nav element should not be present (class is still in CSS)
        assert '<nav class="report-nav">' not in html

    def test_metadata_included(self):
        from tit.reporting.core.templates import get_html_template

        html = get_html_template(
            title="Test", content="body", metadata_html="<span>Subject: 001</span>"
        )
        assert "Subject: 001" in html

    def test_custom_footer(self):
        from tit.reporting.core.templates import get_html_template

        html = get_html_template(
            title="Test", content="body", footer_html="<footer>Custom Footer</footer>"
        )
        assert "Custom Footer" in html

    def test_default_footer(self):
        from tit.reporting.core.templates import get_html_template

        html = get_html_template(title="Test", content="body")
        assert "TI-Toolbox" in html
        assert "report-footer" in html

    def test_custom_css(self):
        from tit.reporting.core.templates import get_html_template

        html = get_html_template(
            title="Test", content="body", custom_css=".my-class { color: red; }"
        )
        assert "Custom Styles" in html
        assert ".my-class { color: red; }" in html

    def test_custom_js(self):
        from tit.reporting.core.templates import get_html_template

        html = get_html_template(
            title="Test", content="body", custom_js="console.log('test');"
        )
        assert "Custom Scripts" in html
        assert "console.log('test');" in html


# ---------------------------------------------------------------------------
# Generators — BaseReportGenerator
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBaseReportGenerator:
    """Tests for BaseReportGenerator (abstract base)."""

    def _make_concrete_generator(self, tmp_path, subject_id="001"):
        """Create a concrete subclass for testing."""
        from tit.reporting.generators.base_generator import BaseReportGenerator

        class ConcreteGenerator(BaseReportGenerator):
            def _get_default_title(self):
                return f"Test Report - {self.subject_id}"

            def _get_report_prefix(self):
                return "test_report"

            def _build_report(self):
                pass

        with patch("subprocess.run", side_effect=FileNotFoundError):
            gen = ConcreteGenerator(
                project_dir=tmp_path,
                subject_id=subject_id,
                session_id="ses01",
                report_type="test",
            )
        return gen

    def test_initialization(self, tmp_path):
        gen = self._make_concrete_generator(tmp_path)
        assert gen.subject_id == "001"
        assert gen.session_id == "ses01"
        assert gen.report_type == "test"
        assert gen.metadata.title == "Test Report - 001"

    def test_default_session_id(self, tmp_path):
        from tit.reporting.generators.base_generator import BaseReportGenerator

        class Gen(BaseReportGenerator):
            def _get_default_title(self):
                return "Title"

            def _get_report_prefix(self):
                return "prefix"

            def _build_report(self):
                pass

        with patch("subprocess.run", side_effect=FileNotFoundError):
            gen = Gen(project_dir=tmp_path)
        # Should have auto-generated session_id
        assert gen.session_id is not None

    def test_collect_software_versions_has_python(self, tmp_path):
        gen = self._make_concrete_generator(tmp_path)
        assert "python" in gen.software_versions

    def test_collect_software_versions_has_ti_toolbox(self, tmp_path):
        gen = self._make_concrete_generator(tmp_path)
        assert "ti_toolbox" in gen.software_versions

    def test_add_error(self, tmp_path):
        gen = self._make_concrete_generator(tmp_path)
        gen.add_error("Something failed", context="test", step="init")
        assert len(gen.errors) == 1
        assert gen.errors[0]["message"] == "Something failed"
        assert gen.errors[0]["severity"] == "error"
        assert "timestamp" in gen.errors[0]

    def test_add_warning(self, tmp_path):
        gen = self._make_concrete_generator(tmp_path)
        gen.add_warning("Something suspicious", context="test", step="check")
        assert len(gen.warnings) == 1
        assert gen.warnings[0]["severity"] == "warning"

    def test_get_output_dir_with_subject(self, tmp_path):
        gen = self._make_concrete_generator(tmp_path, subject_id="001")
        output_dir = gen.get_output_dir()
        assert "sub-001" in str(output_dir)
        assert "reports" in str(output_dir)

    def test_get_output_dir_without_subject(self, tmp_path):
        from tit.reporting.generators.base_generator import BaseReportGenerator

        class Gen(BaseReportGenerator):
            def _get_default_title(self):
                return "No Subject"

            def _get_report_prefix(self):
                return "prefix"

            def _build_report(self):
                pass

        with patch("subprocess.run", side_effect=FileNotFoundError):
            gen = Gen(project_dir=tmp_path)
        output_dir = gen.get_output_dir()
        assert "sub-" not in str(output_dir)

    def test_get_output_path_with_timestamp(self, tmp_path):
        gen = self._make_concrete_generator(tmp_path)
        path = gen.get_output_path(timestamp="20250101_120000")
        assert "test_report_20250101_120000.html" in str(path)

    def test_get_output_path_auto_timestamp(self, tmp_path):
        gen = self._make_concrete_generator(tmp_path)
        path = gen.get_output_path()
        assert "test_report_" in str(path)
        assert str(path).endswith(".html")

    def test_ensure_output_dir_creates(self, tmp_path):
        gen = self._make_concrete_generator(tmp_path)
        output_dir = gen._ensure_output_dir()
        assert output_dir.exists()

    def test_create_dataset_description(self, tmp_path):
        gen = self._make_concrete_generator(tmp_path)
        gen._create_dataset_description()
        desc_path = (
            tmp_path
            / "derivatives"
            / "ti-toolbox"
            / "reports"
            / "dataset_description.json"
        )
        assert desc_path.exists()
        data = json.loads(desc_path.read_text())
        assert data["Name"] == "TI-Toolbox Reports"
        assert data["BIDSVersion"] == "1.8.0"

    def test_add_errors_section(self, tmp_path):
        gen = self._make_concrete_generator(tmp_path)
        gen.add_error("Error 1", context="ctx", step="step1")
        gen.add_warning("Warn 1")
        gen._add_errors_section()
        section = gen.assembler.get_section("errors")
        assert section is not None
        assert section.order == 90

    def test_add_methods_section(self, tmp_path):
        gen = self._make_concrete_generator(tmp_path)
        gen._add_methods_section(pipeline_components=["test"])
        section = gen.assembler.get_section("methods")
        assert section is not None
        assert section.order == 95

    def test_add_references_section(self, tmp_path):
        gen = self._make_concrete_generator(tmp_path)
        gen._add_references_section(pipeline_components=["simulation"])
        section = gen.assembler.get_section("references")
        assert section is not None
        assert section.order == 100

    def test_get_methods_parameters(self, tmp_path):
        gen = self._make_concrete_generator(tmp_path)
        params = gen._get_methods_parameters()
        assert "software_versions" in params

    def test_generate_creates_file(self, tmp_path):
        gen = self._make_concrete_generator(tmp_path)
        output_path = tmp_path / "output" / "report.html"
        result = gen.generate(output_path=output_path)
        assert result == output_path
        assert output_path.exists()
        content = output_path.read_text()
        assert "<!DOCTYPE html>" in content

    def test_generate_auto_path(self, tmp_path):
        gen = self._make_concrete_generator(tmp_path)
        result = gen.generate()
        assert result.exists()
        assert str(result).endswith(".html")


# ---------------------------------------------------------------------------
# Generators — FlexSearchReportGenerator
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFlexSearchReportGenerator:
    """Tests for FlexSearchReportGenerator."""

    def _make_generator(self, tmp_path):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            from tit.reporting.generators.flex_search import FlexSearchReportGenerator

            gen = FlexSearchReportGenerator(
                project_dir=tmp_path,
                subject_id="001",
                session_id="ses01",
            )
        return gen

    def test_initialization(self, tmp_path):
        gen = self._make_generator(tmp_path)
        assert gen.report_type == "flex-search"
        assert gen.subject_id == "001"
        assert (
            gen._get_default_title() == "Flex-Search Optimization Report - Subject 001"
        )
        assert gen._get_report_prefix() == "flex_search_report"

    def test_set_configuration(self, tmp_path):
        gen = self._make_generator(tmp_path)
        gen.set_configuration(
            electrode_net="GSN-128",
            optimization_target="mean",
            n_candidates=200,
            intensity_ch1=1.5,
        )
        assert gen.config["electrode_net"] == "GSN-128"
        assert gen.config["n_candidates"] == 200

    def test_set_roi_info(self, tmp_path):
        gen = self._make_generator(tmp_path)
        gen.set_roi_info(
            roi_name="Hippocampus",
            roi_type="sphere",
            coordinates=[10.0, -20.0, 30.0],
            radius=5.0,
            volume_mm3=500.0,
            n_voxels=100,
        )
        assert gen.roi_info["name"] == "Hippocampus"
        assert gen.roi_info["type"] == "sphere"
        assert gen.roi_info["radius"] == 5.0

    def test_add_search_result(self, tmp_path):
        gen = self._make_generator(tmp_path)
        gen.add_search_result(
            rank=1,
            electrode_1a="E001",
            electrode_1b="E002",
            electrode_2a="E003",
            electrode_2b="E004",
            score=0.85,
            mean_field_roi=0.15,
            max_field_roi=0.25,
            focality=0.9,
        )
        assert len(gen.search_results) == 1
        assert gen.search_results[0]["pair_1"] == "E001-E002"
        assert gen.search_results[0]["pair_2"] == "E003-E004"
        assert gen.search_results[0]["score"] == 0.85

    def test_set_best_solution(self, tmp_path):
        gen = self._make_generator(tmp_path)
        gen.set_best_solution(
            electrode_pairs=[{"electrode1": "E1", "electrode2": "E2"}],
            score=0.95,
            metrics={"mean_field": 0.2},
            montage_image_base64="img_b64",
            field_map_base64="field_b64",
            skin_region_image_base64="skin_b64",
            electrode_coordinates=[[1.0, 2.0, 3.0]],
            channel_array_indices=[[0, 1]],
        )
        assert gen.best_solution is not None
        assert gen.best_solution["score"] == 0.95
        assert gen.best_solution["skin_region_image_base64"] == "skin_b64"

    def test_populate_from_data(self, tmp_path):
        gen = self._make_generator(tmp_path)
        data = {
            "config": {"electrode_net": "GSN-128", "n_candidates": 50},
            "roi": {"name": "Motor Cortex"},
            "results": [
                {
                    "electrode_1a": "E1",
                    "electrode_1b": "E2",
                    "electrode_2a": "E3",
                    "electrode_2b": "E4",
                    "score": 0.8,
                }
            ],
            "best_solution": {"score": 0.8, "electrode_pairs": []},
            "metrics": {"total_time": 120},
        }
        gen.populate_from_data(data)
        assert gen.config["electrode_net"] == "GSN-128"
        assert gen.roi_info["name"] == "Motor Cortex"
        assert len(gen.search_results) == 1
        assert gen.best_solution is not None
        assert gen.optimization_metrics["total_time"] == 120

    def test_load_from_output_dir(self, tmp_path):
        gen = self._make_generator(tmp_path)

        # Create output directory with results and config
        out_dir = tmp_path / "flex_output"
        out_dir.mkdir()
        results_data = {
            "config": {"electrode_net": "test_net"},
            "roi": {"name": "TestROI"},
        }
        (out_dir / "optimization_results.json").write_text(json.dumps(results_data))
        (out_dir / "config.json").write_text(json.dumps({"n_starts": 5}))

        gen.load_from_output_dir(out_dir)
        assert gen.config["n_starts"] == 5

    def test_load_from_output_dir_no_files(self, tmp_path):
        gen = self._make_generator(tmp_path)
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        gen.load_from_output_dir(empty_dir)
        # Should not crash

    def test_build_summary_section(self, tmp_path):
        gen = self._make_generator(tmp_path)
        gen.set_roi_info(roi_name="Target")
        gen.set_configuration(
            optimization_goal="mean",
            n_candidates=50,
            n_starts=3,
            post_processing="waveform",
        )
        gen.set_best_solution(
            electrode_pairs=[],
            score=0.75,
            metrics={},
        )
        gen._build_summary_section()
        section = gen.assembler.get_section("summary")
        assert section is not None

    def test_build_config_section(self, tmp_path):
        gen = self._make_generator(tmp_path)
        gen.set_configuration(
            electrode_net="GSN-128",
            optimization_target="mean",
            n_candidates=100,
            intensity_ch1=1.0,
            intensity_ch2=1.0,
            electrode_shape="circular",
            electrode_dimensions_mm="10x10",
            max_iterations=500,
            detailed_results=True,
        )
        gen._build_config_section()
        section = gen.assembler.get_section("configuration")
        assert section is not None

    def test_build_config_section_empty(self, tmp_path):
        gen = self._make_generator(tmp_path)
        gen._build_config_section()
        section = gen.assembler.get_section("configuration")
        assert section is None

    def test_build_roi_section(self, tmp_path):
        gen = self._make_generator(tmp_path)
        gen.set_roi_info(
            roi_name="Hippocampus",
            roi_type="sphere",
            coordinates=[10.0, 20.0, 30.0],
            radius=5.0,
            volume_mm3=523.6,
            n_voxels=100,
        )
        gen.roi_info["coordinate_space"] = "MNI"
        gen.roi_info["hemisphere"] = "left"
        gen.roi_info["atlas"] = "DK40"
        gen.roi_info["atlas_label"] = 17
        gen.roi_info["volume_atlas"] = "atlas_v1"
        gen.roi_info["volume_label"] = 42
        gen.roi_info["non_roi_method"] = "surround"
        gen.roi_info["non_roi_coordinates"] = [0, 0, 0]
        gen.roi_info["non_roi_radius"] = 15
        gen.roi_info["non_roi_coordinate_space"] = "MNI"
        gen.roi_info["non_roi_atlas"] = "DK40"
        gen.roi_info["non_roi_label"] = 99
        gen._build_roi_section()
        section = gen.assembler.get_section("roi")
        assert section is not None

    def test_build_roi_section_empty(self, tmp_path):
        gen = self._make_generator(tmp_path)
        gen._build_roi_section()
        section = gen.assembler.get_section("roi")
        assert section is None

    def test_build_results_section(self, tmp_path):
        gen = self._make_generator(tmp_path)
        for i in range(25):
            gen.add_search_result(
                rank=i + 1,
                electrode_1a=f"E{i}a",
                electrode_1b=f"E{i}b",
                electrode_2a=f"E{i}c",
                electrode_2b=f"E{i}d",
                score=1.0 - i * 0.01,
                mean_field_roi=0.1 + i * 0.01,
                focality=0.9 - i * 0.01,
            )
        gen._build_results_section()
        section = gen.assembler.get_section("results")
        assert section is not None
        # Description mentions top 20
        assert "20" in section.description

    def test_build_results_section_empty(self, tmp_path):
        gen = self._make_generator(tmp_path)
        gen._build_results_section()
        section = gen.assembler.get_section("results")
        assert section is None

    def test_build_results_section_uses_mapped_labels(self, tmp_path):
        gen = self._make_generator(tmp_path)
        gen.add_search_result(
            rank=1,
            electrode_1a="",
            electrode_1b="",
            electrode_2a="",
            electrode_2b="",
            score=0.9,
            mapped_labels=["E061", "E062", "E063", "E064"],
        )
        gen._build_results_section()
        section = gen.assembler.get_section("results")
        html = section.reportlets[0].render_html()
        assert "E061-E062" in html
        assert "E063-E064" in html
        assert "Mapped Labels" in html

    def test_add_search_result_omits_blank_pairs(self, tmp_path):
        gen = self._make_generator(tmp_path)
        gen.add_search_result(
            rank=1,
            electrode_1a="",
            electrode_1b="",
            electrode_2a="",
            electrode_2b="",
            score=0.9,
        )
        assert gen.search_results[0]["pair_1"] == ""
        assert gen.search_results[0]["pair_2"] == ""

    def test_build_best_solution_section_notes_missing_optional_images(self, tmp_path):
        gen = self._make_generator(tmp_path)
        gen.set_best_solution(
            electrode_pairs=[{"electrode1": "E061", "electrode2": "E062"}],
            score=0.95,
            metrics={},
            mapped_labels=["E061", "E062", "E063", "E064"],
            mapped_positions=[[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11, 12]],
        )
        gen._build_best_solution_section()
        section = gen.assembler.get_section("best_solution")
        html = "\n".join(r.render_html() for r in section.reportlets)
        assert "Mapped EEG Net Electrodes" in html
        assert "Electrode Montage Unavailable" in html
        assert "Electric Field Visualization Unavailable" in html

    def test_build_best_solution_section_with_coordinates(self, tmp_path):
        gen = self._make_generator(tmp_path)
        gen.set_best_solution(
            electrode_pairs=[
                {"electrode1": "E1", "electrode2": "E2"},
                "E3-E4",
            ],
            score=0.95,
            metrics={"mean_field": 0.2, "focality": 0.85},
            montage_image_base64="montage_b64",
            field_map_base64="field_b64",
            skin_region_image_base64="skin_b64",
            electrode_coordinates=[
                [1.0, 2.0, 3.0],
                [4.0, 5.0, 6.0],
                [7.0, 8.0, 9.0],
                [10.0, 11.0, 12.0],
            ],
            channel_array_indices=[[0, 1], [0, 2], [1, 1], [1, 2]],
        )
        gen._build_best_solution_section()
        section = gen.assembler.get_section("best_solution")
        assert section is not None
        html = "\n".join(r.render_html() for r in section.reportlets)
        assert "max-width: 520px" in html
        assert "Valid Skin Region" in html
        assert "data:image/png;base64,skin_b64" in html

    def test_build_best_solution_section_short_coords(self, tmp_path):
        """Test coordinate display when coordinates have < 3 elements."""
        gen = self._make_generator(tmp_path)
        gen.set_best_solution(
            electrode_pairs=[],
            score=0.5,
            metrics={},
            electrode_coordinates=[[1.0, 2.0]],
        )
        gen._build_best_solution_section()
        section = gen.assembler.get_section("best_solution")
        assert section is not None

    def test_build_best_solution_section_empty(self, tmp_path):
        gen = self._make_generator(tmp_path)
        gen._build_best_solution_section()
        section = gen.assembler.get_section("best_solution")
        assert section is None

    def test_get_methods_parameters(self, tmp_path):
        gen = self._make_generator(tmp_path)
        gen.set_roi_info(roi_name="Motor")
        gen.set_configuration(n_candidates=50)
        params = gen._get_methods_parameters()
        assert params["optimization_method"] == "flex-search"
        assert params["target_region"] == "Motor"
        assert params["n_candidates"] == 50

    def test_generate_full_report(self, tmp_path):
        gen = self._make_generator(tmp_path)
        gen.set_configuration(electrode_net="GSN-128", n_candidates=10)
        gen.set_roi_info(roi_name="Hippocampus")
        gen.add_search_result(
            rank=1,
            electrode_1a="E1",
            electrode_1b="E2",
            electrode_2a="E3",
            electrode_2b="E4",
            score=0.9,
        )
        gen.set_best_solution(
            electrode_pairs=[{"electrode1": "E1", "electrode2": "E2"}],
            score=0.9,
            metrics={},
        )
        output = tmp_path / "report.html"
        result = gen.generate(output_path=output)
        assert result.exists()
        content = result.read_text()
        assert "Flex-Search" in content
        assert "Computer-Friendly Output" in content
        assert content.rfind("Computer-Friendly Output") > content.rfind("References")
        assert "Haber2026" in content
        assert "Weise2024" in content
        assert "https://doi.org/10.1016/j.brs.2025.103016" in content
        assert "https://doi.org/10.1016/j.compbiomed.2025.110648" in content
        assert "&quot;search_results&quot;" in content


@pytest.mark.unit
class TestCreateFlexSearchReport:
    """Tests for the create_flex_search_report convenience function."""

    def test_creates_report(self, tmp_path):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            from tit.reporting.generators.flex_search import create_flex_search_report

            data = {
                "config": {"electrode_net": "test"},
                "roi": {"name": "TestROI"},
            }
            output = tmp_path / "flex_report.html"
            result = create_flex_search_report(
                project_dir=tmp_path,
                subject_id="001",
                data=data,
                output_path=output,
            )
            assert result.exists()


# ---------------------------------------------------------------------------
# Generators — SimulationReportGenerator
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestErrorSectionIntegration:
    """Test that errors/warnings flow through the generator pipeline."""

    def test_errors_and_warnings_in_generated_report(self, tmp_path):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            from tit.reporting.generators.base_generator import BaseReportGenerator

            class Gen(BaseReportGenerator):
                def _get_default_title(self):
                    return "Test"

                def _get_report_prefix(self):
                    return "test"

                def _build_report(self):
                    pass

            gen = Gen(project_dir=tmp_path, subject_id="001")
        gen.add_error("Critical failure", context="step1", step="init")
        gen.add_warning("Minor issue", context="step2", step="validate")

        output = tmp_path / "err_report.html"
        gen.generate(output_path=output)
        content = output.read_text()
        assert "Critical failure" in content
        assert "Minor issue" in content
