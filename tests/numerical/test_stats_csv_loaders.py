"""The participants-CSV loaders agree with real pandas on every value pandas reads right.

What this pins
    ``GroupComparisonConfig.load_subjects`` and ``CorrelationConfig.load_subjects`` read with
    the standard ``csv`` module (they used ``pandas.read_csv`` until 2026-10-22). Real pandas
    is the second, independent reader here: for the same file, the loaders' effect sizes,
    weights, skipped rows and ids must equal what pandas parses. The one deliberate
    difference is pinned too: pandas' type inference turns an all-numeric id column
    ``001, 010`` into the integers 1 and 10 (``sub-1`` does not exist), the loaders keep the
    text, which is what ``pd.read_csv(..., dtype=str)`` reads.

Where the numbers come from
    Only from pandas reading the CSV text each test writes; nothing is retyped from the
    loaders.

How to run it
    In the image, where pandas is real (``tests/conftest.py`` mocks it, so this module swaps
    the real package in and puts the mock back afterwards)::

        simnibs_python -m pytest tests/numerical/test_stats_csv_loaders.py -q

    On a host without pandas every test skips with a printed reason.

Deliberately elsewhere
    The parsing rules on their own (``sub-``/``.0`` stripping, BOM, padded cells, error
    messages) are tests/test_stats_config.py::TestCSVLoaders, which runs on every host.
"""

from __future__ import annotations

import math
import sys

import pytest

from tit.stats.config import CorrelationConfig, GroupComparisonConfig


@pytest.fixture(scope="module")
def pd():
    """Real pandas for this module only; the host suite's mock is restored afterwards."""
    saved = {
        k: sys.modules.pop(k) for k in list(sys.modules) if k.split(".")[0] == "pandas"
    }

    def put_back():
        for key in [k for k in sys.modules if k.split(".")[0] == "pandas"]:
            del sys.modules[key]
        sys.modules.update(saved)

    try:
        import pandas
    except Exception as exc:  # noqa: BLE001 - any import failure means "not here"
        put_back()
        print(f"skipping: real pandas is not importable here ({exc})")
        pytest.skip("real pandas is not importable here (it is in the image)")
    if getattr(pandas, "__file__", None) is None:
        put_back()
        pytest.skip("pandas is still a mock, not the real package")
    yield pandas
    put_back()


def _write(tmp_path, name, text, encoding="utf-8"):
    path = tmp_path / name
    path.write_text(text, encoding=encoding)
    return str(path)


def test_correlation_values_and_skipped_rows_match_pandas(pd, tmp_path):
    path = _write(
        tmp_path,
        "corr.csv",
        "subject_id,simulation_name,effect_size,weight\n"
        "sub-101,L_Insula,0.25,2\n"
        ",L_Insula,0.5,1\n"
        "sub-LA,L_Insula,,1\n"
        "sub-CHN,L_Insula,NaN,1\n"
        "sub-ernie,L_Insula,-1.5e-1,\n"
        "sub-MNI152,Thalamus,3,N/A\n"
        "sub-007,Thalamus,12.75,0.5\n",
    )
    frame = pd.read_csv(path)
    kept = frame[frame["subject_id"].notna() & frame["effect_size"].notna()]

    subjects = CorrelationConfig.load_subjects(path)

    assert len(kept) == 4, "fixture: pandas keeps four rows"
    assert [s.effect_size for s in subjects] == kept["effect_size"].astype(
        float
    ).tolist()
    assert [s.weight for s in subjects] == kept["weight"].fillna(1.0).tolist()
    assert [s.subject_id for s in subjects] == [
        sid.removeprefix("sub-") for sid in kept["subject_id"]
    ]
    assert [s.simulation_name for s in subjects] == kept["simulation_name"].tolist()


@pytest.mark.parametrize("token", ["", "nan", "NaN", "NA", "N/A", "null", "None"])
def test_every_missing_token_pandas_knows_skips_the_row(pd, tmp_path, token):
    path = _write(
        tmp_path,
        "tokens.csv",
        "subject_id,simulation_name,effect_size\n"
        "sub-001,m,1.5\n"
        f"sub-002,m,{token}\n"
        "sub-003,m,2.5\n"
        "sub-004,m,4\n",
    )
    frame = pd.read_csv(path)
    assert math.isnan(frame["effect_size"][1]), f"pandas reads {token!r} as NaN"

    subjects = CorrelationConfig.load_subjects(path)

    assert [s.subject_id for s in subjects] == ["001", "003", "004"]


def test_zero_padded_ids_are_read_as_text_not_as_pandas_integers(pd, tmp_path):
    path = _write(
        tmp_path,
        "group.csv",
        "subject_id,simulation_name,response\n001,L_Insula,1\n010,L_Insula,0\n",
    )
    inferred = pd.read_csv(path)["subject_id"].tolist()
    as_text = pd.read_csv(path, dtype=str)["subject_id"].tolist()
    assert inferred == [1, 10], "pandas' inference is what lost the zeros"

    subjects = GroupComparisonConfig.load_subjects(path)

    assert [s.subject_id for s in subjects] == as_text == ["001", "010"]
    assert [s.response for s in subjects] == pd.read_csv(path)["response"].tolist()


def test_a_byte_order_mark_is_read_like_pandas_reads_it(pd, tmp_path):
    path = _write(
        tmp_path,
        "bom.csv",
        "subject_id,simulation_name,effect_size\nsub-1,a,0.1\nsub-2,b,0.2\nsub-3,c,0.3\n",
        encoding="utf-8-sig",
    )
    frame = pd.read_csv(path)
    assert list(frame.columns) == ["subject_id", "simulation_name", "effect_size"]

    subjects = CorrelationConfig.load_subjects(path)

    assert [s.effect_size for s in subjects] == frame["effect_size"].tolist()
    assert [s.simulation_name for s in subjects] == frame["simulation_name"].tolist()
