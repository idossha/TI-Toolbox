"""Every runner that writes files reports them as job artifacts (lane FX3).

What this pins, and the failure each case alone catches:

* ``blender`` — same shape, from ``MontageResult.final_blend``'s own directory
  (job ``9aa38d4d9f414283``: a ``.blend`` plus two STLs written, zero reported).
* ``tools`` — a ``tools`` job is argv, not a spec.json, so no shared wrapper can report
  for it; ``tit.tools.electrode_overlay`` reports its own two files
  (job ``0465e86914a94ea4``), and ``tit.tools.nifti_to_mesh`` — the only other module
  under ``tit/tools/`` a ``tools`` job can run — reports the mesh it wrote.
* ``analyzer`` — the artifact root has to follow ``config.output_dir``. Listing
  ``Analyses/<Space>/`` regardless meant a run with a custom output directory reported
  nothing even though it had written five files; and a *group* run reported nothing at
  all, though ``GroupResult`` names the summary CSV and the comparison PDF it wrote.

The evidence is the runner's own ``events.jsonl``: these tests set ``$TIT_EVENTS_FILE``,
run the entry point with the science call mocked out, and read the JSON lines back --
the same file ``tit.jobs.manager`` reads to build ``JobStatus.artifacts``.

``stats`` is the fourth runner of this lane; its cases live in
``tests/test_stats_main.py`` because importing ``tit.stats.__main__`` needs the real-scipy
restore that file already performs at import time.

Reproduce: ``python3 -m pytest -q tests/test_runner_artifacts.py tests/test_stats_main.py``
"""

from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tit.jobs import events


def _read_events(path) -> list[dict]:
    """Every event line the runner wrote, in order."""
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _artifact_paths(path) -> list[str]:
    return [e["path"] for e in _read_events(path) if e["type"] == "artifact"]


def _results(path) -> list[dict]:
    return [e for e in _read_events(path) if e["type"] == "result"]


@pytest.fixture
def events_file(tmp_path, monkeypatch):
    """A fresh ``$TIT_EVENTS_FILE`` and a clean artifact accumulator."""
    path = tmp_path / "events.jsonl"
    monkeypatch.setenv("TIT_EVENTS_FILE", str(path))
    events._reset_state()
    yield path
    events._reset_state()


def _write_outputs(directory, names) -> list[str]:
    os.makedirs(directory, exist_ok=True)
    written = []
    for name in names:
        p = os.path.join(directory, name)
        with open(p, "w") as fh:
            fh.write("x")
        written.append(p)
    return written


# ---------------------------------------------------------------------------
# blender
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBlenderArtifacts:
    def test_montage_reports_the_directory_its_blend_landed_in(
        self, tmp_path, events_file
    ):
        from tit.blender.__main__ import _run_montage

        out_dir = tmp_path / "visual_exports" / "smoke"
        written = _write_outputs(
            out_dir,
            ["scalp.stl", "gm.stl", "ernie_docs_example_montage_publication.blend"],
        )
        blend = os.path.join(out_dir, "ernie_docs_example_montage_publication.blend")
        result = SimpleNamespace(
            scalp_stl=written[0],
            gm_stl=written[1],
            electrodes_blend=blend,
            final_blend=blend,
        )
        with (
            patch("tit.blender.montage_publication.run_montage", return_value=result),
            patch("tit.blender.__main__.deserialize_config", return_value=MagicMock()),
        ):
            assert _run_montage({}, MagicMock()) == str(out_dir)
        assert set(os.listdir(out_dir)) == {os.path.basename(w) for w in written}

    def test_main_emits_the_handlers_output_dir(self, tmp_path, events_file):
        from tit.blender import __main__ as blender_main

        out_dir = tmp_path / "visual_exports" / "smoke"
        written = _write_outputs(out_dir, ["scalp.stl", "gm.stl", "scene.blend"])
        spec = tmp_path / "config.json"
        spec.write_text(
            json.dumps({"_type": "MontageConfig", "project_dir": str(tmp_path)})
        )

        with (
            patch.object(sys, "argv", ["x", str(spec)]),
            patch("tit.paths.get_path_manager"),
            patch.dict(
                blender_main.__dict__,
                {"_run_montage": lambda data, logger: str(out_dir)},
                clear=False,
            ),
        ):
            assert blender_main.main() == 0

        assert sorted(_artifact_paths(events_file)) == sorted(written)
        [event] = _results(events_file)
        assert event["outputs"]["output_dir"] == str(out_dir)

    def test_a_handler_that_resolved_no_directory_is_not_fatal(
        self, tmp_path, events_file
    ):
        from tit.blender import __main__ as blender_main

        spec = tmp_path / "config.json"
        spec.write_text(
            json.dumps({"_type": "MontageConfig", "project_dir": str(tmp_path)})
        )
        with (
            patch.object(sys, "argv", ["x", str(spec)]),
            patch("tit.paths.get_path_manager"),
            patch.dict(
                blender_main.__dict__,
                {"_run_montage": lambda data, logger: None},
                clear=False,
            ),
        ):
            assert blender_main.main() == 0
        assert _artifact_paths(events_file) == []


# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestToolsArtifacts:
    def test_electrode_overlay_reports_the_overlay_and_its_lut(
        self, tmp_path, events_file
    ):
        from tit.tools import electrode_overlay

        overlay = tmp_path / "overlay.nii"
        lut = tmp_path / "overlay.lut"
        overlay.write_text("x")
        lut.write_text("x")

        argv = ["x", "config.json", "ref.nii.gz", str(overlay)]
        with (
            patch.object(sys, "argv", argv),
            patch.object(
                electrode_overlay,
                "create_electrode_overlay_nifti",
                return_value=str(overlay),
            ),
        ):
            electrode_overlay.main(argv[1:])

        assert _artifact_paths(events_file) == [str(overlay), str(lut)]
        [event] = _results(events_file)
        assert event["outputs"] == {"success": True, "overlay": str(overlay)}

    def test_a_missing_lut_is_simply_not_reported(self, tmp_path, events_file):
        from tit.tools import electrode_overlay

        overlay = tmp_path / "overlay.nii"
        overlay.write_text("x")
        with patch.object(
            electrode_overlay,
            "create_electrode_overlay_nifti",
            return_value=str(overlay),
        ):
            electrode_overlay.main(["config.json", "ref.nii.gz", str(overlay)])

        assert _artifact_paths(events_file) == [str(overlay)]

    def test_nifti_to_mesh_reports_the_mesh_it_wrote(self, tmp_path, events_file):
        """The second runnable ``tit.tools.*`` module reports too.

        ``electrode_overlay`` and ``nifti_to_mesh`` are the only two modules under
        ``tit/tools/`` with a ``__main__`` guard, i.e. the only two a ``tools`` job can
        run today (``tit.jobs.kinds`` allowlists ``tit.tools.*``). Fixing only the first
        would leave the same "job succeeded, artifacts: []" hole open for the other.
        """
        sys.modules.pop("tit.tools.nifti_to_mesh", None)
        with patch.dict(
            sys.modules,
            {"skimage": MagicMock(), "skimage.measure": MagicMock()},
        ):
            from tit.tools import nifti_to_mesh

            mesh = tmp_path / "thalamus.stl"
            mesh.write_text("solid")
            result = {
                "output_file": str(mesh),
                "vertices": 1234,
                "faces": 2468,
                "removed_components": 0,
            }
            argv = ["nifti_to_mesh", "seg.nii.gz", "-o", str(mesh)]
            with (
                patch.object(sys, "argv", argv),
                patch.object(nifti_to_mesh, "nifti_to_mesh", return_value=result),
            ):
                assert nifti_to_mesh.main() == 0

        assert _artifact_paths(events_file) == [str(mesh)]
        [event] = _results(events_file)
        assert event["outputs"] == {
            "success": True,
            "output_file": str(mesh),
            "vertices": 1234,
            "faces": 2468,
        }
        assert event["artifacts"] == [
            {"path": str(mesh), "kind": "mesh", "label": "surface mesh"}
        ]


# ---------------------------------------------------------------------------
# analyzer -- output_dir only
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnalyzerArtifactRoot:
    def _config(self, **kw):
        from tit.analyzer.config import AnalyzerConfig

        base = dict(
            mode="single",
            subject_id="ernie",
            simulation="L_Insula",
            space="mesh",
            analysis_type="spherical",
            center=[0, 0, 0],
            radius=5,
        )
        base.update(kw)
        return AnalyzerConfig(**base)

    def test_custom_output_dir_wins_over_the_space_directory(self):
        from tit.analyzer.__main__ import analysis_artifact_root

        pm = MagicMock()
        pm.analysis_dir.return_value = "/p/Simulations/L_Insula/Analyses/Mesh"
        root = analysis_artifact_root(self._config(output_dir="/p/elsewhere/run1"), pm)
        assert root == "/p/elsewhere/run1"
        pm.analysis_dir.assert_not_called()

    def test_without_one_it_is_the_space_directory(self):
        from tit.analyzer.__main__ import analysis_artifact_root

        pm = MagicMock()
        pm.analysis_dir.return_value = "/p/Simulations/L_Insula/Analyses/Mesh"
        assert (
            analysis_artifact_root(self._config(), pm)
            == "/p/Simulations/L_Insula/Analyses/Mesh"
        )

    def test_a_group_run_reports_the_two_files_it_wrote(self, tmp_path, events_file):
        """A finished group analysis used to report ``artifacts: []`` too.

        The single-subject branch lists its output directory; the group branch wrote a
        summary CSV and a comparison PDF and reported neither, so the Jobs rail and
        Results had nothing to link for a group run.
        """
        from tit.analyzer import __main__ as entry

        summary = tmp_path / "group_analysis_summary.csv"
        plot = tmp_path / "group_comparison.pdf"
        summary.write_text("subject,roi_mean\n")
        plot.write_text("%PDF")
        spec = tmp_path / "config.json"
        spec.write_text(
            json.dumps(
                {
                    "project_dir": str(tmp_path),
                    "mode": "group",
                    "subject_ids": ["101", "ernie"],
                    "simulation": "L_Insula",
                    "analysis_type": "spherical",
                    "center": [0, 0, 0],
                    "radius": 5,
                }
            )
        )
        result = SimpleNamespace(
            subject_results={}, summary_csv_path=summary, comparison_plot_path=plot
        )
        with (
            patch.object(sys, "argv", ["x", str(spec)]),
            patch("tit.analyzer.__main__.get_path_manager"),
            patch("tit.analyzer.run_group_analysis", return_value=result) as run,
        ):
            with pytest.raises(SystemExit) as exc:
                entry.main()

        assert exc.value.code == 0
        run.assert_called_once()
        assert _artifact_paths(events_file) == [str(summary), str(plot)]
        [event] = _results(events_file)
        assert [a["kind"] for a in event["artifacts"]] == ["csv", "pdf"]

    def test_a_group_run_without_a_plot_still_reports_the_summary(
        self, tmp_path, events_file
    ):
        """``GroupResult.comparison_plot_path`` is ``None`` when plotting failed."""
        from tit.analyzer.__main__ import _emit_group_artifacts

        summary = tmp_path / "group_analysis_summary.csv"
        summary.write_text("subject,roi_mean\n")
        _emit_group_artifacts(
            SimpleNamespace(summary_csv_path=summary, comparison_plot_path=None)
        )
        assert _artifact_paths(events_file) == [str(summary)]

    def test_a_group_run_without_a_subject_has_no_root(self):
        from tit.analyzer.__main__ import analysis_artifact_root

        cfg = self._config(mode="group", subject_id=None, subject_ids=["a", "b"])
        assert analysis_artifact_root(cfg, MagicMock()) is None

    def test_an_output_dir_outside_the_simulation_says_so(self, tmp_path, capsys):
        from tit.analyzer.__main__ import _warn_if_undiscoverable

        sim = tmp_path / "Simulations" / "L_Insula"
        sim.mkdir(parents=True)
        pm = MagicMock()
        pm.simulation.return_value = str(sim)
        _warn_if_undiscoverable(self._config(output_dir=str(tmp_path / "scratch")), pm)
        out = capsys.readouterr().out
        assert "is outside" in out and str(sim) in out

    def test_an_output_dir_under_the_simulation_is_silent(self, tmp_path, capsys):
        from tit.analyzer.__main__ import _warn_if_undiscoverable

        sim = tmp_path / "Simulations" / "L_Insula"
        (sim / "Analyses" / "Custom").mkdir(parents=True)
        pm = MagicMock()
        pm.simulation.return_value = str(sim)
        _warn_if_undiscoverable(
            self._config(output_dir=str(sim / "Analyses" / "Custom")), pm
        )
        assert capsys.readouterr().out == ""
