"""A leadfield is identified by the net in its SimNIBS filename, whatever the subject id.

What this pins (package p24, audit_ex.md #12, 2026-10-22): SimNIBS names a leadfield
``<subject>_leadfield_<cap>.hdf5`` -- ``TDCSLEADFIELD._lf_name`` in SimNIBS 4.6
``simnibs/simulation/sim_struct.py:2584`` joins ``basename(fnamehead)`` without its
extension, ``"leadfield"`` and ``basename(eeg_cap)`` without ``.csv``. Both listings
(``LeadfieldGenerator.list_leadfields`` and ``tit.catalog.list_leadfields``) then stripped
the subject id from the *net* half as well, so a subject whose id is a prefix of its net
lost the net: sid ``E`` read ``EG10-10_UI_Jurak_2007``, sid ``B`` read ``ioSemi-64-10-10``.
The Optimizer then said "No leadfield for this net yet" and the runner's ``overwrite=False``
skip regenerated a leadfield that already existed (hours under emulation).
``LeadfieldGenerator.generate`` returned the first ``*.hdf5`` of the folder, which can be
another net's; the plan's not-yet-generated ``output_dir`` was ``<net>.hdf5``, a file no run
writes.

Expected values: the filenames are built in this file from the SimNIBS rule quoted above
(:func:`_simnibs_name`, a second implementation, never ``tit.opt.leadfield``), and each
expected net is the cap the file was named after.

Reproduce: ``.venv/bin/python -m pytest tests/test_leadfield_net_naming.py -q``.
Deliberately elsewhere: real leadfield generation (FEM, forbidden on the host) and the
desktop's bare-name join (``desktop/src/renderer/pages/optimizer/nets.ts``).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tit import catalog
from tit.opt.leadfield import LeadfieldGenerator
from tit.paths import get_path_manager

#: (subject id, cap) -- the first three are ids that are a prefix of their cap's name.
CASES = [
    ("E", "EEG10-10_UI_Jurak_2007"),
    ("B", "BioSemi-64-10-10"),
    ("GSN", "GSN-HydroCel-256"),
    ("ernie", "EEG10-10_UI_Jurak_2007"),
    ("101", "GSN-HydroCel-185"),
]


def _simnibs_name(fnamehead: str, eeg_cap: str) -> str:
    """SimNIBS 4.6 ``TDCSLEADFIELD._lf_name``, re-stated from its source."""
    subid = os.path.splitext(os.path.basename(fnamehead))[0] + "_"
    cap = "_" + os.path.splitext(os.path.basename(eeg_cap))[0]
    return f"{subid}leadfield{cap}.hdf5"


def _project(root: Path, sid: str) -> object:
    (root / "dataset_description.json").write_text("{}")
    pm = get_path_manager(str(root))
    os.makedirs(pm.m2m(sid))
    # A finished head model (charm's mesh and final segmentation): subject_detail lists
    # leadfields only for a subject whose head model is done.
    Path(pm.m2m(sid), f"{sid}.msh").write_bytes(b"")
    Path(pm.m2m(sid), "final_tissues.nii.gz").write_bytes(b"")
    os.makedirs(pm.leadfields(sid))
    return pm


def _leadfield(pm, sid: str, net: str, size: int = 2048) -> str:
    path = os.path.join(
        pm.leadfields(sid), _simnibs_name(f"{pm.m2m(sid)}/{sid}.msh", f"{net}.csv")
    )
    Path(path).write_bytes(b"\0" * size)
    return path


@pytest.mark.parametrize("sid,net", CASES)
def test_generator_listing_reads_the_net_from_the_simnibs_filename(tmp_path, sid, net):
    pm = _project(tmp_path, sid)
    path = _leadfield(pm, sid, net)
    listed = LeadfieldGenerator(sid, electrode_cap=net).list_leadfields()
    assert [(name, p) for name, p, _ in listed] == [(net, path)]


@pytest.mark.parametrize("sid,net", CASES)
def test_catalog_listing_reads_the_net_from_the_simnibs_filename(tmp_path, sid, net):
    pm = _project(tmp_path, sid)
    path = _leadfield(pm, sid, net, size=4096)
    listed = catalog.list_leadfields(pm, sid)
    assert listed == [{"net": net, "path": path, "exists": True, "size_bytes": 4096}]
    # subject_detail's has_leadfields is the same net, spelled as the cap file.
    detail = catalog.subject_detail(pm, sid)
    assert detail["has_leadfields"] == [f"{net}.csv"]


@pytest.mark.parametrize("sid,net", CASES)
def test_runner_skips_an_existing_leadfield_when_overwrite_is_false(
    tmp_path, monkeypatch, capsys, sid, net
):
    from tit.opt import leadfield_runner

    pm = _project(tmp_path, sid)
    path = _leadfield(pm, sid, net)

    def regenerate(self, *args, **kwargs):  # pragma: no cover - the failure path
        raise AssertionError(f"regenerated the existing {path}")

    monkeypatch.setattr(LeadfieldGenerator, "generate", regenerate)
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "project_dir": str(tmp_path),
                "subject_id": sid,
                "eeg_net": net,
                "overwrite": False,
            }
        )
    )
    monkeypatch.setattr(sys, "argv", ["leadfield_runner", str(spec)])
    with pytest.raises(SystemExit) as exit_info:
        leadfield_runner.main()
    assert exit_info.value.code == 0
    assert f"Leadfield already exists for {sid}/{net}" in capsys.readouterr().out


@pytest.mark.parametrize("sid,net", CASES)
def test_generate_returns_the_file_simnibs_wrote_for_this_cap(
    tmp_path, monkeypatch, sid, net
):
    """Another net's leadfield in the folder, listed first, is not this run's result."""
    pm = _project(tmp_path, sid)
    other = _leadfield(pm, sid, "AAA-Other-Net")
    seen: dict = {}

    def run_simnibs(lf):
        seen["eeg_cap"] = lf.eeg_cap
        name = _simnibs_name(lf.fnamehead, lf.eeg_cap)
        Path(lf.pathfem, name).write_bytes(b"lf")

    simnibs = sys.modules["simnibs"]
    monkeypatch.setattr(simnibs, "run_simnibs", run_simnibs)
    monkeypatch.setattr(
        simnibs, "sim_struct", SimpleNamespace(TDCSLEADFIELD=SimpleNamespace)
    )
    real_glob = Path.glob

    def other_first(self, pattern):
        found = sorted(real_glob(self, pattern), key=lambda p: str(p) != other)
        return iter(found)

    monkeypatch.setattr(Path, "glob", other_first)

    result = LeadfieldGenerator(sid, electrode_cap=net).generate()

    expected = os.path.join(
        pm.leadfields(sid), _simnibs_name(f"{sid}.msh", f"{net}.csv")
    )
    assert seen["eeg_cap"] == os.path.join(pm.eeg_positions(sid), f"{net}.csv")
    assert str(result) == expected
    assert Path(other).is_file()  # the other net's leadfield is left alone


def test_generate_returns_the_simnibs_file_even_for_a_cap_given_with_csv(
    tmp_path, monkeypatch
):
    """``electrode_cap`` is a stem by contract; given ``x.csv`` anyway, generate() hands
    SimNIBS ``x.csv.csv``, SimNIBS writes ``<sid>_leadfield_x.csv.hdf5``, and that is the
    file generate() must return -- not raise because it looked for ``..._x.hdf5``."""
    pm = _project(tmp_path, "E")
    cap = "EEG10-10_UI_Jurak_2007.csv"

    def run_simnibs(lf):
        Path(lf.pathfem, _simnibs_name(lf.fnamehead, lf.eeg_cap)).write_bytes(b"lf")

    simnibs = sys.modules["simnibs"]
    monkeypatch.setattr(simnibs, "run_simnibs", run_simnibs)
    monkeypatch.setattr(
        simnibs, "sim_struct", SimpleNamespace(TDCSLEADFIELD=SimpleNamespace)
    )
    result = LeadfieldGenerator("E", electrode_cap=cap).generate()
    assert result.name == "E_leadfield_EEG10-10_UI_Jurak_2007.csv.hdf5"
    assert result.is_file()


def test_generate_raises_when_simnibs_wrote_no_leadfield_for_the_cap(
    tmp_path, monkeypatch
):
    pm = _project(tmp_path, "E")
    _leadfield(pm, "E", "BioSemi-64-10-10")  # some other net's file is present
    simnibs = sys.modules["simnibs"]
    monkeypatch.setattr(simnibs, "run_simnibs", lambda lf: None)
    monkeypatch.setattr(
        simnibs, "sim_struct", SimpleNamespace(TDCSLEADFIELD=SimpleNamespace)
    )
    with pytest.raises(FileNotFoundError, match="E_leadfield_EEG10-10_UI_Jurak_2007"):
        LeadfieldGenerator("E", electrode_cap="EEG10-10_UI_Jurak_2007").generate()


@pytest.mark.parametrize(
    "legacy,net",
    [
        ("GSN-HydroCel-185_leadfield", "GSN-HydroCel-185"),
        ("E_EEG10-10_leadfield", "EEG10-10"),
    ],
)
def test_older_suffix_names_keep_their_net(tmp_path, legacy, net):
    """``<net>_leadfield.hdf5`` and ``<sid>_<net>_leadfield.hdf5`` (older toolbox names, still
    used by the desktop config corpus) keep reading as their net."""
    pm = _project(tmp_path, "E")
    Path(pm.leadfields("E"), f"{legacy}.hdf5").write_bytes(b"x")
    assert [item["net"] for item in catalog.list_leadfields(pm, "E")] == [net]
    assert [n for n, _, _ in LeadfieldGenerator("E").list_leadfields()] == [net]


# ── plan ────────────────────────────────────────────────────────────────────

TOKEN = "lf-naming-token"


def _plan(project: Path, sid: str, net: str) -> dict:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from tit.server.app import create_app
    from tit.server.settings import ServerSettings

    client = TestClient(
        create_app(ServerSettings(project_dir=str(project), token=TOKEN)),
        base_url="http://127.0.0.1:8765",
    )
    resp = client.post(
        "/api/plan/leadfield",
        json={"config": {"subject_id": sid, "eeg_net": net}},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert resp.status_code == 200, resp.text
    (job,) = resp.json()["jobs"]
    return job


@pytest.mark.parametrize("sid,net", CASES)
def test_plan_names_the_file_the_run_will_write(tmp_path, sid, net):
    pm = _project(tmp_path, sid)
    job = _plan(tmp_path, sid, net)
    assert job["exists"] is False
    assert job["output_dir"] == os.path.join(
        pm.leadfields(sid), _simnibs_name(f"{sid}.msh", f"{net}.csv")
    )


@pytest.mark.parametrize("sid,net", CASES)
def test_plan_sees_the_existing_leadfield(tmp_path, sid, net):
    pm = _project(tmp_path, sid)
    path = _leadfield(pm, sid, net)
    job = _plan(tmp_path, sid, net)
    assert job["exists"] is True
    assert job["output_dir"] == path
