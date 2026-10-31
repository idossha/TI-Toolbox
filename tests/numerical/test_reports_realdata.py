"""Every Dataset 000 simulation, flex and ex run rebuilds its report, and the facts on it are physically and logically right.

Pins (2026-10-22, package p25), read-only on the real files; reports are written to ``tmp_path``
with ``create_*(out_dir=tmp_path)`` and nothing is re-simulated:

* **Simulation outputs** (every TI ``Simulations/*`` with a config; carrier-only runs have
  no envelope and are left out, and the tests skip when none is left): the grey-matter subject
  ``TI_max`` NIfTI is 3-D on the m2m T1 grid (same shape and affine, which the report figure
  needs), finite, >= 0, with > 1000 non-zero voxels; ``median <= p99.9 <= max``; the envelope
  obeys TI_max <= 2 min(|E1|, |E2|) (Grossman 2017), checked as ``p99.9(TI) <= 1.05 * 2 *
  min(carrier p99.9)`` with the carriers' grey-matter ``magnE`` 99.9th percentiles from SimNIBS's
  own ``fields_summary.txt`` (measured ratio 0.28-0.89; the 5 % absorbs mesh-vs-voxel
  percentiles; a percentile of a minimum is at most the minimum of the percentiles). Each
  carrier's p99.9 per mA lies in [0.01, 3] V/m. MNI volumes, when present, are 182x218x182(x1)
  at 1 mm. Do not assert TI_max <= max(|E1|, |E2|): aligned equal fields give 2|E|.
* **The report's numbers and hot spot** (``collect`` + ``to_mni``): the median and p99.9 equal
  those computed here with numpy from the same file, and no raw maximum is recorded (2026-10-31);
  the voxel at ``hotspot_world`` is at or above the p99.9 and charm's ``final_tissues`` labels it
  grey matter (2); in MNI the hot spot is inside
  the MNI box [-90, 90] x [-126, 90] x [-72, 108] and ``final_tissues_MNI`` labels it 1 or 2
  (5 GM + 1 WM boundary voxel measured). In the image, ``to_mni`` is within 2 mm of SimNIBS's
  ``subject2mni_coords``.
* **The simulation page** (image only: the figure needs matplotlib): no TOC anchor without a
  section body; no ``None``/``nan``/``Infinity``/``[[``/``? mm`` in the text outside scripts,
  styles and code blocks; under ``SIZE_BUDGET``; the headline is the grey p99.9 computed here;
  ``id="field"`` holds an ``<img>``; the carrier table has one row per pair whose 99.9 % column
  is SimNIBS's; the total current is the sum of the pairs' currents. Before 2026-10-22 this
  crashed for both flex-free (XYZ) simulations.
* **Flex pages**: the same text checks; one optimiser-run row per ``all_values`` entry; the
  Currents tile is the accepted candidate's ch1/ch2 currents (the ``current_split`` when it is
  recorded); the position table is ``electrode_positions.json`` in channel order, channel k's
  electrodes named Ek+ (array 0) and Ek-; the four centres are distinct and >= 0.9 x
  ``min_electrode_distance`` apart.
* **Flex -> simulation**: a simulation named after a flex run of the same subject simulated
  exactly the run's ``optimized_positions`` (pairs in ``channel_array_indices`` order) at its
  accepted currents.
* **Ex pages**: the same text checks (winner, counts and leadfield facts are
  ``tests/numerical/test_ex_report_realdata.py``; CSV identities ``tests/test_ex_realdata_csv.py``).

Where the numbers come from: the NIfTIs (numpy over nibabel), SimNIBS's ``fields_summary.txt``
and logs (regex), charm's tissue labels and SimNIBS's ``subject2mni_coords``, the flex
manifests and candidate CSVs (json/csv): never the report's own output. Deliberately elsewhere:
flex manifest/candidate invariants (``tests/test_flex_realdata_runs.py``), electrode placement
(``tests/test_sim_electrode_placement_realdata.py``).

Gated: ``export TIT_DATASET_000=/path/to/Dataset000`` (read-only; an mtime listing of every
file under the folders read is compared before and after); skips with the reason otherwise.
The ``host_numerical`` tests need only numpy/nibabel/PIL; the page and SimNIBS tests run in the
image::

    docker run --rm --platform linux/amd64 --entrypoint bash -v "$PWD":/ti-toolbox \\
      -w /ti-toolbox -v /path/to/000:/data/000:ro -e TIT_DATASET_000=/data/000 \\
      idossha/ti-toolbox:v3.1.1 -lc \\
      'simnibs_python -m pytest tests/numerical/test_reports_realdata.py -q -p no:cacheprovider'
"""

from __future__ import annotations

import csv
import html as htmllib
import importlib
import json
import math
import os
import re
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = os.environ.get("TIT_DATASET_000", "")
_SIMNIBS = Path(ROOT) / "derivatives" / "SimNIBS"
real_data = pytest.mark.skipif(
    not ROOT or not _SIMNIBS.is_dir(),
    reason="skipping: TIT_DATASET_000 is unset or has no derivatives/SimNIBS "
    "(export TIT_DATASET_000=/path/to/Dataset000, read-only)",
)

#: Mesh percentiles (SimNIBS, element-weighted) and voxel percentiles (resampled NIfTI) differ
#: by a few percent; the physical bound itself has no slack.
VOXEL_VS_MESH = 1.05
#: The report takes percentiles of the volume as float32 (its dtype on disk), this file in
#: float64: NumPy 2.3's interpolation then differs by 3e-6 relative (sub-101 p99.9).
FLOAT32_PERCENTILE = 1e-5
#: charm's MNI box (mm) for MNI152 1 mm space.
MNI_BOX = ((-90, 90), (-126, 90), (-72, 108))
#: ``to_mni`` reads the warp at the nearest voxel (1 mm grid); SimNIBS interpolates it.
TO_MNI_TOLERANCE_MM = 2.0
#: Placeholder text a page must never show: Python's None, a NaN, an infinity, a nested list
#: (an XYZ montage printed raw) or an unknown size. Case matters for None: "none: electrodes
#: placed at subject-space coordinates" is a sentence.
_TEXT_FAULTS = re.compile(r"\bNone\b|\b(?:nan|NaN|NAN)\b|Infinity|\[\[|\? mm")


# ── independent readers ──────────────────────────────────────────────────


def _sid(path: Path) -> str:
    return next(p for p in path.parts if p.startswith("sub-")).removeprefix("sub-")


def _simulations() -> list[Path]:
    """The dataset's TI simulations; skips when it has none.

    A carrier-only run (``carrier_only: true``, the HF carriers without an envelope) writes no
    ``TI_max``, and which runs a user's Dataset 000 holds changes whenever a simulation is
    re-run, so those runs are left out rather than failed.
    """
    sims = sorted(
        p.parent.parent
        for p in _SIMNIBS.glob("sub-*/Simulations/*/documentation/config.json")
        if not json.loads(p.read_text()).get("carrier_only")
    )
    if not sims:
        pytest.skip(
            "skipping: TIT_DATASET_000 has no TI simulation (every Simulations/* run is "
            "carrier-only or has no documentation/config.json)"
        )
    return sims


def _flex_runs() -> list[Path]:
    return sorted(p.parent for p in _SIMNIBS.glob("sub-*/flex-search/*/flex_meta.json"))


def _ex_runs() -> list[Path]:
    return sorted(
        p.parent
        for p in _SIMNIBS.glob("sub-*/ex-search/*/final_output.csv")
        if (p.parent / "run_config.json").is_file()
    )


def _carrier_p999(sim: Path) -> list[float]:
    """Per carrier, the grey-matter ``magnE`` 99.9th percentile SimNIBS printed (V/m)."""
    text = (sim / "high_Frequency" / "analysis" / "fields_summary.txt").read_text()
    out = []
    for block in re.split(r"\n(?=\S+_TDCS_\d+\n=+\n)", text.strip()):
        head = re.search(r"\|Field\s*\|([^\n]+)\|", block)
        row = re.search(r"\|magnE\s*\|([^\n]+)\|", block)
        cols = [h.strip() for h in head.group(1).split("|")]
        vals = [v.strip().split()[0] for v in row.group(1).split("|")]
        out.append(float(vals[cols.index("99.9%")]))
    return out


def _grey(sim: Path) -> Path:
    hits = [
        p
        for p in (sim / "TI" / "niftis").glob("grey_*_subject_TI_max.nii.gz")
        if "_MNI_" not in p.name
    ]
    assert len(hits) == 1, (sim, hits)
    return hits[0]


def _volume(path: Path):
    import nibabel as nib

    img = nib.load(str(path))
    return img, np.asarray(img.dataobj, dtype=np.float64)


def _stats(data: np.ndarray) -> dict:
    v = data[data > 0]
    return {
        "median": float(np.median(v)),
        "p99_9": float(np.percentile(v, 99.9)),
        "max": float(v.max()),
    }


def _label_at(path: Path, world: list[float]) -> int:
    img, data = _volume(path)
    ijk = np.round(np.linalg.inv(img.affine) @ [*world, 1])[:3].astype(int)
    return int(data[tuple(ijk)].squeeze())


def _m2m(sim: Path) -> Path:
    return sim.parent.parent / f"m2m_{_sid(sim)}"


def _section(html: str, anchor: str) -> str:
    match = re.search(
        rf'<section[^>]*\bid="{re.escape(anchor)}"[^>]*>(.*?)</section>', html, re.S
    )
    return match.group(1) if match else ""


def _text(fragment: str) -> str:
    bare = re.sub(r"<(script|style|pre)\b.*?</\1>", " ", fragment, flags=re.S)
    return htmllib.unescape(re.sub(r"<[^>]+>", " ", bare))


def page_problems(html: str, budget: int) -> list[str]:
    """What is structurally wrong with a rebuilt report page."""
    problems = []
    if len(html.encode("utf-8")) > budget:
        problems.append(f"{len(html.encode('utf-8'))} bytes > budget {budget}")
    toc = re.search(r'<ol class="toc">(.*?)</ol>', html, re.S)
    anchors = re.findall(r'href="#([^"]+)"', toc.group(1)) if toc else []
    if not anchors:
        problems.append("no table of contents")
    for anchor in anchors:
        body = _section(html, anchor)
        heading = re.sub(r"<h2\b.*?</h2>", " ", body, flags=re.S)
        if not re.search(r"\w", _text(heading)):
            problems.append(f"TOC anchor #{anchor} has no section body")
    faults = sorted(set(_TEXT_FAULTS.findall(_text(html))))
    if faults:
        problems.append(f"text shows {faults}")
    return problems


def _accepted(run: Path, meta: dict) -> dict:
    """The best restart's accepted ``candidates.csv`` row."""
    hist = run / "candidate_history" / f"{meta['result']['best_run_index']:02d}"
    manifest = json.loads((hist / "candidate_manifest.json").read_text())
    with (hist / "candidates.csv").open(newline="") as stream:
        rows = [
            r
            for r in csv.DictReader(stream)
            if r["candidate_id"] == manifest["accepted_candidate_id"]
        ]
    assert len(rows) == 1, hist
    return rows[0]


def _flex_currents(run: Path, meta: dict) -> list[float]:
    best = _accepted(run, meta)
    if best.get("current_ch1_mA"):
        return [float(best["current_ch1_mA"]), float(best["current_ch2_mA"])]
    return [float(v) for v in meta.get("current_split") or [meta["current_mA"]] * 2]


def _mtimes(roots: list[Path]) -> dict[str, int]:
    out = {}
    for root in roots:
        for p in [root, *root.rglob("*")] if root.is_dir() else [root]:
            if p.exists():
                out[str(p)] = p.stat().st_mtime_ns
    return out


@pytest.fixture(scope="module")
def untouched():
    """Fails the module if anything under the folders it reads changed."""
    roots = [
        p
        for sub in _SIMNIBS.glob("sub-*")
        for p in [
            sub / "Simulations",
            sub / "flex-search",
            sub / "ex-search",
            sub / "leadfields",
            *sub.glob("m2m_*/T1.nii.gz"),
            *sub.glob("m2m_*/final_tissues.nii.gz"),
            *sub.glob("m2m_*/toMNI"),
            *sub.glob("m2m_*/eeg_positions"),
        ]
        if p.exists()
    ]
    before = _mtimes(roots)
    assert before, "has nothing to read"
    yield
    assert _mtimes(roots) == before, "a test wrote into the read-only dataset"


@pytest.fixture(autouse=True)
def _no_job_events(monkeypatch):
    monkeypatch.delenv("TIT_EVENTS_FILE", raising=False)


@pytest.fixture
def real_simnibs():
    """The real ``simnibs`` package in place of ``tests/conftest.py``'s mock; skips without it."""
    saved = {
        k: sys.modules.pop(k) for k in list(sys.modules) if k.split(".")[0] == "simnibs"
    }
    try:
        module = importlib.import_module("simnibs")
    except ImportError:
        sys.modules.update(saved)
        pytest.skip("skipping: real SimNIBS is unavailable; run in the toolbox image")
    yield module
    for k in [k for k in sys.modules if k.split(".")[0] == "simnibs"]:
        del sys.modules[k]
    sys.modules.update(saved)


# ── simulations: the files ───────────────────────────────────────────────


@pytest.mark.host_numerical
@real_data
def test_every_simulation_envelope_is_plausible_on_the_t1_grid_and_under_the_carrier_bound(
    untouched,
):
    sims = _simulations()
    for sim in sims:
        config = json.loads((sim / "documentation" / "config.json").read_text())
        n_pairs = len(config["electrode_pairs"])
        img, grey = _volume(_grey(sim))
        t1, _ = _volume(_m2m(sim) / "T1.nii.gz")
        assert grey.ndim == 3 and grey.shape == t1.shape, (sim, grey.shape, t1.shape)
        import nibabel as nib

        assert np.allclose(img.affine, nib.load(str(_m2m(sim) / "T1.nii.gz")).affine)
        assert np.isfinite(grey).all() and grey.min() >= 0, sim
        assert np.count_nonzero(grey) > 1000, sim

        s = _stats(grey)
        assert s["median"] <= s["p99_9"] <= s["max"], (sim, s)

        carriers = _carrier_p999(sim)
        assert len(carriers) == n_pairs, (sim, carriers)
        assert s["p99_9"] <= VOXEL_VS_MESH * 2 * min(carriers), (sim, s, carriers)
        for p999, mA in zip(carriers, config["intensities"]):
            assert 0.01 <= p999 / float(mA) <= 3, (sim, p999, mA)

        for mni in (sim / "TI" / "niftis").glob("*_MNI_*.nii.gz"):
            mimg = nib.load(str(mni))
            assert mimg.shape[:3] == (182, 218, 182), mni
            assert all(d == 1 for d in mimg.shape[3:]), mni
            assert np.allclose(mimg.header.get_zooms()[:3], 1.0), mni


@pytest.mark.host_numerical
@real_data
def test_the_report_reads_the_envelope_and_finds_its_peak_in_grey_matter(untouched):
    from tit.reporting.generators.simulation import collect, to_mni

    sims = _simulations()
    for sim in sims:
        rec = collect(sim)
        img, grey = _volume(_grey(sim))
        assert Path(rec["niftis"]["grey"]) == _grey(sim), sim
        expected = _stats(grey)
        env = rec["envelope"]
        assert "max" not in env, sim
        for key in ("median", "p99_9"):
            assert env[key] == pytest.approx(expected[key], rel=FLOAT32_PERCENTILE), (sim, key)

        ijk = np.round(np.linalg.inv(img.affine) @ [*env["hotspot_world"], 1])[:3]
        assert grey[tuple(ijk.astype(int))] >= expected["p99_9"] * (1 - FLOAT32_PERCENTILE)
        m2m = _m2m(sim)
        assert _label_at(m2m / "final_tissues.nii.gz", env["hotspot_world"]) == 2, sim

        mni = to_mni(env["hotspot_world"], m2m)
        assert mni is not None, sim
        for v, (lo, hi) in zip(mni, MNI_BOX):
            assert lo <= v <= hi, (sim, mni)
        label = _label_at(m2m / "toMNI" / "final_tissues_MNI.nii.gz", mni)
        assert label in (1, 2), (sim, mni, label)


@real_data
def test_to_mni_agrees_with_simnibs(untouched, real_simnibs):
    simnibs = real_simnibs
    from tit.reporting.generators.simulation import collect, to_mni

    for sim in _simulations():
        peak = collect(sim)["envelope"]["hotspot_world"]
        ours = to_mni(peak, _m2m(sim))
        theirs = np.asarray(simnibs.subject2mni_coords(peak, str(_m2m(sim)))).ravel()
        assert math.dist(ours, theirs) <= TO_MNI_TOLERANCE_MM, (sim, ours, theirs)


# ── simulations: the page ────────────────────────────────────────────────


@real_data
def test_every_simulation_report_rebuilds_with_its_own_facts(untouched, tmp_path):
    from tit.reporting.generators import simulation

    sims = _simulations()
    for sim in sims:
        sid = _sid(sim)
        config = json.loads((sim / "documentation" / "config.json").read_text())
        n_pairs = len(config["electrode_pairs"])
        out = tmp_path / sid / sim.name
        path = simulation.create_simulation_report(ROOT, sid, sim.name, out_dir=out)
        assert path.parent == out
        page = path.read_text(encoding="utf-8")
        assert page_problems(page, simulation.SIZE_BUDGET) == [], sim

        head = re.search(
            r'<h2 id="verdict-h">([\d.]+) V/m envelope in grey matter \(99\.9th percentile\)',
            page,
        )
        _, grey = _volume(_grey(sim))
        assert head and float(head.group(1)) == pytest.approx(
            _stats(grey)["p99_9"], abs=5e-4
        ), sim
        assert "<img" in _section(page, "field"), sim
        assert re.search(r"is at MNI \(-?\d+, -?\d+, -?\d+\) mm", page), sim

        table = re.search(
            r"<caption>Each high-frequency carrier alone.*?<tbody>(.*?)</tbody>",
            page,
            re.S,
        )
        rows = re.findall(r"<tr>(.*?)</tr>", table.group(1), re.S) if table else []
        assert len(rows) == n_pairs, (sim, len(rows))
        for row, p999 in zip(rows, _carrier_p999(sim)):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            assert float(cells[2]) == pytest.approx(p999, abs=5e-4), (sim, cells)

        total = re.search(r"<dt>Total current</dt><dd><b>([\d.]+)<small>mA", page)
        want = sum(abs(float(v)) for v in config["intensities"][:n_pairs])
        assert total and float(total.group(1)) == pytest.approx(want, rel=1e-3), sim


# ── flex ─────────────────────────────────────────────────────────────────


@pytest.mark.host_numerical
@real_data
def test_every_flex_report_states_its_runs_currents_and_positions(untouched, tmp_path):
    from tit.reporting.generators import flex_search

    runs = _flex_runs()
    assert runs, "has no flex runs to check"
    for run in runs:
        meta = json.loads((run / "flex_meta.json").read_text())
        positions = json.loads((run / "electrode_positions.json").read_text())
        path = flex_search.create_flex_search_report(
            ROOT, _sid(run), run, out_dir=tmp_path / _sid(run) / run.name
        )
        page = path.read_text(encoding="utf-8")
        assert page_problems(page, flex_search.SIZE_BUDGET) == [], run

        runs_table = _section(page, "runs")
        rows = re.findall(r"<tr>(.*?)</tr>", runs_table.split("<tbody>", 1)[1], re.S)
        assert len(rows) == len(meta["result"]["all_values"]), run

        tile = re.search(r"<dt>Currents</dt><dd><b>([\d. /]+)<small>mA", page)
        shown = [float(v) for v in tile.group(1).split("/")]
        want = _flex_currents(run, meta)
        if meta.get("current_split"):
            assert want == pytest.approx([float(v) for v in meta["current_split"]])
        assert (shown * 2 if len(shown) == 1 else shown) == pytest.approx(
            want, rel=1e-3
        ), run

        centres = positions["optimized_positions"]
        table = re.search(
            r"<caption>Optimised electrode centres.*?<tbody>(.*?)</tbody>", page, re.S
        )
        cells = re.findall(r"<tr>(.*?)</tr>", table.group(1), re.S)
        assert len(cells) == len(centres) == 4, run
        for row, centre, (ch, arr) in zip(
            cells, centres, positions["channel_array_indices"]
        ):
            ch_cell, pole, xyz = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            # Channel k is electrodes Ek+ (array 0) and Ek- (array 1), as everywhere else.
            assert ch_cell == f"Channel {ch + 1}"
            assert pole == f"E{ch + 1}{'+' if arr == 0 else '-'}", (run, pole)
            got = [float(v) for v in xyz.strip("()").split(",")]
            assert got == pytest.approx(centre, abs=0.051), (run, got, centre)

        floor = 0.9 * float(meta["min_electrode_distance"])
        for i, a in enumerate(centres):
            for b in centres[i + 1 :]:
                assert math.dist(a, b) >= floor, (run, a, b)


@pytest.mark.host_numerical
@real_data
def test_a_simulation_named_after_a_flex_run_simulates_its_positions_and_currents(
    untouched,
):
    matched = 0
    for run in _flex_runs():
        sim = run.parent.parent / "Simulations" / run.name
        if not (sim / "documentation" / "config.json").is_file():
            continue
        matched += 1
        meta = json.loads((run / "flex_meta.json").read_text())
        positions = json.loads((run / "electrode_positions.json").read_text())
        config = json.loads((sim / "documentation" / "config.json").read_text())
        pairs = [[None, None], [None, None]]
        for centre, (ch, arr) in zip(
            positions["optimized_positions"], positions["channel_array_indices"]
        ):
            pairs[ch][arr] = centre
        assert len(config["electrode_pairs"]) == 2, sim
        for got_pair, want_pair in zip(config["electrode_pairs"], pairs):
            for got, want in zip(got_pair, want_pair):
                assert math.dist(got, want) <= 1e-3, (sim, got, want)
        assert [float(v) for v in config["intensities"]] == pytest.approx(
            _flex_currents(run, meta), abs=1e-9
        ), sim
    assert matched, "has no simulation of a flex run to check"


# ── ex ───────────────────────────────────────────────────────────────────


@pytest.mark.host_numerical
@real_data
def test_every_ex_report_rebuilds_without_empty_sections_or_placeholder_text(
    untouched, tmp_path
):
    from tit.reporting.generators import ex_search

    runs = _ex_runs()
    assert runs, "has no ex-search runs to check"
    for run in runs:
        path = ex_search.create_ex_search_report(
            ROOT, _sid(run), run, out_dir=tmp_path / _sid(run) / run.name
        )
        page = path.read_text(encoding="utf-8")
        assert page_problems(page, ex_search.SIZE_BUDGET) == [], run


@pytest.mark.host_numerical
def test_the_page_checks_catch_an_empty_section_placeholder_text_and_an_oversized_page():
    good = (
        '<ol class="toc"><li><a href="#a">A</a></li></ol>'
        '<section class="sec" id="a"><h2 id="a-h">A</h2><p>0.359 V/m</p></section>'
        "<pre>[[1, 2], None]</pre><script>var x = NaN;</script>"
    )
    assert page_problems(good, 10_000) == []
    empty = good.replace("<p>0.359 V/m</p>", "")
    assert page_problems(empty, 10_000) == ["TOC anchor #a has no section body"]
    for bad in ("None", "nan V/m", "Infinity", "[[1, 2]]", "gel ? mm"):
        assert page_problems(good.replace("0.359 V/m", bad), 10_000), bad
    assert page_problems(good, 100)[0].endswith("> budget 100")
    missing = good.replace('id="a"', 'id="b"')
    assert page_problems(missing, 10_000) == ["TOC anchor #a has no section body"]
