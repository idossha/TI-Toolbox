"""A net whose electrodes collapsed onto one point is refused before anything uses it.

What this pins (2026-10-22, package p07, task app-flags-stale-nets):

* :func:`tit.caps.net_stats` calls two electrodes closer than ``COLLAPSE_MM`` collapsed,
  except the four 10-20 sites that carry two names (T3/T7, T4/T8, T5/P7, T6/P8; Oostenveld &
  Praamstra 2001, Table 1), which SimNIBS's ``EEG10-20_extended_SPM12`` cap puts on one point
  by design. Those are reported under ``aliases``. Before this, the caps panel told users to
  "re-apply or fix" that correct cap.
* Job preflight refuses a sim montage, a flex mapping, a leadfield and an ex search on a
  collapsed net with a finding whose fix is "Re-apply in EEG caps"; the SPM12-like net passes.
* The scene's ``read_net`` (viewer, run-page panes) refuses a collapsed net with the same
  sentence; the caps panel's Inspect still reads it (its job is to show the collapse).
* The Blender montage export refuses a collapsed net instead of drawing a few blobs.

Every expected pair below is read off the hand-written coordinates (three electrodes share
one point, so the pairs are the three 2-combinations of their labels); nothing is taken
from the code under test. Measured on Dataset 000 the same day: sub-LA and sub-CHN still
hold GSN-HydroCel-128 / BioSemi nets warped before 3.1.1 with 29-110 collapsed pairs each
(``tests/test_net_sanity_realdata.py`` checks those).

Reproduce: ``.venv/bin/python -m pytest tests/test_stale_nets_flagged.py -q``.
"""

from __future__ import annotations

from itertools import combinations
from pathlib import Path

import numpy as np
import pytest

from tests.test_caps import BEARER, project  # noqa: F401  (fixture re-used)
from tit import caps
from tit.jobs.preflight import preflight
from tit.paths import get_path_manager
from tit.scene import build

# Three electrodes on one scalp point (the stale-warp failure) and three spread out.
STALE = (
    "Electrode,0.0,0.0,95.0,E1\n"
    "Electrode,0.0,0.0,95.0,E2\n"
    "Electrode,0.0,0.0,95.0,E3\n"
    "Electrode,70.0,0.0,60.0,E4\n"
    "Electrode,-70.0,0.0,60.0,E5\n"
    "Electrode,0.0,70.0,60.0,E6\n"
    "Fiducial,0.0,90.0,0.0,Nz\n"
)
STALE_PAIRS = {frozenset(p) for p in combinations(("E1", "E2", "E3"), 2)}

# SPM12-like: every old/new 10-20 name pair on one point, as SimNIBS ships it.
SPM12_LIKE = (
    "Electrode,-80.0,0.0,10.0,T3\n"
    "Electrode,-80.0,0.0,10.0,T7\n"
    "Electrode,80.0,0.0,10.0,T4\n"
    "Electrode,80.0,0.0,10.0,T8\n"
    "Electrode,-70.0,-40.0,10.0,T5\n"
    "Electrode,-70.0,-40.0,10.0,P7\n"
    "Electrode,70.0,-40.0,10.0,T6\n"
    "Electrode,70.0,-40.0,10.0,P8\n"
    "Electrode,0.0,60.0,60.0,Fz\n"
    "ReferenceElectrode,0.0,0.0,95.0,Cz\n"
    "Fiducial,0.0,90.0,0.0,Nz\n"
)
# The 10-20 nomenclature's synonyms, typed from the table, not from tit.caps.
ALIASES_1020 = {
    frozenset(("T3", "T7")),
    frozenset(("T4", "T8")),
    frozenset(("T5", "P7")),
    frozenset(("T6", "P8")),
}


def _pairs(rows: list[dict]) -> set[frozenset]:
    return {frozenset((r["a"], r["b"])) for r in rows}


def _stats(text: str) -> dict:
    # Electrode and ReferenceElectrode rows, as the caps panel's Inspect passes them.
    rows = [r.split(",") for r in text.splitlines() if not r.startswith("Fiducial")]
    names = [r[4] for r in rows]
    world = np.array([[float(v) for v in r[1:4]] for r in rows])
    return caps.net_stats(names, world)


# ── tit.caps.net_stats ───────────────────────────────────────────────────────


def test_three_electrodes_on_one_point_are_three_collapsed_pairs() -> None:
    out = _stats(STALE)
    assert _pairs(out["collapsed"]) == STALE_PAIRS
    assert all(r["distance_mm"] == 0.0 for r in out["collapsed"])
    assert out["aliases"] == []


def test_the_spm12_synonyms_are_aliases_not_a_collapse() -> None:
    out = _stats(SPM12_LIKE)
    assert out["collapsed"] == []
    assert _pairs(out["aliases"]) == ALIASES_1020


def test_only_the_named_synonym_pairs_are_excused() -> None:
    # T3 and T8 are each half of an alias pair, but not of the same one: a collapse.
    out = caps.net_stats(["T3", "T8"], np.zeros((2, 3)))
    assert _pairs(out["collapsed"]) == {frozenset(("T3", "T8"))}
    assert out["aliases"] == []


def test_a_third_electrode_on_an_alias_point_is_still_collapsed() -> None:
    out = caps.net_stats(["T3", "T7", "X"], np.zeros((3, 3)))
    assert _pairs(out["aliases"]) == {frozenset(("T3", "T7"))}
    assert _pairs(out["collapsed"]) == {frozenset(("T3", "X")), frozenset(("T7", "X"))}


def test_a_net_file_with_a_collapse_is_reported_from_disk(tmp_path: Path) -> None:
    (tmp_path / "stale.csv").write_text(STALE)
    (tmp_path / "spm.csv").write_text(SPM12_LIKE)
    assert _pairs(caps.net_file_collapsed(tmp_path / "stale.csv")) == STALE_PAIRS
    assert caps.net_file_collapsed(tmp_path / "spm.csv") == []
    assert caps.net_file_collapsed(tmp_path / "absent.csv") == []


# ── job preflight ────────────────────────────────────────────────────────────


@pytest.fixture
def head(tmp_path: Path) -> Path:
    pm = get_path_manager(str(tmp_path))
    m2m = Path(pm.m2m("ernie"))
    positions = m2m / "eeg_positions"
    positions.mkdir(parents=True)
    (m2m / "ernie.msh").write_bytes(b"mesh")
    (positions / "Stale.csv").write_text(STALE)
    (positions / "SPM.csv").write_text(SPM12_LIKE)
    return positions


def _sim(net: str, *pairs: list[str]) -> dict:
    return {
        "subject_id": "ernie",
        "montages": [
            {"name": f"m{i}", "mode": "net", "eeg_net": net, "electrode_pairs": [p]}
            for i, p in enumerate(pairs)
        ],
    }


def _assert_reapply(found: list, csv_path: Path, n_pairs: int) -> None:
    assert len(found) == 1, [f.to_dict() for f in found]
    finding = found[0]
    assert finding.expected_path == str(csv_path)
    assert "Re-apply in EEG caps" in finding.how_to_fix
    assert f"{n_pairs} electrode pairs" in finding.what
    assert csv_path.name in finding.what


def test_a_sim_on_a_collapsed_net_is_refused_once_per_net(
    tmp_path: Path, head: Path
) -> None:
    # Two montages on the same stale net: one finding, not one per montage.
    found = preflight(
        "sim", _sim("Stale.csv", ["E4", "E5"], ["E6", "E1"]), str(tmp_path)
    )
    _assert_reapply(found, head / "Stale.csv", len(STALE_PAIRS))


def test_a_flex_mapped_montage_on_a_collapsed_net_is_refused(
    tmp_path: Path, head: Path
) -> None:
    config = _sim("Stale.csv", ["E4", "E5"])
    config["montages"][0]["mode"] = "flex_mapped"
    _assert_reapply(
        preflight("sim", config, str(tmp_path)), head / "Stale.csv", len(STALE_PAIRS)
    )


def test_a_sim_on_the_spm12_cap_passes(tmp_path: Path, head: Path) -> None:
    assert (
        preflight("sim", _sim("SPM.csv", ["T7", "T8"], ["T3", "Fz"]), str(tmp_path))
        == []
    )


def test_an_xyz_montage_needs_no_net(tmp_path: Path, head: Path) -> None:
    config = {
        "subject_id": "ernie",
        "montages": [
            {
                "name": "xyz",
                "mode": "flex_free",
                "eeg_net": "Stale.csv",
                "electrode_pairs": [[[0, 0, 95], [70, 0, 60]]],
            }
        ],
    }
    assert preflight("sim", config, str(tmp_path)) == []


def test_a_flex_mapping_onto_a_collapsed_net_is_refused(
    tmp_path: Path, head: Path
) -> None:
    config = {"subject_id": "ernie", "enable_mapping": True, "eeg_net": "Stale"}
    _assert_reapply(
        preflight("flex", config, str(tmp_path)), head / "Stale.csv", len(STALE_PAIRS)
    )
    config["eeg_net"] = "SPM.csv"
    assert preflight("flex", config, str(tmp_path)) == []


def test_the_skin_picture_net_alone_does_not_block_a_flex_run(
    tmp_path: Path, head: Path
) -> None:
    # Design: the skin-region picture only draws the net; the run's numbers never use it.
    config = {"subject_id": "ernie", "skin_visualization_net": "Stale.csv"}
    assert preflight("flex", config, str(tmp_path)) == []


def test_a_leadfield_on_a_collapsed_net_is_refused(tmp_path: Path, head: Path) -> None:
    found = preflight(
        "leadfield", {"subject_id": "ernie", "eeg_net": "Stale"}, str(tmp_path)
    )
    _assert_reapply(found, head / "Stale.csv", len(STALE_PAIRS))
    assert (
        preflight("leadfield", {"subject_id": "ernie", "eeg_net": "SPM"}, str(tmp_path))
        == []
    )


def test_an_ex_search_on_a_leadfield_of_a_collapsed_net_is_refused(
    tmp_path: Path, head: Path
) -> None:
    pm = get_path_manager(str(tmp_path))
    leadfields = Path(pm.leadfields("ernie"))
    leadfields.mkdir(parents=True)
    rois = Path(pm.rois("ernie"))
    rois.mkdir(parents=True)
    (rois / "target.csv").write_text("0,0,50\n")
    for net in ("Stale", "SPM"):
        (leadfields / f"ernie_leadfield_{net}.hdf5").write_bytes(b"h5")
    config = {
        "subject_id": "ernie",
        "leadfield_hdf": "ernie_leadfield_Stale.hdf5",
        "roi_name": "target",
    }
    found = preflight("ex", config, str(tmp_path))
    _assert_reapply(found, head / "Stale.csv", len(STALE_PAIRS))
    assert "regenerate this leadfield" in found[0].how_to_fix
    config["leadfield_hdf"] = "ernie_leadfield_SPM.hdf5"
    assert preflight("ex", config, str(tmp_path)) == []


# ── viewer / scene, caps Inspect, Blender montage ────────────────────────────


def test_read_net_refuses_a_collapsed_net_with_the_reapply_sentence(
    tmp_path: Path, head: Path
) -> None:
    pm = get_path_manager(str(tmp_path))
    with pytest.raises(build.SceneUnavailable, match="Re-apply in EEG caps") as err:
        build.read_net(pm, "ernie", "Stale.csv")
    assert "3 electrode pairs" in str(err.value)
    shown = build.read_net(pm, "ernie", "Stale.csv", allow_collapsed=True)
    assert [e["name"] for e in shown["electrodes"]] == [
        "E1",
        "E2",
        "E3",
        "E4",
        "E5",
        "E6",
    ]
    sound = build.read_net(pm, "ernie", "SPM.csv")
    assert [r["name"] for r in sound["reference"]] == ["Cz"]


def test_the_scene_route_refuses_and_inspect_still_shows_the_collapse(
    project,
) -> None:  # noqa: F811
    (project.positions / "Stale.csv").write_text(STALE)
    c = project.client
    refused = c.get("/api/scene/electrodes?subject=ernie&net=Stale.csv", headers=BEARER)
    assert refused.status_code == 404
    assert "Re-apply in EEG caps" in refused.json()["detail"]
    inspected = c.get("/api/caps/inspect?subject=ernie&net=Stale.csv", headers=BEARER)
    assert inspected.status_code == 200, inspected.text
    assert _pairs(inspected.json()["collapsed"]) == STALE_PAIRS


def test_the_blender_montage_export_refuses_a_collapsed_net(
    tmp_path: Path, head: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tit.blender import montage_publication as mp

    pm = get_path_manager(str(tmp_path))
    Path(pm.simulation("ernie", "sim1")).mkdir(parents=True)
    monkeypatch.setattr(mp, "get_path_manager", lambda: pm)
    monkeypatch.setattr(
        mp.be_utils,
        "load_simulation_config",
        lambda sid, sim: {"eeg_net": "Stale.csv", "electrode_pairs": [["E4", "E5"]]},
    )
    monkeypatch.setattr(mp, "export_scalp_stl_from_sim", lambda *a, **k: None)
    monkeypatch.setattr(mp, "export_gm_stl_from_sim", lambda *a, **k: None)
    with pytest.raises(ValueError, match="Re-apply in EEG caps"):
        mp.build_montage_publication_blend(
            subject_id="ernie", simulation_name="sim1", output_dir=str(tmp_path / "out")
        )
    assert mp._resolve_eeg_net_csv(subject_id="ernie", eeg_net_name="SPM.csv") == str(
        head / "SPM.csv"
    )
