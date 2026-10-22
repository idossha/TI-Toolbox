"""Re-running a group analysis under an existing name leaves only the new run's files (p23).

What this pins: a confirmed re-run ("Replace and rerun" in the app; any second call under one
name from Python) replaces the earlier run instead of writing over part of it.

- Cluster permutation (``python -m tit.stats``): run 1 is a correlation with a planted block, so
  it forms clusters and draws ``cluster_size_mass_correlation.pdf``; run 2, under the same
  ``analysis_name``, forms none (cluster-forming p 1e-12 on noise), so it draws no such figure.
  Before, ``_resolve_output_dir`` reused the folder: run 1's figure and its timestamped log
  stayed beside run 2's outputs, and ``catalog.group_stats_detail`` -- which lists every file in
  the folder -- showed them as run 2's.
- NIfTI averaging (``python -m tit.stats.nifti_average``): run 1 averages groups A and B, run 2
  groups A and C; ``average_B.nii.gz`` must not survive. A re-run that fails while reading its
  inputs (a missing file) replaces nothing: run 1's files stay as they were, because the runner
  reads every input before it clears the folder. (The stats runner clears its folder before it
  starts, as the run log is opened inside it; that order is not pinned here.)

Where the expected file sets come from: the runner's own artifact events of the SECOND run
(what it says it wrote) and the groups the second config names, compared with ``os.listdir``;
the figure rule (drawn only when a cluster formed) is ``run_correlation``'s documented
behaviour, and run 1 is checked to have drawn it so the test cannot pass vacuously.

Host leg: real numpy/scipy, nibabel and matplotlib are mocked here, so the writers of the NIfTI
maps and figures are replaced by ones that write placeholder bytes at the path they are given.
Reproduce: ``.venv/bin/python -m pytest tests/test_group_rerun_overwrite.py -q -p no:cacheprovider``.
Dated 2026-10-22.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

for _mod in ("scipy.ndimage", "scipy.stats"):
    sys.modules.setdefault(_mod, MagicMock())

EFFECTS = np.arange(1.0, 7.0)


def _planted_block() -> np.ndarray:
    """A 3x3x3 block whose field falls with the effect (r near -1) on a flat background."""
    rng = np.random.default_rng(12)
    data = np.ones((6, 6, 6, EFFECTS.size), dtype=np.float32)
    for k, e in enumerate(EFFECTS):
        data[1:4, 1:4, 1:4, k] = 10.0 - e + rng.random((3, 3, 3))
    return data


def _noise() -> np.ndarray:
    rng = np.random.default_rng(8)
    return (rng.random((6, 6, 6, EFFECTS.size)) + 1.0).astype(np.float32)


def _write_placeholder(*args, **_kwargs) -> None:
    path = next(a for a in args if isinstance(a, str) and os.sep in a)
    Path(path).write_bytes(b"placeholder")


@pytest.fixture()
def events_file(tmp_path, monkeypatch):
    import tit.jobs.events as events_mod
    import tit.logger as logger_mod

    path = tmp_path / "events.jsonl"

    def reset():
        path.unlink(missing_ok=True)
        monkeypatch.setenv("TIT_EVENTS_FILE", str(path))
        logger_mod._event_sinks.clear()
        events_mod._reset_state()

    yield path, reset
    logger_mod._event_sinks.clear()
    events_mod._reset_state()


def _artifacts(path: Path) -> set[str]:
    events = [json.loads(line) for line in path.read_text().splitlines()]
    return {os.path.basename(e["path"]) for e in events if e["type"] == "artifact"}


def _main(module, config_path: Path, monkeypatch) -> int:
    monkeypatch.setattr(sys, "argv", [module.__name__, str(config_path)])
    try:
        module.main()
    except SystemExit as exc:
        return exc.code
    return 0


def test_a_correlation_rerun_that_forms_no_cluster_keeps_none_of_the_first_runs_files(
    real_scipy, tmp_path, monkeypatch, events_file
) -> None:
    import tit.stats.__main__ as stats_main
    import tit.stats.permutation as perm
    from tit.catalog import group_stats_detail
    from tit.paths import get_path_manager

    events_path, reset_events = events_file
    monkeypatch.delenv("TIT_JOB_ID", raising=False)
    template = SimpleNamespace(affine=np.eye(4), header=None)
    volumes = {}
    monkeypatch.setattr(
        perm,
        "load_group_data_ti_toolbox",
        lambda dicts, **_: (
            volumes["data"],
            template,
            [d["subject_id"] for d in dicts],
        ),
    )
    monkeypatch.setattr(perm, "_save_nifti", _write_placeholder)
    monkeypatch.setattr(perm, "plot_permutation_null_distribution", _write_placeholder)
    monkeypatch.setattr(perm, "plot_cluster_size_mass_correlation", _write_placeholder)

    project = tmp_path / "project"
    project.mkdir()
    config = {
        "_type": "CorrelationConfig",
        "project_dir": str(project),
        "analysis_name": "rerun",
        "subjects": [
            {"subject_id": f"s{i}", "simulation_name": "N", "effect_size": float(e)}
            for i, e in enumerate(EFFECTS, 1)
        ],
        "n_permutations": 20,
        "n_jobs": 1,
        "use_weights": False,
    }
    run_dir = project / "derivatives" / "ti-toolbox" / "stats" / "correlation" / "rerun"

    volumes["data"] = _planted_block()
    reset_events()
    cfg1 = tmp_path / "run1.json"
    cfg1.write_text(json.dumps(config))
    assert _main(stats_main, cfg1, monkeypatch) == 0
    # Run 1 formed clusters, so it drew the figure the second run will not.
    assert (run_dir / "cluster_size_mass_correlation.pdf").is_file()

    volumes["data"] = _noise()
    reset_events()
    cfg2 = tmp_path / "run2.json"
    cfg2.write_text(json.dumps({**config, "cluster_threshold": 1e-12}))
    assert _main(stats_main, cfg2, monkeypatch) == 0

    on_disk = set(os.listdir(run_dir))
    assert "cluster_size_mass_correlation.pdf" not in on_disk
    assert on_disk == _artifacts(events_path)
    logs = [name for name in on_disk if name.endswith(".log")]
    assert len(logs) == 1
    banner = "CORRELATION-BASED CLUSTER PERMUTATION TESTING"
    assert (run_dir / logs[0]).read_text().count(banner) == 1

    detail = group_stats_detail(get_path_manager(str(project)), "correlation", "rerun")
    assert detail["status"] == "ok"
    assert sorted(os.path.basename(a["path"]) for a in detail["artifacts"]) == sorted(
        on_disk
    )


def test_a_nifti_average_rerun_with_other_groups_drops_the_old_groups_maps(
    tmp_path, monkeypatch, events_file
) -> None:
    import tit.stats.nifti as nifti_mod
    import tit.stats.nifti_average as runner

    events_path, reset_events = events_file
    monkeypatch.delenv("TIT_JOB_ID", raising=False)

    def load_one(subject_id, simulation_name, pattern, dtype=np.float32):
        img = SimpleNamespace(affine=np.eye(4), header={})
        return np.full((2, 2, 2), 1.0, dtype=dtype), img, f"/in/{subject_id}"

    monkeypatch.setattr(nifti_mod, "load_subject_nifti_ti_toolbox", load_one)
    monkeypatch.setattr(
        nifti_mod,
        "nib",
        SimpleNamespace(
            Nifti1Image=lambda d, a, h: SimpleNamespace(affine=a, header=h)
        ),
    )
    monkeypatch.setattr(
        runner,
        "nib",
        SimpleNamespace(Nifti1Image=lambda d, a, h: d, save=_write_placeholder),
    )
    project = tmp_path / "project"
    project.mkdir()
    out = project / "derivatives" / "ti-toolbox" / "nifti_average" / "groups"

    def run(groups: dict[str, str]) -> int:
        reset_events()
        cfg = tmp_path / "avg.json"
        rows = [
            {"subject_id": s, "simulation_name": "M1", "group": g}
            for s, g in groups.items()
        ]
        cfg.write_text(
            json.dumps(
                {"project_dir": str(project), "output_name": "groups", "subjects": rows}
            )
        )
        return _main(runner, cfg, monkeypatch)

    assert run({"1": "A", "2": "B"}) == 0
    assert (out / "average_B.nii.gz").is_file()
    assert run({"1": "A", "2": "C"}) == 0

    on_disk = set(os.listdir(out))
    assert on_disk == {
        "average_A.nii.gz",
        "average_C.nii.gz",
        "difference_A_minus_C.nii.gz",
        "config.json",
    }
    assert on_disk == _artifacts(events_path)


def test_a_nifti_average_rerun_that_cannot_read_its_inputs_keeps_the_earlier_run(
    tmp_path, monkeypatch, events_file
) -> None:
    import tit.stats.nifti as nifti_mod
    import tit.stats.nifti_average as runner

    _events_path, reset_events = events_file
    monkeypatch.delenv("TIT_JOB_ID", raising=False)
    missing = {"3"}

    def load_one(subject_id, simulation_name, pattern, dtype=np.float32):
        if subject_id in missing:
            raise FileNotFoundError(f"NIfTI file not found: /in/{subject_id}")
        img = SimpleNamespace(affine=np.eye(4), header={})
        return np.full((2, 2, 2), 1.0, dtype=dtype), img, f"/in/{subject_id}"

    monkeypatch.setattr(nifti_mod, "load_subject_nifti_ti_toolbox", load_one)
    monkeypatch.setattr(
        nifti_mod,
        "nib",
        SimpleNamespace(
            Nifti1Image=lambda d, a, h: SimpleNamespace(affine=a, header=h)
        ),
    )
    monkeypatch.setattr(
        runner,
        "nib",
        SimpleNamespace(Nifti1Image=lambda d, a, h: d, save=_write_placeholder),
    )
    project = tmp_path / "project"
    project.mkdir()
    out = project / "derivatives" / "ti-toolbox" / "nifti_average" / "groups"

    def run(groups: dict[str, str]) -> int:
        reset_events()
        cfg = tmp_path / "avg.json"
        rows = [
            {"subject_id": s, "simulation_name": "M1", "group": g}
            for s, g in groups.items()
        ]
        cfg.write_text(
            json.dumps(
                {"project_dir": str(project), "output_name": "groups", "subjects": rows}
            )
        )
        return _main(runner, cfg, monkeypatch)

    assert run({"1": "A", "2": "B"}) == 0
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    assert set(before) == {
        "average_A.nii.gz",
        "average_B.nii.gz",
        "difference_A_minus_B.nii.gz",
        "config.json",
    }

    assert run({"1": "A", "3": "C"}) == 1
    assert {p.name: p.read_bytes() for p in out.iterdir()} == before
