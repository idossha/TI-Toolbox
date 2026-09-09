"""2026-09-09: project montage sources reject outward file access.

Run: python3 -m pytest tests/test_montage_source_safety.py -q
Authored JSON/CSV sentinel bytes and real symlinks test containment. Only the
heavy SimNIBS CSV parser and optimization assignment are replaced; reads and
mapping writes use actual files. Scientific mapping correctness is elsewhere.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tit.paths import PathManager
from tit.sim import montage_sources as sources
from tit.server.routes.plan import _plan_sim

POSITIONS = [[11, 12, 13], [21, 22, 23], [31, 32, 33], [41, 42, 43]]
POSITION_DOCUMENT = {
    "optimized_positions": POSITIONS,
    "channel_array_indices": [[0, 0]] * 4,
}
FREEHAND = {
    "name": "authored",
    "electrode_positions": dict(zip(["E1+", "E1-", "E2+", "E2-"], POSITIONS)),
}


@pytest.fixture
def storage(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "project-other"
    outside.mkdir()
    pm = PathManager(project_dir=str(project))
    run = Path(pm.flex_search_run("001", "legacy.run with spaces"))
    run.mkdir(parents=True)
    (run / "electrode_positions.json").write_text(json.dumps(POSITION_DOCUMENT))
    net = Path(pm.eeg_positions("001")) / "legacy net.csv"
    net.parent.mkdir(parents=True)
    net.write_text("Electrode,11,12,13,A\n")
    return pm, run, net, outside


@pytest.mark.parametrize("case", ["absolute", "parent", "directory-link", "leaf-link"])
def test_plan_does_not_return_external_positions(storage, case):
    pm, run, _, outside = storage
    (outside / "electrode_positions.json").write_text(json.dumps(POSITION_DOCUMENT))
    run_name = run.name
    if case == "absolute":
        run_name = str(outside)
    elif case == "parent":
        import os

        run_name = os.path.relpath(outside, run.parent)
    elif case == "directory-link":
        (run / "electrode_positions.json").unlink()
        run.rmdir()
        run.symlink_to(outside, target_is_directory=True)
    else:
        (run / "electrode_positions.json").unlink()
        (run / "electrode_positions.json").symlink_to(
            outside / "electrode_positions.json"
        )
    warnings = []
    _, resolved = _plan_sim(
        "sim",
        pm,
        SimpleNamespace(subject_id="001", montages=[]),
        {},
        [],
        warnings,
        {"flex": [{"run": run_name, "electrode_type": "optimized"}]},
    )
    assert resolved["montages"] == []
    assert warnings


@pytest.mark.parametrize("level", ["directory", "leaf"])
def test_freehand_resolution_and_listing_skip_outward_links(storage, level):
    pm, _, _, outside = storage
    directory = Path(pm.m2m("001")) / "stim_configs"
    (outside / "secret.json").write_text(json.dumps(FREEHAND))
    if level == "directory":
        directory.symlink_to(outside, target_is_directory=True)
    else:
        directory.mkdir()
        (directory / "secret.json").symlink_to(outside / "secret.json")
    assert sources.list_freehand_configs(pm, "001") == []
    with pytest.raises(ValueError):
        sources.resolve_freehand_montage(pm, "001", "authored")


@pytest.fixture
def mapping(monkeypatch):
    from tit.tools import map_electrodes

    reads = []

    def read_csv(path):
        reads.append(Path(path).read_text())
        return POSITIONS, ["A", "B", "C", "D"]

    monkeypatch.setattr(map_electrodes, "read_csv_positions", read_csv)
    monkeypatch.setattr(
        map_electrodes,
        "map_electrodes_to_net",
        lambda *args: {"mapped_labels": ["A", "B", "C", "D"]},
    )
    return reads


@pytest.mark.parametrize(
    "case", ["net-leaf", "net-parent", "net-absolute", "mapping-leaf"]
)
def test_mapping_checks_all_inputs_and_output_before_io(storage, mapping, case):
    pm, run, net, outside = storage
    sentinel = outside / "sentinel.json"
    sentinel.write_bytes(b"untouched")
    net_name = net.name
    if case == "net-leaf":
        net.unlink()
        net.symlink_to(sentinel)
    elif case == "net-parent":
        net.unlink()
        net.parent.rmdir()
        net.parent.symlink_to(outside, target_is_directory=True)
        (outside / net.name).write_bytes(b"untouched")
    elif case == "net-absolute":
        net_name = str(sentinel)
    else:
        (run / "electrode_mapping_legacy net.json").symlink_to(sentinel)
    with pytest.raises(ValueError):
        sources.resolve_flex_montage(pm, "001", run.name, "mapped", eeg_net=net_name)
    assert mapping == []
    assert sentinel.read_bytes() == b"untouched"


def test_legacy_names_and_inside_aliases_resolve_and_map(storage, mapping):
    pm, run, net, _ = storage
    target = Path(pm.project_dir) / "positions.json"
    (run / "electrode_positions.json").rename(target)
    (run / "electrode_positions.json").symlink_to(target)
    optimized = sources.resolve_flex_montage(pm, "001", run.name, "optimized")
    assert optimized.electrode_pairs == [
        (POSITIONS[0], POSITIONS[1]),
        (POSITIONS[2], POSITIONS[3]),
    ]
    mapped = sources.resolve_flex_montage(
        pm, "001", run.name, "mapped", eeg_net=net.name
    )
    assert mapped.electrode_pairs == [("A", "B"), ("C", "D")]
    assert json.loads((run / "electrode_mapping_legacy net.json").read_text())[
        "mapped_labels"
    ] == ["A", "B", "C", "D"]
    assert len(mapping) == 1


@pytest.mark.parametrize("level", ["directory", "leaf"])
def test_flex_discovery_skips_outward_links(storage, level):
    pm, run, _, outside = storage
    (outside / "electrode_positions.json").write_text(json.dumps(POSITION_DOCUMENT))
    (run / "electrode_positions.json").unlink()
    if level == "directory":
        run.rmdir()
        run.symlink_to(outside, target_is_directory=True)
    else:
        (run / "electrode_positions.json").symlink_to(
            outside / "electrode_positions.json"
        )
    assert sources.list_flex_run_options(pm, "001") == []


@pytest.mark.parametrize("alias_kind", ["run", "net", "mapping"])
def test_mapping_inside_project_aliases_remain_supported(storage, mapping, alias_kind):
    pm, run, net, _ = storage
    project = Path(pm.project_dir)
    mapping_path = run / "electrode_mapping_legacy net.json"
    if alias_kind == "run":
        actual = project / "actual-run"
        run.rename(actual)
        run.symlink_to(actual, target_is_directory=True)
    elif alias_kind == "net":
        actual = project / "actual-net.csv"
        net.rename(actual)
        net.symlink_to(actual)
    else:
        actual = project / "actual-mapping.json"
        actual.write_text("{}")
        mapping_path.symlink_to(actual)
    result = sources.resolve_flex_montage(
        pm, "001", run.name, "mapped", eeg_net=net.name
    )
    assert result.electrode_pairs == [("A", "B"), ("C", "D")]
    assert json.loads(mapping_path.read_text())["mapped_labels"] == ["A", "B", "C", "D"]
    assert json.loads(mapping_path.read_text())["eeg_net"] == net.name
    if alias_kind == "mapping":
        assert mapping_path.is_symlink()
        assert json.loads(actual.read_text())["mapped_labels"] == ["A", "B", "C", "D"]


@pytest.mark.parametrize("level", ["directory", "leaf"])
def test_freehand_inside_project_aliases_remain_supported(storage, level):
    pm, _, _, _ = storage
    project = Path(pm.project_dir)
    directory = Path(pm.m2m("001")) / "stim_configs"
    actual = project / "actual-freehand"
    actual.mkdir()
    (actual / "authored.json").write_text(json.dumps(FREEHAND))
    if level == "directory":
        directory.symlink_to(actual, target_is_directory=True)
    else:
        directory.mkdir()
        (directory / "authored.json").symlink_to(actual / "authored.json")
    assert sources.list_freehand_configs(pm, "001") == ["authored"]
    assert sources.resolve_freehand_montage(pm, "001", "authored").electrode_pairs == [
        (POSITIONS[0], POSITIONS[1]),
        (POSITIONS[2], POSITIONS[3]),
    ]


def test_mapping_dangling_external_output_is_not_created(storage, mapping):
    pm, run, net, outside = storage
    target = outside / "absent.json"
    alias = run / "electrode_mapping_legacy net.json"
    alias.symlink_to(target)
    with pytest.raises(ValueError):
        sources.resolve_flex_montage(pm, "001", run.name, "mapped", eeg_net=net.name)
    assert not target.exists()
    assert alias.is_symlink()
    assert mapping == []


@pytest.mark.parametrize(
    "run_id", ["../escape", "id/../../escape", "id\\escape", "..", "bad\x00id"]
)
def test_flex_montage_name_rejects_path_valued_run_id(run_id):
    with pytest.raises(ValueError):
        sources.flex_montage_name("legacy.run with spaces", run_id, "optimized")


@pytest.mark.parametrize(
    "run_id", ["../escape", "id/../../escape", "id\\escape", "..", "bad\x00id"]
)
def test_plan_rejects_path_valued_run_id(storage, run_id):
    pm, run, _, _ = storage
    warnings = []
    jobs, resolved = _plan_sim(
        "sim",
        pm,
        SimpleNamespace(subject_id="001", montages=[]),
        {},
        [],
        warnings,
        {"flex": [{"run": run.name, "run_id": run_id, "electrode_type": "optimized"}]},
    )
    assert jobs == []
    assert resolved["montages"] == []
    assert warnings


@pytest.mark.parametrize("run_id", ["custom-id", "legacy.id_42", "ID with spaces"])
def test_legacy_run_id_remains_supported_by_name_and_plan(storage, run_id):
    pm, run, _, _ = storage
    name = sources.flex_montage_name(run.name, run_id, "optimized")
    assert name == f"flex_legacy_run_with_spaces_{run_id}_optimized"
    warnings = []
    jobs, resolved = _plan_sim(
        "sim",
        pm,
        SimpleNamespace(subject_id="001", montages=[]),
        {},
        [],
        warnings,
        {"flex": [{"run": run.name, "run_id": run_id, "electrode_type": "optimized"}]},
    )
    assert resolved["montages"][0]["name"] == name
    assert Path(jobs[0].output_dir).name == name
    assert warnings == []
