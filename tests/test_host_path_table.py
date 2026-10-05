"""Pure host <-> container path rules in ``tit.host_path`` (2026-10-05).

Pins: a Windows host path is joined in its own separator, compared case-insensitively, and
``/mnt/000x`` is never taken for ``/mnt/000``. The cases live in ``tests/fixtures/host_paths.json``
(groundTruth: authored), which ``desktop/tests/unit/paths.test.ts`` reads too, so Python and
TypeScript cannot drift. No fastapi, no Docker: CI runs this file on windows-latest as well.
Reproduce: ``pytest tests/test_host_path_table.py``. Route behaviour is in test_host_path.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tit.host_path import (
    bind_mount,
    flavour,
    get_host_project_dir,
    project_dir_name,
    to_container,
    to_host,
)

TABLE = json.loads(
    (Path(__file__).parent / "fixtures" / "host_paths.json").read_text(encoding="utf-8")
)


def test_table_has_cases_to_check():
    assert all(TABLE[key] for key in ("to_host", "to_container", "project_dir_name"))


@pytest.mark.parametrize("case", TABLE["to_host"], ids=lambda c: c["why"])
def test_to_host(case):
    got = to_host(case["container"], case["container_root"], case["host_root"])
    assert got == case["expected"]


@pytest.mark.parametrize("case", TABLE["to_container"], ids=lambda c: c["why"])
def test_to_container(case):
    got = to_container(case["host"], case["host_root"], case["container_root"])
    assert got == case["expected"]


@pytest.mark.parametrize("case", TABLE["project_dir_name"], ids=lambda c: c["host_dir"])
def test_project_dir_name(case):
    if case["expected"] is None:
        with pytest.raises(ValueError, match="no name"):
            project_dir_name(case["host_dir"])
    else:
        assert project_dir_name(case["host_dir"]) == case["expected"]


@pytest.mark.parametrize(
    "raw,joined",
    [
        ("C:\\Users\\me\\proj", "C:\\Users\\me\\proj\\derivatives\\qsiprep"),
        ("D:/data/proj", "D:\\data\\proj\\derivatives\\qsiprep"),
        ("\\\\server\\share\\proj", "\\\\server\\share\\proj\\derivatives\\qsiprep"),
        ("/Users/me/proj", "/Users/me/proj/derivatives/qsiprep"),
    ],
)
def test_flavour_joins_in_host_separator(raw, joined):
    p = flavour(raw)
    assert p.is_absolute()
    assert str(p / "derivatives" / "qsiprep") == joined


class TestGetHostProjectDir:
    def test_returns_env(self, monkeypatch):
        monkeypatch.setenv("LOCAL_PROJECT_DIR", "/host/proj")
        assert get_host_project_dir() == "/host/proj"

    def test_missing_raises(self, monkeypatch):
        monkeypatch.delenv("LOCAL_PROJECT_DIR", raising=False)
        with pytest.raises(ValueError, match="LOCAL_PROJECT_DIR"):
            get_host_project_dir()

    def test_relative_raises(self, monkeypatch):
        monkeypatch.setenv("LOCAL_PROJECT_DIR", "proj")
        with pytest.raises(ValueError, match="absolute"):
            get_host_project_dir()

    def test_windows_path_passes_through(self, monkeypatch):
        monkeypatch.setenv("LOCAL_PROJECT_DIR", "C:\\Users\\me\\proj")
        assert get_host_project_dir() == "C:\\Users\\me\\proj"


@pytest.mark.parametrize(
    "source,target,readonly,spec",
    [
        (
            "C:\\Users\\me\\proj",
            "/data",
            True,
            "type=bind,source=C:\\Users\\me\\proj,target=/data,readonly",
        ),
        (
            "/Users/me/my proj",
            "/mnt/my proj",
            False,
            "type=bind,source=/Users/me/my proj,target=/mnt/my proj",
        ),
        # Docker parses --mount as CSV, so a comma in a path must be quoted (RFC 4180).
        ("/data/a,b", "/out", False, 'type=bind,"source=/data/a,b",target=/out'),
    ],
)
def test_bind_mount(source, target, readonly, spec):
    assert bind_mount(source, target, readonly=readonly) == ["--mount", spec]
