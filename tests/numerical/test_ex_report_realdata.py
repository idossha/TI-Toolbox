"""Every ex-search run in Dataset 000 gets a report whose facts are the run's own.

Pins (2026-10-22), on the real files (read-only): for each ``derivatives/SimNIBS/sub-*/ex-search/*``
run that holds ``final_output.csv`` and ``run_config.json``,
``create_ex_search_report(dataset, sid, run, out_dir=tmp)`` writes a page with the verdict, winner,
results, target and technical sections, whose headline montage is a highest-``Composite_Index``
row of the CSV and whose montage count is the CSV's row count. Where a run's leadfield log exists,
the electrode geometry on the page is the one in the log that wrote the run's HDF5 (sub-101 also
holds later GSN-185/BioSemi-128 attempts, the newest a BioSemi one), and an older run whose
``run_config.json`` lacks the ROI definition (sub-101 20260914_112857) is not called a sphere.

Where the numbers come from: the expected winner, count and geometry are read in this file with
``csv`` and a regex over the log, not through ``tit``. The dataset is never written: the mtimes of
every file the report reads are compared before and after.

Real-data, gated: ``export TIT_DATASET_000=/path/to/dataset000`` (skips with a reason otherwise).
Needs only the report stack (real nibabel for atlas label names), so it runs on a bare host
(``host_numerical``) and in the image:
``TIT_DATASET_000=... .venv/bin/python -m pytest tests/numerical/test_ex_report_realdata.py -q``.
"""

from __future__ import annotations

import csv
import os
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.host_numerical

_DATASET = os.environ.get("TIT_DATASET_000", "")
_SIMNIBS = Path(_DATASET) / "derivatives" / "SimNIBS"
_SKIP = not _DATASET or not _SIMNIBS.is_dir()
_REASON = (
    "skipping: TIT_DATASET_000 unset or not a Dataset 000 copy (no derivatives/SimNIBS)"
)


def _runs() -> list[Path]:
    return sorted(
        run
        for run in _SIMNIBS.glob("sub-*/ex-search/*")
        if (run / "final_output.csv").is_file() and (run / "run_config.json").is_file()
    )


def _mtimes(paths: list[Path]) -> dict[Path, int]:
    out = {}
    for root in paths:
        if root.is_file():
            out[root] = root.stat().st_mtime_ns
        elif root.is_dir():
            out.update(
                {p: p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}
            )
            out[root] = root.stat().st_mtime_ns
    return out


def _montage_name(cell: str) -> str:
    """``AF7_AFz <> CP6_P10_I1-1.6mA_I2-0.4mA`` -> ``AF7–AFz ‖ CP6–P10`` (the page's spelling)."""
    bare = re.sub(r"_I1?-[\d.]+mA(_I2-[\d.]+mA)?$", "", cell.strip())
    return " ‖ ".join("–".join(pair.strip().split("_", 1)) for pair in bare.split("<>"))


def _hdf5_log_facts(leadfields: Path, hdf: str) -> tuple[str, str | None] | None:
    """``("ellipse 10×10 mm, gel 4 mm", ", isotropic")`` from the log that names *hdf* (SimNIBS
    writes the HDF5 path when the leadfield finishes), read with plain regexes."""
    for log in sorted(leadfields.glob("simnibs_simulation_*.log")):
        text = log.read_text(errors="replace")
        if hdf not in text:
            continue
        shape = re.search(r"\nshape: (\S+)", text)
        dims = re.search(r"\ndimensions: \[(\d+), (\d+)\]", text)
        gel = re.search(r"\nthickness:\s*\[(\d+)\]", text)
        if shape and dims and gel:
            cond = (
                ", anisotropic"
                if "Using anisotropic" in text
                else ", isotropic" if "Using isotropic conductivities" in text else None
            )
            return f"{shape[1]} {dims[1]}×{dims[2]} mm, gel {gel[1]} mm", cond
    return None


def _section(html: str, sid: str) -> str:
    return re.sub(
        r"<[^>]+>", " ", html.split(f'id="{sid}"', 1)[1].split("</section>", 1)[0]
    )


@pytest.mark.skipif(_SKIP, reason=_REASON)
def test_every_dataset_ex_run_reports_its_own_best_row_and_facts(tmp_path, monkeypatch):
    import json

    from tit.reporting.generators.ex_search import create_ex_search_report

    monkeypatch.delenv("TIT_EVENTS_FILE", raising=False)
    runs = _runs()
    assert runs, f"no ex-search run with final_output.csv under {_SIMNIBS}"
    read = runs + [run.parent.parent / "leadfields" for run in runs]
    before = _mtimes(read)
    checked_geometry = 0

    for run in runs:
        sid = run.parent.parent.name.removeprefix("sub-")
        with open(run / "final_output.csv", newline="") as f:
            rows = list(csv.DictReader(f))
        best = max(float(r["Composite_Index"]) for r in rows)
        winners = {
            _montage_name(r["Montage"])
            for r in rows
            if float(r["Composite_Index"]) == best
        }

        path = create_ex_search_report(
            _DATASET, sid, run, out_dir=tmp_path / sid / run.name
        )
        html = path.read_text(encoding="utf-8")
        assert path.parent == tmp_path / sid / run.name
        for section in ("verdict", "winner", "results", "target", "technical"):
            assert f'id="{section}"' in html, (run, section)
        head = re.search(r'<h2 id="verdict-h">(.*?) leads ([\d,]+) montages</h2>', html)
        assert head, run
        assert head[1] in winners, (run, head[1], winners)
        assert int(head[2].replace(",", "")) == len(rows)
        assert f"<dt>Montages</dt><dd><b>{len(rows):,}</b>" in html

        cfg = json.loads((run / "run_config.json").read_text())
        facts = _hdf5_log_facts(
            run.parent.parent / "leadfields", Path(cfg["leadfield_hdf"]).name
        )
        winner = _section(html, "winner")
        if facts:
            checked_geometry += 1
            geometry, cond = facts
            assert geometry in winner, (run, geometry)
            if cond:  # the Leadfield row: "<hdf5> , isotropic" once tags are stripped
                assert re.search(rf"\.hdf5\s*{cond}", winner), (run, cond)
        assert "?" not in winner and "at most 0 mA" not in winner
        if not (run / "roi.tetravox.json").is_file() and "roi_names" not in cfg:
            assert "sphere" not in _section(html, "target"), run

    assert (
        checked_geometry
    ), "no run's leadfield log was found to check the geometry against"
    assert _mtimes(read) == before
