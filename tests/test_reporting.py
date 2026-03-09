#!/usr/bin/env python3
"""
Unit tests for TI-Toolbox reporting system: assembler, reportlets, and protocols.
"""

import pytest
from pathlib import Path

from tit.reporting.core.assembler import ReportAssembler
from tit.reporting.core.base import (
    MetadataReportlet,
    TableReportlet,
    TextReportlet,
    ErrorReportlet,
    ReferencesReportlet,
)
from tit.reporting.core.protocols import (
    ReportMetadata,
    ReportSection,
    SeverityLevel,
)


# ---------------------------------------------------------------------------
# ReportAssembler
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReportAssemblerConstruction:
    """Tests for ReportAssembler creation."""

    def test_creates_with_default_metadata(self):
        assembler = ReportAssembler()
        assert assembler.metadata.title == "Report"
        assert assembler.metadata.subject_id is None
        assert assembler.sections == []

    def test_creates_with_custom_title(self):
        assembler = ReportAssembler(title="My Custom Report")
        assert assembler.metadata.title == "My Custom Report"

    def test_title_overrides_metadata_title(self):
        meta = ReportMetadata(title="Meta Title")
        assembler = ReportAssembler(metadata=meta, title="Override")
        assert assembler.metadata.title == "Override"

    def test_metadata_preserved_when_no_title_override(self):
        meta = ReportMetadata(title="Original", subject_id="sub01")
        assembler = ReportAssembler(metadata=meta)
        assert assembler.metadata.title == "Original"
        assert assembler.metadata.subject_id == "sub01"


@pytest.mark.unit
class TestReportAssemblerSections:
    """Tests for section management."""

    def test_add_section_returns_report_section(self):
        assembler = ReportAssembler()
        section = assembler.add_section("overview", "Overview")
        assert isinstance(section, ReportSection)
        assert section.section_id == "overview"
        assert section.title == "Overview"

    def test_add_section_with_all_params(self):
        assembler = ReportAssembler()
        section = assembler.add_section(
            "details", "Details", description="Extra info", collapsed=True, order=5
        )
        assert section.description == "Extra info"
        assert section.collapsed is True
        assert section.order == 5

    def test_get_section_returns_none_for_missing(self):
        assembler = ReportAssembler()
        assert assembler.get_section("nonexistent") is None

    def test_get_section_returns_correct_section(self):
        assembler = ReportAssembler()
        assembler.add_section("sec1", "First")
        assembler.add_section("sec2", "Second")
        section = assembler.get_section("sec2")
        assert section is not None
        assert section.title == "Second"

    def test_add_reportlet_creates_section_if_missing(self):
        assembler = ReportAssembler()
        reportlet = TextReportlet("hello", title="Test")
        assembler.add_reportlet_to_section(
            "new_section", reportlet, create_if_missing=True
        )
        section = assembler.get_section("new_section")
        assert section is not None
        assert len(section.reportlets) == 1

    def test_add_reportlet_uses_section_title_for_auto_created(self):
        assembler = ReportAssembler()
        reportlet = TextReportlet("hello")
        assembler.add_reportlet_to_section(
            "my_sec", reportlet, create_if_missing=True, section_title="My Section"
        )
        section = assembler.get_section("my_sec")
        assert section.title == "My Section"

    def test_add_reportlet_raises_when_missing_and_not_create(self):
        assembler = ReportAssembler()
        reportlet = TextReportlet("hello")
        with pytest.raises(ValueError, match="not found"):
            assembler.add_reportlet_to_section(
                "missing", reportlet, create_if_missing=False
            )


@pytest.mark.unit
class TestReportAssemblerRendering:
    """Tests for HTML rendering."""

    def test_render_toc_generates_links(self):
        assembler = ReportAssembler()
        assembler.add_section("sec1", "Section One")
        assembler.add_section("sec2", "Section Two")
        toc = assembler.render_toc()
        assert '<a href="#sec1">Section One</a>' in toc
        assert '<a href="#sec2">Section Two</a>' in toc
        assert "toc-list" in toc

    def test_render_toc_respects_order(self):
        assembler = ReportAssembler()
        assembler.add_section("sec2", "Second", order=2)
        assembler.add_section("sec1", "First", order=1)
        toc = assembler.render_toc()
        first_pos = toc.index("First")
        second_pos = toc.index("Second")
        assert first_pos < second_pos

    def test_render_html_complete_document(self):
        assembler = ReportAssembler(title="Test Report")
        assembler.add_section("s1", "Intro")
        html = assembler.render_html()
        assert "<!DOCTYPE html>" in html
        assert "<title>Test Report</title>" in html
        assert "Intro" in html

    def test_save_writes_html_file(self, tmp_path):
        assembler = ReportAssembler(title="Saved Report")
        assembler.add_section("s1", "Content")
        output_file = tmp_path / "report.html"
        result = assembler.save(output_file)
        assert result == output_file
        assert output_file.exists()
        content = output_file.read_text()
        assert "<!DOCTYPE html>" in content
        assert "Saved Report" in content

    def test_save_creates_parent_directories(self, tmp_path):
        assembler = ReportAssembler()
        output_file = tmp_path / "sub" / "dir" / "report.html"
        assembler.save(output_file)
        assert output_file.exists()


@pytest.mark.unit
class TestReportAssemblerSerialization:
    """Tests for to_dict / from_dict round-trip."""

    def test_to_dict_contains_metadata_and_sections(self):
        assembler = ReportAssembler(title="Ser Test")
        assembler.add_section("s1", "Section One", description="Desc")
        d = assembler.to_dict()
        assert "metadata" in d
        assert "sections" in d
        assert d["metadata"]["title"] == "Ser Test"
        assert len(d["sections"]) == 1

    def test_from_dict_round_trip_preserves_metadata(self):
        meta = ReportMetadata(
            title="Round Trip",
            subject_id="sub-01",
            session_id="ses-01",
            report_type="simulation",
        )
        original = ReportAssembler(metadata=meta)
        original.add_section("s1", "First", description="Desc1", order=3)
        original.add_section("s2", "Second", collapsed=True, order=1)

        data = original.to_dict()
        restored = ReportAssembler.from_dict(data)

        assert restored.metadata.title == "Round Trip"
        assert restored.metadata.subject_id == "sub-01"
        assert restored.metadata.session_id == "ses-01"
        assert len(restored.sections) == 2
        assert restored.get_section("s1").description == "Desc1"
        assert restored.get_section("s2").collapsed is True


# ---------------------------------------------------------------------------
# MetadataReportlet
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMetadataReportlet:
    """Tests for MetadataReportlet rendering."""

    def test_table_mode_renders_key_value_rows(self):
        r = MetadataReportlet({"name": "Alice", "age": 30}, display_mode="table")
        html = r.render_html()
        assert "metadata-table" in html
        assert "table-mode" in html
        assert "Name" in html
        assert "30" in html

    def test_card_mode_renders_card_grid(self):
        r = MetadataReportlet(
            {"subject": "sub-01"}, display_mode="cards", columns=3
        )
        html = r.render_html()
        assert "card-mode" in html
        assert "card-grid" in html
        assert "columns-3" in html
        assert "Subject" in html

    def test_format_value_none(self):
        r = MetadataReportlet({"key": None})
        html = r.render_html()
        assert "N/A" in html

    def test_format_value_bool_true(self):
        r = MetadataReportlet({"flag": True})
        html = r.render_html()
        assert "Yes" in html

    def test_format_value_bool_false(self):
        r = MetadataReportlet({"flag": False})
        html = r.render_html()
        assert "No" in html

    def test_format_value_list(self):
        r = MetadataReportlet({"items": ["a", "b", "c"]})
        html = r.render_html()
        assert "a, b, c" in html

    def test_format_value_dict(self):
        r = MetadataReportlet({"nested": {"x": 1, "y": 2}})
        html = r.render_html()
        assert "x: 1" in html
        assert "y: 2" in html

    def test_title_rendered_when_provided(self):
        r = MetadataReportlet({"k": "v"}, title="Meta Title")
        html = r.render_html()
        assert "<h3>Meta Title</h3>" in html

    def test_no_title_when_none(self):
        r = MetadataReportlet({"k": "v"})
        html = r.render_html()
        assert "<h3>" not in html


# ---------------------------------------------------------------------------
# TableReportlet
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTableReportlet:
    """Tests for TableReportlet rendering."""

    def test_list_of_dicts(self):
        data = [{"name": "A", "val": 1}, {"name": "B", "val": 2}]
        r = TableReportlet(data, title="Table")
        assert r.headers == ["name", "val"]
        assert len(r.rows) == 2
        html = r.render_html()
        assert "data-table" in html
        assert "<th>name</th>" in html

    def test_list_of_lists_with_headers(self):
        data = [[1, 2], [3, 4]]
        r = TableReportlet(data, headers=["X", "Y"])
        assert r.headers == ["X", "Y"]
        assert r.rows == [[1, 2], [3, 4]]

    def test_list_of_lists_no_headers(self):
        data = [[1, 2], [3, 4]]
        r = TableReportlet(data)
        assert r.headers == []
        assert len(r.rows) == 2

    def test_empty_data_renders_no_data_message(self):
        r = TableReportlet([])
        html = r.render_html()
        assert "No data available" in html

    def test_custom_headers_override_dict_keys(self):
        data = [{"a": 1, "b": 2}]
        r = TableReportlet(data, headers=["Col1", "Col2"])
        assert r.headers == ["Col1", "Col2"]

    def test_format_cell_none(self):
        r = TableReportlet([[None]])
        html = r.render_html()
        # None becomes em-dash
        assert "\u2014" in html or "—" in html

    def test_format_cell_float(self):
        r = TableReportlet([[3.14159]])
        html = r.render_html()
        assert "3.142" in html

    def test_striped_class_applied_by_default(self):
        r = TableReportlet([{"a": 1}])
        html = r.render_html()
        assert "striped" in html


# ---------------------------------------------------------------------------
# TextReportlet
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTextReportlet:
    """Tests for TextReportlet rendering."""

    def test_plain_text_wraps_in_paragraphs(self):
        r = TextReportlet("Hello world", content_type="text")
        html = r.render_html()
        assert "<p>Hello world</p>" in html

    def test_code_renders_pre_code_block(self):
        r = TextReportlet("x = 1", content_type="code")
        html = r.render_html()
        assert "<pre><code>" in html
        assert "x = 1" in html

    def test_code_escapes_html(self):
        r = TextReportlet("<script>alert(1)</script>", content_type="code")
        html = r.render_html()
        assert "&lt;script&gt;" in html
        assert "<script>alert" not in html

    def test_html_content_passes_through(self):
        r = TextReportlet("<b>bold</b>", content_type="html")
        html = r.render_html()
        assert "<b>bold</b>" in html

    def test_title_rendered(self):
        r = TextReportlet("text", title="My Title")
        html = r.render_html()
        assert "<h3>My Title</h3>" in html

    def test_monospace_class(self):
        r = TextReportlet("text", monospace=True)
        html = r.render_html()
        assert "monospace" in html

    def test_copyable_adds_button(self):
        r = TextReportlet("text", copyable=True)
        html = r.render_html()
        assert "copy-btn" in html
        assert "Copy to Clipboard" in html


# ---------------------------------------------------------------------------
# ErrorReportlet
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestErrorReportlet:
    """Tests for ErrorReportlet rendering."""

    def test_no_messages_shows_success(self):
        r = ErrorReportlet()
        html = r.render_html()
        assert "success" in html
        assert "[OK]" in html
        assert "No errors or warnings" in html

    def test_with_messages_shows_items(self):
        msgs = [{"message": "Something broke", "severity": "error"}]
        r = ErrorReportlet(messages=msgs)
        html = r.render_html()
        assert "Something broke" in html
        assert "messages-list" in html

    def test_default_title(self):
        r = ErrorReportlet()
        assert r.title == "Errors and Warnings"

    def test_custom_title(self):
        r = ErrorReportlet(title="Issues")
        assert r.title == "Issues"

    def test_add_error(self):
        r = ErrorReportlet()
        r.add_error("File missing", context="loader", step="load")
        assert len(r.messages) == 1
        assert r.messages[0]["message"] == "File missing"
        assert r.messages[0]["severity"] == "error"
        assert r.messages[0]["context"] == "loader"
        assert r.messages[0]["step"] == "load"

    def test_add_warning(self):
        r = ErrorReportlet()
        r.add_warning("Deprecated usage")
        assert len(r.messages) == 1
        assert r.messages[0]["severity"] == "warning"

    def test_add_error_and_warning_combined(self):
        r = ErrorReportlet()
        r.add_error("Error one")
        r.add_warning("Warning one")
        assert len(r.messages) == 2
        html = r.render_html()
        assert "Error one" in html
        assert "Warning one" in html

    def test_warning_icon(self):
        r = ErrorReportlet()
        r.add_warning("Warn")
        html = r.render_html()
        assert "[!]" in html

    def test_error_icon(self):
        r = ErrorReportlet()
        r.add_error("Err")
        html = r.render_html()
        assert "[X]" in html

    def test_context_rendered(self):
        r = ErrorReportlet()
        r.add_error("msg", context="mycontext")
        html = r.render_html()
        assert "mycontext" in html

    def test_step_rendered(self):
        r = ErrorReportlet()
        r.add_error("msg", step="step3")
        html = r.render_html()
        assert "Step: step3" in html


# ---------------------------------------------------------------------------
# ReferencesReportlet
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReferencesReportlet:
    """Tests for ReferencesReportlet rendering."""

    def test_empty_returns_empty_string(self):
        r = ReferencesReportlet()
        assert r.render_html() == ""

    def test_with_doi_link(self):
        refs = [
            {
                "key": "simnibs",
                "citation": "Thielscher et al.",
                "doi": "10.1234/test",
            }
        ]
        r = ReferencesReportlet(references=refs)
        html = r.render_html()
        assert "https://doi.org/10.1234/test" in html
        assert "[DOI]" in html
        assert "Thielscher et al." in html
        assert "references-list" in html

    def test_with_url_link(self):
        refs = [
            {
                "key": "tool",
                "citation": "Some tool",
                "url": "https://example.com",
            }
        ]
        r = ReferencesReportlet(references=refs)
        html = r.render_html()
        assert "https://example.com" in html
        assert "[Link]" in html

    def test_doi_takes_priority_over_url(self):
        refs = [
            {
                "key": "both",
                "citation": "Both",
                "doi": "10.5678/x",
                "url": "https://example.com",
            }
        ]
        r = ReferencesReportlet(references=refs)
        html = r.render_html()
        assert "[DOI]" in html
        assert "[Link]" not in html

    def test_default_title_is_references(self):
        r = ReferencesReportlet()
        assert r.title == "References"

    def test_add_reference(self):
        r = ReferencesReportlet()
        r.add_reference("key1", "Citation text", doi="10.1/a")
        assert len(r.references) == 1
        assert r.references[0]["key"] == "key1"
        assert r.references[0]["doi"] == "10.1/a"

    def test_ref_key_rendered(self):
        refs = [{"key": "mykey", "citation": "text"}]
        r = ReferencesReportlet(references=refs)
        html = r.render_html()
        assert "[mykey]" in html


# ---------------------------------------------------------------------------
# ReportMetadata
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReportMetadata:
    """Tests for the ReportMetadata dataclass."""

    def test_to_dict_includes_all_fields(self):
        meta = ReportMetadata(
            title="Test", subject_id="sub-01", report_type="simulation"
        )
        d = meta.to_dict()
        assert d["title"] == "Test"
        assert d["subject_id"] == "sub-01"
        assert d["report_type"] == "simulation"
        assert "generation_time" in d
        assert "bids_version" in d

    def test_defaults(self):
        meta = ReportMetadata(title="T")
        assert meta.report_type == "general"
        assert meta.bids_version == "1.8.0"
        assert meta.dataset_type == "derivative"
        assert meta.software_versions == {}
