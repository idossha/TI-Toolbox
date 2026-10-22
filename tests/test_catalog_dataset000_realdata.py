"""Dataset 000 through the catalog: everything on disk is listed, everything listed exists,
and every number it serves is physically ordered.

What this pins (package p24, audit_server-contracts.md "Dataset 000 catalog invariants",
2026-10-22). The filesystem is the oracle, read here with ``os``/``csv`` independently of
``tit.catalog``:

- every NIfTI under ``Simulations/<sim>/{TI,mTI,high_Frequency}/niftis`` is in its
  ``simulation_detail``; every analysis folder (``analysis.json`` + ``results.csv``) is in
  ``analyses``; every flex run (``flex_meta.json``) and ex run (``run_config.json``) is in
  ``flex_runs`` / ``ex_runs``; every report of a known subject is in ``reports``; every
  ``stats/<type>/<name>``, ``nifti_average/<name>`` and ``nilearn_visuals/<name>`` folder is in
  ``group_catalog`` -- and every path any of them lists exists;
- a NIfTI's field is the one its filename ends with (a registered output field, or SimNIBS's
  ``magnE`` for a carrier under ``high_Frequency``), and its space is the filename's
  ``_subject_`` / ``_MNI_MNI_`` token;
- every ``results.csv`` served equals the file and obeys roi_min <= roi_mean <= roi_max,
  roi_focality = roi_mean / gm_mean, p95 <= p99 <= p99.9 <= gm_max, focality areas
  50 >= 75 >= 90 >= 95, n_elements > 0, all finite, field values in [0, 10] V/m;
- ex best montages are distinct labels of the run's own net; ``eeg_nets`` counts are right
  and labels distinct; every leadfield names a net the subject has;
- the viewer's simulation layers (``tit.viewspec._ti_max_layers`` / ``_hf_layers``) are exactly
  the ``TI_max``/``mTI_max`` envelopes and ``magnE`` carriers on disk in that space.

Read-only: the mtime of every file and folder in the dataset is compared before and after.

Vacuous legs on today's Dataset 000: its ``derivatives/ti-toolbox/nilearn_visuals`` and
``nifti_average`` folders are empty, so the real-data coverage check for those two compares
empty sets (only the ``stats`` leg has runs). The synthetic
``test_group_output_folders_are_listed_one_for_one`` runs on every host and covers them.

Run: ``TIT_DATASET_000=/Users/idohaber/datasets/000 .venv/bin/python -m pytest
tests/test_catalog_dataset000_realdata.py -q``. Skips with a reason when the variable is unset.
Deliberately elsewhere: field values inside the NIfTIs (tests/numerical), report contents
(tests/test_report_*).
"""

from __future__ import annotations

import csv
import math
import os
import re
from pathlib import Path

import pytest

DATASET = os.environ.get("TIT_DATASET_000", "")
HAVE_DATASET = bool(DATASET) and os.path.isdir(
    os.path.join(DATASET, "derivatives", "SimNIBS")
)

#: SimNIBS's own name for |E| of one carrier pair (``<sid>_TDCS_<n>_<scalar|vn>_..._magnE``).
CARRIER_FIELD = "magnE"


def _mtimes(root: str) -> dict[str, int]:
    out = {root: os.lstat(root).st_mtime_ns}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            path = os.path.join(dirpath, name)
            out[path] = os.lstat(path).st_mtime_ns
    return out


@pytest.fixture(scope="module")
def view():
    """Every catalog response for the dataset, with a before/after mtime listing."""
    if not HAVE_DATASET:
        pytest.skip("skipping: TIT_DATASET_000 is unset or not a Dataset 000 copy")
    from tit import catalog, viewspec
    from tit.paths import get_path_manager

    root = os.path.realpath(DATASET)
    before = _mtimes(root)
    pm = get_path_manager(root)
    sids = catalog.subject_ids(pm)
    known = set(sids) | set(catalog.sourcedata_only_subject_ids(pm))
    data = {
        "root": root,
        "pm": pm,
        "sids": sids,
        "known": known,
        "sims": {},
        "analyses": {},
        "summaries": {},
        "flex": {sid: catalog.flex_runs(pm, sid) for sid in sids},
        "ex": {sid: catalog.ex_runs(pm, sid, "ex") for sid in sids},
        "mex": {sid: catalog.ex_runs(pm, sid, "mex") for sid in sids},
        "reports": {sid: catalog.reports(pm, sid) for sid in known},
        "nets": {sid: catalog.eeg_nets(pm, sid) for sid in sids},
        "leadfields": {sid: catalog.list_leadfields(pm, sid) for sid in sids},
        "group": catalog.group_catalog(pm),
        "layers": {},
    }
    for sid in sids:
        for item in catalog.list_simulations(pm, sid):
            sim = item["name"]
            data["sims"][(sid, sim)] = catalog.simulation_detail(pm, sid, sim)
            sim_dir = pm.simulation(sid, sim)
            for space in ("subject", "mni"):
                data["layers"][(sid, sim, space)] = (
                    viewspec._ti_max_layers(sim_dir, space),
                    viewspec._hf_layers(sim_dir, space),
                )
            listed = catalog.analyses(pm, sid, sim)
            data["analyses"][(sid, sim)] = listed
            for analysis in listed:
                data["summaries"][(sid, sim, analysis["name"])] = (
                    catalog.analysis_summary(pm, sid, sim, analysis["name"])
                )
    data["after"] = _mtimes(root)
    data["before"] = before
    return data


def _sim_root(view) -> Path:
    return Path(view["root"]) / "derivatives" / "SimNIBS"


def test_the_catalog_read_left_the_dataset_untouched(view):
    assert view["after"] == view["before"]


def test_there_is_something_to_check(view):
    assert len(view["sids"]) >= 4
    assert len(view["sims"]) >= 4
    assert sum(len(a) for a in view["analyses"].values()) >= 5


# ── simulations ─────────────────────────────────────────────────────────────


def test_every_simulation_nifti_on_disk_is_listed_and_every_listed_one_exists(view):
    for (sid, sim), detail in view["sims"].items():
        sim_dir = _sim_root(view) / f"sub-{sid}" / "Simulations" / sim
        on_disk = {
            str(p)
            for mode in ("TI", "mTI", "high_Frequency")
            for p in (sim_dir / mode / "niftis").glob("*.nii*")
            if p.is_file()
        }
        listed = [n["path"] for n in detail["niftis"]]
        assert len(listed) == len(set(listed)), f"{sid}/{sim} lists a NIfTI twice"
        assert set(listed) == on_disk, f"{sid}/{sim}"
        for mesh in detail["meshes"]:
            assert os.path.isfile(mesh["path"]), mesh


def _field_from_name(basename: str, registered: tuple[str, ...]) -> str | None:
    stem = re.sub(r"\.nii(\.gz)?$", "", basename)
    # Longest first, so ``..._mTI_max`` is mTI_max and not TI_max.
    for field in sorted((*registered, CARRIER_FIELD), key=len, reverse=True):
        if stem.endswith(f"_{field}"):
            return field
    return None


def test_nifti_field_and_space_are_the_ones_the_filename_says(view):
    from tit.constants import get_field_names

    registered = get_field_names()
    checked = 0
    for (sid, sim), detail in view["sims"].items():
        for nifti in detail["niftis"]:
            path, base = nifti["path"], os.path.basename(nifti["path"])
            carrier = f"{os.sep}high_Frequency{os.sep}" in path
            expected_field = _field_from_name(base, registered)
            assert expected_field is not None, f"{path}: no field in its name"
            assert nifti["field"] == expected_field, path
            if carrier:
                assert nifti["field"] == CARRIER_FIELD, path
            else:
                assert nifti["field"] in registered, path
            tokens = {"subject": "_subject_" in base, "mni": "_MNI_MNI_" in base}
            assert sum(tokens.values()) == 1, f"{base}: space token ambiguous"
            assert tokens[nifti["space"]], path
            checked += 1
        # The fields a simulation offers are the envelope fields its NIfTIs carry.
        envelope = {
            n["field"]
            for n in detail["niftis"]
            if f"{os.sep}high_Frequency{os.sep}" not in n["path"]
        }
        assert envelope <= set(detail["fields"]), (sid, sim, detail["fields"])
    assert checked > 20


def test_viewer_layers_are_the_envelope_and_carrier_niftis_of_their_space(view):
    """The Viewer's per-simulation layers, against the folder listing and filename tokens."""
    checked = 0
    for (sid, sim, space), (ti_layers, hf_layers) in view["layers"].items():
        sim_dir = _sim_root(view) / f"sub-{sid}" / "Simulations" / sim

        def in_space(p: Path) -> bool:
            return ("_MNI_MNI_" in p.name) == (space == "mni")

        envelopes = {
            str(p)
            for mode in ("TI", "mTI")
            for p in (sim_dir / mode / "niftis").glob("*.nii*")
            if re.search(r"_m?TI_max\.nii(\.gz)?$", p.name) and in_space(p)
        }
        carriers = {
            str(p)
            for p in (sim_dir / "high_Frequency" / "niftis").glob("*.nii*")
            if re.search(r"_magnE\.nii(\.gz)?$", p.name) and in_space(p)
        }
        assert sorted(layer["path"] for layer in ti_layers) == sorted(envelopes), (
            sid,
            sim,
            space,
        )
        assert sorted(layer["path"] for layer in hf_layers) == sorted(carriers), (
            sid,
            sim,
            space,
        )
        # Grey matter's envelope is shown; the whole-head and white-matter ones and every
        # carrier start hidden.
        for layer in ti_layers:
            assert layer["visible"] == os.path.basename(layer["path"]).startswith(
                "grey_"
            ), layer["path"]
        assert not any(layer["visible"] for layer in hf_layers)
        checked += len(ti_layers) + len(hf_layers)
    assert checked > 20


# ── analyses ────────────────────────────────────────────────────────────────


def test_every_analysis_on_disk_is_listed(view):
    for (sid, sim), listed in view["analyses"].items():
        sim_dir = _sim_root(view) / f"sub-{sid}" / "Simulations" / sim
        on_disk = {
            str(p.parent)
            for p in sim_dir.rglob("analysis.json")
            if (p.parent / "results.csv").is_file() and p.parent != sim_dir
        }
        names = [a["name"] for a in listed]
        assert len(names) == len(set(names)), f"{sid}/{sim}: duplicate analysis name"
        assert {os.path.dirname(a["csv"]) for a in listed} == on_disk, f"{sid}/{sim}"
        for analysis in listed:
            assert os.path.isfile(analysis["csv"]), analysis
            assert os.path.isfile(analysis["json"]), analysis


def _raw_results(csv_path: str) -> dict[str, str]:
    with open(csv_path, newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["Metric", "Value"], csv_path
    return {row[0]: row[1] for row in rows[1:] if len(row) >= 2}


def test_every_results_csv_is_served_as_written_and_physically_ordered(view):
    checked = 0
    for (sid, sim), listed in view["analyses"].items():
        for analysis in listed:
            raw = _raw_results(analysis["csv"])
            served = view["summaries"][(sid, sim, analysis["name"])]
            assert served is not None, analysis["name"]
            assert {r[0]: r[1] for r in served["rows"]} == raw, analysis["csv"]

            where = analysis["csv"]
            num = {
                k: float(v)
                for k, v in raw.items()
                if k not in ("field_name", "region_name", "space", "analysis_type")
            }
            assert all(math.isfinite(v) for v in num.values()), where
            # The ROI is taken inside the analysed tissue, so its peak is the tissue's at most.
            assert (
                num["roi_min"] <= num["roi_mean"] <= num["roi_max"] <= num["gm_max"]
            ), where
            assert num["roi_focality"] == pytest.approx(
                num["roi_mean"] / num["gm_mean"], rel=1e-6
            ), where
            assert (
                num["percentile_95"]
                <= num["percentile_99"]
                <= num["percentile_99_9"]
                <= num["gm_max"]
            ), where
            assert (
                num["focality_50_area"]
                >= num["focality_75_area"]
                >= num["focality_90_area"]
                >= num["focality_95_area"]
                >= 0
            ), where
            assert num["n_elements"] > 0, where
            for key in ("roi_min", "roi_mean", "roi_max", "gm_mean", "gm_max"):
                assert 0.0 <= num[key] <= 10.0, (where, key, num[key])
            checked += 1
    assert checked >= 5


# ── runs ────────────────────────────────────────────────────────────────────


def test_every_flex_and_ex_run_on_disk_is_listed(view):
    for sid in view["sids"]:
        sub = _sim_root(view) / f"sub-{sid}"
        for key, folder, marker, name_key in (
            ("flex", "flex-search", "flex_meta.json", "name"),
            ("ex", "ex-search", "run_config.json", "run_name"),
            ("mex", "mex-search", "run_config.json", "run_name"),
        ):
            on_disk = {
                p.parent.name
                for p in (sub / folder).glob(f"*/{marker}")
                if not p.parent.name.startswith(".")
            }
            listed = [r[name_key] for r in view[key][sid]]
            assert len(listed) == len(set(listed)), (sid, key)
            assert set(listed) == on_disk, (sid, key)
            for run in view[key][sid]:
                assert os.path.isdir(run["path"]), run["path"]
                for artifact in run.get("artifacts") or []:
                    assert os.path.isfile(artifact["path"]), artifact


def _net_labels(view, sid: str, net: str) -> list[str]:
    path = _sim_root(view) / f"sub-{sid}" / f"m2m_{sid}" / "eeg_positions" / net
    with open(path, newline="") as handle:
        return [
            row[4].strip()
            for row in csv.reader(handle)
            if len(row) >= 5 and row[0].strip() == "Electrode"
        ]


def test_ex_best_montages_are_distinct_labels_of_the_run_net(view):
    checked = 0
    for sid in view["sids"]:
        for run in view["ex"][sid] + view["mex"][sid]:
            best = run["best"]
            if best is None:
                continue
            labels = set(_net_labels(view, sid, run["eeg_net"]))
            # "<a>_<b> <> <c>_<d>_I1-<x>mA_I2-<y>mA": one "<> "-separated pair per channel.
            pairs = [
                re.sub(r"_I\d*-.*$", "", part).split("_")
                for part in best["montage"].split(" <> ")
            ]
            for pair in pairs:
                assert len(pair) == 2 and pair[0] != pair[1], (run["path"], pair)
                assert set(pair) <= labels, (run["path"], pair, run["eeg_net"])
            electrodes = [e for pair in pairs for e in pair]
            assert len(electrodes) == len(set(electrodes)), run["path"]
            checked += 1
        for run in view["flex"][sid]:
            for mapping in run["mappings"]:
                labels = set(_net_labels(view, sid, mapping["eeg_net"]))
                flat = [e for pair in mapping["pairs"] for e in pair]
                assert len(flat) == len(set(flat)) and set(flat) <= labels, run["path"]
    assert checked >= 1


# ── reports and group outputs ───────────────────────────────────────────────


def test_a_subject_with_only_staged_dicoms_lists_its_reports(tmp_path):
    """Synthetic twin of Dataset 000's sub-102, which runs on every host: DICOMs staged under
    sourcedata/, a pre-processing report written, nothing converted yet. list_subjects shows
    the subject; reports() must not answer "unknown subject" for it."""
    from tit import catalog
    from tit.paths import get_path_manager

    (tmp_path / "dataset_description.json").write_text("{}")
    pm = get_path_manager(str(tmp_path))
    dicom = Path(pm.sourcedata_subject("102")) / "T1w" / "IM0001.dcm"
    dicom.parent.mkdir(parents=True)
    dicom.write_bytes(b"dicom")
    report = (
        Path(pm.reports()) / "sub-102" / "pre_processing_report_20260403_103720.html"
    )
    report.parent.mkdir(parents=True)
    report.write_text("<html></html>")
    assert "102" in [s["id"] for s in catalog.list_subjects(pm)]
    listed = catalog.reports(pm, "102")
    assert listed is not None
    assert [(r["id"], r["path"]) for r in listed] == [
        ("102/pre_processing_report_20260403_103720", str(report))
    ]
    assert catalog.reports(pm, "999") is None  # a subject nobody knows is still unknown


def test_every_report_of_a_known_subject_is_listed(view):
    reports_root = Path(view["root"]) / "derivatives" / "ti-toolbox" / "reports"
    for sid in view["known"]:
        on_disk = {str(p) for p in (reports_root / f"sub-{sid}").glob("*.html")}
        listed = view["reports"][sid]
        assert listed is not None, sid
        assert {r["path"] for r in listed} == on_disk, sid
        assert len({r["id"] for r in listed}) == len(listed), sid


def test_every_group_output_folder_is_listed(view):
    tt = Path(view["root"]) / "derivatives" / "ti-toolbox"
    group = view["group"]

    def subdirs(path: Path) -> set[str]:
        return (
            {str(p) for p in path.iterdir() if p.is_dir()} if path.is_dir() else set()
        )

    stats = {
        run
        for kind in subdirs(tt / "stats")
        if os.path.basename(kind) != "data"
        for run in subdirs(Path(kind))
    }
    assert {s["path"] for s in group["stats"]} == stats
    assert {n["path"] for n in group["nilearn"]} == subdirs(tt / "nilearn_visuals")
    assert {n["path"] for n in group["nifti_average"]} == subdirs(tt / "nifti_average")
    for entry in group["stats"] + group["nilearn"] + group["nifti_average"]:
        assert os.path.isdir(entry["path"]), entry


def test_group_output_folders_are_listed_one_for_one(tmp_path):
    """Synthetic twin of the group-output check, on every host: Dataset 000's nilearn_visuals
    and nifti_average are empty, so there the check compares empty sets."""
    from tit import catalog
    from tit.paths import get_path_manager

    (tmp_path / "dataset_description.json").write_text("{}")
    pm = get_path_manager(str(tmp_path))
    tt = tmp_path / "derivatives" / "ti-toolbox"
    made = {
        "nilearn": ["alpha_glass", "beta_slices"],
        "nifti_average": ["group_mean", "responders"],
    }
    roots = {"nilearn": tt / "nilearn_visuals", "nifti_average": tt / "nifti_average"}
    for key, names in made.items():
        for name in names:
            (roots[key] / name).mkdir(parents=True)
        (roots[key] / "notes.txt").write_text("a file, not a run")

    group = catalog.group_catalog(pm)
    for key, names in made.items():
        assert [(e["name"], e["path"]) for e in group[key]] == [
            (name, str(roots[key] / name)) for name in names
        ], key


# ── nets and leadfields ─────────────────────────────────────────────────────


def test_eeg_net_counts_and_labels(view):
    for sid, nets in view["nets"].items():
        assert nets, sid
        for net in nets:
            electrodes = net["electrodes"]
            assert net["n"] == len(electrodes) == len(set(electrodes)), (
                sid,
                net["name"],
            )
            assert sorted(electrodes) == sorted(_net_labels(view, sid, net["name"]))


def test_every_leadfield_names_a_net_the_subject_has(view):
    checked = 0
    for sid, leadfields in view["leadfields"].items():
        names = {n["name"] for n in view["nets"][sid]}
        for leadfield in leadfields:
            assert os.path.isfile(leadfield["path"]), leadfield
            assert f"{leadfield['net']}.csv" in names, (sid, leadfield)
            checked += 1
    assert checked >= 1
