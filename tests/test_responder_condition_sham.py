from __future__ import annotations

from pathlib import Path

import pytest

from tit.ml.responder.dataset import is_sham_condition, load_subject_table


def _write(p: Path, s: str) -> Path:
    p.write_text(s)
    return p


def test_is_sham_condition_case_insensitive() -> None:
    assert is_sham_condition("sham", sham_value="sham") is True
    assert is_sham_condition("ShAm", sham_value="sham") is True
    assert is_sham_condition("active", sham_value="sham") is False
    assert is_sham_condition(None, sham_value="sham") is False


def test_load_subject_table_allows_empty_simulation_name_for_sham(tmp_path: Path) -> None:
    csv_path = tmp_path / "subjects.csv"
    _write(
        csv_path,
        "subject_id,simulation_name,condition,response\n"
        "101,,sham,0\n"
        "102,simA,active,1\n",
    )
    rows = load_subject_table(
        csv_path,
        task="classification",
        target_col="response",
        condition_col="condition",
        sham_value="sham",
        require_target=True,
    )
    assert len(rows) == 2
    assert rows[0].subject_id == "101"
    assert rows[0].simulation_name == ""
    assert rows[0].condition == "sham"


def test_load_subject_table_rejects_empty_simulation_name_for_active(tmp_path: Path) -> None:
    csv_path = tmp_path / "subjects.csv"
    _write(
        csv_path,
        "subject_id,simulation_name,condition,response\n"
        "101,,active,0\n",
    )
    with pytest.raises(ValueError, match="Empty simulation_name"):
        load_subject_table(
            csv_path,
            task="classification",
            target_col="response",
            condition_col="condition",
            sham_value="sham",
            require_target=True,
        )

