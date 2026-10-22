"""Ex and mEx jobs use only electrodes their leadfield has (2026-10-22, package c1_4).

What this pins
    * ``tit.jobs.preflight`` for kinds ``ex`` and ``mex``: every bucket or pool label that is
      not an electrode of the leadfield's net is one finding naming the labels, the net and the
      fix (the ``sim`` rule, ``_check_sim``, applied to the Ex family); ``POST /api/jobs``
      answers 422 "Missing inputs" and creates no record, ``POST /api/jobs/preflight`` lists it.
      Before this, ``_check_ex`` never looked at the labels and the job died inside the runner
      after loading the leadfield.
    * ``run_ex_search`` / ``run_m_ex_search`` refuse the same config with a ``ValueError``
      naming the net and every missing label *before* the engine (whose ``initialize`` loads the
      whole multi-GB leadfield) is built and before the run folder is created -- so a notebook
      caller gets the app's refusal.
    * The runner reads the names off the HDF5 attributes, read-only, without reading the field.

Where the expectations come from
    * Which labels a leadfield accepts is SimNIBS's rule, read in ``idossha/ti-toolbox:v3.1.1``
      on 2026-10-22: ``simnibs.utils.TI_utils.load_leadfield`` maps every entry of the
      ``tdcs_leadfield`` dataset's ``electrode_names`` attribute, the reference electrode
      included (index ``None``, which ``get_field`` treats as the zero-potential pole of the
      pair); any other label is a ``KeyError`` in ``get_field``. On Dataset 000 both leadfields
      hold the 75 ``Electrode`` rows of ``EEG10-10_UI_Jurak_2007.csv`` plus its
      ``ReferenceElectrode`` row ``Cz`` -- pinned on the real files by
      ``tests/numerical/test_leadfield_electrode_names_real.py``. So the net-CSV rule here is
      Electrode rows plus the ReferenceElectrode row; a ``Fiducial`` row is not an electrode.
    * The nets, labels and configs below are hand-written.

Reproduce: ``.venv/bin/python -m pytest tests/test_ex_electrodes_on_net.py -q -p no:cacheprovider``
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from tit.jobs.preflight import preflight
from tit.paths import get_path_manager

SID = "001"
NET = "EEG10-10_UI_Jurak_2007"
HDF = f"{SID}_leadfield_{NET}.hdf5"
#: The hand-written net: nine Electrode rows, a ReferenceElectrode (Cz) and a Fiducial (Nz).
ELECTRODES = ("Fp1", "F3", "F4", "C3", "C4", "P3", "P4", "O1", "O2")
REFERENCE = "Cz"
FIDUCIAL = "Nz"
EX_KEYS = ("e1_plus", "e1_minus", "e2_plus", "e2_minus")
MEX_KEYS = EX_KEYS + ("e3_plus", "e3_minus", "e4_plus", "e4_minus")


def _write_net(path: Path, electrodes=ELECTRODES, *, collapsed: bool = False) -> Path:
    """A SimNIBS net CSV; electrodes 10 mm apart, or all on one point when *collapsed*."""
    rows = [
        f"Electrode,{0 if collapsed else 10 * i},0,60,{name}"
        for i, name in enumerate(electrodes)
    ]
    rows.append(f"ReferenceElectrode,0,40,90,{REFERENCE}")
    rows.append(f"Fiducial,0,95,-30,{FIDUCIAL}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows) + "\n")
    return path


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """sub-001 with a head model, the net CSV, the leadfield file (empty) and an ROI CSV."""
    pm = get_path_manager(str(tmp_path))
    m2m = Path(pm.m2m(SID))
    m2m.mkdir(parents=True)
    (m2m / f"{SID}.msh").write_bytes(b"")
    _write_net(Path(pm.eeg_positions(SID)) / f"{NET}.csv")
    leadfields = Path(pm.leadfields(SID))
    leadfields.mkdir(parents=True)
    (leadfields / HDF).write_bytes(b"")
    rois = Path(pm.rois(SID))
    rois.mkdir(parents=True)
    (rois / "target.csv").write_text("0,0,0\n")
    return tmp_path


def _net_csv(project: Path) -> Path:
    return Path(get_path_manager(str(project)).eeg_positions(SID)) / f"{NET}.csv"


def _buckets(keys, fill: dict[str, list[str]]) -> dict:
    """Buckets for *keys*, each a distinct on-net electrode unless *fill* names its labels."""
    out: dict = {"_type": "BucketElectrodes"}
    for i, key in enumerate(keys):
        out[key] = fill.get(key, [ELECTRODES[i]])
    return out


def _pool(labels: list[str]) -> dict:
    return {"_type": "PoolElectrodes", "electrodes": labels}


def _config(kind: str, electrodes: dict) -> dict:
    """The wire config the desktop sends (tests/fixtures/desktop_configs/optimizer-ex)."""
    config = {
        "subject_id": SID,
        "leadfield_hdf": HDF,
        "roi_name": "target",
        "roi_names": None,
        "roi_atlas": None,
        "roi_coordinate_space": "subject",
        "roi_radius": 3,
        "electrodes": electrodes,
        "run_name": None,
        "n_jobs": 1,
        "symmetric_bucket": False,
        "symmetry_eeg_csv": None,
        "symmetry_pairing": "within_pairs",
    }
    if kind == "ex":
        config.update(total_current=2, current_step=0.5, channel_limit=None)
    else:
        config.update(current_mA=1)
    return config


def _label_finding(found) -> list:
    return [m for m in found if "electrode(s)" in m.what]


# -- preflight ---------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["ex", "mex"])
def test_labels_all_on_the_net_pass(project: Path, kind: str) -> None:
    keys = EX_KEYS if kind == "ex" else MEX_KEYS
    assert preflight(kind, _config(kind, _buckets(keys, {})), str(project)) == []
    pool = list(ELECTRODES)
    assert preflight(kind, _config(kind, _pool(pool)), str(project)) == []


def test_ex_buckets_off_the_net_are_one_finding_naming_each_label_once(
    project: Path,
) -> None:
    electrodes = _buckets(
        EX_KEYS,
        {
            "e1_plus": ["F3", "E200"],
            "e2_plus": ["C3", "T7"],
            "e2_minus": ["E200", "C4"],
        },
    )
    found = preflight("ex", _config("ex", electrodes), str(project))
    assert len(found) == 1, found
    what = found[0].what
    # Every missing label once, in the order the buckets list them; nothing on the net named.
    assert "E200, T7" in what
    assert what.count("E200") == 1
    for on_net in ("F3", "F4", "C3", "C4"):
        assert on_net not in what.replace(NET, "")
    assert NET in what
    assert found[0].expected_path == str(_net_csv(project))
    assert f"Pick electrodes from {NET}" in found[0].how_to_fix
    # The wire discriminator is not a label.
    assert "BucketElectrodes" not in what


def test_ex_pool_off_the_net_is_refused(project: Path) -> None:
    pool = ["Fp1", "E200", "F3", "O2", "T7"]
    found = preflight("ex", _config("ex", _pool(pool)), str(project))
    assert [m.expected_path for m in found] == [str(_net_csv(project))]
    assert "E200, T7" in found[0].what
    assert "PoolElectrodes" not in found[0].what


def test_mex_bucket_off_the_net_in_the_last_bucket_is_refused(project: Path) -> None:
    electrodes = _buckets(MEX_KEYS, {"e4_minus": ["E201"]})
    found = preflight("mex", _config("mex", electrodes), str(project))
    assert len(found) == 1, found
    assert "E201" in found[0].what and NET in found[0].what


def test_mex_pool_off_the_net_is_refused(project: Path) -> None:
    pool = [*ELECTRODES[:7], "E185", "E256"]
    found = preflight("mex", _config("mex", _pool(pool)), str(project))
    assert len(found) == 1, found
    assert "E185, E256" in found[0].what


@pytest.mark.parametrize("kind", ["ex", "mex"])
def test_the_reference_electrode_is_usable_and_a_fiducial_is_not(
    project: Path, kind: str
) -> None:
    """SimNIBS maps the reference into the leadfield index; a fiducial is no electrode."""
    keys = EX_KEYS if kind == "ex" else MEX_KEYS
    with_reference = _buckets(keys, {"e1_minus": [REFERENCE]})
    assert preflight(kind, _config(kind, with_reference), str(project)) == []
    with_fiducial = _buckets(keys, {"e1_minus": [FIDUCIAL]})
    found = preflight(kind, _config(kind, with_fiducial), str(project))
    assert len(found) == 1 and FIDUCIAL in found[0].what


def test_a_collapsed_net_gives_the_collapse_finding_and_the_label_finding(
    project: Path,
) -> None:
    _write_net(_net_csv(project), collapsed=True)
    electrodes = _buckets(EX_KEYS, {"e1_plus": ["E200"]})
    found = preflight("ex", _config("ex", electrodes), str(project))
    assert len(found) == 2, found
    assert "closer than" in found[0].what  # tit.caps.collapsed_summary's sentence
    assert "E200" in found[1].what and "E200" not in found[0].what
    assert [m.expected_path for m in found] == [str(_net_csv(project))] * 2


def test_no_net_csv_means_no_label_finding(project: Path) -> None:
    """Without the CSV the labels cannot be judged here; the runner's HDF5 check covers it."""
    _net_csv(project).unlink()
    electrodes = _buckets(EX_KEYS, {"e1_plus": ["E200"]})
    assert preflight("ex", _config("ex", electrodes), str(project)) == []


def test_a_missing_leadfield_and_off_net_labels_are_both_named(project: Path) -> None:
    pm = get_path_manager(str(project))
    (Path(pm.leadfields(SID)) / HDF).unlink()
    electrodes = _buckets(EX_KEYS, {"e1_plus": ["E200"]})
    found = preflight("ex", _config("ex", electrodes), str(project))
    assert [m.expected_path for m in found] == [
        str(Path(pm.leadfields(SID)) / HDF),
        str(_net_csv(project)),
    ]
    assert len(_label_finding(found)) == 1


def test_the_absolute_leadfield_path_the_desktop_sends_resolves_the_same_net(
    project: Path,
) -> None:
    pm = get_path_manager(str(project))
    config = _config("ex", _buckets(EX_KEYS, {"e1_plus": ["E200"]}))
    config["leadfield_hdf"] = str(Path(pm.leadfields(SID)) / HDF)
    found = preflight("ex", config, str(project))
    assert [m.expected_path for m in found] == [str(_net_csv(project))]


# -- the real routes ---------------------------------------------------------------------------

TOKEN = "c1-4-token"
BEARER = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(project: Path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from tit.jobs import bootstrap
    from tit.jobs.manager import JobManager
    from tit.jobs.spec import Cost
    from tit.server.app import create_app
    from tit.server.settings import ServerSettings

    monkeypatch.setattr("tit.surfer_settings.available_threads", lambda: 8)
    monkeypatch.setattr(
        "tit.surfer_settings.settings_path", lambda: project / "preferences.json"
    )
    manager = JobManager(str(project), budget=Cost(cpus=8, mem_gb=64))
    bootstrap.set_manager_for_testing(manager)
    try:
        yield TestClient(
            create_app(ServerSettings(project_dir=str(project), token=TOKEN)),
            base_url="http://127.0.0.1:8765",
        )
    finally:
        bootstrap.reset_manager()


@pytest.mark.parametrize("kind", ["ex", "mex"])
def test_submit_answers_422_and_preflight_lists_the_labels(
    client, project: Path, kind: str
) -> None:
    keys = EX_KEYS if kind == "ex" else MEX_KEYS
    config = _config(kind, _buckets(keys, {"e1_plus": ["E200"]}))
    body = {"kind": kind, "config": config, "subject_ids": [SID]}

    checked = client.post("/api/jobs/preflight", headers=BEARER, json=body)
    assert checked.status_code == 200, checked.text
    missing = checked.json()["missing"]
    assert [m["expected_path"] for m in missing] == [str(_net_csv(project))]
    assert "E200" in missing[0]["what"]

    refused = client.post("/api/jobs", headers=BEARER, json=body)
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"] == "Missing inputs"
    assert refused.json()["missing"] == missing
    assert client.get("/api/jobs", headers=BEARER).json() == []

    fine = dict(body, config=_config(kind, _buckets(keys, {})))
    assert client.post("/api/jobs/preflight", headers=BEARER, json=fine).json() == {
        "missing": []
    }


# -- the runners -------------------------------------------------------------------------------

#: What the HDF5 attribute holds for the hand-written net: the reference first, as SimNIBS
#: writes it (Dataset 000: Cz first, Fp1 moved to Cz's place).
LEADFIELD_NAMES = [REFERENCE, *ELECTRODES[1:], ELECTRODES[0]]


def _runner_pm(tmp_path: Path) -> MagicMock:
    pm = MagicMock()
    pm.logs.return_value = str(tmp_path / "logs")
    pm.leadfields.return_value = str(tmp_path / "leadfields")
    pm.ex_search_run.return_value = str(tmp_path / "out")
    pm.m_ex_search_run.return_value = str(tmp_path / "out")
    pm.rois.return_value = str(tmp_path / "rois")
    pm.m2m.return_value = str(tmp_path / "m2m")
    return pm


def _leadfield_file(tmp_path: Path) -> Path:
    path = tmp_path / "leadfields" / HDF
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


def _ex_config(electrodes):
    from tit.opt.config import ExConfig

    return ExConfig(
        subject_id=SID,
        leadfield_hdf=HDF,
        roi_name="target",
        electrodes=electrodes,
        total_current=2.0,
        current_step=0.5,
        run_name="run",
    )


def _mex_config(electrodes):
    from tit.opt.config import MExConfig

    return MExConfig(
        subject_id=SID,
        leadfield_hdf=HDF,
        roi_name="target",
        electrodes=electrodes,
        current_mA=1.0,
        run_name="run",
    )


def _run(kind: str, config, tmp_path: Path, names=LEADFIELD_NAMES):
    """Run the real runner with the engine, the report and the name reader replaced.

    Returns ``(outcome, engine_class, reader)``; *outcome* is the result or the exception.
    """
    module = "tit.opt.ex.ex" if kind == "ex" else "tit.opt.mex.mex"
    engine_name = "ExSearchEngine" if kind == "ex" else "MExSearchEngine"
    runner_name = "run_ex_search" if kind == "ex" else "run_m_ex_search"
    reader = MagicMock(return_value=list(names))
    with (
        patch(f"{module}.get_path_manager", return_value=_runner_pm(tmp_path)),
        patch(f"{module}.add_file_handler"),
        patch(f"{module}.{engine_name}") as engine_cls,
        patch(
            f"{module}.process_and_save",
            return_value={"config_json_path": "c.json", "csv_path": "r.csv"},
        ),
        patch(f"{module}._write_report"),
        patch("tit.opt.ex.ex.leadfield_electrode_names", reader, create=True),
    ):
        engine_cls.return_value.run.return_value = {"m1": {"v": 1.0}}
        import importlib

        runner = getattr(importlib.import_module(module), runner_name)
        try:
            outcome = runner(config)
        except ValueError as exc:
            outcome = exc
    return outcome, engine_cls, reader


@pytest.mark.parametrize("mode", ["bucket", "pool"])
def test_ex_runner_refuses_labels_off_the_leadfield_before_loading_it(
    tmp_path: Path, mode: str
) -> None:
    from tit.opt.config import ExConfig

    lf = _leadfield_file(tmp_path)
    if mode == "bucket":
        electrodes = ExConfig.BucketElectrodes(
            e1_plus=["F3", "E200"], e1_minus=["F4"], e2_plus=["C3"], e2_minus=["T7"]
        )
    else:
        electrodes = ExConfig.PoolElectrodes(electrodes=["F3", "E200", "F4", "T7"])
    outcome, engine_cls, reader = _run("ex", _ex_config(electrodes), tmp_path)
    assert isinstance(outcome, ValueError), outcome
    assert str(outcome).startswith(
        f"ex-search electrodes not in the leadfield of {NET}: E200, T7"
    )
    reader.assert_called_once_with(str(lf))
    engine_cls.assert_not_called()  # initialize() is what loads the field
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("mode", ["bucket", "pool"])
def test_mex_runner_refuses_labels_off_the_leadfield_before_loading_it(
    tmp_path: Path, mode: str
) -> None:
    from tit.opt.config import MExConfig

    lf = _leadfield_file(tmp_path)
    if mode == "bucket":
        labels = {key: [ELECTRODES[i]] for i, key in enumerate(MEX_KEYS)}
        labels["e4_minus"] = ["E201"]
        electrodes = MExConfig.BucketElectrodes(**labels)
    else:
        electrodes = MExConfig.PoolElectrodes(
            electrodes=[*ELECTRODES[:7], "E201", "E202"]
        )
    outcome, engine_cls, reader = _run("mex", _mex_config(electrodes), tmp_path)
    assert isinstance(outcome, ValueError), outcome
    expected = "E201" if mode == "bucket" else "E201, E202"
    assert str(outcome).startswith(
        f"m-ex-search electrodes not in the leadfield of {NET}: {expected}"
    )
    reader.assert_called_once_with(str(lf))
    engine_cls.assert_not_called()
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("kind", ["ex", "mex"])
def test_runner_accepts_the_reference_electrode(tmp_path: Path, kind: str) -> None:
    from tit.opt.config import ExConfig, MExConfig

    _leadfield_file(tmp_path)
    if kind == "ex":
        config = _ex_config(
            ExConfig.BucketElectrodes(
                e1_plus=["F3"], e1_minus=[REFERENCE], e2_plus=["C3"], e2_minus=["C4"]
            )
        )
    else:
        labels = {key: [ELECTRODES[i]] for i, key in enumerate(MEX_KEYS)}
        labels["e1_minus"] = [REFERENCE]
        config = _mex_config(MExConfig.BucketElectrodes(**labels))
    outcome, engine_cls, reader = _run(kind, config, tmp_path)
    assert not isinstance(outcome, ValueError), outcome
    reader.assert_called_once()
    engine_cls.return_value.initialize.assert_called_once()


@pytest.mark.parametrize("kind", ["ex", "mex"])
def test_runner_leaves_a_missing_leadfield_to_the_engine(
    tmp_path: Path, kind: str
) -> None:
    """No file, nothing to read: the engine's load raises FileNotFoundError naming it."""
    from tit.opt.config import ExConfig, MExConfig

    if kind == "ex":
        config = _ex_config(
            ExConfig.PoolElectrodes(electrodes=["E200", "F3", "F4", "C3"])
        )
    else:
        config = _mex_config(MExConfig.PoolElectrodes(electrodes=[*ELECTRODES[:8]]))
    outcome, engine_cls, reader = _run(kind, config, tmp_path)
    reader.assert_not_called()
    engine_cls.assert_called_once()


@pytest.mark.parametrize("kind", ["ex", "mex"])
def test_runner_leaves_an_empty_name_list_to_the_engine(
    tmp_path: Path, kind: str
) -> None:
    """A name list that reads empty judges nothing (no real leadfield has one; SimNIBS's
    load refuses it). It is what the host suite's h5py stand-in reads, so this keeps
    synthetic-leadfield chain tests (tests/test_ex_desktop_runner_chain.py) running."""
    from tit.opt.config import ExConfig, MExConfig

    _leadfield_file(tmp_path)
    if kind == "ex":
        config = _ex_config(
            ExConfig.PoolElectrodes(electrodes=["E200", "F3", "F4", "C3"])
        )
    else:
        config = _mex_config(
            MExConfig.PoolElectrodes(electrodes=["E200", *ELECTRODES[:7]])
        )
    outcome, engine_cls, reader = _run(kind, config, tmp_path, names=[])
    assert not isinstance(outcome, ValueError), outcome
    reader.assert_called_once()
    engine_cls.assert_called_once()


# -- the HDF5 name reader ----------------------------------------------------------------------


class _NoFieldRead:
    """The ``tdcs_leadfield`` dataset: attributes readable, the field itself never."""

    def __init__(self, names):
        self.attrs = {"electrode_names": names, "reference_electrode": REFERENCE}

    def __getitem__(self, item):
        raise AssertionError(f"the leadfield field was read ({item!r})")

    def __array__(self, *args, **kwargs):
        raise AssertionError("the leadfield field was converted to an array")


def test_reader_takes_the_names_from_the_attributes_read_only(monkeypatch) -> None:
    opened: list[tuple[str, str]] = []
    names = np.array([REFERENCE, b"F3", "Fp1"], dtype=object)

    class _File:
        def __init__(self, path, mode="r"):
            opened.append((str(path), mode))

        def __enter__(self):
            return {
                "mesh_leadfield": {
                    "leadfields": {"tdcs_leadfield": _NoFieldRead(names)}
                }
            }

        def __exit__(self, *exc):
            return False

    monkeypatch.setitem(sys.modules, "h5py", types.SimpleNamespace(File=_File))
    from tit.opt.ex.ex import leadfield_electrode_names

    assert leadfield_electrode_names("/x/lf.hdf5") == [REFERENCE, "F3", "Fp1"]
    assert opened == [("/x/lf.hdf5", "r")]
