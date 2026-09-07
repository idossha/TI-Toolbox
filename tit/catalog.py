"""Project catalog: subject and simulation discovery for the UI.

Built only on :class:`tit.paths.PathManager` (plus the existing per-domain
helpers it composes: :mod:`tit.sim.utils` montage I/O, :mod:`tit.atlas`
discovery, :mod:`tit.opt.ex.roi`/:mod:`tit.opt.leadfield` ROI and leadfield
helpers, :mod:`tit.opt.flex.manifest`); the server routes
(``tit.server.routes.catalog``, ``tit.server.routes.catalog_v1``) serialise
these dicts as-is, so the BIDS / derivative layout rules are never
re-implemented outside ``tit``.

v1 additions (this module is extended, not replaced, for Stage 1 / lane B2 —
see ``docs/dev/HISTORY.md § 2026-08-27 (v3 build program)`` §3 "Catalog"): subject/simulation detail,
montage CRUD, EEG nets, atlases + regions, ROI CRUD, leadfields, flex/ex/mex
runs, analyses, reports, freehand configs, the project-level group catalog,
Quick Notes, and the subject-info presence matrix. A run/analysis directory
without the manifest file that marks it complete (``flex_meta.json``,
``run_config.json``, or the ``analysis.json``+``results.csv`` pair) is
ignored, so a cancelled or in-progress run never appears as a result.
"""

from __future__ import annotations

import csv
import glob
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

from tit.atlas.constants import VOXEL_ATLASES, mni_resources_dir
from tit.atlas.mesh import MeshAtlasManager
from tit.atlas.voxel import VoxelAtlasManager, parse_region_label
from tit.paths import PathManager, natural_key

# NOTE: tit.opt.ex.roi (used by list_rois) is imported lazily inside the
# function that needs it, never at module level -- tit/opt/__init__.py
# eagerly imports tit.opt.ex.engine, which imports simnibs (AGENTS.md
# "SimNIBS imports - use lazy loading pattern in opt/"). tit.catalog is
# imported at server startup by every route module, so a module-level
# import here would make the whole server fail to boot outside a SimNIBS
# environment (host dev tooling, --dump-openapi, CI without the container).


def subject_ids(pm: PathManager) -> list[str]:
    """Union of raw-BIDS, FastSurfer, legacy-FreeSurfer and m2m subjects.

    Naturally sorted. ``derivatives/freesurfer`` is still unioned in so a
    project processed before FastSurfer replaced ``recon-all`` keeps listing
    its subjects.

    Deliberately excludes subjects known only from ``sourcedata/`` (DICOMs
    staged, nothing converted yet) -- this is the *onboarded* set every other
    catalog function gates on (montages, ROIs, EEG nets, ...), where a
    subject with no derivative of any kind would be meaningless. See
    :func:`sourcedata_only_subject_ids` and, for the two routes that do need
    to see a not-yet-onboarded subject, :func:`list_subjects` /
    :func:`subject_detail`.
    """
    ids = (
        set(pm.list_bids_subjects())
        | set(pm.list_fastsurfer_subjects())
        | set(pm.list_freesurfer_subjects())
        | set(pm.list_simnibs_subjects())
    )
    return sorted(ids, key=natural_key)


# A DICOM-or-equivalent series directory, per the sourcedata half of
# :func:`tit.pre.utils.discover_subjects` (duplicated here, not imported:
# ``tit.pre``'s ``__init__`` eagerly imports ``.structural``/``.charm``,
# which are not safe to import at ``tit.server`` module-load time -- see the
# ``tit.opt`` note above ``list_rois``. Keep the two rules in sync by hand;
# they are small and unlikely to drift, and a difference here can only ever
# make a subject *visible sooner or later*, never silently misconvert one --
# the actual conversion still runs ``tit.pre.dicom2nifti`` on the real files).
_DICOM_LIKE_EXTS = (
    ".dcm",
    ".dicom",
    ".zip",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".json",
    ".nii",
    ".nii.gz",
)


def _has_sourcedata_raw(pm: PathManager, sid: str) -> bool:
    """``sourcedata/sub-<sid>/`` has a T1w or T2w series staged (any format)."""
    subj_dir = pm.sourcedata_subject(sid)
    if not os.path.isdir(subj_dir):
        return False
    for modality_dir in (
        os.path.join(subj_dir, "T1w"),
        os.path.join(subj_dir, "T2w"),
    ):
        if not os.path.isdir(modality_dir):
            continue
        try:
            entries = os.listdir(modality_dir)
        except OSError:
            continue
        if any(os.path.isdir(os.path.join(modality_dir, e)) for e in entries):
            return True
        if any(e.lower().endswith(_DICOM_LIKE_EXTS) for e in entries):
            return True
    try:
        return any(f.endswith(".tgz") for f in os.listdir(subj_dir))
    except OSError:
        return False


def sourcedata_only_subject_ids(pm: PathManager) -> list[str]:
    """Subject ids with raw data staged under ``sourcedata/`` and nowhere else.

    :func:`subject_ids` would never mention these -- no BIDS directory, no
    m2m, no FastSurfer/FreeSurfer -- so a project's own newly-arrived DICOMs
    (Dataset 000's ``sub-102``, before its DICOM-conversion stage has ever
    run) were invisible to every page built on the catalog (lane FX5,
    ``docs/dev/HISTORY.md § 2026-09-03 (pipelines program)``). Naturally sorted; a subject that
    already appears in :func:`subject_ids` is never repeated here even if
    ``sourcedata/`` also holds a copy of its DICOMs.
    """
    if not pm.project_dir:
        return []
    try:
        entries = os.listdir(pm.sourcedata())
    except OSError:
        return []
    known = set(subject_ids(pm))
    ids = []
    for name in entries:
        if not name.startswith("sub-"):
            continue
        sid = name[len("sub-") :]
        if sid in known:
            continue
        if _has_sourcedata_raw(pm, sid):
            ids.append(sid)
    return sorted(ids, key=natural_key)


def list_subjects(pm: PathManager) -> list[dict]:
    """One entry per subject: presence flags and the simulation count.

    Also lists subjects known only from ``sourcedata/`` (DICOMs staged, no
    BIDS directory yet -- see :func:`sourcedata_only_subject_ids`): the
    Subjects page and Pre-processing's own subjects table are exactly where
    a project's newest subject needs to be plannable, before anything else
    about them exists. An entry carries ``has_sourcedata: True`` when staged
    raw data is present (so a client can tell "staged, not yet converted"
    from ``has_raw`` False); the key is left out entirely otherwise -- the
    overwhelming common case (a subject with no sourcedata copy at all), and
    the shape every existing caller/test built before this field existed
    stays byte-identical (``/api/catalog/subjects`` is served with
    ``response_model_exclude_unset``, ``tit/server/routes/catalog.py``).
    """
    ids = sorted(
        set(subject_ids(pm)) | set(sourcedata_only_subject_ids(pm)), key=natural_key
    )
    rows = []
    for sid in ids:
        row = {
            "id": sid,
            "has_raw": os.path.isdir(pm.bids_subject(sid)),
            "has_fastsurfer": os.path.isdir(pm.fastsurfer_subject(sid)),
            "has_freesurfer": os.path.isdir(pm.freesurfer_subject(sid)),
            "has_m2m": os.path.isdir(pm.m2m(sid)),
            "n_simulations": len(pm.list_simulations(sid)),
        }
        if _has_sourcedata_raw(pm, sid):
            row["has_sourcedata"] = True
        rows.append(row)
    return rows


def list_simulations(pm: PathManager, sid: str) -> list[dict] | None:
    """Simulations of *sid* (``TI/`` and ``mTI/`` presence), ``None`` if unknown."""
    if sid not in subject_ids(pm):
        return None
    items: list[dict] = []
    for name in pm.list_simulations(sid):
        item = {
            "name": name,
            "path": pm.simulation(sid, name),
            "has_ti": os.path.isdir(os.path.dirname(pm.ti_mesh_dir(sid, name))),
            "has_mti": os.path.isdir(os.path.dirname(pm.mti_mesh_dir(sid, name))),
        }
        # The v1 contract enriches every list item with the SimulationDetail keys (fields,
        # montages, niftis, meshes, ...); the v0 keys above always win. Found on real data:
        # the Results page crashed on ``fields`` missing from the list shape.
        try:
            detail = simulation_detail(pm, sid, name) or {}
        except (
            Exception
        ):  # pragma: no cover - a broken run dir must not hide the others
            detail = {}
        for key, value in detail.items():
            item.setdefault(key, value)
        items.append(item)
    return items


# ── small shared helpers ─────────────────────────────────────────────────────


def _mtime_iso(path: str) -> str:
    """*path*'s mtime as an ISO-8601 UTC timestamp (``created`` fallback)."""
    try:
        ts = os.path.getmtime(path)
    except OSError:
        ts = time.time()
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _read_json(path: str) -> dict | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _read_csv_table(path: str) -> dict[str, Any]:
    """A CSV file as ``{"columns": [...], "rows": [[...], ...]}``."""
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return {"columns": [], "rows": []}
    columns, *data = rows
    return {"columns": columns, "rows": data}


_ARTIFACT_KIND_BY_EXT = {".png": "image", ".csv": "csv", ".json": "json", ".pdf": "pdf"}
_MANIFEST_FILENAMES = {"flex_meta.json", "run_config.json"}


def _dir_artifacts(root: str, *, max_depth: int = 3) -> list[dict]:
    """PNG/CSV/JSON files under *root* (shallow-recursive) as ``Artifact`` dicts.

    Shared by :func:`flex_runs` and :func:`ex_runs` for the v1 ``artifacts``
    array (Pareto-front/convergence/skin-visualization PNGs,
    ``final_output.csv``, the ``flex_meta.json``/``run_config.json``
    manifest) -- run outputs the Results/Optimizer pages list directly
    instead of only a "reveal in folder" link. Recursion is bounded because
    flex-search's ``detailed_results/`` and per-electrode-array PNGs can
    nest a few levels deep (see ``tit/opt/flex/builder.py``'s candidate
    paths); anything deeper is not worth surfacing as a top-level artifact.
    """
    out: list[dict] = []
    if not os.path.isdir(root):
        return out
    root_depth = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        if dirpath.rstrip(os.sep).count(os.sep) - root_depth >= max_depth:
            dirnames[:] = []
            continue
        for name in sorted(filenames):
            ext = os.path.splitext(name)[1].lower()
            kind = _ARTIFACT_KIND_BY_EXT.get(ext)
            if kind is None:
                continue
            if name in _MANIFEST_FILENAMES:
                kind = "manifest"
            label = os.path.splitext(name)[0].replace("_", " ")
            out.append(
                {"path": os.path.join(dirpath, name), "kind": kind, "label": label}
            )
    return sorted(out, key=lambda a: a["path"])


def _has_ct(pm: PathManager, sid: str) -> bool:
    """CT as a local BIDS extension: ``anat/sub-<id>_ct.nii(.gz)``."""
    anat_dir = pm.bids_anat(sid)
    if not os.path.isdir(anat_dir):
        return False
    return any(
        name.endswith(("_ct.nii.gz", "_ct.nii")) for name in os.listdir(anat_dir)
    )


# ── subject / simulation detail ──────────────────────────────────────────────


def subject_detail(pm: PathManager, sid: str) -> dict | None:
    """Full detail for one subject, ``None`` if unknown.

    "Unknown" also admits a sourcedata-only subject (see
    :func:`sourcedata_only_subject_ids`) -- the Subjects page fetches this
    for every row :func:`list_subjects` returns, sourcedata-only rows
    included, and a 404 there would just blank the detail pane rather than
    error, but there is real information to return (``has_sourcedata``) so
    it is returned rather than dropped.
    """
    if sid not in subject_ids(pm) and sid not in sourcedata_only_subject_ids(pm):
        return None
    has_m2m = os.path.isdir(pm.m2m(sid))
    # Only caps that carry electrodes: see :func:`_eeg_caps_with_electrodes`.
    eeg_nets_list = [n for n, _ in _eeg_caps_with_electrodes(pm, sid)] if has_m2m else []
    has_leadfields: list[str] = []
    if has_m2m:
        try:
            from tit.opt.leadfield import LeadfieldGenerator

            has_leadfields = sorted(
                {
                    f"{net}.csv"
                    for net, _, _ in LeadfieldGenerator(subject_id=sid).list_leadfields(
                        sid
                    )
                }
            )
        except OSError:
            has_leadfields = []
    return {
        "id": sid,
        "has_raw": os.path.isdir(pm.bids_subject(sid)),
        "has_fastsurfer": os.path.isdir(pm.fastsurfer_subject(sid)),
        "has_freesurfer": os.path.isdir(pm.freesurfer_subject(sid)),
        "has_m2m": has_m2m,
        "n_simulations": len(pm.list_simulations(sid)),
        "m2m_path": pm.m2m(sid) if has_m2m else None,
        "eeg_nets": eeg_nets_list,
        "has_leadfields": has_leadfields,
        "has_dwi": os.path.isdir(pm.bids_dwi(sid)),
        "has_ct": _has_ct(pm, sid),
        "has_sourcedata": _has_sourcedata_raw(pm, sid),
    }


_MODE_DIRS = ("mTI", "TI")
_TISSUE_PREFIXES = ("grey_", "white_", "csf_", "bone_", "skin_", "eyes_")
_FIELD_RE = re.compile(r"_(TI_max|TI_normal|TI_focality|magnE)(?:\.nii)")


def _strip_tissue_prefix(basename: str) -> tuple[str, str | None]:
    for prefix in _TISSUE_PREFIXES:
        if basename.startswith(prefix):
            return basename[len(prefix) :], prefix.rstrip("_")
    return basename, None


def _guess_field(rest: str) -> str:
    stem = re.sub(r"\.nii(\.gz)?$", "", rest)
    tokens = stem.split("_")
    return tokens[-1] if tokens else stem


def _mode_niftis(mode_dir: str) -> list[dict]:
    niftis_dir = os.path.join(mode_dir, "niftis")
    out: list[dict] = []
    if not os.path.isdir(niftis_dir):
        return out
    for path in sorted(glob.glob(os.path.join(niftis_dir, "*.nii*"))):
        basename = os.path.basename(path)
        if "TDCS" in basename:
            continue
        rest, tissue = _strip_tissue_prefix(basename)
        space = "mni" if "_MNI" in basename else "subject"
        match = _FIELD_RE.search(rest)
        field = match.group(1) if match else _guess_field(rest)
        out.append({"path": path, "field": field, "space": space, "tissue": tissue})
    return out


def _hf_niftis(hf_dir: str) -> list[dict]:
    out = []
    for path in sorted(glob.glob(os.path.join(hf_dir, "*_scalar_*magnE.nii.gz"))):
        basename = os.path.basename(path)
        space = "mni" if "_MNI" in basename else "subject"
        out.append({"path": path, "field": "magnE", "space": space, "tissue": None})
    return out


def _dir_meshes(mesh_dir: str, kind: str) -> list[dict]:
    return [
        {"path": path, "kind": kind}
        for path in sorted(glob.glob(os.path.join(mesh_dir, "*.msh")))
    ]


def _report_ids_for_simulation(all_reports: list[dict], sim: str) -> list[str]:
    """Best-effort match of report ids to a simulation.

    Report filenames (``<prefix>_report_<timestamp>.html``) do not embed the
    simulation name today, so this only matches reports a future generator
    tags by path; it returns ``[]`` harmlessly otherwise (see the module
    docstring / this lane's final report for the gap).
    """
    needle = sim.lower()
    return [r["id"] for r in all_reports if needle in r["path"].lower()]


def simulation_detail(pm: PathManager, sid: str, sim: str) -> dict | None:
    """Full detail for one simulation, ``None`` if unknown."""
    if sid not in subject_ids(pm) or sim not in pm.list_simulations(sid):
        return None
    sim_dir = pm.simulation(sid, sim)
    has_ti = os.path.isdir(os.path.dirname(pm.ti_mesh_dir(sid, sim)))
    has_mti = os.path.isdir(os.path.dirname(pm.mti_mesh_dir(sid, sim)))
    config = _read_json(os.path.join(sim_dir, "documentation", "config.json")) or {}
    montage_name = config.get("montage_name") or sim

    niftis: list[dict] = []
    meshes: list[dict] = []
    for mode in _MODE_DIRS:
        mode_dir = os.path.join(sim_dir, mode)
        if not os.path.isdir(mode_dir):
            continue
        niftis.extend(_mode_niftis(mode_dir))
        meshes.extend(_dir_meshes(os.path.join(mode_dir, "mesh"), "field"))
        meshes.extend(
            _dir_meshes(os.path.join(mode_dir, "mesh", "surfaces"), "surface")
        )
    hf_dir = os.path.join(sim_dir, "high_Frequency")
    if os.path.isdir(os.path.join(hf_dir, "niftis")):
        niftis.extend(_hf_niftis(os.path.join(hf_dir, "niftis")))
    if os.path.isdir(os.path.join(hf_dir, "mesh")):
        meshes.extend(_dir_meshes(os.path.join(hf_dir, "mesh"), "high_frequency"))

    fields = sorted({n["field"] for n in niftis if n["field"]})
    spaces = sorted({n["space"] for n in niftis})
    all_reports = reports(pm, sid) or []
    return {
        "name": sim,
        "path": sim_dir,
        "has_ti": has_ti,
        "has_mti": has_mti,
        "montages": [montage_name],
        "fields": fields,
        "space": spaces,
        "report_ids": _report_ids_for_simulation(all_reports, sim),
        "niftis": niftis,
        "meshes": meshes,
    }


def electrode_overlays(pm: PathManager, sid: str, sim: str) -> list[dict] | None:
    """Electrode-overlay NIfTI presence for one simulation, per TI/mTI mode.

    ``None`` if the subject/simulation is unknown. This is the listing half
    of the electrode-overlay v1 gap documented in
    ``tit/server/routes/viewers.py`` and ``pages/viewer/PARITY.md`` #1:
    creating the overlay is a ``tools`` job
    (``tit.tools.electrode_overlay``), and once it exists on disk,
    :func:`tit.viewspec._electrode_overlay_layer` already picks it up for
    ``kind=simulation`` ViewSpecs -- this endpoint just tells the Viewer page
    whether that file is there yet (and its path), without a separate job
    kind or catalog change for the overlay-*building* side.
    """
    if sid not in subject_ids(pm) or sim not in pm.list_simulations(sid):
        return None
    sim_dir = pm.simulation(sid, sim)
    out = []
    for mode in _MODE_DIRS:
        path = os.path.join(
            sim_dir, mode, "montage_imgs", "electrode_overlay_subject.nii.gz"
        )
        out.append({"mode": mode, "path": path, "exists": os.path.isfile(path)})
    return out


# ── montages ─────────────────────────────────────────────────────────────────


def get_montages(pm: PathManager) -> dict:
    """``montage_list.json``, reshaped to the v1 ``Montages`` schema.

    ``pm`` is accepted for interface symmetry with the rest of this module;
    :mod:`tit.sim.utils` reads/writes through the process-wide PathManager
    singleton (the same instance in practice, since the server sets it once
    at startup).
    """
    from tit.sim.utils import load_montage_data

    data = load_montage_data()
    nets = {
        net: {
            "uni_polar": entry.get("uni_polar_montages", {}),
            "multi_polar": entry.get("multi_polar_montages", {}),
        }
        for net, entry in data.get("nets", {}).items()
    }
    return {"nets": nets}


def put_montage(
    pm: PathManager, net: str, kind: str, name: str, pairs: list[list[str]]
) -> list[list[str]]:
    """Create or overwrite one montage; returns *pairs* back."""
    if not is_safe_name(name):
        raise ValueError(
            "name must match ^[A-Za-z0-9_-]{1,64}$ (no path separators or '..')"
        )
    from tit.sim.utils import upsert_montage

    mode = "U" if kind == "uni_polar" else "M"
    upsert_montage(
        eeg_net=net,
        montage_name=name,
        electrode_pairs=[list(pair) for pair in pairs],
        mode=mode,
    )
    return pairs


def delete_montage(pm: PathManager, net: str, kind: str, name: str) -> bool:
    """Delete one montage; ``False`` if it did not exist."""
    from tit.sim.utils import load_montage_data, save_montage_data

    data = load_montage_data()
    key = "uni_polar_montages" if kind == "uni_polar" else "multi_polar_montages"
    montages = data.get("nets", {}).get(net, {}).get(key, {})
    if name not in montages:
        return False
    del montages[name]
    save_montage_data(data)
    return True


# ── EEG nets ─────────────────────────────────────────────────────────────────


def _read_cap_electrode_labels(path: str) -> list[str]:
    """Electrode labels from an EEG cap CSV (``Electrode,x,y,z,label`` rows)."""
    labels: list[str] = []
    try:
        with open(path, newline="") as f:
            for row in csv.reader(f):
                if len(row) >= 5 and row[0].strip().lower() == "electrode":
                    labels.append(row[4].strip())
    except OSError:
        return []
    return labels


def _eeg_caps_with_electrodes(pm: PathManager, sid: str) -> list[tuple[str, list[str]]]:
    """Cap files under the subject's ``eeg_positions`` that carry at least one electrode.

    ``m2m_<sid>/eeg_positions`` also holds ``Fiducials.csv``, whose rows are all
    ``Fiducial`` (Nz/Iz/LPA/RPA) and never ``Electrode``. It is a registration
    landmark file, not an EEG net: nothing can be placed from it, no leadfield
    can be built on it, and a flex run mapped onto it resolves to no labels. It
    was nevertheless offered everywhere a net is chosen, where picking it left
    the row permanently unrunnable with nothing said. A cap with no electrodes
    is not a net, so it is not listed as one.
    """
    out: list[tuple[str, list[str]]] = []
    for cap_name in pm.list_eeg_caps(sid):
        electrodes = _read_cap_electrode_labels(
            os.path.join(pm.eeg_positions(sid), cap_name)
        )
        if electrodes:
            out.append((cap_name, electrodes))
    return out


def eeg_nets(pm: PathManager, sid: str) -> list[dict] | None:
    """EEG nets available to *sid*, with electrode labels; ``None`` if unknown."""
    if sid not in subject_ids(pm):
        return None
    return [
        {"name": name, "electrodes": electrodes, "n": len(electrodes)}
        for name, electrodes in _eeg_caps_with_electrodes(pm, sid)
    ]


# ── atlases / regions ────────────────────────────────────────────────────────


def atlases(
    pm: PathManager, sid: str, space: str | None = None, kind: str | None = None
) -> list[dict] | None:
    """Atlases available to *sid*; ``None`` if the subject is unknown."""
    if sid not in subject_ids(pm):
        return None
    space = (space or "subject").lower()
    out: list[dict] = []

    if kind in (None, "cortical") and space == "subject":
        seg_dir = os.path.join(pm.m2m(sid), "segmentation")
        mesh_mgr = MeshAtlasManager(seg_dir)
        for name in mesh_mgr.list_atlases():
            lh_path = mesh_mgr.find_atlas_file(name, "lh")
            out.append(
                {
                    "id": name,
                    "name": name,
                    "path": lh_path or "",
                    "hemispheres": ["lh", "rh"],
                }
            )

    if kind in (None, "subcortical"):
        if space == "mni":
            for path in VoxelAtlasManager.detect_mni_atlases(mni_resources_dir()):
                name = os.path.basename(path)
                out.append({"id": name, "name": name, "path": path})
        else:
            seg_dir = os.path.join(pm.m2m(sid), "segmentation")
            voxel_mgr = VoxelAtlasManager(
                fastsurfer_mri_dir=pm.fastsurfer_mri(sid),
                freesurfer_mri_dir=pm.freesurfer_mri(sid),
                seg_dir=seg_dir,
                masks_dir=pm.masks(sid),
            )
            for display_name, path in voxel_mgr.list_atlases():
                entry: dict = {"id": display_name, "name": display_name, "path": path}
                hemi = VOXEL_ATLASES.get(display_name)
                if hemi in ("lh", "rh"):
                    entry["hemispheres"] = [hemi]
                out.append(entry)

    return out


def atlas_regions(
    pm: PathManager, sid: str, atlas_id: str, hemi: str | None = None
) -> list[dict] | None:
    """Regions of *atlas_id* for *sid*; ``None`` if the subject/atlas is unknown.

    Per the reconciled v1 ``Region`` schema: for a cortical (surface/annotation)
    atlas, ``id`` is the FreeSurfer ``.annot`` label index *within that
    region's own hemisphere file* -- exactly the integer
    ``FlexConfig.AtlasROI.label`` / ``ExConfig``'s equivalent needs, resolved
    the same way :func:`tit.opt.roi_spec.resolve_cortical_region_index_map`
    does -- and ``hemi`` is that region's hemisphere. For a subcortical
    (volumetric) atlas, ``id`` is the voxel label value and ``hemi`` is
    ``None`` (a region whose label cannot be parsed as an integer is dropped
    rather than returned with a non-conforming id).
    """
    if sid not in subject_ids(pm):
        return None
    seg_dir = os.path.join(pm.m2m(sid), "segmentation")

    mesh_mgr = MeshAtlasManager(seg_dir)
    if atlas_id in mesh_mgr.list_atlases():
        hemis = ("lh", "rh") if hemi in (None, "both") else (hemi,)
        out: list[dict] = []
        for h in hemis:
            annot_path = mesh_mgr.find_atlas_file(atlas_id, h)
            if not annot_path:
                continue
            for index, name in mesh_mgr.list_annot_regions(annot_path):
                if name == "unknown":
                    continue
                out.append({"id": index, "name": name, "hemi": h})
        return out

    voxel_mgr = VoxelAtlasManager(
        fastsurfer_mri_dir=pm.fastsurfer_mri(sid),
        freesurfer_mri_dir=pm.freesurfer_mri(sid),
        seg_dir=seg_dir,
        masks_dir=pm.masks(sid),
    )
    atlas_path = dict(voxel_mgr.list_atlases()).get(atlas_id)
    if atlas_path is None:
        candidate = os.path.join(mni_resources_dir(), atlas_id)
        if os.path.isfile(candidate):
            atlas_path = candidate
    if atlas_path is None:
        return None

    entries = voxel_mgr.list_regions(atlas_path)
    out = []
    for entry in entries:
        try:
            region_id = parse_region_label(entry)
        except ValueError:
            continue  # non-integer label: cannot satisfy Region.id: integer
        name = re.sub(r"\s*\(ID:\s*-?\d+\)\s*$", "", entry)
        out.append({"id": region_id, "name": name, "hemi": None})
    return out


def nifti_labels(pm: PathManager, sid: str, path: str | None = None) -> list[dict] | None:
    """Unique integer labels present in one label volume, named where a LUT applies.

    The 3D Visual Exporter's sub-cortical mode asks the user for label *numbers*
    (``10,49``); 2.5.0 answered that with a Qt dialog that parsed a FreeSurfer LUT
    itself. This is that browser's data, from the toolbox's own segstats path
    (:func:`tit.atlas.segstats.compute_segstats` +
    :func:`~tit.atlas.segstats.resolve_lut_for_atlas`), which also writes the
    ``<name>_labels.txt`` sidecar cache beside the volume -- so the first call on a
    subject pays for the scan and every later one reads the cache, same as
    :meth:`VoxelAtlasManager.list_regions`.

    Parameters
    ----------
    pm : PathManager
    sid : str
        Subject whose ``m2m`` holds the default volume.
    path : str or None
        A specific label volume. ``None``/empty means the subject's own
        ``<m2m>/segmentation/labeling.nii.gz`` -- the sub-cortical mode's default,
        and the only path the panel ever sends for an untouched form.

    Returns
    -------
    list of dict or None
        ``[{"id": int, "name": str, "n_voxels": int}]`` sorted by ``id``; ``None``
        for an unknown subject, a path outside the project jail, or a file that is
        not there. The caller (``routes/catalog_v1``) turns ``None`` into a 404 --
        deliberately one status for all three, so probing this route cannot tell a
        file that exists outside the jail from one that does not exist at all.
    """
    if sid not in subject_ids(pm):
        return None

    raw = (path or "").strip()
    if not raw:
        m2m = pm.m2m(sid)
        if not m2m:
            return None
        raw = os.path.join(m2m, "segmentation", "labeling.nii.gz")

    from tit.viewspec import resolve_jailed

    resolved = resolve_jailed(raw)
    if resolved is None:
        return None

    cached = _read_segstats_sum(_segstats_sidecar(str(resolved)))
    if cached is not None:
        return cached

    from tit.atlas.segstats import (
        compute_segstats,
        resolve_lut_for_atlas,
        write_segstats_sum,
    )

    try:
        lut = resolve_lut_for_atlas(str(resolved))
        stats = compute_segstats(str(resolved), lut)
    except (OSError, ValueError):
        # An unreadable or non-label volume is "nothing to browse", not a 500: the
        # path came from a text field the user can type anything into.
        return None
    try:
        write_segstats_sum(stats, _segstats_sidecar(str(resolved)))
    except OSError:
        # A read-only project still gets its answer -- it just pays for the scan again.
        pass
    return [
        {"id": int(s.seg_id), "name": s.name, "n_voxels": int(s.n_voxels)}
        for s in stats
    ]


def _segstats_sidecar(volume_path: str) -> str:
    """``<dir>/<name>_labels.txt`` -- the cache filename ``VoxelAtlasManager`` already uses."""
    bname = os.path.splitext(os.path.basename(volume_path))[0]
    if bname.endswith(".nii"):
        bname = os.path.splitext(bname)[0]
    return os.path.join(os.path.dirname(volume_path), f"{bname}_labels.txt")


def _read_segstats_sum(labels_file: str) -> list[dict] | None:
    """Parse an ``mri_segstats --sum`` sidecar; ``None`` if it is not there or is unusable.

    Same file and columns (``Index SegId NVoxels Volume_mm3 StructName``) as
    :meth:`VoxelAtlasManager._parse_labels_file`, which throws the voxel count away --
    kept here because the size of a label is exactly what tells a real structure from a
    stray voxel when you are picking one out of a hundred.
    """
    if not os.path.isfile(labels_file):
        return None
    out: list[dict] = []
    try:
        with open(labels_file) as fh:
            for line in fh:
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.split()
                if len(parts) < 5:
                    continue
                try:
                    seg_id = int(parts[1])
                    n_voxels = int(parts[2])
                except ValueError:
                    continue
                out.append(
                    {"id": seg_id, "name": " ".join(parts[4:]), "n_voxels": n_voxels}
                )
    except OSError:
        return None
    if not out:
        return None
    return sorted(out, key=lambda r: r["id"])


# ── ROIs ─────────────────────────────────────────────────────────────────────

# User-supplied identifiers that become filename components (ROI names,
# free-hand config names, montage names) -- traversal segments (``..``),
# path separators, and NUL are the concrete attack this blocks (a name of
# ``../../../../outside/escaped`` previously escaped the project entirely;
# see ``contracts/SCHEMA-CHANGES.md``). Deliberately conservative: callers
# needing a friendlier display name should map it to one of these first.
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def is_safe_name(name: Any) -> bool:
    """``True`` if *name* is safe to use as a filename component.

    Used for ROI names, free-hand config names, and montage names on every
    write path -- never trust a client-supplied string used to build a path.
    """
    return isinstance(name, str) and bool(_SAFE_NAME_RE.match(name))


def as_float(value: Any, field_name: str) -> float:
    """Coerce *value* to ``float``; raises ``ValueError`` naming the field on failure.

    ``bool`` is rejected even though ``isinstance(True, int)`` is ``True`` in
    Python -- a checkbox value has no business landing in a coordinate.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{field_name} must be a number")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc


def list_rois(pm: PathManager, sid: str) -> list[dict] | None:
    """Saved ROIs for *sid*; ``None`` if the subject is unknown."""
    if sid not in subject_ids(pm):
        return None
    from tit.opt.ex.roi import read_roi_center

    roi_dir = pm.rois(sid)
    if not os.path.isdir(roi_dir):
        return []
    out = []
    for name in sorted(os.listdir(roi_dir)):
        if not name.endswith(".csv"):
            continue
        try:
            x, y, z = read_roi_center(os.path.join(roi_dir, name))[:3]
        except (OSError, ValueError):
            continue
        roi_name = name[: -len(".csv")]
        space = "mni" if roi_name.upper().endswith("_MNI") else "subject"
        out.append({"name": roi_name, "x": x, "y": y, "z": z, "space": space})
    return out


def create_roi(pm: PathManager, sid: str, roi: dict) -> dict:
    """Save a new spherical ROI centre for *sid* (subject-space CSV convention).

    Mirrors :meth:`tit.opt.ex.engine.ExSearchEngine.create_roi` (a plain
    ``x,y,z`` row plus a ``roi_list.txt`` entry) rather than importing it, so
    this module stays the single writer of the CRUD shape the v1 contract
    expects (radius/space are accepted but not persisted -- the CSV format
    has never carried them; see this lane's final report).
    """
    name = str(roi["name"])
    if not is_safe_name(name):
        raise ValueError(
            "name must match ^[A-Za-z0-9_-]{1,64}$ (no path separators or '..')"
        )
    x = as_float(roi["x"], "x")
    y = as_float(roi["y"], "y")
    z = as_float(roi["z"], "z")
    radius = roi.get("radius")
    if radius is not None:
        radius = as_float(radius, "radius")

    roi_dir = pm.rois(sid)
    os.makedirs(roi_dir, exist_ok=True)
    filename = f"{name}.csv"
    base_name = name

    with open(os.path.join(roi_dir, filename), "w", newline="") as f:
        csv.writer(f).writerow([x, y, z])

    roi_list = os.path.join(roi_dir, "roi_list.txt")
    existing = []
    if os.path.isfile(roi_list):
        existing = [line.strip() for line in open(roi_list) if line.strip()]
    if filename not in existing:
        with open(roi_list, "a") as f:
            f.write(f"{filename}\n")

    space = "mni" if base_name.upper().endswith("_MNI") else "subject"
    return {
        "name": base_name,
        "x": x,
        "y": y,
        "z": z,
        "space": roi.get("space", space),
        "radius": radius,
    }


def delete_roi(pm: PathManager, sid: str, name: str) -> bool:
    """Delete one saved ROI; ``False`` if it did not exist (also if *name* is unsafe)."""
    if not is_safe_name(name):
        return False
    roi_dir = pm.rois(sid)
    filename = name if name.endswith(".csv") else f"{name}.csv"
    roi_path = os.path.join(roi_dir, filename)
    existed = os.path.isfile(roi_path)
    if existed:
        os.remove(roi_path)

    roi_list = os.path.join(roi_dir, "roi_list.txt")
    if os.path.isfile(roi_list):
        lines = [line.strip() for line in open(roi_list) if line.strip()]
        if filename in lines:
            lines.remove(filename)
            with open(roi_list, "w") as f:
                f.write("\n".join(lines) + ("\n" if lines else ""))
    return existed


# ── leadfields ───────────────────────────────────────────────────────────────


def list_leadfields(pm: PathManager, sid: str) -> list[dict] | None:
    """Precomputed leadfields for *sid*; ``None`` if the subject is unknown."""
    if sid not in subject_ids(pm):
        return None
    from tit.opt.leadfield import LeadfieldGenerator

    out = []
    for net, path, _size_gb in LeadfieldGenerator(subject_id=sid).list_leadfields(sid):
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        out.append(
            {
                "net": net,
                "path": path,
                "exists": os.path.isfile(path),
                "size_bytes": size,
            }
        )
    return out


# ── flex-search runs ─────────────────────────────────────────────────────────


def _pair_by_channel(electrodes: list, channel_array_indices: list | None) -> list[list]:
    """Group *electrodes* into ``[a, b]`` pairs, one pair per stimulation channel.

    ``channel_array_indices`` is flex-search's own ``[[channel, array], ...]``
    bookkeeping (``electrode_positions.json`` / ``electrode_mapping_*.json``):
    entry *i* says which channel and which of that channel's two arrays
    electrode *i* belongs to. When it is missing or unusable the electrodes are
    paired consecutively, which is what ``resolve_flex_montage`` does.
    """
    if isinstance(channel_array_indices, list) and len(channel_array_indices) == len(
        electrodes
    ):
        by_channel: dict = {}
        ok = True
        for electrode, idx in zip(electrodes, channel_array_indices):
            if not isinstance(idx, (list, tuple)) or len(idx) != 2:
                ok = False
                break
            by_channel.setdefault(idx[0], []).append((idx[1], electrode))
        if ok:
            pairs = []
            for channel in sorted(by_channel):
                members = [e for _, e in sorted(by_channel[channel], key=lambda t: t[0])]
                if len(members) != 2:
                    pairs = []
                    break
                pairs.append(list(members))
            if pairs:
                return pairs
    return [
        [electrodes[i], electrodes[i + 1]] for i in range(0, len(electrodes) - 1, 2)
    ]


def _read_json(path: str) -> dict | None:
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _flex_mappings(run_dir: str) -> list[dict]:
    """EEG-label pairs already mapped for this run, one entry per net.

    Reads the ``electrode_mapping_<net>.json`` files
    :func:`tit.sim.montage_sources.resolve_flex_montage` writes; purely
    read-only, so a run that has never been mapped simply reports none.
    """
    out: list[dict] = []
    try:
        names = sorted(os.listdir(run_dir))
    except OSError:
        return out
    for name in names:
        if not (name.startswith("electrode_mapping_") and name.endswith(".json")):
            continue
        data = _read_json(os.path.join(run_dir, name))
        if data is None:
            continue
        labels = [
            label
            for label in data.get("mapped_labels") or []
            if isinstance(label, str)
        ]
        if len(labels) < 4:
            continue
        net = data.get("eeg_net")
        if not isinstance(net, str) or not net:
            net = name[len("electrode_mapping_") : -len(".json")] + ".csv"
        out.append(
            {
                "eeg_net": net,
                "pairs": _pair_by_channel(labels, data.get("channel_array_indices")),
            }
        )
    return out


def _flex_optimized_pairs(run_dir: str) -> list[list] | None:
    """The run's free (un-mapped) XYZ electrode pairs, or ``None``.

    ``electrode_positions.json`` is written by every flex-search run, which is
    what makes a run selectable in the Simulator even when it has never been
    mapped onto an EEG net (``Montage.Mode.FLEX_FREE``).
    """
    data = _read_json(os.path.join(run_dir, "electrode_positions.json"))
    if data is None:
        return None
    positions = [
        p
        for p in data.get("optimized_positions") or []
        if isinstance(p, (list, tuple)) and len(p) == 3
    ]
    if len(positions) < 4:
        return None
    return _pair_by_channel(
        [list(p) for p in positions], data.get("channel_array_indices")
    )


def flex_runs(pm: PathManager, sid: str) -> list[dict] | None:
    """Flex-search runs for *sid*; ``None`` if the subject is unknown."""
    if sid not in subject_ids(pm):
        return None
    from tit.opt.flex.manifest import read_manifest

    out = []
    for name in pm.list_flex_search_runs(sid):
        run_dir = pm.flex_search_run(sid, name)
        manifest = read_manifest(run_dir)
        if manifest is None:  # no flex_meta.json: ignore, per the plan
            continue
        out.append(
            {
                "name": name,
                "path": run_dir,
                "goal": manifest.get("goal", ""),
                "roi": manifest.get("roi") or {},
                "created": manifest.get("created") or _mtime_iso(run_dir),
                "manifest": manifest,
                # The electrodes the run actually produced. `flex_meta.json` records
                # none of them, so a client that reads only `manifest` has no way to
                # turn a run into a `Montage` for submission (simulator PARITY.md #4).
                "mappings": _flex_mappings(run_dir),
                "optimized": _flex_optimized_pairs(run_dir),
                "artifacts": _dir_artifacts(run_dir),
            }
        )
    return out


# ── ex / mex-search runs ─────────────────────────────────────────────────────


def _net_from_leadfield_hdf(leadfield_hdf: str) -> str:
    """``<net>.csv`` from a leadfield hdf5 path (``<net>_leadfield.hdf5`` etc.)."""
    stem = os.path.splitext(os.path.basename(leadfield_hdf))[0]
    if "_leadfield_" in stem:
        net = stem.split("_leadfield_", 1)[-1]
    elif stem.endswith("_leadfield"):
        net = stem[: -len("_leadfield")]
    else:
        net = stem
    return net if net.endswith(".csv") else f"{net}.csv"


def _ex_best(run_dir: str) -> dict | None:
    """Highest-``Composite_Index`` row of ``final_output.csv``, or ``None``."""
    csv_path = os.path.join(run_dir, "final_output.csv")
    if not os.path.isfile(csv_path):
        return None
    best_montage, best_score = None, None
    try:
        with open(csv_path, newline="") as f:
            for row in csv.DictReader(f):
                try:
                    score = float(row["Composite_Index"])
                except (KeyError, ValueError, TypeError):
                    continue
                if best_score is None or score > best_score:
                    best_score, best_montage = score, row.get("Montage")
    except OSError:
        return None
    if best_montage is None or best_score is None:
        return None
    return {"montage": best_montage, "score": best_score}


def ex_runs(pm: PathManager, sid: str, kind: str = "ex") -> list[dict] | None:
    """Ex/mEx-search runs for *sid*; ``None`` if the subject is unknown."""
    if sid not in subject_ids(pm):
        return None
    root = pm.ex_search(sid) if kind == "ex" else pm.m_ex_search(sid)
    if not os.path.isdir(root):
        return []
    out = []
    for entry in sorted(os.scandir(root), key=lambda e: e.name):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        run_config = _read_json(os.path.join(entry.path, "run_config.json"))
        if run_config is None:  # no run_config.json: ignore, per the plan
            continue
        out.append(
            {
                "run_name": entry.name,
                "path": entry.path,
                "eeg_net": _net_from_leadfield_hdf(run_config.get("leadfield_hdf", "")),
                "created": _mtime_iso(entry.path),
                "best": _ex_best(entry.path),
                "artifacts": _dir_artifacts(entry.path),
            }
        )
    return out


def ex_run_results(pm: PathManager, sid: str, kind: str, run: str) -> dict | None:
    """Full ``final_output.csv`` of one ex/mEx run, as ``TableData``."""
    if sid not in subject_ids(pm):
        return None
    root = pm.ex_search_run(sid, run) if kind == "ex" else pm.m_ex_search_run(sid, run)
    csv_path = os.path.join(root, "final_output.csv")
    if not os.path.isfile(csv_path):
        return None
    return _read_csv_table(csv_path)


# ── analyses ─────────────────────────────────────────────────────────────────


def _analysis_entry(path: str, name: str) -> dict | None:
    json_path = os.path.join(path, "analysis.json")
    csv_path = os.path.join(path, "results.csv")
    if not (os.path.isfile(json_path) and os.path.isfile(csv_path)):
        return None
    meta = _read_json(json_path) or {}
    field = meta.get("field_name") or ""
    regions = meta.get("regions") or []
    roi = "+".join(regions) if regions else (meta.get("atlas") or "")
    space = (
        "mni" if str(meta.get("coordinate_space") or "").lower() == "mni" else "subject"
    )
    msh = next(iter(glob.glob(os.path.join(path, "*.msh"))), None)
    nifti = os.path.join(path, "roi_overlay.nii.gz")
    if not os.path.isfile(nifti):
        matches = glob.glob(os.path.join(path, "*.nii*"))
        nifti = matches[0] if matches else None
    pdf = next(iter(glob.glob(os.path.join(path, "*.pdf"))), None)
    return {
        "name": name,
        "space": space,
        "field": field,
        "roi": roi,
        "csv": csv_path,
        "json": json_path,
        "msh": msh,
        "nifti": nifti,
        "pdf": pdf,
    }


#: The two directories :meth:`PathManager.analysis_dir` writes into. An analysis found
#: directly under one of them keeps its bare directory name (what every existing client
#: and URL already uses); one found anywhere else under the simulation is named by its
#: path relative to the simulation directory.
_ANALYSIS_SPACE_DIRS = ("Mesh", "Voxel")

#: What a path separator becomes in a non-standard analysis's name. A name is a URL path
#: segment -- ``GET /api/catalog/analyses/{name}/summary`` -- and a ``/`` inside it cannot
#: survive that trip: percent-encoded by the client, the ASGI server decodes ``%2F`` back
#: to ``/`` before routing, so the request misses the route entirely and the server answers
#: the router's ``{"detail":"Not found"}`` rather than the handler's own message (measured
#: against the dev container, 2026-09-03). Two segments joined by this can only be confused
#: with a directory whose own name contains it, which no analyzer run produces.
_ANALYSIS_NAME_SEP = "__"


def _find_analysis_dirs(sim_dir: str) -> list[tuple[str, str, bool]]:
    """Every analysis directory under *sim_dir*, as ``(path, name, is_standard)``.

    An analysis is a directory holding both ``analysis.json`` and ``results.csv`` -- the
    pair :mod:`tit.analyzer` writes wherever it was told to write, which is the only
    thing that identifies a run on disk. Scanning ``Analyses/Mesh`` and ``Analyses/Voxel``
    alone (what this did before) made every run with a custom ``output_dir`` invisible to
    the app even though the runner had honoured it: ``Analyzer(output_dir=...)`` is a
    documented public argument, so reading what the runner wrote beats forbidding it.

    A found directory is not descended into (an analysis holds no analyses), which also
    keeps the walk to the ~100 entries a real simulation directory has.

    Names: bare directory name under ``Analyses/{Mesh,Voxel}`` (unchanged -- every client
    and every existing ``/summary`` URL keeps working), and elsewhere the path relative to
    the simulation with each separator replaced by :data:`_ANALYSIS_NAME_SEP`, because a
    name has to survive being a URL path segment (see that constant).
    """
    standard_parents = {
        os.path.join(sim_dir, "Analyses", space) for space in _ANALYSIS_SPACE_DIRS
    }
    found: list[tuple[str, str, bool]] = []
    for dirpath, dirnames, filenames in os.walk(sim_dir):
        dirnames.sort()
        if "analysis.json" in filenames and "results.csv" in filenames:
            dirnames.clear()  # an analysis contains no analyses
            if dirpath == sim_dir:
                continue  # the simulation itself is not one of its own analyses
            is_standard = os.path.dirname(dirpath) in standard_parents
            name = (
                os.path.basename(dirpath)
                if is_standard
                else os.path.relpath(dirpath, sim_dir).replace(
                    os.sep, _ANALYSIS_NAME_SEP
                )
            )
            found.append((dirpath, name, is_standard))
    # Standard locations first, in their existing Mesh-then-Voxel-then-name order;
    # anything else after, by name -- so an added custom run never reorders the list a
    # client already knows.
    found.sort(key=lambda item: (not item[2], item[0] if item[2] else item[1]))
    return found


def analyses(pm: PathManager, sid: str, sim: str) -> list[dict] | None:
    """Analyzer runs for *sid*/*sim*; ``None`` if either is unknown."""
    if sid not in subject_ids(pm) or sim not in pm.list_simulations(sid):
        return None
    out = []
    for path, name, _standard in _find_analysis_dirs(pm.simulation(sid, sim)):
        item = _analysis_entry(path, name)
        if item:
            out.append(item)
    return out


def analysis_summary(pm: PathManager, sid: str, sim: str, name: str) -> dict | None:
    """``results.csv`` of one analysis, as ``TableData``.

    *name* is what :func:`analyses` listed; a caller holding the run's own path relative
    to the simulation (``Analyses/Custom/run1``) resolves too, so the one string a script
    already has does not have to be translated into the listed form.
    """
    if sid not in subject_ids(pm) or sim not in pm.list_simulations(sid):
        return None
    sim_dir = pm.simulation(sid, sim)
    for path, found_name, _standard in _find_analysis_dirs(sim_dir):
        relative = os.path.relpath(path, sim_dir).replace(os.sep, "/")
        if name in (found_name, relative):
            return _read_csv_table(os.path.join(path, "results.csv"))
    return None


# ── reports ──────────────────────────────────────────────────────────────────

_REPORT_KIND_TITLES = {
    "simulation_report": "Simulation report",
    "flex_search_report": "Flex-search report",
    "pre_processing_report": "Preprocessing report",
    "ex_search_report": "Ex-search report",
    "m_ex_search_report": "mEx-search report",
    "dti_qc_report": "DTI QC report",
}


def _report_kind_from_stem(stem: str) -> str:
    """``"<kind>_<YYYYMMDD>_<HHMMSS>"`` -> ``"<kind>"``."""
    parts = stem.split("_")
    return "_".join(parts[:-2]) if len(parts) > 2 else stem


def _report_entry(path: str, sid: str) -> dict:
    stem = os.path.splitext(os.path.basename(path))[0]
    kind = _report_kind_from_stem(stem)
    title = _REPORT_KIND_TITLES.get(kind, kind.replace("_", " ").capitalize())
    return {
        "id": f"{sid}/{stem}",
        "kind": kind,
        "title": title,
        "path": path,
        "created": _mtime_iso(path),
    }


def reports(pm: PathManager, sid: str) -> list[dict] | None:
    """Generated HTML reports for *sid*; ``None`` if the subject is unknown."""
    if sid not in subject_ids(pm):
        return None
    root = os.path.join(pm.reports(), f"sub-{sid}")
    if not os.path.isdir(root):
        return []
    return [
        _report_entry(os.path.join(root, name), sid)
        for name in sorted(os.listdir(root))
        if name.endswith(".html")
    ]


def find_report_path(pm: PathManager, report_id: str) -> str | None:
    """Resolve a ``reports()`` ``id`` back to its file path (used by ``/api/files/report``)."""
    if "/" not in report_id:
        return None
    sid, stem = report_id.split("/", 1)
    if any(c in stem for c in ("/", "\\", "..")):
        return None
    path = os.path.join(pm.reports(), f"sub-{sid}", f"{stem}.html")
    return path if os.path.isfile(path) else None


# ── freehand (stim_configs) ──────────────────────────────────────────────────


def _read_freehand_file(path: str) -> dict | None:
    data = _read_json(path)
    if data is None:
        return None
    positions = data.get("electrode_positions") or {}
    return {
        "name": data.get("name") or os.path.splitext(os.path.basename(path))[0],
        "type": data.get("type") or "U",
        "electrode_positions": [
            {"label": label, "x": xyz[0], "y": xyz[1], "z": xyz[2]}
            for label, xyz in positions.items()
        ],
    }


def freehand_configs(pm: PathManager, sid: str) -> list[dict] | None:
    """Saved free-hand electrode configs for *sid*; ``None`` if unknown.

    Reads ``m2m_<id>/stim_configs/*.json``. The on-disk format, written by the
    free-hand electrode placement UI, is
    ``{"name", "type": "U"|"M", "electrode_positions": {label: [x, y, z]}}``.
    The contract's ``FreehandConfig.type`` enum is ``[U, M]`` (unipolar/
    multipolar), matching this on-disk value exactly (fixed from an earlier
    ``xyz``/``label`` enum that matched nothing real -- see
    ``contracts/SCHEMA-CHANGES.md``); ``type`` is passed through verbatim.
    """
    if sid not in subject_ids(pm):
        return None
    stim_dir = os.path.join(pm.m2m(sid), "stim_configs")
    if not os.path.isdir(stim_dir):
        return []
    out = []
    for name in sorted(os.listdir(stim_dir)):
        if not name.endswith(".json"):
            continue
        cfg = _read_freehand_file(os.path.join(stim_dir, name))
        if cfg:
            out.append(cfg)
    return out


def put_freehand_config(pm: PathManager, sid: str, name: str, config: dict) -> dict:
    """Create or overwrite one free-hand electrode configuration."""
    if not is_safe_name(name):
        raise ValueError(
            "name must match ^[A-Za-z0-9_-]{1,64}$ (no path separators or '..')"
        )
    stim_dir = os.path.join(pm.m2m(sid), "stim_configs")
    os.makedirs(stim_dir, exist_ok=True)
    positions = {
        (entry.get("label") or f"E{i + 1}"): [
            as_float(entry["x"], "electrode_positions[].x"),
            as_float(entry["y"], "electrode_positions[].y"),
            as_float(entry["z"], "electrode_positions[].z"),
        ]
        for i, entry in enumerate(config.get("electrode_positions", []))
    }
    data = {
        "name": name,
        "type": config.get("type", "U"),
        "electrode_positions": positions,
    }
    path = os.path.join(stim_dir, f"{name}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return {
        "name": name,
        "type": data["type"],
        "electrode_positions": [
            {"label": label, "x": xyz[0], "y": xyz[1], "z": xyz[2]}
            for label, xyz in positions.items()
        ],
    }


# ── project-level: group catalog, notes, subject-info ──────────────────────


def group_catalog(pm: PathManager) -> dict:
    """Project-level group catalog: stats runs, nilearn visuals, group analyses.

    Directory conventions for the ``nilearn`` and ``group_analyses`` sections
    are a best-effort guess (``derivatives/ti-toolbox/{nilearn_visuals,
    group_analysis}/``) -- unverified against a real project, since Dataset
    000 has neither populated. ``stats`` (``derivatives/ti-toolbox/stats/
    <type>/<name>/``) is confirmed by :meth:`PathManager.stats_output`.
    """

    def _subdirs(root: str) -> list[str]:
        try:
            return sorted(
                n for n in os.listdir(root) if os.path.isdir(os.path.join(root, n))
            )
        except OSError:
            return []

    stats = []
    stats_root = os.path.join(pm.ti_toolbox(), "stats")
    for analysis_type in _subdirs(stats_root):
        if analysis_type == "data":
            continue
        type_dir = os.path.join(stats_root, analysis_type)
        for name in _subdirs(type_dir):
            run_dir = os.path.join(type_dir, name)
            stats.append(
                {
                    "type": analysis_type,
                    "name": name,
                    "path": run_dir,
                    "created": _mtime_iso(run_dir),
                }
            )

    nilearn = []
    nilearn_root = os.path.join(pm.ti_toolbox(), "nilearn_visuals")
    for name in _subdirs(nilearn_root):
        path = os.path.join(nilearn_root, name)
        nilearn.append({"name": name, "path": path, "created": _mtime_iso(path)})

    group_analyses = []
    group_root = os.path.join(pm.ti_toolbox(), "group_analysis")
    for name in _subdirs(group_root):
        path = os.path.join(group_root, name)
        group_analyses.append({"name": name, "path": path, "created": _mtime_iso(path)})

    return {"stats": stats, "nilearn": nilearn, "group_analyses": group_analyses}


def read_notes(pm: PathManager) -> dict:
    """Quick Notes content (``derivatives/ti-toolbox/notes.txt``)."""
    path = os.path.join(pm.ti_toolbox(), "notes.txt")
    if not os.path.isfile(path):
        return {"text": "", "updated_at": None}
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return {"text": text, "updated_at": _mtime_iso(path)}


def write_notes(pm: PathManager, text: str) -> dict:
    """Replace Quick Notes content, atomically."""
    path = os.path.join(pm.ti_toolbox(), "notes.txt")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    return {"text": text, "updated_at": _mtime_iso(path)}


def subject_info_matrix(pm: PathManager) -> dict:
    """Presence matrix (subject x data-stage) across the whole project."""
    columns = [
        "subject",
        "raw",
        "fastsurfer",
        "freesurfer",
        "m2m",
        "dwi",
        "ct",
        "simulations",
    ]
    rows = []
    for sid in subject_ids(pm):
        rows.append(
            [
                sid,
                os.path.isdir(pm.bids_subject(sid)),
                os.path.isdir(pm.fastsurfer_subject(sid)),
                os.path.isdir(pm.freesurfer_subject(sid)),
                os.path.isdir(pm.m2m(sid)),
                os.path.isdir(pm.bids_dwi(sid)),
                _has_ct(pm, sid),
                len(pm.list_simulations(sid)),
            ]
        )
    return {"columns": columns, "rows": rows}
