"""Candidate snapping uses real assignment, checked against exhaustive enumeration.

Authored asymmetric positions make independent nearest-neighbour snapping collide.
Run inside the runtime: simnibs_python -m pytest tests/numerical/test_candidate_snap.py.
No FEM, project files or winner mappings are changed.
"""

import importlib
import itertools
from types import SimpleNamespace

import numpy as np
import pytest


def test_candidate_assignment_is_unique_and_candidate_specific(tmp_path, monkeypatch):
    from tit.opt import candidate_catalog
    from tit.tools import map_electrodes

    importlib.reload(map_electrodes)
    original = [[0, 0, 0], [0.2, 0, 0], [5, 1, 0], [9, 2, 0]]
    cap = np.array([[0, 0, 0], [2, 0, 0], [5, 0, 0], [10, 2, 0]], dtype=float)
    labels = ["A", "B", "C", "D"]
    seen = []

    def detail(pm, subject, kind, run, candidate_id):
        seen.append((subject, kind, run, candidate_id))
        return {
            "simulation_config": {
                "montages": [{"electrode_pairs": [original[:2], original[2:]]}]
            }
        }

    monkeypatch.setattr(candidate_catalog, "candidate_detail", detail)
    monkeypatch.setattr(
        map_electrodes, "read_csv_positions", lambda path: (cap, labels)
    )
    path = tmp_path / "cap.csv"
    path.write_text("fixture")
    pm = SimpleNamespace(
        project_dir=str(tmp_path), eeg_positions=lambda subject: str(tmp_path)
    )
    result = candidate_catalog.candidate_mapping(
        pm, "ernie", "run", "trial-not-winner", "cap.csv"
    )
    assert seen == [("ernie", "flex", "run", "trial-not-winner")]
    costs = [
        (
            sum(
                float(np.linalg.norm(np.array(point) - cap[j]))
                for point, j in zip(original, permutation)
            ),
            permutation,
        )
        for permutation in itertools.permutations(range(4))
    ]
    best_cost, best = min(costs)
    assert result["pairs"] == [
        [labels[best[0]], labels[best[1]]],
        [labels[best[2]], labels[best[3]]],
    ]
    assert sum(result["distances"]) == pytest.approx(best_cost)
    assert result["optimized_positions"] == original
    assert result["mapped_positions"] == cap[list(best)].tolist()
    assert list(tmp_path.iterdir()) == [path]
    # A cap cannot silently drop a carrier, and duplicate labels cannot be replayed.
    for invalid_cap, invalid_labels in [
        (cap[:3], labels[:3]),
        (cap, ["A", "A", "C", "D"]),
    ]:
        monkeypatch.setattr(
            map_electrodes,
            "read_csv_positions",
            lambda path: (invalid_cap, invalid_labels),
        )
        with pytest.raises(ValueError, match="enough distinct"):
            candidate_catalog.candidate_mapping(pm, "ernie", "run", "trial", "cap.csv")
    with pytest.raises(ValueError, match="filename"):
        candidate_catalog.candidate_mapping(pm, "ernie", "run", "trial", "../cap.csv")
    outside = tmp_path.parent / (tmp_path.name + "-outside.csv")
    outside.write_text("outside")
    try:
        (tmp_path / "escape.csv").symlink_to(outside)
        with pytest.raises(ValueError, match="escapes"):
            candidate_catalog.candidate_mapping(
                pm, "ernie", "run", "trial", "escape.csv"
            )
    finally:
        outside.unlink()
