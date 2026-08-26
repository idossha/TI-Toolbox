"""
Unit tests for GUI module hygiene and importability.

These tests verify coding-standard compliance (no stale framework
references, no leftover debug widgets) and that key GUI modules can
be imported without crashing.
"""

import json
import os
import re
import sys
import types
from pathlib import Path

import pytest

# Root of the tit/gui package on disk
GUI_ROOT = Path(__file__).resolve().parent.parent / "tit" / "gui"


def _all_py_sources() -> list[Path]:
    """Return every .py file under tit/gui/ (recursive)."""
    return sorted(GUI_ROOT.rglob("*.py"))


def _mock_simnibs_ti_utils() -> None:
    """Install minimal ``simnibs.utils.TI_utils`` stand-ins.

    ``tit.gui.ex_search_tab`` imports ``tit.opt.ex.engine.ExSearchEngine``,
    which does ``from simnibs.utils import TI_utils as TI`` at module level.
    conftest.py's global mock hierarchy doesn't cover that specific
    submodule, so tests that import ``tit.gui.ex_search_tab`` need this
    stand-in first (real SimNIBS is unavailable outside Docker).
    """
    simnibs_mod = sys.modules.setdefault("simnibs", types.ModuleType("simnibs"))
    utils_mod = sys.modules.setdefault(
        "simnibs.utils", types.ModuleType("simnibs.utils")
    )
    ti_utils_mod = sys.modules.setdefault(
        "simnibs.utils.TI_utils", types.ModuleType("simnibs.utils.TI_utils")
    )
    setattr(simnibs_mod, "utils", utils_mod)
    setattr(utils_mod, "TI_utils", ti_utils_mod)


# ============================================================================
# Source-code hygiene checks (no Qt import needed)
# ============================================================================


class TestGuiSourceHygiene:
    """Static checks over gui/ source files."""

    @pytest.mark.unit
    def test_no_pyside6_references(self):
        """No gui/ file should import PySide6 — the project uses PyQt5."""
        violations: list[str] = []
        for py_file in _all_py_sources():
            source = py_file.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(source.splitlines(), start=1):
                if "from PySide6" in line or "import PySide6" in line:
                    rel = py_file.relative_to(GUI_ROOT.parent.parent)
                    violations.append(f"{rel}:{i}: {line.strip()}")

        assert violations == [], "Found PySide6 imports in gui/ files:\n" + "\n".join(
            violations
        )

    @pytest.mark.unit
    def test_no_debug_checkbox_references(self):
        """No gui/ file should reference the removed debug_checkbox widget."""
        violations: list[str] = []
        for py_file in _all_py_sources():
            source = py_file.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(source.splitlines(), start=1):
                if "debug_checkbox" in line:
                    rel = py_file.relative_to(GUI_ROOT.parent.parent)
                    violations.append(f"{rel}:{i}: {line.strip()}")

        assert (
            violations == []
        ), "Found debug_checkbox references in gui/ files:\n" + "\n".join(violations)


# ============================================================================
# Import tests (require PyQt5 at runtime)
# ============================================================================


class TestGuiImports:
    """Verify that key GUI modules can be imported."""

    @pytest.mark.unit
    def test_gui_components_init(self):
        """tit.gui.components can be imported without error."""
        pyqt5 = pytest.importorskip("PyQt5")
        from tit.gui.components import (  # noqa: F401
            ConsoleWidget,
            ElectrodeConfigWidget,
            ROIPickerWidget,
            RunStopButtons,
            SolverParamsWidget,
            SubjectRow,
            SubjectRowManager,
            detect_message_type_from_content,
        )

    @pytest.mark.unit
    def test_ex_search_config_writer_includes_project_dir(self):
        """GUI Ex-Search JSON includes project_dir required by backend CLI."""
        pytest.importorskip("PyQt5")
        _mock_simnibs_ti_utils()

        from tit.gui.ex_search_tab import ExSearchTab
        from tit.opt.config import ExConfig

        config = ExConfig(
            subject_id="ernie",
            leadfield_hdf="/leadfields/ernie_leadfield_easycap.hdf5",
            roi_name="18_Left_Amyg.csv",
            electrodes=ExConfig.BucketElectrodes(
                e1_plus=["E1"],
                e1_minus=["E2"],
                e2_plus=["E3"],
                e2_minus=["E4"],
            ),
        )

        config_path = ExSearchTab._write_ex_config(config, "/project")
        try:
            with open(config_path) as f:
                data = json.load(f)
        finally:
            os.unlink(config_path)

        assert data["project_dir"] == "/project"
        assert data["electrodes"]["_type"] == "BucketElectrodes"

    @pytest.mark.unit
    def test_ex_search_coordinate_space_value(self):
        """Subject/MNI radio state maps to ExConfig.roi_coordinate_space."""
        pytest.importorskip("PyQt5")
        from tit.gui.ex_search_tab import ExSearchTab

        assert ExSearchTab.coordinate_space_value(False) == "subject"
        assert ExSearchTab.coordinate_space_value(True) == "mni"

    @pytest.mark.unit
    def test_ex_search_build_roi_atlas_entries_single_region(self):
        """N=1 case: one selected subcortical region -> one AtlasROI dict."""
        pytest.importorskip("PyQt5")
        from tit.gui.ex_search_tab import ExSearchTab

        entries = ExSearchTab.build_roi_atlas_entries("/atlas/aseg.mgz", ["17"])
        assert entries == [{"atlas_path": "/atlas/aseg.mgz", "label": 17}]

    @pytest.mark.unit
    def test_ex_search_build_roi_atlas_entries_multi_region(self):
        """Multiple selected labels from the same atlas union into one list."""
        pytest.importorskip("PyQt5")
        from tit.gui.ex_search_tab import ExSearchTab
        from tit.opt.config import ExConfig

        entries = ExSearchTab.build_roi_atlas_entries("/atlas/aseg.mgz", ["17", "53"])
        assert entries == [
            {"atlas_path": "/atlas/aseg.mgz", "label": 17},
            {"atlas_path": "/atlas/aseg.mgz", "label": 53},
        ]

        # Feeds straight into ExConfig.roi_atlas without further conversion.
        config = ExConfig(
            subject_id="ernie",
            leadfield_hdf="/leadfields/ernie_leadfield_easycap.hdf5",
            roi_name="18_Left_Amyg.csv",
            roi_atlas=entries,
            electrodes=ExConfig.BucketElectrodes(
                e1_plus=["E1"],
                e1_minus=["E2"],
                e2_plus=["E3"],
                e2_minus=["E4"],
            ),
        )
        assert config.roi_atlas == [
            ExConfig.AtlasROI(atlas_path="/atlas/aseg.mgz", label=17),
            ExConfig.AtlasROI(atlas_path="/atlas/aseg.mgz", label=53),
        ]

    @pytest.mark.unit
    def test_ex_search_build_roi_atlas_entries_empty_is_optional(self):
        """No atlas or no region selected -> None (Atlas ROI stays optional)."""
        pytest.importorskip("PyQt5")
        from tit.gui.ex_search_tab import ExSearchTab

        assert ExSearchTab.build_roi_atlas_entries(None, []) is None
        assert ExSearchTab.build_roi_atlas_entries("/atlas/aseg.mgz", []) is None
        assert ExSearchTab.build_roi_atlas_entries("", ["17"]) is None

    @pytest.mark.unit
    def test_ex_search_roi_names_for_mode(self):
        """ROI Type toggle maps to ExConfig.roi_names: sphere passes through, atlas empties it.

        Atlas mode must produce an *explicit* empty list (ExConfig treats
        that as "no spherical centers at all"), not None (which falls back
        to a single roi_name).
        """
        pytest.importorskip("PyQt5")
        from tit.gui.ex_search_tab import ExSearchTab, ROI_MODE_SPHERE, ROI_MODE_ATLAS

        assert ExSearchTab.roi_names_for_mode(ROI_MODE_SPHERE, ["a.csv", "b.csv"]) == [
            "a.csv",
            "b.csv",
        ]
        assert ExSearchTab.roi_names_for_mode(ROI_MODE_SPHERE, None) is None
        assert ExSearchTab.roi_names_for_mode(ROI_MODE_ATLAS, ["a.csv"]) == []
        assert ExSearchTab.roi_names_for_mode(ROI_MODE_ATLAS, None) == []

    @pytest.mark.unit
    def test_ex_search_roi_atlas_for_mode(self):
        """ROI Type toggle maps to roi_atlas: sphere disables it, atlas passes it through.

        Applies to both ExConfig and MExConfig (mex has no roi_names union
        equivalent, so this is the only mode-gated field it has).
        """
        pytest.importorskip("PyQt5")
        from tit.gui.ex_search_tab import ExSearchTab, ROI_MODE_SPHERE, ROI_MODE_ATLAS

        entries = [{"atlas_path": "/atlas/aseg.mgz", "label": 17}]
        assert ExSearchTab.roi_atlas_for_mode(ROI_MODE_SPHERE, entries) is None
        assert ExSearchTab.roi_atlas_for_mode(ROI_MODE_SPHERE, None) is None
        assert ExSearchTab.roi_atlas_for_mode(ROI_MODE_ATLAS, entries) == entries
        assert ExSearchTab.roi_atlas_for_mode(ROI_MODE_ATLAS, None) is None

    @pytest.mark.unit
    def test_ex_search_roi_mode_kwargs_build_ti_and_mti_configs(self):
        """Sphere vs Atlas mode produce the documented ExConfig/MExConfig shapes.

        Sphere: roi_names populated, roi_atlas=None.
        Atlas: roi_names=[] (ExConfig only), roi_atlas populated.
        """
        pytest.importorskip("PyQt5")
        from tit.gui.ex_search_tab import ExSearchTab, ROI_MODE_SPHERE, ROI_MODE_ATLAS
        from tit.opt.config import ExConfig, MExConfig

        entries = [{"atlas_path": "/atlas/aseg.mgz", "label": 17}]
        electrodes = ExConfig.BucketElectrodes(
            e1_plus=["E1"], e1_minus=["E2"], e2_plus=["E3"], e2_minus=["E4"]
        )

        sphere_config = ExConfig(
            subject_id="ernie",
            leadfield_hdf="/leadfields/ernie.hdf5",
            roi_name="target.csv",
            roi_names=ExSearchTab.roi_names_for_mode(ROI_MODE_SPHERE, ["target.csv"]),
            roi_atlas=ExSearchTab.roi_atlas_for_mode(ROI_MODE_SPHERE, entries),
            electrodes=electrodes,
        )
        assert sphere_config.roi_names == ["target.csv"]
        assert sphere_config.roi_atlas is None

        atlas_config = ExConfig(
            subject_id="ernie",
            leadfield_hdf="/leadfields/ernie.hdf5",
            roi_name="atlas_17",
            roi_names=ExSearchTab.roi_names_for_mode(ROI_MODE_ATLAS, ["target.csv"]),
            roi_atlas=ExSearchTab.roi_atlas_for_mode(ROI_MODE_ATLAS, entries),
            electrodes=electrodes,
        )
        assert atlas_config.roi_names == []
        assert atlas_config.roi_atlas == [ExConfig.AtlasROI(**entries[0])]

        mex_electrodes = MExConfig.BucketElectrodes(
            e1_plus=["E1"],
            e1_minus=["E2"],
            e2_plus=["E3"],
            e2_minus=["E4"],
            e3_plus=["E5"],
            e3_minus=["E6"],
            e4_plus=["E7"],
            e4_minus=["E8"],
        )
        mex_sphere = MExConfig(
            subject_id="ernie",
            leadfield_hdf="/leadfields/ernie.hdf5",
            roi_name="target.csv",
            roi_atlas=ExSearchTab.roi_atlas_for_mode(ROI_MODE_SPHERE, entries),
            electrodes=mex_electrodes,
        )
        assert mex_sphere.roi_atlas is None

        mex_atlas = MExConfig(
            subject_id="ernie",
            leadfield_hdf="/leadfields/ernie.hdf5",
            roi_name="target.csv",
            roi_atlas=ExSearchTab.roi_atlas_for_mode(ROI_MODE_ATLAS, entries),
            electrodes=mex_electrodes,
        )
        assert mex_atlas.roi_atlas == [MExConfig.AtlasROI(**entries[0])]

    @pytest.mark.unit
    def test_ex_search_atlas_only_roi_label(self):
        """Synthetic ExConfig.roi_name label built from selected atlas region keys."""
        pytest.importorskip("PyQt5")
        from tit.gui.ex_search_tab import ExSearchTab

        assert ExSearchTab.atlas_only_roi_label([]) == "atlas_roi"
        assert ExSearchTab.atlas_only_roi_label(["17"]) == "atlas_17"
        assert ExSearchTab.atlas_only_roi_label(["17", "53"]) == "atlas_17_53"

    @pytest.mark.unit
    def test_ex_search_no_add_whole_file_reference(self):
        """The removed 'Add Whole File' handler/button leaves no trace."""
        source = (GUI_ROOT / "ex_search_tab.py").read_text(encoding="utf-8")
        assert "Add Whole File" not in source
        assert "_on_add_atlas_whole_file" not in source
        assert "atlas_roi_chip_key" not in source

    @pytest.mark.unit
    def test_ex_search_tab_compiles(self):
        """tit/gui/ex_search_tab.py is syntactically valid Python.

        Unlike the other tests in this class, this one needs no PyQt5 (or
        any other import) at all -- py_compile only parses/compiles to
        bytecode, it never executes module-level code -- so it actually
        runs (not skips) on hosts without PyQt5 installed.
        """
        import py_compile

        py_compile.compile(str(GUI_ROOT / "ex_search_tab.py"), doraise=True)

    @pytest.mark.unit
    def test_analyzer_tab_compiles(self):
        """tit/gui/analyzer_tab.py is syntactically valid Python.

        No PyQt5 needed (py_compile only compiles to bytecode, never runs
        module-level code), so this actually runs -- not skips -- on hosts
        without PyQt5 installed.
        """
        import py_compile

        py_compile.compile(str(GUI_ROOT / "analyzer_tab.py"), doraise=True)

    @pytest.mark.unit
    def test_ex_search_atlas_roi_mode_available_in_both_search_modes(self):
        """Atlas targeting must not be gated on the TI/mTI choice.

        It used to be: tit/opt/mex/mex.py built the sphere path from
        ``roi_name`` unconditionally, so a multipolar run always needed a
        spherical ROI and the Atlas radio was disabled under mTI. MExConfig now
        carries ``roi_names`` like ExConfig and mex.py honours the empty list,
        so both mechanisms work in both modes.
        """
        source = (GUI_ROOT / "ex_search_tab.py").read_text(encoding="utf-8")
        body = source.split("def _on_search_mode_changed(self):", 1)[1]
        body = body.split("\n    def ", 1)[0]
        assert "roi_mode_atlas_radio.setEnabled" not in body
        # and the handler must not force the user back to Sphere
        assert "self.roi_mode_sphere_radio.setChecked(True)" not in body
        # ROI validation branches on ROI Type alone, not on the search mode
        validate = source.split("def validate_inputs(self):", 1)[1]
        validate = validate.split("\n    def ", 1)[0]
        assert "if self._current_roi_mode() == ROI_MODE_SPHERE:" in validate
        assert (
            "SEARCH_MODE_MTI\n            or self._current_roi_mode()" not in validate
        )

    def test_ex_search_mex_config_passes_roi_names(self):
        """The mTI config builder must send roi_names, or atlas mode is inert.

        ``roi_names=[]`` is the only thing telling mex.py to skip the sphere
        CSV; omitting the field leaves it None and the backend falls back to
        reading ``roi_name`` as a file that does not exist.
        """
        source = (GUI_ROOT / "ex_search_tab.py").read_text(encoding="utf-8")
        body = source.split("def _build_mex_config(self", 1)[1]
        body = body.split("\n    @", 1)[0]
        assert "roi_names=self.roi_names_for_mode(mode, None)" in body

    @pytest.mark.unit
    def test_ex_search_roi_pipeline_honours_atlas_mode_in_both_search_modes(self):
        """mTI + Atlas must not try to open the synthetic ``atlas_<labels>.csv``.

        ``_mti_roi_targets`` queues a label-only name in Atlas mode; if
        ``run_roi_pipeline`` gated its atlas-only branch on the TI search
        mode, the mTI run fell into the CSV-reading branch, logged "Error
        reading ROI file", and completed with zero runs.
        """
        source = (GUI_ROOT / "ex_search_tab.py").read_text(encoding="utf-8")
        body = source.split("def run_roi_pipeline(self", 1)[1]
        body = body.split("\n    def ", 1)[0]
        assert "is_atlas_only = self._current_roi_mode() == ROI_MODE_ATLAS" in body
        assert "SEARCH_MODE_MTI\n            and self._current_roi_mode()" not in body
        # A failed sphere-CSV read must be recorded so pipeline_completed()
        # cannot report success after skipping every ROI.
        error_branch = body.split("Error reading ROI file", 1)[0]
        assert error_branch.rstrip().endswith(
            "self._exsearch_had_errors = True\n"
            "                    self.update_output(\n"
            '                        f"'
        )

    def test_ex_search_roi_mode_stack_keeps_a_stable_height(self):
        """Switching ROI Type must not move anything below the ROI box.

        The stack's default "tallest page" sizing is what holds the column
        still; sizing it to the current page instead made everything below jump
        on every Sphere/Atlas toggle. The region chips get a reserved height
        for the same reason -- a flow layout grows as chips are added.
        """
        source = (GUI_ROOT / "ex_search_tab.py").read_text(encoding="utf-8")
        assert "self._size_stack_to_current(self.roi_mode_stack)" not in source
        assert "_resize_roi_mode_stack" not in source
        assert "subcortical_chips.setMinimumHeight(" in source

    def test_mti_electrode_grid_gives_spare_width_to_the_inputs(self):
        """Label columns must not absorb spare width.

        A QGridLayout with no column stretch spreads leftover width equally
        over every column, so the label columns grew along with the input
        columns -- that is the gap between each "E1+:" and its box, and it made
        the panel demand more width than it needed. Stretch belongs on the
        input columns only.
        """
        source = (GUI_ROOT / "ex_search_tab.py").read_text(encoding="utf-8")
        body = source.split("def _build_mti_bucketed_panel(self):", 1)[1]
        body = body.split("\n    def ", 1)[0]
        for col, stretch in ((0, 0), (1, 1), (2, 0), (3, 1)):
            assert f"layout.setColumnStretch({col}, {stretch})" in body
        # Uniform label width, left-aligned: lines up the "E" glyphs AND the
        # inputs. Right-aligning lines up the colons instead, which leaves the
        # E's ragged because "E1+:" is wider than "E1-:".
        assert "label.setFixedWidth(MTI_BUCKET_LABEL_WIDTH)" in body
        assert "QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter" in body
        # and the inputs carry the width requirement, not the panel
        assert "setMinimumWidth(MTI_BUCKET_INPUT_MIN_WIDTH)" in body

    def test_ex_search_stacks_size_to_current_page(self):
        """Every QStackedWidget in the tab must track its current page.

        A stack reserves the maximum over all pages on both axes. Vertically
        that is dead space; horizontally it was a real defect -- the mTI
        electrode panel is a four-column grid of eight inputs, about twice the
        width of the two-pair panel, so the TI view was forced that wide and
        its inputs ran off the right edge behind a horizontal scrollbar.
        """
        source = (GUI_ROOT / "ex_search_tab.py").read_text(encoding="utf-8")
        # the helper collapses both axes, not just height
        assert "def _size_stack_to_current(self, stack):" in source
        assert "policy.setHorizontalPolicy(" in source
        # and all three stacks are wired to it
        # the ROI stack is deliberately excluded -- see
        # test_ex_search_roi_mode_stack_keeps_a_stable_height
        for stack in ("self.electrode_stack", "self.current_config_stack"):
            assert f"self._size_stack_to_current({stack})" in source, stack

    def test_ex_search_uses_independent_columns_not_a_grid(self):
        """Paired boxes must not share a row height.

        A QGridLayout makes every cell in a row as tall as the tallest box in
        it, so a short box beside a tall one is stuck in an oversized cell no
        matter how it is aligned or how little it wants to grow. Subject
        Selection sat beside the taller Electrode Selection, and ROI Selection
        beside the shorter Current Configuration -- the two dead gaps. Aligning
        the boxes to the top of their cells moved them but could not shrink the
        rows, so the grid is gone in favour of two independent QVBoxLayouts.

        Only the trailing scroll_layout stretch may absorb slack; a stretch at
        the end of either column would reserve the space again.
        """
        source = (GUI_ROOT / "ex_search_tab.py").read_text(encoding="utf-8")
        # inner panels (e.g. the mTI electrode grid) may still use a grid --
        # it is the top-level box placement that must not
        assert "main_grid_layout" not in source
        assert "left_column = QtWidgets.QVBoxLayout()" in source
        assert "right_column = QtWidgets.QVBoxLayout()" in source
        for widget, column in (
            ("subject_container", "left_column"),
            ("roi_container", "left_column"),
            ("electrode_container", "right_column"),
            ("self.current_container", "right_column"),
        ):
            assert f"{column}.addWidget({widget})" in source, widget
        # full-width box lives below the columns, not inside one
        assert "scroll_layout.addWidget(leadfield_container)" in source
        assert "left_column.addStretch" not in source
        assert "right_column.addStretch" not in source

    def test_ex_search_containers_hug_content_not_fixed_height(self):
        """ROI/Subject/Electrode/Current/Leadfield containers no longer reserve dead space.

        Every top-level group box in ex_search_tab.py used to call
        setFixedHeight with a hand-picked number, reserving that height
        whether the content needed it or not (with zero setSizePolicy calls
        anywhere in the file). The fix: each container gets a vertical
        QSizePolicy.Maximum so it hugs its content instead, and a single
        trailing stretch in scroll_layout absorbs the freed space.

        Inner-widget fixed heights (list boxes, buttons, spinbox rows) are
        deliberate and must remain untouched.
        """
        source = (GUI_ROOT / "ex_search_tab.py").read_text(encoding="utf-8")

        # The five container-level setFixedHeight calls are gone.
        for removed in (
            "subject_container.setFixedHeight",
            "electrode_container.setFixedHeight",
            "roi_container.setFixedHeight",
            "self.current_container.setFixedHeight",
            "leadfield_container.setFixedHeight",
        ):
            assert removed not in source, f"expected {removed} to be removed"

        # Each container instead hugs its content vertically.
        for container in (
            "subject_container",
            "electrode_container",
            "roi_container",
            "self.current_container",
            "leadfield_container",
        ):
            assert (
                f"{container}.setSizePolicy(\n"
                f"            QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum\n"
                f"        )" in source
            ), f"expected {container} to get a Maximum vertical size policy"

        # A single trailing stretch absorbs the freed vertical space.
        assert "scroll_layout.addStretch(1)" in source

        # Deliberate inner-widget fixed heights must remain untouched.
        assert "self.roi_list.setFixedHeight(80)" in source
        assert "self.leadfield_list.setFixedHeight(140)" in source
        assert "self.add_roi_btn.setFixedHeight(25)" in source

    @pytest.mark.unit
    def test_analyzer_target_groups_use_stacked_widget(self):
        """cortical_group/spherical_group live in target_stack, not toggled visibility.

        Toggling target type used to call setVisible() on both group boxes
        directly, which reflows/resizes the right-hand column because the
        two boxes have different natural widths. A QStackedWidget reserves
        the size of its largest page, so the fix is checked at the source
        level (no PyQt5 needed): update_atlas_visibility must no longer call
        setVisible on cortical_group/spherical_group, and must instead use
        target_stack.setCurrentWidget.
        """
        source = (GUI_ROOT / "analyzer_tab.py").read_text(encoding="utf-8")

        assert "self.target_stack = QtWidgets.QStackedWidget()" in source
        assert "self.target_stack.addWidget(self.cortical_group)" in source
        assert "self.target_stack.addWidget(self.spherical_group)" in source

        # Locate update_atlas_visibility and ensure it uses the stack, not
        # setVisible(), to switch between the two target groups.
        start = source.index("def update_atlas_visibility")
        end = source.index("\n    def ", start + 1)
        body = source[start:end]

        assert "self.target_stack.setCurrentWidget(self.cortical_group)" in body
        assert "self.target_stack.setCurrentWidget(self.spherical_group)" in body
        assert "self.cortical_group.setVisible" not in body
        assert "self.spherical_group.setVisible" not in body


class TestAnalyzerTabStopAndMasks:
    """stop_analysis drains the sphere queue; voxel atlas managers see masks/."""

    @pytest.mark.unit
    def test_stop_analysis_clears_single_analysis_queue(self):
        """Stopping must not let _on_single_analysis_cmd_finished launch the
        next queued sphere."""
        pytest.importorskip("PyQt5")
        from unittest.mock import MagicMock

        from tit.gui.analyzer_tab import AnalyzerTab

        tab = MagicMock()
        tab.optimization_process.isRunning.return_value = True
        tab.optimization_process.terminate_process.return_value = True
        tab._single_analysis_queue = [["cmd2"], ["cmd3"]]
        tab._single_analysis_all_ok = True

        AnalyzerTab.stop_analysis(tab)

        assert tab._single_analysis_queue == []
        assert tab._single_analysis_all_ok is False

    @pytest.mark.unit
    def test_stop_analysis_clears_queue_in_source(self):
        """Source-level guard that runs on hosts without PyQt5."""
        src = (GUI_ROOT / "analyzer_tab.py").read_text(encoding="utf-8")
        body = src.split("def stop_analysis(self):", 1)[1].split("\n    def ", 1)[0]
        assert "self._single_analysis_queue = []" in body

    @pytest.mark.unit
    def test_voxel_atlas_managers_receive_masks_dir(self):
        """analyzer_tab and nifti_viewer_tab must pass masks_dir so custom
        masks in m2m_<id>/masks/ are discoverable (as roi_picker already does)."""
        for name in ("analyzer_tab.py", "nifti_viewer_tab.py"):
            src = (GUI_ROOT / name).read_text(encoding="utf-8")
            ctor = src.split("VoxelAtlasManager(", 1)[1][:400]
            assert "masks_dir=self.pm.masks(subject_id)" in ctor, name
