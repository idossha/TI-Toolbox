"""Unit tests for :mod:`tit.opt.leadfield_runner` (mocked ``LeadfieldGenerator``)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tit.opt import leadfield_runner
from tit.paths import get_path_manager


def _write_spec(tmp_path: Path, project_dir: str, **overrides) -> str:
    data = {
        "project_dir": project_dir,
        "subject_id": "001",
        "eeg_net": "GSN-HydroCel-185",
        "tissues": [1, 2],
        "overwrite": False,
    }
    data.update(overrides)
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(data))
    return str(spec_path)


@pytest.fixture(autouse=True)
def _reset_pm():
    from tit.paths import reset_path_manager

    yield
    reset_path_manager()


def test_generates_and_prints_expected_hdf5_path(tmp_path, monkeypatch, capsys):
    from tit.jobs import events

    emitted = MagicMock()
    monkeypatch.setattr(events, "emit_result", emitted)
    project_dir = str(tmp_path)
    expected = str(tmp_path / "leadfields" / "001_leadfield_GSN-HydroCel-185.hdf5")

    fake_generator = MagicMock()
    fake_generator.list_leadfields.return_value = []
    fake_generator.generate.return_value = expected

    fake_cls = MagicMock(return_value=fake_generator)
    monkeypatch.setattr(leadfield_runner, "LeadfieldGenerator", fake_cls)

    spec_path = _write_spec(tmp_path, project_dir)
    monkeypatch.setattr(sys, "argv", ["leadfield_runner.py", spec_path])

    with pytest.raises(SystemExit) as exc:
        leadfield_runner.main()
    assert exc.value.code == 0

    fake_cls.assert_called_once_with("001", electrode_cap="GSN-HydroCel-185")
    fake_generator.generate.assert_called_once_with(tissues=[1, 2])
    assert get_path_manager().project_dir == project_dir
    assert expected in capsys.readouterr().out
    emitted.assert_called_once_with({"leadfield_hdf": expected})


def test_skips_generation_when_leadfield_exists_and_overwrite_false(
    tmp_path, monkeypatch, capsys
):
    from tit.jobs import events

    emitted = MagicMock()
    monkeypatch.setattr(events, "emit_result", emitted)
    existing_path = str(tmp_path / "leadfields" / "001_leadfield_GSN-HydroCel-185.hdf5")
    fake_generator = MagicMock()
    fake_generator.list_leadfields.return_value = [
        ("GSN-HydroCel-185", existing_path, 0.5)
    ]

    fake_cls = MagicMock(return_value=fake_generator)
    monkeypatch.setattr(leadfield_runner, "LeadfieldGenerator", fake_cls)

    spec_path = _write_spec(tmp_path, str(tmp_path), overwrite=False)
    monkeypatch.setattr(sys, "argv", ["leadfield_runner.py", spec_path])

    with pytest.raises(SystemExit) as exc:
        leadfield_runner.main()
    assert exc.value.code == 0

    fake_generator.generate.assert_not_called()
    assert "already exists" in capsys.readouterr().out
    emitted.assert_called_once_with({"leadfield_hdf": existing_path, "skipped": True})


def test_regenerates_when_overwrite_true_even_if_existing(tmp_path, monkeypatch):
    existing_path = str(tmp_path / "leadfields" / "001_leadfield_GSN-HydroCel-185.hdf5")
    fake_generator = MagicMock()
    fake_generator.list_leadfields.return_value = [
        ("GSN-HydroCel-185", existing_path, 0.5)
    ]
    fake_generator.generate.return_value = existing_path

    fake_cls = MagicMock(return_value=fake_generator)
    monkeypatch.setattr(leadfield_runner, "LeadfieldGenerator", fake_cls)

    spec_path = _write_spec(tmp_path, str(tmp_path), overwrite=True)
    monkeypatch.setattr(sys, "argv", ["leadfield_runner.py", spec_path])

    with pytest.raises(SystemExit) as exc:
        leadfield_runner.main()
    assert exc.value.code == 0
    fake_generator.generate.assert_called_once_with(tissues=[1, 2])
