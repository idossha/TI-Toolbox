"""Re-running flex-search into an existing output folder replaces the previous run's outputs.

Pins (2026-10-22, package p12; spec: a run folder describes exactly the run in its
``flex_meta.json``, docs/wiki/flex-search.md "flex_meta.json"):
* after an aborted run (``00/candidates.csv`` left behind, as in Dataset 000's sub-ernie
  ``l_precuneus_mean_TImax_v2/00``) the re-run succeeds instead of raising ``FileExistsError``
  from the candidate recorder, and ``candidate_history/00`` holds only the new trials;
* after a finished 4-restart run with an EEG-net mapping, a 1-restart re-run without mapping
  leaves ``candidate_history == ['00']``, no ``electrode_mapping_*.json``, no ``final_sim_*``,
  ``catalog.flex_runs(...)['mappings'] == []`` and a report with one run row;
* a file the run did not write (``notes.txt``) survives.

The runner is the real ``run_flex_search`` (manifest, recorder, promotion, report) with only the
SimNIBS optimiser replaced by :class:`FakeOpt`, whose ``run`` evaluates one candidate through the
real ``install_candidate_recorder`` wrapper. Expected values are the fixture's own numbers
(``ROI`` below), not the runner's output.
Run: ``python -m pytest tests/test_flex_rerun_same_folder.py -q``.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from tit.opt.config import FlexConfig

#: The target field samples a fake optimiser evaluates (V/m); its mean, 0.25 V/m, is the
#: candidate's ``roi_mean`` and, negated, the ``mean`` goal's objective.
ROI = np.array([0.1, 0.2, 0.3, 0.4])
NON_ROI = np.array([0.05, 0.1, 0.15])
#: Electrode centres (mm) of channel 0 array 0/1 and channel 1 array 0/1.
CENTRES = [
    [70.0, -10.0, 20.0],
    [65.0, 30.0, 25.0],
    [-70.0, -12.0, 18.0],
    [-66.0, 28.0, 22.0],
]


class FakeOpt:
    """The part of SimNIBS's ``TesFlexOptimization`` that ``run_flex_search`` drives.

    ``run`` evaluates one candidate through ``goal_fun`` (wrapped by the real candidate
    recorder), accepts it as the optimum, and writes the files SimNIBS writes into the restart
    folder: ``electrode_positions.json``, ``summary.txt`` and, with mapping, the unrenamed
    ``electrode_mapping.json``.
    """

    def __init__(self, config: FlexConfig, scale: float = 1.0):
        self.config = config
        self.scale = scale
        self.output_folder = None
        self.optimizer_termination = {"global": {"evaluations": 1, "iterations": 1}}
        self.electrode_pos = [CENTRES[:2], CENTRES[2:]]
        self.electrode = []
        for ch in range(2):
            arrays = []
            for arr in range(2):
                pose = np.eye(4)
                pose[:3, 3] = CENTRES[2 * ch + arr]
                current = 0.001 * config.current_mA * (1 if arr == 0 else -1)
                arrays.append(
                    SimpleNamespace(
                        electrodes=[SimpleNamespace(posmat=pose, ele_current=current)]
                    )
                )
            self.electrode.append(SimpleNamespace(_electrode_arrays=arrays))
        self.goal = str(getattr(config.goal, "value", config.goal))
        self.update_field = lambda *a, **k: [[ROI * self.scale, NON_ROI]]
        self.compute_goal = lambda fields: -float(np.mean(fields[0][0]))
        self.goal_fun = self._goal_fun
        from tit.opt.flex.candidates import install_candidate_recorder

        install_candidate_recorder(self, config)

    def _goal_fun(self, parameters):
        fields = self.update_field(parameters)
        return self.compute_goal(fields)

    def run(self, cpus=None):
        out = Path(self.output_folder)
        params = np.array([0.5, -0.25, 0.125])
        self.optim_funvalue = self.goal_fun(params)
        self.optim_parameters = params
        (out / "electrode_positions.json").write_text(
            json.dumps(
                {
                    "optimized_positions": CENTRES,
                    "channel_array_indices": [[0, 0], [0, 1], [1, 0], [1, 1]],
                }
            )
        )
        (out / "summary.txt").write_text("Goal: <function>\nOptimizer: fake\n")
        if self.config.enable_mapping:
            (out / "electrode_mapping.json").write_text(
                json.dumps(
                    {
                        "eeg_net": self.config.eeg_net,
                        "mapped_labels": ["E1", "E2", "E3", "E4"],
                        "channel_array_indices": [[0, 0], [0, 1], [1, 0], [1, 1]],
                    }
                )
            )


def flex_config(output_folder: str, **overrides) -> FlexConfig:
    kw = dict(
        subject_id="001",
        goal="mean",
        postproc="max_TI",
        current_mA=1.0,
        electrode=FlexConfig.ElectrodeConfig(),
        roi=FlexConfig.SphericalROI(x=-40.0, y=-20.0, z=50.0, radius=10.0),
        n_multistart=1,
        output_folder=output_folder,
    )
    kw.update(overrides)
    return FlexConfig(**kw)


@pytest.fixture
def flex_project(init_pm):
    """A project whose subject 001 has a head mesh, and the patches that stand in for SimNIBS:
    ``build_optimization`` returns a :class:`FakeOpt` (``opt_scales`` sets each new optimiser's
    field scale, in call order) and the skin figure is skipped. Yields ``(pm, opt_scales)``.
    """
    m2m = Path(init_pm.m2m("001"))
    (m2m / "001.msh").touch()
    scales: list[float] = []
    built = iter(range(10_000))

    def build(config):
        i = next(built)
        return FakeOpt(config, scales[i] if i < len(scales) else 1.0)

    with (
        patch("tit.opt.flex.flex.builder.build_optimization", side_effect=build),
        patch("tit.opt.flex.flex.builder.configure_optimizer_options"),
        patch("tit.opt.flex.flex.create_valid_skin_region_visualization"),
    ):
        yield init_pm, scales


def reports(pm) -> list[Path]:
    return sorted(Path(pm.reports(), "sub-001").glob("flex_search_report_*.html"))


def report_runs(page: Path) -> str:
    return re.search(r"<dt>Runs</dt><dd>(.*?)</dd>", page.read_text()).group(1)


def test_a_rerun_after_an_aborted_run_replaces_its_trials(flex_project):
    from tit.opt.flex.flex import run_flex_search

    pm, _ = flex_project
    base = Path(pm.flex_search("001")) / "l_precuneus_mean_TImax_v2"
    stale = base / "00"
    stale.mkdir(parents=True)
    (stale / "candidates.csv").write_text(
        "candidate_id,evaluation,objective\nstale:1,1,-9.0\n"
    )
    (stale / "candidate_geometry.jsonl").write_text('{"candidate_id": "stale:1"}\n')

    result = run_flex_search(flex_config(str(base)))

    assert result.success and result.best_value == pytest.approx(-0.25)
    with (base / "candidate_history" / "00" / "candidates.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert [float(r["roi_mean"]) for r in rows] == pytest.approx([0.25])
    assert not any(r["candidate_id"].startswith("stale") for r in rows)
    assert not (base / "00").exists()  # the temporary restart folder is gone


def test_a_rerun_after_a_finished_run_leaves_only_the_new_run(flex_project):
    from tit.catalog import flex_runs
    from tit.opt.flex.flex import run_flex_search

    pm, _ = flex_project
    base = Path(pm.flex_search("001")) / "thalamus"
    # The previous run: 4 restarts, mapped onto GSN-HydroCel-185, final simulations.
    _net(pm)
    run_flex_search(
        flex_config(
            str(base),
            n_multistart=4,
            enable_mapping=True,
            eeg_net="GSN-HydroCel-185.csv",
        )
    )
    assert sorted(p.name for p in (base / "candidate_history").iterdir()) == [
        "00",
        "01",
        "02",
        "03",
    ]
    assert (base / "electrode_mapping_GSN-HydroCel-185.json").is_file()
    (base / "final_sim_1").mkdir()
    (base / "final_sim_1" / "fields_summary.txt").write_text("stale")
    (base / "roi.png").write_bytes(b"stale target figure")
    (base / "notes.txt").write_text("mine")

    result = run_flex_search(flex_config(str(base)))

    assert result.success and result.function_values == pytest.approx([-0.25])
    assert sorted(p.name for p in (base / "candidate_history").iterdir()) == ["00"]
    assert not list(base.glob("electrode_mapping*.json"))
    assert not list(base.glob("final_sim_*"))
    assert not (base / "roi.png").exists()  # a sphere target writes no ROI plate
    assert (base / "notes.txt").read_text() == "mine"
    meta = json.loads((base / "flex_meta.json").read_text())
    assert meta["n_multistart"] == 1 and len(meta["result"]["all_values"]) == 1
    (entry,) = [r for r in flex_runs(pm, "001") if r["name"] == "thalamus"]
    assert entry["mappings"] == []
    pages = reports(pm)
    assert len(pages) == 2  # one per run
    assert report_runs(pages[-1]) == "1"


def _net(pm) -> bool:
    """Write the GSN-HydroCel-185 net the mapped run validates (header + 4 electrodes)."""
    net = Path(pm.eeg_positions("001")) / "GSN-HydroCel-185.csv"
    net.parent.mkdir(parents=True, exist_ok=True)
    net.write_text(
        "Electrode,E1,70,-10,20\nElectrode,E2,65,30,25\n"
        "Electrode,E3,-70,-12,18\nElectrode,E4,-66,28,22\n"
    )
    return True
