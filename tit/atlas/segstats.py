"""Pure-Python replacement for FreeSurfer's ``mri_segstats`` (region listing).

Lists the unique nonzero integer labels present in a volumetric atlas, with
names resolved from a lookup table (LUT) and voxel counts/volumes computed
directly from the array -- replacing the two
``mri_segstats --seg <atlas> --excludeid 0 --ctab-default --sum <out>``
subprocess calls in :mod:`tit.atlas.voxel` and :mod:`tit.analyzer.analyzer`.

Validated voxel-for-voxel against live ``mri_segstats`` (FreeSurfer 7.4.1,
``idossha/ti-toolbox_freesurfer:v7.4.1``) on ``sub-ernie``'s real recon-all
output (``aparc.DKTatlas+aseg.mgz``, ``aparc.a2009s+aseg.mgz``,
``ThalamicNuclei.v13.T1.mgz``) and charm's own ``labeling.nii.gz``: identical
label-id sets and voxel counts in every case (see
``dev/spikes/native/fs-binaries/REPORT.md`` for the exact commands and
numbers).

Public API
----------
SegStat
    One label's id, name, voxel count and volume.
load_lut
    Parse a FreeSurfer-style colour lookup table into ``{id: name}``.
resolve_lut_for_atlas
    Pick the right LUT for a voxel atlas: a sidecar file next to it, or the
    bundled standard FreeSurfer colour table as a fallback.
compute_segstats
    List labels present in a volume with names, voxel counts and volumes.
format_segstats_sum / write_segstats_sum
    Render :class:`SegStat` rows in ``mri_segstats --sum``'s own text layout,
    kept byte-compatible because other modules in this codebase discover and
    parse this exact sidecar filename pattern.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SegStat:
    """One label's identity, size and name in a voxel atlas.

    Attributes
    ----------
    seg_id : int
        Integer voxel label.
    name : str
        Region name, resolved from a LUT or ``"Label {seg_id}"`` if
        unresolved.
    n_voxels : int
        Count of voxels carrying this label.
    volume_mm3 : float
        ``n_voxels`` times the volume of one voxel, from the image's own
        affine (``|det(affine[:3, :3])|``).
    """

    seg_id: int
    name: str
    n_voxels: int
    volume_mm3: float


def load_lut(lut_path: str) -> dict[int, str]:
    """Parse a FreeSurfer-style colour lookup table into ``{id: name}``.

    Column-order agnostic (mirrors
    :func:`tit.opt.roi_spec._parse_lut_line`): on each non-comment,
    non-blank line the first all-digit token is the label id and the
    remaining non-numeric tokens are joined as the name (so a trailing
    ``R G B A`` colour triple/quad is naturally excluded).

    Args:
        lut_path: Path to a LUT text file.

    Returns:
        ``{label_id: name}``. Empty if *lut_path* does not exist or cannot
        be read.
    """
    lut: dict[int, str] = {}
    if not lut_path or not os.path.isfile(lut_path):
        return lut
    try:
        with open(lut_path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) < 2 or not parts[0].lstrip("-").isdigit():
                    continue
                name_tokens = [p for p in parts[1:] if not p.lstrip("-").isdigit()]
                if not name_tokens:
                    continue
                lut[int(parts[0])] = " ".join(name_tokens)
    except OSError:
        return {}
    return lut


def _strip_nifti_suffix(filename: str) -> str:
    if filename.endswith(".nii.gz"):
        return filename[: -len(".nii.gz")]
    return os.path.splitext(filename)[0]


#: Legacy ``recon-all`` thalamic-nuclei atlas family (Iglesias et al. histological atlas):
#: ``ThalamicNuclei.v13.T1.mgz`` and its FreeSurfer-voxel-space sibling
#: ``ThalamicNuclei.v13.T1.FSvoxelSpace.mgz``. Their 8100s/8200s label ids are absent from the
#: bundled ``FreeSurferColorLUT.txt`` (that table predates this atlas), so they fall through to
#: ``"Label {id}"`` unless named separately -- see :data:`_THALAMIC_NUCLEI_LUT_FILENAME`.
_THALAMIC_NUCLEI_STEM_PREFIX = "ThalamicNuclei"
_THALAMIC_NUCLEI_LUT_FILENAME = "ThalamicNuclei_LUT.txt"


def resolve_lut_for_atlas(atlas_path: str) -> dict[int, str]:
    """Pick the LUT that names *atlas_path*'s integer labels.

    Mirrors the sidecar-first, bundled-fallback resolution already used for
    display names elsewhere in the codebase
    (:func:`tit.opt.roi_spec.resolve_volume_label_names`,
    ``RoiPickerWidget._find_volume_lut``): a sidecar colour table sitting
    next to the atlas file wins (``labeling_LUT.txt`` for charm's
    ``labeling.nii.gz``, else ``{stem}_LUT.txt``); for the legacy thalamic-
    nuclei atlas family (``ThalamicNuclei.v13.T1*.mgz``) the vendored
    ``resources/atlas/ThalamicNuclei_LUT.txt`` is tried next (FreeSurfer's
    own id -> name table for that atlas, absent from the general-purpose
    ``FreeSurferColorLUT.txt``); and the bundled standard FreeSurfer colour
    table (``resources/atlas/FreeSurferColorLUT.txt``, ``--ctab-default``'s
    own table) is the final fallback -- covering the other FreeSurfer volume
    atlases (``aparc.DKTatlas+aseg.mgz`` and friends) that ship no sidecar of
    their own.

    The thalamic-nuclei table is a *fixed* id -> name mapping, not read from
    the per-subject ``ThalamicNuclei.v13.T1.volumes.txt`` sidecar some
    ``recon-all`` outputs carry: that file lists names in a fixed but
    non-numeric (anatomically grouped) order that does not line up 1:1
    against any one subject's own sorted voxel-label ids -- confirmed against
    three real subjects' derivatives, where the *set* of ids actually
    carrying voxels differs subject to subject (small nuclei are sometimes
    absent), so pairing by row order would silently produce wrong names for
    some ids. See ``ThalamicNuclei_LUT.txt``'s own header for the full
    citation and verification note.

    Deliberately does **not** treat a ``{stem}_labels.txt`` file as a LUT
    candidate: that filename is this module's own ``mri_segstats``-format
    cache (see :func:`write_segstats_sum`), not a colour table -- confusing
    the two would misparse the summary's ``Index``/``NVoxels``/``Volume_mm3``
    columns as label names.

    Args:
        atlas_path: Absolute path to the atlas volume.

    Returns:
        ``{label_id: name}``, possibly empty if no LUT (sidecar or bundled)
        can be found or read.
    """
    from tit.atlas.constants import MNI_ATLAS_DIR

    atlas = Path(atlas_path)
    stem = _strip_nifti_suffix(atlas.name)

    candidates = []
    if atlas.name == "labeling.nii.gz":
        candidates.append(atlas.with_name("labeling_LUT.txt"))
    candidates.append(atlas.with_name(f"{stem}_LUT.txt"))

    for candidate in candidates:
        if candidate.is_file():
            lut = load_lut(str(candidate))
            if lut:
                return lut

    if stem.startswith(_THALAMIC_NUCLEI_STEM_PREFIX):
        lut = load_lut(os.path.join(MNI_ATLAS_DIR, _THALAMIC_NUCLEI_LUT_FILENAME))
        if lut:
            return lut

    return load_lut(os.path.join(MNI_ATLAS_DIR, "FreeSurferColorLUT.txt"))


def compute_segstats(
    atlas_path: str, lut: dict[int, str] | None = None
) -> list[SegStat]:
    """List labels present in *atlas_path* with names, voxel counts and volumes.

    Replaces ``mri_segstats --seg <atlas_path> --excludeid 0 --sum <out>``:
    every unique nonzero integer voxel value becomes one :class:`SegStat`,
    named via *lut* (``"Label {id}"`` when unresolved), with ``n_voxels``
    from :func:`numpy.unique` and ``volume_mm3 = n_voxels *
    |det(affine[:3, :3])|`` -- matches ``mri_segstats``'s own per-voxel
    volume for an orthogonal affine (the case for every atlas this codebase
    ships or produces). Validated with exact voxel-count matches against
    live ``mri_segstats`` output (module docstring).

    Args:
        atlas_path: Path to a label volume (``.mgz``/``.nii``/``.nii.gz``).
        lut: Optional ``{id: name}`` mapping, e.g. from
            :func:`resolve_lut_for_atlas`. Defaults to no names resolved
            (every label becomes ``"Label {id}"``).

    Returns:
        :class:`SegStat` entries sorted by ``seg_id`` ascending (matching
        ``mri_segstats``'s own row order).
    """
    import nibabel as nib
    import numpy as np

    lut = lut or {}
    img = nib.load(atlas_path)
    data = np.asarray(img.dataobj)
    if data.ndim > 3:
        data = data[..., 0]
    voxel_volume = float(abs(np.linalg.det(np.asarray(img.affine)[:3, :3])))

    values, counts = np.unique(data.astype(np.int64), return_counts=True)
    out: list[SegStat] = []
    for value, count in zip(values.tolist(), counts.tolist()):
        if value == 0:
            continue
        name = lut.get(value, f"Label {value}")
        out.append(
            SegStat(
                seg_id=value,
                name=name,
                n_voxels=int(count),
                volume_mm3=float(count) * voxel_volume,
            )
        )
    out.sort(key=lambda s: s.seg_id)
    return out


def format_segstats_sum(stats: list[SegStat]) -> str:
    """Render *stats* in ``mri_segstats --sum``'s own text layout.

    Kept byte-compatible with FreeSurfer's historical output columns
    (``Index SegId NVoxels Volume_mm3 StructName``) because other modules in
    this codebase (:mod:`tit.opt.roi_spec`,
    ``tit.gui.components.roi_picker``, :mod:`tit.viewspec`) discover and
    parse this exact sidecar filename pattern (``{atlas_stem}_labels.txt``)
    for cache reuse -- changing the column layout would silently break those
    readers.
    """
    lines = [
        "# Title Segmentation Statistics\n",
        "# generating_program tit.atlas.segstats (nibabel/numpy, no FreeSurfer binary)\n",
        f"# NRows {len(stats)}\n",
        "# ColHeaders Index SegId NVoxels Volume_mm3 StructName\n",
    ]
    for index, stat in enumerate(stats, start=1):
        lines.append(
            f"{index:3d} {stat.seg_id:5d} {stat.n_voxels:10d} "
            f"{stat.volume_mm3:12.4f} {stat.name}\n"
        )
    return "".join(lines)


def write_segstats_sum(stats: list[SegStat], out_path: str) -> None:
    """Write :func:`format_segstats_sum`'s text to *out_path*."""
    with open(out_path, "w") as fh:
        fh.write(format_segstats_sum(stats))
