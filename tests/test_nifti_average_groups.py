"""NIfTI group averaging: trimmed, validated group labels and difference pairs that name groups (p23).

What this pins, for ``NiftiAverageConfig`` (``tit/stats/nifti_average_config.py``) and its runner
``python -m tit.stats.nifti_average``:

- a label typed with an edge space is the same group (``"Group1 "`` == ``"Group1"``); before,
  it was a third group and every average and difference was off;
- a difference pair of hyphenated labels resolves (``"post-op-pre-op"``); before, the runner
  split at the first hyphen, skipped the pair with a log warning and exited 0 without the map;
- a pair naming an absent group, a pair that splits two ways, a label that cannot be part of a
  file name (``x/y``: an errno crash at ``nib.save`` before) and an ``output_name`` that is not
  a folder name are refused by the config, so ``POST /api/validate/nifti_average`` says so;
- so are a pair of one group with itself (``A-A`` wrote an all-zero ``difference_A_minus_A``)
  and a pair typed twice (``A-B, A-B`` wrote one file twice and listed it twice in
  ``config.json``); ``A-B`` and ``B-A`` are two maps of opposite sign, both allowed.

Where the numbers come from: hand arithmetic over constant volumes a=1, b=3, c=10, d=20 --
mean(a, b) = 2, mean(c, d) = 15, 2 - 15 = -13 and 15 - 2 = 13. The runner reads them through
the real grouping loaders (``load_grouped_subjects_ti_toolbox`` -> ``load_group_data_ti_toolbox``);
only the single-file read and ``nibabel`` itself are replaced (nibabel is mocked on the host),
and what the runner hands ``nib.save`` is written as ``.npy`` bytes and read back. The same
arithmetic through real NIfTI files is ``tests/numerical/test_nifti_average_runner.py``.

Reproduce: ``.venv/bin/python -m pytest tests/test_nifti_average_groups.py -q -p no:cacheprovider``.
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

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

for _mod in ("scipy.ndimage", "scipy.stats"):
    sys.modules.setdefault(_mod, MagicMock())

from fastapi.testclient import TestClient  # noqa: E402

from tit.config_io import deserialize_config  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402
from tit.stats.nifti_average_config import NiftiAverageConfig  # noqa: E402

TOKEN = "nifti-groups-token"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
#: The constant value of each subject's volume (hand-picked; the means are hand-computed above).
VALUES = {"a": 1.0, "b": 3.0, "c": 10.0, "d": 20.0}
SHAPE = (4, 4, 4)


def _rows(groups: dict[str, str]) -> list[dict]:
    return [
        {"subject_id": sid, "simulation_name": "M1", "group": group}
        for sid, group in groups.items()
    ]


def _config(groups: dict[str, str], **overrides) -> dict:
    return {"output_name": "avg", "subjects": _rows(groups), **overrides}


# ── the config ─────────────────────────────────────────────────────────────


def test_an_edge_space_does_not_make_a_second_group() -> None:
    config = deserialize_config(
        NiftiAverageConfig,
        _config({"a": "Group1", "b": "Group1 ", "c": " Group2", "d": "Group2"}),
        strict=True,
    )
    assert [s.group for s in config.subjects] == [
        "Group1",
        "Group1",
        "Group2",
        "Group2",
    ]
    assert config.difference_pairs() == [("Group1", "Group2")]


def test_hyphenated_labels_resolve_to_the_pair_the_user_typed() -> None:
    config = deserialize_config(
        NiftiAverageConfig,
        _config(
            {"a": "pre-op", "b": "pre-op", "c": "post-op", "d": "post-op"},
            diff_pairs=["post-op-pre-op", " pre-op - post-op "],
        ),
        strict=True,
    )
    assert config.difference_pairs() == [("post-op", "pre-op"), ("pre-op", "post-op")]


def test_no_pairs_means_every_pair_alphabetically() -> None:
    config = NiftiAverageConfig(
        output_name="avg",
        subjects=deserialize_config(
            NiftiAverageConfig, _config({"a": "B", "b": "C", "c": "A"})
        ).subjects,
    )
    assert config.difference_pairs() == [("A", "B"), ("A", "C"), ("B", "C")]


def test_both_directions_of_a_pair_are_two_maps() -> None:
    config = deserialize_config(
        NiftiAverageConfig,
        _config({"a": "A", "b": "B"}, diff_pairs=["A-B", "B-A"]),
        strict=True,
    )
    assert config.difference_pairs() == [("A", "B"), ("B", "A")]


REFUSED = [
    (
        "self-pair",
        _config({"a": "A", "b": "B"}, diff_pairs=["A-A"]),
        "diff_pairs",
        "same group on both sides",
    ),
    (
        "hyphenated-self-pair",
        _config({"a": "pre-op", "b": "post-op"}, diff_pairs=["pre-op-pre-op"]),
        "diff_pairs",
        "same group on both sides",
    ),
    (
        "repeated-pair",
        _config({"a": "A", "b": "B"}, diff_pairs=["A-B", " A - B "]),
        "diff_pairs",
        "repeats an earlier pair",
    ),
    (
        "absent-group",
        _config({"a": "Group1", "b": "Group2"}, diff_pairs=["Group1-Group3"]),
        "diff_pairs",
        "does not name two of the groups",
    ),
    (
        "no-hyphen",
        _config({"a": "Group1", "b": "Group2"}, diff_pairs=["Group1"]),
        "diff_pairs",
        "does not name two of the groups",
    ),
    (
        "two-ways",
        _config({"a": "A", "b": "B-C", "c": "A-B", "d": "C"}, diff_pairs=["A-B-C"]),
        "diff_pairs",
        "more than one way",
    ),
    ("slash-label", _config({"a": "x/y", "b": "Group2"}), "subjects", "subjects[0]"),
    ("dot-label", _config({"a": "Group1", "b": ".."}), "subjects", "subjects[1]"),
    ("blank-label", _config({"a": "Group1", "b": "  "}), "subjects", "subjects[1]"),
    (
        "slash-output-name",
        _config({"a": "G1", "b": "G2"}, output_name="x/y"),
        "output_name",
        "invalid output_name",
    ),
    (
        "dotdot-output-name",
        _config({"a": "G1", "b": "G2"}, output_name=".."),
        "output_name",
        "invalid output_name",
    ),
]


@pytest.mark.parametrize(
    "data,field,phrase", [pytest.param(d, f, p, id=i) for i, d, f, p in REFUSED]
)
def test_the_config_refuses(data: dict, field: str, phrase: str) -> None:
    with pytest.raises(ValueError, match=None) as err:
        deserialize_config(NiftiAverageConfig, data, strict=True)
    assert phrase in str(err.value)


@pytest.fixture(scope="module")
def client(tmp_path_factory) -> TestClient:
    project = tmp_path_factory.mktemp("project")
    settings = ServerSettings(project_dir=str(project), token=TOKEN)
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8765")


@pytest.mark.parametrize(
    "data,field,phrase", [pytest.param(d, f, p, id=i) for i, d, f, p in REFUSED]
)
def test_validate_route_refuses_with_the_field(
    client: TestClient, data: dict, field: str, phrase: str
) -> None:
    resp = client.post(
        "/api/validate/nifti_average", json={"config": data}, headers=BEARER
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert [e["path"] for e in body["errors"]] == [field]
    assert phrase in body["errors"][0]["message"]


# ── the runner ─────────────────────────────────────────────────────────────


class _Writer:
    """Stands in for ``nibabel`` in the runner: an image is its array, a save writes ``.npy``."""

    @staticmethod
    def Nifti1Image(data, affine, header=None):  # noqa: N802 - nibabel's name
        return np.asarray(data)

    @staticmethod
    def save(img, path):
        with open(path, "wb") as fh:
            np.save(fh, img)


@pytest.fixture()
def run_average(tmp_path, monkeypatch):
    """Run ``python -m tit.stats.nifti_average``'s ``main`` on a config; return (code, dir, events)."""
    import tit.jobs.events as events_mod
    import tit.logger as logger_mod
    import tit.stats.nifti as nifti_mod
    import tit.stats.nifti_average as runner

    def load_one(subject_id, simulation_name, pattern, dtype=np.float32):
        img = SimpleNamespace(affine=np.eye(4), header={})
        return np.full(SHAPE, VALUES[subject_id], dtype=dtype), img, f"/in/{subject_id}"

    monkeypatch.setattr(nifti_mod, "load_subject_nifti_ti_toolbox", load_one)
    monkeypatch.setattr(
        nifti_mod,
        "nib",
        SimpleNamespace(
            Nifti1Image=lambda d, a, h: SimpleNamespace(affine=a, header=h)
        ),
    )
    monkeypatch.setattr(runner, "nib", _Writer)
    monkeypatch.delenv("TIT_JOB_ID", raising=False)
    project = tmp_path / "project"
    project.mkdir()

    def run(config: dict):
        events_file = tmp_path / "events.jsonl"
        events_file.unlink(missing_ok=True)
        monkeypatch.setenv("TIT_EVENTS_FILE", str(events_file))
        logger_mod._event_sinks.clear()
        events_mod._reset_state()
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({**config, "project_dir": str(project)}))
        monkeypatch.setattr(sys, "argv", ["tit.stats.nifti_average", str(cfg)])
        try:
            runner.main()
            code = 0
        except SystemExit as exc:
            code = exc.code
        finally:
            logger_mod._event_sinks.clear()
            events_mod._reset_state()
        events = [json.loads(line) for line in events_file.read_text().splitlines()]
        out = (
            project
            / "derivatives"
            / "ti-toolbox"
            / "nifti_average"
            / config["output_name"]
        )
        return code, out, events

    return run


def _volume(path: Path) -> np.ndarray:
    with open(path, "rb") as fh:
        return np.load(fh)


def test_a_trailing_space_label_averages_into_its_group(run_average) -> None:
    code, out, events = run_average(
        _config({"a": "Group1", "b": "Group1 ", "c": "Group2", "d": "Group2"})
    )
    assert code == 0
    written = sorted(p.name for p in out.iterdir())
    assert written == [
        "average_Group1.nii.gz",
        "average_Group2.nii.gz",
        "config.json",
        "difference_Group1_minus_Group2.nii.gz",
    ]
    np.testing.assert_array_equal(
        _volume(out / "average_Group1.nii.gz"), np.full(SHAPE, 2.0)
    )
    np.testing.assert_array_equal(
        _volume(out / "average_Group2.nii.gz"), np.full(SHAPE, 15.0)
    )
    np.testing.assert_array_equal(
        _volume(out / "difference_Group1_minus_Group2.nii.gz"), np.full(SHAPE, -13.0)
    )
    (result,) = [e for e in events if e["type"] == "result"]
    assert result["outputs"]["groups"] == ["Group1", "Group2"]
    assert result["outputs"]["differences"] == ["Group1 - Group2"]


def test_a_hyphenated_pair_writes_its_difference(run_average) -> None:
    code, out, events = run_average(
        _config(
            {"a": "pre-op", "b": "pre-op", "c": "post-op", "d": "post-op"},
            diff_pairs=["post-op-pre-op"],
        )
    )
    assert code == 0
    diffs = sorted(p.name for p in out.iterdir() if p.name.startswith("difference_"))
    assert diffs == ["difference_post-op_minus_pre-op.nii.gz"]
    np.testing.assert_array_equal(
        _volume(out / "difference_post-op_minus_pre-op.nii.gz"), np.full(SHAPE, 13.0)
    )
    recorded = json.loads((out / "config.json").read_text())
    assert recorded["differences"] == ["post-op - pre-op"]
    assert recorded["groups"] == {"pre-op": ["a", "b"], "post-op": ["c", "d"]}
    artifacts = {os.path.basename(e["path"]) for e in events if e["type"] == "artifact"}
    assert artifacts == {p.name for p in out.iterdir()}
