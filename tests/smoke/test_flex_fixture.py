"""Fixture verifier rejects incomplete/corrupt results; no FEM or dataset writes."""

import json
import sys

import pytest

from tests.smoke.prepare_flex_fixture import main, verify_result


def _result(tmp_path, *, objective=-0.25, success=True, xyz=None, channels=None):
    # Synthetic unit data is confined to pytest's temporary directory. The actual
    # fixture command never writes these result files; only the real runner does.
    (tmp_path / "flex_meta.json").write_text(
        json.dumps({"result": {"success": success, "best_value": objective}})
    )
    (tmp_path / "electrode_positions.json").write_text(
        json.dumps(
            {
                "optimized_positions": (
                    xyz
                    if xyz is not None
                    else [[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11, 12]]
                ),
                "channel_array_indices": (
                    channels
                    if channels is not None
                    else [[0, 0], [0, 1], [1, 0], [1, 1]]
                ),
            }
        )
    )


def test_success_reports_measured_values(tmp_path):
    _result(tmp_path)
    result = verify_result(tmp_path)
    assert result["objective"] == -0.25
    assert result["xyz"][3] == [10, 11, 12]
    assert result["channels"] == [[0, 0], [0, 1], [1, 0], [1, 1]]


@pytest.mark.parametrize(
    "changes",
    [
        {"success": False},
        {"objective": float("inf")},
        {"objective": float("nan")},
        {"xyz": [[1, 2, 3]]},
        {"xyz": [[1, 2, 3]] * 3 + [[1, 2, float("nan")]]},
        {"channels": [[0, 0], [0, 0], [1, 0], [1, 1]]},
    ],
)
def test_rejects_unusable_results(tmp_path, changes):
    _result(tmp_path, **changes)
    with pytest.raises(ValueError):
        verify_result(tmp_path)


def test_refuses_original_project_before_docker_or_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "fixture",
            "--container",
            "unused",
            "--project-host",
            str(tmp_path),
            "--source-project",
            str(tmp_path),
            "--run-name",
            "smoke-unit",
            "--execute",
        ],
    )
    with pytest.raises(ValueError, match="separate"):
        main()
    assert list(tmp_path.iterdir()) == []
