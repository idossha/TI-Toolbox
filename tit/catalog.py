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
from tit.paths import PathManager, is_valid_subject_id, is_within, natural_key

# NOTE: tit.opt.ex.roi (used by list_rois) is imported lazily inside the
# function that needs it, never at module level -- tit/opt/__init__.py
# eagerly imports tit.opt.ex.engine, which imports simnibs (AGENTS.md
# "SimNIBS imports - use lazy loading pattern in opt/"). tit.catalog is
# imported at server startup by every route module, so a module-level
# import here would make the whole server fail to boot outside a SimNIBS
# environment (host dev tooling, --dump-openapi, CI without the container).


def _metadata_names(root: str, project_root: str | None) -> list[str]:
    """List only jailed children; outward links must not disclose metadata."""
    if project_root and not is_within(project_root, root):
        return []
    try:
        return sorted(
            name
            for name in os.listdir(root)
            if not project_root or is_within(project_root, os.path.join(root, name))
        )
    except OSError:
        return []


def _project_isdir(pm: PathManager, path: str) -> bool:
    return _project_paths_safe(pm, path) and os.path.isdir(path)


def _simulation_names(pm: PathManager, sid: str) -> list[str]:
    root = pm.simulations(sid)
    return [
        name
        for name in _metadata_names(root, pm.project_dir)
        if not name.startswith(".") and os.path.isdir(os.path.join(root, name))
    ]


def _metadata_glob(root: str, pattern: str, project_root: str | None) -> list[str]:
    if project_root and not is_within(project_root, root):
        return []
    return [
        path
        for path in sorted(glob.glob(os.path.join(root, pattern)))
        if not project_root or is_within(project_root, path)
    ]


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
    if not pm.project_dir:
        return []
    ids = set()
    for root, needs_m2m in (
        (pm.project_dir, False),
        (pm.fastsurfer(), False),
        (pm.freesurfer(), False),
        (pm.simnibs(), True),
    ):
        if not root:
            continue
        for name in _metadata_names(root, pm.project_dir):
            sid = name.removeprefix("sub-")
            if not name.startswith("sub-") or not is_valid_subject_id(sid):
                continue
            if os.path.isdir(os.path.join(root, name)) and (
                not needs_m2m or _project_isdir(pm, pm.m2m(sid))
            ):
                ids.add(sid)
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
    if not _project_isdir(pm, subj_dir):
        return False
    for modality_dir in (
        os.path.join(subj_dir, "T1w"),
        os.path.join(subj_dir, "T2w"),
    ):
        if not _project_isdir(pm, modality_dir):
            continue
        try:
            entries = _metadata_names(modality_dir, pm.project_dir)
        except OSError:
            continue
        if any(os.path.isdir(os.path.join(modality_dir, e)) for e in entries):
            return True
        if any(e.lower().endswith(_DICOM_LIKE_EXTS) for e in entries):
            return True
    try:
        return any(
            f.endswith(".tgz") for f in _metadata_names(subj_dir, pm.project_dir)
        )
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
        entries = _metadata_names(pm.sourcedata(), pm.project_dir)
    except OSError:
        return []
    known = set(subject_ids(pm))
    ids = []
    for name in entries:
        if not name.startswith("sub-"):
            continue
        sid = name[len("sub-") :]
        if not is_valid_subject_id(sid) or sid in known:
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
            "has_raw": _project_isdir(pm, pm.bids_subject(sid)),
            "has_fastsurfer": _project_isdir(pm, pm.fastsurfer_subject(sid)),
            "has_freesurfer": _project_isdir(pm, pm.freesurfer_subject(sid)),
            "has_m2m": _project_isdir(pm, pm.m2m(sid)),
            "n_simulations": len(_simulation_names(pm, sid)),
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
    for name in _simulation_names(pm, sid):
        item = {
            "name": name,
            "path": pm.simulation(sid, name),
            "has_ti": _project_isdir(pm, os.path.dirname(pm.ti_mesh_dir(sid, name))),
            "has_mti": _project_isdir(pm, os.path.dirname(pm.mti_mesh_dir(sid, name))),
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


def _dir_artifacts(
    root: str, *, max_depth: int = 3, project_root: str | None = None
) -> list[dict]:
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
    if (project_root and not is_within(project_root, root)) or not os.path.isdir(root):
        return out
    root_depth = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        if dirpath.rstrip(os.sep).count(os.sep) - root_depth >= max_depth:
            dirnames[:] = []
            continue
        for name in sorted(filenames):
            if project_root and not is_within(
                project_root, os.path.join(dirpath, name)
            ):
                continue
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
    if not _project_isdir(pm, anat_dir):
        return False
    return any(
        name.endswith(("_ct.nii.gz", "_ct.nii"))
        for name in _metadata_names(anat_dir, pm.project_dir)
    )


# ── what a file *is*, for every menu that offers one ─────────────────────────
#
# Maintainer, 2026-09-07, on the Menu's Anatomy branch tagging `lh.central`, `lh.pial` and
# `lh.white` as MESH next to the true `Head mesh (ernie)`:
#
#   *"Please distinguish between NIfTI, mesh, and a surface — a mesh is a tetrahedral FEM,
#   a surface is just a triangular 2-D surface."*
#
# That is not a labelling nicety. The two are different objects with different things you can do
# to them:
#
#   * a **mesh** (`.msh`) is SimNIBS's tetrahedral volume mesh — the FEM domain itself, 24-420 MB,
#     carrying the solved field on its elements. You cut it, you colour it by a field, you read a
#     value at a point inside the head.
#   * a **surface** (`lh.central.gii`, `rh.pial`) is a two-dimensional triangulated sheet — the
#     cortical ribbon, ~150 k vertices, ~8 MB, carrying *nothing* on its own. What makes it worth
#     looking at is what you hang on it: a `.annot` parcellation, a morphometry curve
#     (`lh.thickness`), or a data GIfTI of per-vertex numbers.
#
# Calling both "mesh" told a reader that ticking `lh.pial` would give them the same kind of thing
# as ticking `ernie.msh`, which is wrong about the size, the load time, the colouring and the
# question it answers. It also had a concrete cost: with one word for two objects there was
# nowhere to put a surface's attachments, so the `.annot` files SimNIBS writes right next to the
# surfaces were simply never offered.
#
# This function is the one place that decides, and every menu that offers a file — the composition
# tree, the Results and Analyzer "Open in viewer" links, the "+ Add…" picker — reads its answer
# rather than re-deriving one from the extension. Seven kinds, and `None` for "not something a
# scene can use", which is a real and common answer (`.mat`, `.txt`, `.geo`, `.sigma`, a log).

#: A volume: a regular 3-D lattice of numbers.
_VOLUME_EXTS = (".nii.gz", ".nii", ".mgz", ".mgh")

#: A surface handed over as a general triangle-soup format rather than as FreeSurfer/GIfTI.
_TRIANGLE_EXTS = (".stl", ".ply", ".obj")

#: FreeSurfer's extensionless binary **geometry** files, matched exactly after the `?h.` prefix.
#:
#: Exactly, not by prefix, and that matters: `surf/` also holds `lh.pial.T1`, `lh.orig.nofix`,
#: `lh.qsphere.nofix`, `lh.white.preaparc` and `lh.inflated.H` — intermediate and derived files
#: from recon-all's own bookkeeping, not things to offer someone. A prefix match would sweep all
#: of them in. A name this function does not recognise is `None`, which is the honest answer for a
#: file whose format we would be guessing at.
_FS_SURFACE_STEMS = frozenset(
    {"pial", "white", "central", "inflated", "sphere", "smoothwm", "orig"}
)

#: FreeSurfer's extensionless per-vertex **morphometry** curves — one scalar per vertex of the
#: same hemisphere's surface. Exactly, for the same reason: `lh.curv.pial` and `lh.area.mid` are
#: computed against a different surface than the one `lh.curv` goes with.
_FS_MORPH_STEMS = frozenset({"thickness", "curv", "sulc", "area"})

#: Basename shapes that are a **label** volume — an integer parcellation, drawn through a lookup
#: table at partial opacity, never windowed like a continuous field.
#:
#: Checked in addition to (not instead of) the `<stem>_LUT.txt` sidecar test below, because the
#: FreeSurfer/FastSurfer outputs carry no sidecar of their own: `aparc+aseg.mgz` is a label volume
#: whether or not anybody wrote a table next to it.
_LABEL_VOLUME_PATTERNS = (
    re.compile(r"^labeling$"),
    # Every `aparc*` is a cortical parcellation, `+aseg` merged or not, resampled or not
    # (`aparc_resampled_256x256x208.nii.gz` is the analyzer's own resampled copy of one).
    re.compile(r"^aparc.*$"),
    re.compile(r"^wmparc.*$"),
    re.compile(r"^(?:[lr]h\.)?ribbon$"),
    re.compile(r"^.*labels.*$", re.IGNORECASE),
    re.compile(r"^ThalamicNuclei.*$"),
    re.compile(r"^final_tissues.*$"),
    re.compile(r"^tissue_labeling.*$"),
    re.compile(r"^aseg(\..*)?$"),
    re.compile(r"^.*_seg$"),
)


def _hemi_split(basename: str) -> tuple[str, str] | None:
    """``("lh", "central.gii")`` for a hemisphere-prefixed name, else ``None``."""
    if basename[:3] in ("lh.", "rh."):
        return basename[:2], basename[3:]
    return None


def _strip_view_ext(basename: str) -> str:
    for ext in (".nii.gz", ".nii", ".mgz", ".mgh", ".msh", ".gii", ".annot"):
        if basename.lower().endswith(ext):
            return basename[: -len(ext)]
    return basename


def _has_lut_sidecar(path: str) -> bool:
    """``<stem>_LUT.txt`` beside the file — how SimNIBS marks its own label volumes."""
    directory = os.path.dirname(path)
    stem = _strip_view_ext(os.path.basename(path))
    return os.path.isfile(os.path.join(directory, f"{stem}_LUT.txt"))


def classify_view_file(path: str) -> str | None:
    """What *path* is, as one of the seven kinds a scene understands — or ``None``.

    ``volume`` · ``label-volume`` · ``surface`` · ``mesh`` · ``annotation`` · ``morph`` ·
    ``surface-data``.

    Decided from the **name and its neighbours only**. No file is opened: this runs once per row
    of a menu that is redrawn on every keystroke, and a menu that reads its way through a
    FreeSurfer `surf/` directory is a menu that stutters. The one filesystem touch is
    :func:`_has_lut_sidecar`, a single `os.path.isfile` on a sibling.

    ``None`` means "not something a scene can use" and is returned for everything unrecognised —
    `.mat`, `.txt`, `.geo`, `.sigma`, `.label`, `.ctab`, a log, and the derived FreeSurfer files
    (`lh.pial.T1`, `lh.smoothwm.K.crv`) that are recon-all's bookkeeping rather than anyone's
    input. Refusing to guess is the point: a file offered under the wrong kind fails at Open,
    which is a much worse moment to find out than not being offered at all.
    """
    basename = os.path.basename(path)
    lowered = basename.lower()

    # A tetrahedral FEM mesh. The only extension that earns the word.
    if lowered.endswith(".msh"):
        return "mesh"

    if lowered.endswith(".annot"):
        return "annotation"

    if lowered.endswith(".gii"):
        # GIfTI says what it carries in its own second-to-last suffix. `.func`/`.shape`/`.time`
        # are per-vertex numbers *for* a surface; `.surf` and a bare `.gii` are the geometry.
        # SimNIBS writes the geometry bare (`lh.central.gii`), which is why the bare case is
        # geometry and not the other way round.
        if re.search(r"\.(func|shape|time)\.gii$", lowered):
            return "surface-data"
        return "surface"

    if lowered.endswith(_TRIANGLE_EXTS):
        return "surface"

    if lowered.endswith(_VOLUME_EXTS):
        stem = _strip_view_ext(basename)
        if _has_lut_sidecar(path) or any(
            pattern.match(stem) for pattern in _LABEL_VOLUME_PATTERNS
        ):
            return "label-volume"
        return "volume"

    # FreeSurfer's extensionless binaries, which is where the distinction is easiest to get wrong:
    # `lh.pial` and `lh.thickness` look identical to a filename matcher that only splits on dots.
    hemi = _hemi_split(basename)
    if hemi is not None:
        _, rest = hemi
        if rest in _FS_SURFACE_STEMS:
            return "surface"
        if rest in _FS_MORPH_STEMS:
            return "morph"

    return None


#: The kinds that are a *geometry* — something a scene draws directly, rather than something it
#: hangs on a geometry.
VIEW_GEOMETRY_KINDS = frozenset({"surface", "mesh"})

#: The kinds that attach to a surface rather than standing alone. Matched to their surface by
#: hemisphere (`lh.`/`rh.`), which is the only pairing FreeSurfer guarantees.
VIEW_ATTACHMENT_KINDS = frozenset({"annotation", "morph", "surface-data"})


def surface_attachments(
    surface_path: str,
    *,
    extra_dirs: tuple[str, ...] = (),
    project_root: str | None = None,
) -> list[str]:
    """Every annotation / morph / data-GIfTI file that belongs on *surface_path*.

    Matched by hemisphere and nothing else, because that is the only correspondence FreeSurfer
    actually promises: `lh.thickness` has one value per vertex of *every* `lh.*` surface, since
    they all share a vertex numbering. Which `lh.` surface you hang it on is the viewer's choice,
    not a fact about the file. (Tetravox's own worker checks the vertex count when the file is
    attached, so a genuine mismatch is refused there with both counts named — this side does not
    need to read a byte to be safe, only to be plausible.)

    Searched in the surface's own directory plus *extra_dirs* — SimNIBS keeps the geometry in
    `m2m_<sid>/surfaces/` but writes the parcellations it made into `m2m_<sid>/segmentation/`,
    two directories apart, which is exactly why nothing offered them before.
    """
    if project_root and not is_within(project_root, surface_path):
        return []
    hemi = _hemi_split(os.path.basename(surface_path))
    if hemi is None:
        return []
    prefix = f"{hemi[0]}."
    found: list[str] = []
    for directory in (os.path.dirname(surface_path), *extra_dirs):
        for name in _metadata_names(directory, project_root):
            if not name.startswith(prefix):
                continue
            candidate = os.path.join(directory, name)
            if not os.path.isfile(candidate):
                continue
            if classify_view_file(candidate) in VIEW_ATTACHMENT_KINDS:
                found.append(candidate)
    return found


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
    has_m2m = _project_isdir(pm, pm.m2m(sid))
    # Only caps that carry electrodes: see :func:`_eeg_caps_with_electrodes`.
    eeg_nets_list = (
        [n for n, _ in _eeg_caps_with_electrodes(pm, sid)] if has_m2m else []
    )
    has_leadfields = (
        sorted({f"{item['net']}.csv" for item in (list_leadfields(pm, sid) or [])})
        if has_m2m
        else []
    )
    return {
        "id": sid,
        "has_raw": _project_isdir(pm, pm.bids_subject(sid)),
        "has_fastsurfer": _project_isdir(pm, pm.fastsurfer_subject(sid)),
        "has_freesurfer": _project_isdir(pm, pm.freesurfer_subject(sid)),
        "has_m2m": has_m2m,
        "n_simulations": len(_simulation_names(pm, sid)),
        "m2m_path": pm.m2m(sid) if has_m2m else None,
        "eeg_nets": eeg_nets_list,
        "has_leadfields": has_leadfields,
        "has_dwi": _project_isdir(pm, pm.bids_dwi(sid)),
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


def _mode_niftis(mode_dir: str, *, project_root: str | None = None) -> list[dict]:
    niftis_dir = os.path.join(mode_dir, "niftis")
    out: list[dict] = []
    for path in _metadata_glob(niftis_dir, "*.nii*", project_root):
        basename = os.path.basename(path)
        if "TDCS" in basename:
            continue
        rest, tissue = _strip_tissue_prefix(basename)
        space = "mni" if "_MNI" in basename else "subject"
        match = _FIELD_RE.search(rest)
        field = match.group(1) if match else _guess_field(rest)
        out.append({"path": path, "field": field, "space": space, "tissue": tissue})
    return out


def _hf_niftis(hf_dir: str, *, project_root: str | None = None) -> list[dict]:
    out = []
    for path in _metadata_glob(hf_dir, "*_scalar_*magnE.nii.gz", project_root):
        basename = os.path.basename(path)
        space = "mni" if "_MNI" in basename else "subject"
        out.append({"path": path, "field": "magnE", "space": space, "tissue": None})
    return out


def _dir_meshes(
    mesh_dir: str, kind: str, *, project_root: str | None = None
) -> list[dict]:
    return [
        {"path": path, "kind": kind}
        for path in _metadata_glob(mesh_dir, "*.msh", project_root)
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
    if sid not in subject_ids(pm) or sim not in _simulation_names(pm, sid):
        return None
    sim_dir = pm.simulation(sid, sim)
    if not _project_paths_safe(pm, sim_dir):
        return None
    has_ti = _project_isdir(pm, os.path.dirname(pm.ti_mesh_dir(sid, sim)))
    has_mti = _project_isdir(pm, os.path.dirname(pm.mti_mesh_dir(sid, sim)))
    config_path = os.path.join(sim_dir, "documentation", "config.json")
    config = (
        _read_json(config_path) if _project_paths_safe(pm, config_path) else None
    ) or {}
    montage_name = config.get("montage_name") or sim

    niftis: list[dict] = []
    meshes: list[dict] = []
    for mode in _MODE_DIRS:
        mode_dir = os.path.join(sim_dir, mode)
        if not _project_isdir(pm, mode_dir):
            continue
        niftis.extend(_mode_niftis(mode_dir, project_root=pm.project_dir))
        meshes.extend(
            _dir_meshes(
                os.path.join(mode_dir, "mesh"), "field", project_root=pm.project_dir
            )
        )
        meshes.extend(
            _dir_meshes(
                os.path.join(mode_dir, "mesh", "surfaces"),
                "surface",
                project_root=pm.project_dir,
            )
        )
    hf_dir = os.path.join(sim_dir, "high_Frequency")
    if _project_isdir(pm, os.path.join(hf_dir, "niftis")):
        niftis.extend(
            _hf_niftis(os.path.join(hf_dir, "niftis"), project_root=pm.project_dir)
        )
    if _project_isdir(pm, os.path.join(hf_dir, "mesh")):
        meshes.extend(
            _dir_meshes(
                os.path.join(hf_dir, "mesh"),
                "high_frequency",
                project_root=pm.project_dir,
            )
        )

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


def simulation_figures(pm: PathManager, sid: str, sim: str) -> list[dict] | None:
    """Pictures a simulation run saved of itself; ``None`` if subject/simulation is unknown.

    Today that is the montage visualisation ``tit.tools.montage_visualizer`` writes as
    ``<sim>/<TI|mTI>/montage_imgs/<name>_highlighted_visualization.png`` -- the EEG net with
    this run's electrodes highlighted. The Results pane shows it beside the channel chips,
    which name the same montage in text, and in the run's Figures grid.

    Not folded into ``SimulationDetail``: that response has a Pydantic ``response_model``
    generated from the frozen v1 contract, so a new field there is a contract change. This is
    the same shape as :func:`electrode_overlays` above -- a small presence query beside the
    main read.
    """
    if sid not in subject_ids(pm) or sim not in _simulation_names(pm, sid):
        return None
    sim_dir = pm.simulation(sid, sim)
    out: list[dict] = []
    for mode in _MODE_DIRS:
        path = os.path.join(
            sim_dir, mode, "montage_imgs", f"{sim}_highlighted_visualization.png"
        )
        if _project_paths_safe(pm, path) and os.path.isfile(path):
            out.append(
                {
                    "path": path,
                    "kind": "image",
                    "label": f"{mode} montage",
                }
            )
    return out


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
    if sid not in subject_ids(pm) or sim not in _simulation_names(pm, sid):
        return None
    sim_dir = pm.simulation(sid, sim)
    out = []
    for mode in _MODE_DIRS:
        path = os.path.join(
            sim_dir, mode, "montage_imgs", "electrode_overlay_subject.nii.gz"
        )
        out.append(
            {
                "mode": mode,
                "path": path,
                "exists": (_project_paths_safe(pm, path) and os.path.isfile(path)),
            }
        )
    return out


# ── montages ─────────────────────────────────────────────────────────────────


def get_montages(pm: PathManager) -> dict:
    """``montage_list.json``, reshaped to the v1 ``Montages`` schema.

    Reads the explicitly selected project's montage file through the shared writer API.
    """
    from tit.sim.utils import load_montage_data

    if not _project_paths_safe(pm, pm.montage_config()):
        return {"nets": {}}
    data = load_montage_data(pm=pm)
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

    if not _project_paths_safe(pm, pm.montage_config()):
        raise ValueError("Montage path must remain inside the project")
    mode = "U" if kind == "uni_polar" else "M"
    upsert_montage(
        eeg_net=net,
        montage_name=name,
        electrode_pairs=[list(pair) for pair in pairs],
        mode=mode,
        pm=pm,
    )
    return pairs


def delete_montage(pm: PathManager, net: str, kind: str, name: str) -> bool:
    """Delete one montage; ``False`` if it did not exist."""
    from tit.sim.utils import load_montage_data, save_montage_data

    if not _project_paths_safe(pm, pm.montage_config()):
        return False
    data = load_montage_data(pm=pm)
    key = "uni_polar_montages" if kind == "uni_polar" else "multi_polar_montages"
    montages = data.get("nets", {}).get(net, {}).get(key, {})
    if name not in montages:
        return False
    del montages[name]
    save_montage_data(data, pm=pm)
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
    if not _project_paths_safe(pm, pm.eeg_positions(sid)):
        return out
    for cap_name in pm.list_eeg_caps(sid):
        if not _project_paths_safe(pm, os.path.join(pm.eeg_positions(sid), cap_name)):
            continue
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
        mesh_mgr = MeshAtlasManager(seg_dir if _project_paths_safe(pm, seg_dir) else "")
        for name in mesh_mgr.list_atlases():
            lh_path = mesh_mgr.find_atlas_file(name, "lh")
            if lh_path and not _project_paths_safe(pm, lh_path):
                continue
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
                fastsurfer_mri_dir=(
                    pm.fastsurfer_mri(sid)
                    if _project_paths_safe(pm, pm.fastsurfer_mri(sid))
                    else ""
                ),
                freesurfer_mri_dir=(
                    pm.freesurfer_mri(sid)
                    if _project_paths_safe(pm, pm.freesurfer_mri(sid))
                    else ""
                ),
                seg_dir=seg_dir if _project_paths_safe(pm, seg_dir) else "",
                masks_dir=(
                    pm.masks(sid) if _project_paths_safe(pm, pm.masks(sid)) else ""
                ),
            )
            for display_name, path in voxel_mgr.list_atlases():
                if not _project_paths_safe(pm, path):
                    continue
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
    if hemi not in (None, "both", "lh", "rh") or sid not in subject_ids(pm):
        return None
    seg_dir = os.path.join(pm.m2m(sid), "segmentation")

    mesh_mgr = MeshAtlasManager(seg_dir if _project_paths_safe(pm, seg_dir) else "")
    if atlas_id in mesh_mgr.list_atlases():
        hemis = ("lh", "rh") if hemi in (None, "both") else (hemi,)
        out: list[dict] = []
        for h in hemis:
            annot_path = mesh_mgr.find_atlas_file(atlas_id, h)
            if not annot_path:
                continue
            if not is_within(pm.project_dir, annot_path):
                return None
            for index, name in mesh_mgr.list_annot_regions(annot_path):
                if name == "unknown":
                    continue
                out.append({"id": index, "name": name, "hemi": h})
        return out

    voxel_mgr = VoxelAtlasManager(
        fastsurfer_mri_dir=(
            pm.fastsurfer_mri(sid)
            if _project_paths_safe(pm, pm.fastsurfer_mri(sid))
            else ""
        ),
        freesurfer_mri_dir=(
            pm.freesurfer_mri(sid)
            if _project_paths_safe(pm, pm.freesurfer_mri(sid))
            else ""
        ),
        seg_dir=seg_dir if _project_paths_safe(pm, seg_dir) else "",
        masks_dir=pm.masks(sid) if _project_paths_safe(pm, pm.masks(sid)) else "",
    )
    atlas_path = dict(voxel_mgr.list_atlases()).get(atlas_id)
    atlas_root = pm.project_dir
    if atlas_path is None:
        atlas_root = mni_resources_dir()
        atlas_path = {
            os.path.basename(path): path
            for path in VoxelAtlasManager.detect_mni_atlases(atlas_root)
        }.get(atlas_id)
    if atlas_path is None:
        return None
    atlas_path = _jailed_atlas_path(atlas_root, atlas_path)
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


def _jailed_atlas_path(root: str, path: str) -> str | None:
    """Contain the volume and its derived cache/LUT paths, including dangling symlinks."""
    resolved = os.path.realpath(path)
    if not is_within(root, resolved):
        return None
    labels = _segstats_sidecar(resolved)
    lut = labels.removesuffix("_labels.txt") + "_LUT.txt"
    if not all(is_within(root, sibling) for sibling in (labels, lut)):
        return None
    return resolved


def nifti_labels(
    pm: PathManager, sid: str, path: str | None = None
) -> list[dict] | None:
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

    from tit.viewspec import jail_roots, resolve_jailed

    resolved = resolve_jailed(raw)
    if resolved is None:
        return None
    if not any(
        _jailed_atlas_path(str(root), str(resolved)) is not None
        for root in jail_roots()
    ):
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
# see ``contracts/CHANGES.md``). Deliberately conservative: callers
# needing a friendlier display name should map it to one of these first.
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def is_safe_name(name: Any) -> bool:
    """``True`` if *name* is safe to use as a filename component.

    Used for ROI names, free-hand config names, and montage names on every
    write path -- never trust a client-supplied string used to build a path.
    """
    return isinstance(name, str) and bool(_SAFE_NAME_RE.match(name))


def _project_paths_safe(pm: PathManager, *paths: str) -> bool:
    """Reject outward parent/leaf symlinks before any part of a catalog mutation."""
    return bool(pm.project_dir) and all(
        is_within(pm.project_dir, path) for path in paths
    )


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
    if not _project_paths_safe(pm, roi_dir) or not os.path.isdir(roi_dir):
        return []
    out = []
    for name in sorted(os.listdir(roi_dir)):
        if not name.endswith(".csv") or not _project_paths_safe(
            pm, os.path.join(roi_dir, name)
        ):
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
    filename = f"{name}.csv"
    base_name = name
    roi_path = os.path.join(roi_dir, filename)
    roi_list = os.path.join(roi_dir, "roi_list.txt")
    if not _project_paths_safe(pm, roi_path, roi_list):
        raise ValueError("ROI paths must remain inside the project")
    os.makedirs(roi_dir, exist_ok=True)

    with open(roi_path, "w", newline="") as f:
        csv.writer(f).writerow([x, y, z])

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
    roi_list = os.path.join(roi_dir, "roi_list.txt")
    if not _project_paths_safe(pm, roi_path, roi_list):
        return False
    existed = os.path.isfile(roi_path)
    if existed:
        os.remove(roi_path)

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
    root = pm.leadfields(sid)
    out = []
    for name in _metadata_names(root, pm.project_dir):
        if not name.endswith(".hdf5"):
            continue
        path = os.path.join(root, name)
        # Match LeadfieldGenerator's established net naming without its unjailed stat.
        stem = name[:-5]
        net = (
            stem.split("_leadfield_", 1)[-1]
            if "_leadfield_" in stem
            else stem.removesuffix("_leadfield")
        )
        for prefix in (f"{sid}_", sid):
            if net.startswith(prefix):
                net = net[len(prefix) :]
                break
        net = net.strip("_") or "unknown"
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
    return sorted(out, key=lambda item: (item["net"], item["path"]))


# ── flex-search runs ─────────────────────────────────────────────────────────


def _pair_by_channel(
    electrodes: list, channel_array_indices: list | None
) -> list[list]:
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
                members = [
                    e for _, e in sorted(by_channel[channel], key=lambda t: t[0])
                ]
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


def _flex_mappings(run_dir: str, *, project_root: str | None = None) -> list[dict]:
    """EEG-label pairs already mapped for this run, one entry per net.

    Reads the ``electrode_mapping_<net>.json`` files
    :func:`tit.sim.montage_sources.resolve_flex_montage` writes; purely
    read-only, so a run that has never been mapped simply reports none.
    """
    out: list[dict] = []
    if project_root and not is_within(project_root, run_dir):
        return out
    try:
        names = sorted(os.listdir(run_dir))
    except OSError:
        return out
    for name in names:
        if not (name.startswith("electrode_mapping_") and name.endswith(".json")):
            continue
        path = os.path.join(run_dir, name)
        if project_root and not is_within(project_root, path):
            continue
        data = _read_json(path)
        if data is None:
            continue
        labels = [
            label for label in data.get("mapped_labels") or [] if isinstance(label, str)
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


def _flex_optimized_pairs(
    run_dir: str, *, project_root: str | None = None
) -> list[list] | None:
    """The run's free (un-mapped) XYZ electrode pairs, or ``None``.

    ``electrode_positions.json`` is written by every flex-search run, which is
    what makes a run selectable in the Simulator even when it has never been
    mapped onto an EEG net (``Montage.Mode.FLEX_FREE``).
    """
    path = os.path.join(run_dir, "electrode_positions.json")
    if project_root and not is_within(project_root, path):
        return None
    data = _read_json(path)
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
    if not _project_paths_safe(pm, pm.flex_search(sid)):
        return out
    for name in pm.list_flex_search_runs(sid):
        run_dir = pm.flex_search_run(sid, name)
        if not _project_paths_safe(
            pm, run_dir, os.path.join(run_dir, "flex_meta.json")
        ):
            continue
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
                "mappings": _flex_mappings(run_dir, project_root=pm.project_dir),
                "optimized": _flex_optimized_pairs(
                    run_dir, project_root=pm.project_dir
                ),
                "artifacts": _dir_artifacts(run_dir, project_root=pm.project_dir),
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


def _ex_best(run_dir: str, *, project_root: str | None = None) -> dict | None:
    """Highest-``Composite_Index`` row of ``final_output.csv``, or ``None``."""
    csv_path = os.path.join(run_dir, "final_output.csv")
    if project_root and not is_within(project_root, csv_path):
        return None
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
    if not _project_paths_safe(pm, root) or not os.path.isdir(root):
        return []
    out = []
    for entry in sorted(os.scandir(root), key=lambda e: e.name):
        if not _project_paths_safe(
            pm, entry.path, os.path.join(entry.path, "run_config.json")
        ):
            continue
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
                "best": _ex_best(entry.path, project_root=pm.project_dir),
                "artifacts": _dir_artifacts(entry.path, project_root=pm.project_dir),
            }
        )
    return out


def ex_run_results(pm: PathManager, sid: str, kind: str, run: str) -> dict | None:
    """Full ``final_output.csv`` of one ex/mEx run, as ``TableData``."""
    if sid not in subject_ids(pm):
        return None
    root = pm.ex_search_run(sid, run) if kind == "ex" else pm.m_ex_search_run(sid, run)
    csv_path = os.path.join(root, "final_output.csv")
    if not _project_paths_safe(pm, csv_path):
        return None
    if not os.path.isfile(csv_path):
        return None
    return _read_csv_table(csv_path)


# ── analyses ─────────────────────────────────────────────────────────────────


def _analysis_entry(
    path: str, name: str, *, project_root: str | None = None
) -> dict | None:
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
    msh = next(iter(_metadata_glob(path, "*.msh", project_root)), None)
    nifti = os.path.join(path, "roi_overlay.nii.gz")
    if (project_root and not is_within(project_root, nifti)) or not os.path.isfile(
        nifti
    ):
        matches = _metadata_glob(path, "*.nii*", project_root)
        nifti = matches[0] if matches else None
    pdf = next(iter(_metadata_glob(path, "*.pdf", project_root)), None)
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


def _find_analysis_dirs(
    sim_dir: str, *, project_root: str | None = None
) -> list[tuple[str, str, bool]]:
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
    if project_root and not is_within(project_root, sim_dir):
        return []
    standard_parents = {
        os.path.join(sim_dir, "Analyses", space) for space in _ANALYSIS_SPACE_DIRS
    }
    found: list[tuple[str, str, bool]] = []
    for dirpath, dirnames, filenames in os.walk(sim_dir):
        dirnames.sort()
        if "analysis.json" in filenames and "results.csv" in filenames:
            dirnames.clear()  # an analysis contains no analyses
            if project_root and not all(
                is_within(project_root, os.path.join(dirpath, filename))
                for filename in ("analysis.json", "results.csv")
            ):
                continue
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
    if sid not in subject_ids(pm) or sim not in _simulation_names(pm, sid):
        return None
    out = []
    for path, name, _standard in _find_analysis_dirs(
        pm.simulation(sid, sim), project_root=pm.project_dir
    ):
        item = _analysis_entry(path, name, project_root=pm.project_dir)
        if item:
            out.append(item)
    return out


def analysis_summary(pm: PathManager, sid: str, sim: str, name: str) -> dict | None:
    """``results.csv`` of one analysis, as ``TableData``.

    *name* is what :func:`analyses` listed; a caller holding the run's own path relative
    to the simulation (``Analyses/Custom/run1``) resolves too, so the one string a script
    already has does not have to be translated into the listed form.
    """
    if sid not in subject_ids(pm) or sim not in _simulation_names(pm, sid):
        return None
    sim_dir = pm.simulation(sid, sim)
    for path, found_name, _standard in _find_analysis_dirs(
        sim_dir, project_root=pm.project_dir
    ):
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
    if not _project_paths_safe(pm, root) or not os.path.isdir(root):
        return []
    return [
        _report_entry(os.path.join(root, name), sid)
        for name in sorted(os.listdir(root))
        if name.endswith(".html") and _project_paths_safe(pm, os.path.join(root, name))
    ]


def find_report_path(pm: PathManager, report_id: str) -> str | None:
    """Resolve a ``reports()`` ``id`` back to its file path (used by ``/api/files/report``)."""
    if "/" not in report_id:
        return None
    sid, stem = report_id.split("/", 1)
    if any(c in stem for c in ("/", "\\", "..")):
        return None
    path = os.path.join(pm.reports(), f"sub-{sid}", f"{stem}.html")
    return path if _project_paths_safe(pm, path) and os.path.isfile(path) else None


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
    ``contracts/CHANGES.md``); ``type`` is passed through verbatim.
    """
    if sid not in subject_ids(pm):
        return None
    stim_dir = os.path.join(pm.m2m(sid), "stim_configs")
    if not _project_paths_safe(pm, stim_dir) or not os.path.isdir(stim_dir):
        return []
    out = []
    for name in sorted(os.listdir(stim_dir)):
        if not name.endswith(".json") or not _project_paths_safe(
            pm, os.path.join(stim_dir, name)
        ):
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
    path = os.path.join(stim_dir, f"{name}.json")
    if not _project_paths_safe(pm, path):
        raise ValueError("Free-hand config path must remain inside the project")
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
        if not _project_paths_safe(pm, root):
            return []
        try:
            return sorted(
                n
                for n in os.listdir(root)
                if _project_paths_safe(pm, os.path.join(root, n))
                and os.path.isdir(os.path.join(root, n))
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


# ── group statistics detail ──────────────────────────────────────────────────

#: Files a ``tit.stats`` run writes, in the order the Results pane shows them, with the
#: label it shows them under. ``tit/stats/permutation.py`` names every one of these
#: literally; there is no manifest, so this table IS the contract between the two.
_STATS_FILE_LABELS = {
    "average_responders.nii.gz": "Group 1 average field",
    "average_non_responders.nii.gz": "Group 2 average field",
    "difference_map.nii.gz": "Difference map (group 1 − group 2)",
    "pvalues_map.nii.gz": "p-value map (−log10 p)",
    "t_statistics_map.nii.gz": "t-statistic map",
    "correlation_map.nii.gz": "Correlation map",
    "correlation_map_thresholded.nii.gz": "Correlation map (thresholded)",
    "average_efield.nii.gz": "Average field",
    "significant_voxels_mask.nii.gz": "Significant-voxel mask",
    "permutation_null_distribution.pdf": "Permutation null distribution",
    "cluster_size_mass_correlation.pdf": "Cluster size vs mass",
    "analysis_summary.txt": "Analysis summary",
    "permutation_details.txt": "Permutation details",
    "significant_clusters.csv": "Significant clusters",
    "surface_maps.npz": "Surface maps",
}

_STATS_KIND_BY_EXT = {
    ".pdf": "pdf",
    ".png": "image",
    ".csv": "csv",
    ".txt": "text",
    ".log": "log",
    ".npz": "npz",
    ".json": "json",
}

#: ``Config:   test=unpaired  alt=two-sided  stat=mass  threshold=0.050  perms=1000 ...``
_STATS_CONFIG_LINE = re.compile(r"Config:\s+(.*)$")
_STATS_CONFIG_FIELD = re.compile(r"(\w+)=(\S+)")
#: ``Loaded 2 Responders: ['101', 'MNI152']``
_STATS_LOADED_LINE = re.compile(r"Loaded (\d+) (.+?): \[(.*)\]$")
_STATS_SHAPE_LINE = re.compile(r"Image shape: (\(.*?\))")
#: ``  Cluster 3: mass=41.20, size=118, p=0.0230 (SIGNIFICANT)``
_STATS_CLUSTER_LINE = re.compile(
    r"Cluster (\d+): (\w+)=([-\d.eE+]+), size=(\d+), p=([\d.eE+-]+)\s*\((\w+)\)"
)

#: The outcome lines the engine logs, as (regex, [labels]) -- the run writes no machine-readable
#: result file, so these are where the pane's "Key numbers" come from.
_STATS_RESULT_LINES = [
    (
        re.compile(r"Min p=([\d.eE+-]+) over (\d+) testable voxel"),
        ["Smallest uncorrected p", "Testable voxels"],
    ),
    (
        re.compile(r"p<0\.05: (\d+)\s*\("),
        ["Voxels at p < 0.05"],
    ),
    (
        re.compile(r"Clusters at p<[\d.]+ \(uncorrected, sign-separated\): (\d+)"),
        ["Candidate clusters"],
    ),
    (
        re.compile(r"Threshold \(p<[\d.]+\): ([\d.eE+-]+) (\w+) units"),
        ["Cluster threshold", None],
    ),
    (
        re.compile(r"Significant: (\d+) clusters?, (\d+) voxels?"),
        ["Significant clusters", "Significant voxels"],
    ),
]

_STATS_CONFIG_LABELS = {
    "test": "Test",
    "alt": "Alternative",
    "stat": "Cluster statistic",
    "threshold": "Cluster-forming p",
    "perms": "Permutations",
    "alpha": "Cluster alpha",
    "jobs": "Parallel jobs",
}


def _stats_log_path(run_dir: str) -> str | None:
    """The newest ``*_analysis_<ts>.log`` in *run_dir*."""
    try:
        logs = sorted(n for n in os.listdir(run_dir) if n.endswith(".log"))
    except OSError:
        return None
    return os.path.join(run_dir, logs[-1]) if logs else None


def _parse_stats_log(text: str) -> dict:
    """The run's inputs and its outcome, read from its own log.

    ``tit.stats`` writes no machine-readable config into the output directory -- the job's
    ``config.json`` lives under ``jobs/<job_id>/`` and is not reachable from the run
    directory. The run log's own header lines carry every input the pane shows (the config
    line, one ``Loaded N <group>: [ids]`` line per group, the image shape), and the cluster
    lines carry the outcome, so they are the source here. Every field is optional: a log
    truncated by a crash yields fewer rows, never a wrong one.
    """
    config: list[dict] = []
    results: list[dict] = []
    groups: list[dict] = []
    clusters: list[list] = []
    shape: str | None = None
    error: str | None = None
    for raw in text.splitlines():
        line = raw.split(" | ")[-1].strip() if " | " in raw else raw.strip()
        m = _STATS_CONFIG_LINE.search(line)
        if m and not config:
            for key, value in _STATS_CONFIG_FIELD.findall(m.group(1)):
                config.append(
                    {"label": _STATS_CONFIG_LABELS.get(key, key), "value": value}
                )
            continue
        m = _STATS_LOADED_LINE.search(line)
        if m:
            ids = [s.strip().strip("'\"") for s in m.group(3).split(",") if s.strip()]
            groups.append({"name": m.group(2), "n": int(m.group(1)), "subjects": ids})
            continue
        m = _STATS_SHAPE_LINE.search(line)
        if m:
            shape = m.group(1)
            continue
        m = _STATS_CLUSTER_LINE.search(line)
        if m:
            clusters.append(
                [
                    int(m.group(1)),
                    float(m.group(3)),
                    int(m.group(4)),
                    float(m.group(5)),
                    m.group(6),
                ]
            )
            continue
        for pattern, labels in _STATS_RESULT_LINES:
            m = pattern.search(line)
            if not m:
                continue
            for label, value in zip(labels, m.groups()):
                if label and not any(r["label"] == label for r in results):
                    results.append({"label": label, "value": value})
        if "| ERROR |" in raw or raw.startswith("ERROR"):
            error = line
    stat_name = next(
        (c["value"] for c in config if c["label"] == "Cluster statistic"), "mass"
    )
    return {
        "config": config,
        "results": results,
        "groups": groups,
        "image_shape": shape,
        "clusters": (
            {
                "columns": ["Cluster", stat_name, "Size (voxels)", "p", "Verdict"],
                "rows": clusters,
            }
            if clusters
            else None
        ),
        "error": error,
    }


def group_stats_detail(pm: PathManager, analysis_type: str, name: str) -> dict | None:
    """One ``derivatives/ti-toolbox/stats/<type>/<name>/`` run, read for the Results pane.

    ``None`` when the run directory does not exist. ``status`` is ``"ok"`` once the run has
    written something besides its log, and ``"empty"`` when it has not -- the state the
    maintainer hit, where a failed 2-vs-1 group comparison left a bare ``.log`` and the pane
    could say nothing about it. ``reason`` is then the log's own ERROR line, so the UI
    reports why instead of showing an empty file list.
    """
    if "/" in analysis_type or "/" in name or ".." in (analysis_type, name):
        return None
    run_dir = os.path.join(pm.ti_toolbox(), "stats", analysis_type, name)
    if not _project_paths_safe(pm, run_dir) or not os.path.isdir(run_dir):
        return None

    try:
        names = sorted(os.listdir(run_dir))
    except OSError:
        names = []

    artifacts: list[dict] = []
    for filename in names:
        path = os.path.join(run_dir, filename)
        if not _project_paths_safe(pm, path) or not os.path.isfile(path):
            continue
        if filename.endswith(".nii.gz") or filename.endswith(".nii"):
            kind = "nifti"
        else:
            kind = _STATS_KIND_BY_EXT.get(os.path.splitext(filename)[1], "file")
        artifacts.append(
            {
                "path": path,
                "kind": kind,
                "label": _STATS_FILE_LABELS.get(
                    filename, os.path.splitext(filename)[0].replace("_", " ")
                ),
            }
        )
    # The run's own files first, in the order the labels table lists them; anything else after.
    order = list(_STATS_FILE_LABELS)
    artifacts.sort(
        key=lambda a: (
            (
                order.index(os.path.basename(a["path"]))
                if os.path.basename(a["path"]) in order
                else len(order)
            ),
            a["path"],
        )
    )

    log_path = _stats_log_path(run_dir)
    if log_path and not _project_paths_safe(pm, log_path):
        log_path = None
    parsed = {
        "config": [],
        "results": [],
        "groups": [],
        "image_shape": None,
        "clusters": None,
        "error": None,
    }
    if log_path:
        try:
            with open(log_path, encoding="utf-8", errors="replace") as f:
                parsed = _parse_stats_log(f.read())
        except OSError:
            pass

    clusters = parsed["clusters"]
    csv_path = os.path.join(run_dir, "significant_clusters.csv")
    if (
        clusters is None
        and _project_paths_safe(pm, csv_path)
        and os.path.isfile(csv_path)
    ):
        try:
            clusters = _read_csv_table(csv_path)
        except OSError:
            clusters = None

    produced = [a for a in artifacts if a["kind"] != "log"]
    status = "ok" if produced else "empty"
    reason = parsed["error"]
    if status == "empty" and not reason:
        reason = (
            "This run wrote no output files. Its log is the only record; open it for the "
            "last step it reached."
        )

    return {
        "type": analysis_type,
        "name": name,
        "path": run_dir,
        "created": _mtime_iso(run_dir),
        "status": status,
        "reason": reason,
        "config": parsed["config"],
        "results": parsed["results"],
        "groups": parsed["groups"],
        "image_shape": parsed["image_shape"],
        "clusters": clusters,
        "log": log_path,
        "artifacts": artifacts,
    }


def read_notes(pm: PathManager) -> dict:
    """Quick Notes content (``derivatives/ti-toolbox/notes.txt``)."""
    path = os.path.join(pm.ti_toolbox(), "notes.txt")
    if not _project_paths_safe(pm, path) or not os.path.isfile(path):
        return {"text": "", "updated_at": None}
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return {"text": text, "updated_at": _mtime_iso(path)}


def write_notes(pm: PathManager, text: str) -> dict:
    """Replace Quick Notes content, atomically."""
    path = os.path.join(pm.ti_toolbox(), "notes.txt")
    tmp = f"{path}.tmp"
    if not _project_paths_safe(pm, path, tmp):
        raise ValueError("Notes paths must remain inside the project")
    os.makedirs(os.path.dirname(path), exist_ok=True)
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
                _project_isdir(pm, pm.bids_subject(sid)),
                _project_isdir(pm, pm.fastsurfer_subject(sid)),
                _project_isdir(pm, pm.freesurfer_subject(sid)),
                _project_isdir(pm, pm.m2m(sid)),
                _project_isdir(pm, pm.bids_dwi(sid)),
                _has_ct(pm, sid),
                len(_simulation_names(pm, sid)),
            ]
        )
    return {"columns": columns, "rows": rows}
