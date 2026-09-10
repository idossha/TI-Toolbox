"""Pure-Python ROI-spec resolution for flex-search targets.

Extracted from the former PyQt ``RoiPickerWidget`` (as of the v3 audit): the
parts of that widget that turn a
*selection* (an atlas display name + region names, a volume atlas path +
integer labels, or explicit sphere centers/radii) into one of
:class:`tit.opt.config.FlexConfig`'s nested ROI dataclasses
(``SphericalROI``, ``AtlasROI``, ``SubcorticalROI``), plus the LUT/label
name resolution the widget uses to show human-readable region names.

Nothing here imports PyQt. Every function takes plain values (subject id,
project dir, atlas/region names, coordinates) instead of reading Qt widget
state, so it is reusable from :mod:`tit.server.routes.plan`, notebooks, and
future non-Qt UIs alike.

Public API
----------
get_roi_spec
    Build a ``SphericalROI`` / ``AtlasROI`` / ``SubcorticalROI`` instance
    from plain parameters.
resolve_cortical_region_index_map
    ``(hemisphere, region_name) -> annot label index`` for one atlas.
resolve_atlas_name_for_subject
    Subject-prefixed atlas base name (``"{subject_id}_{atlas_display}"``).
resolve_volume_atlas_path
    Absolute path to a volumetric atlas file from its display name/space.
resolve_volume_label_names
    ``label_id -> region name`` for a volumetric atlas, via its sidecar
    LUT (or, absent one, the bundled FreeSurfer colour table).

See Also
--------
tit.atlas.mesh.MeshAtlasManager : Cortical (.annot) atlas discovery.
tit.atlas.voxel.VoxelAtlasManager : Volumetric atlas discovery.
tit.opt.config.FlexConfig : Owner of the three nested ROI dataclasses this
    module builds.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from tit.atlas import MNI_ATLAS_DIR, MeshAtlasManager
from tit.opt.config import FlexConfig

__all__ = [
    "get_roi_spec",
    "resolve_cortical_region_index_map",
    "resolve_atlas_name_for_subject",
    "resolve_volume_atlas_path",
    "resolve_volume_label_names",
    "parse_region_names",
]


def _as_list(values: Any) -> list:
    """Wrap a scalar in a single-element list; pass lists/tuples through."""
    if isinstance(values, (list, tuple)):
        return list(values)
    return [values]


def _collapse(values: list) -> Any:
    """Collapse a single-element list to a scalar; pass longer lists through.

    Keeps single-region ROI dataclasses byte-identical to the pre-union
    format, while a union of several regions yields a list -- mirrors
    ``RoiPickerWidget._collapse``.
    """
    return values[0] if len(values) == 1 else values


def parse_region_names(text: str) -> list[tuple[str, str]]:
    """Parse a comma-separated list of hemisphere-prefixed region names.

    Parameters
    ----------
    text : str
        E.g. ``"lh.precentral, rh.superiorfrontal"``.

    Returns
    -------
    list of (str, str)
        ``(hemisphere, region_name)`` tuples, hemisphere lowercased.

    Raises
    ------
    ValueError
        If any non-empty token is not ``"<lh|rh>.<name>"``.
    """
    tokens: list[tuple[str, str]] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "." not in part:
            raise ValueError(
                f"Region {part!r} must be hemisphere-prefixed, e.g. 'lh.precentral'"
            )
        hemi, name = part.split(".", 1)
        hemi = hemi.strip().lower()
        if hemi not in ("lh", "rh"):
            raise ValueError(f"Region {part!r} hemisphere must be 'lh' or 'rh'")
        tokens.append((hemi, name.strip()))
    return tokens


# ---------------------------------------------------------------------------
# Cortical (surface / .annot) atlas resolution
# ---------------------------------------------------------------------------


def resolve_atlas_name_for_subject(atlas_display: str, subject_id: str) -> str:
    """Convert an atlas display name to the subject-specific atlas base name.

    The display name is already the atlas type (e.g. ``"DK40"``,
    ``"HCP_MMP1"``) because :meth:`MeshAtlasManager.find_all_atlases` strips
    the subject prefix; this just prepends the target subject id, mirroring
    ``RoiPickerWidget._resolve_atlas_name_for_subject``.
    """
    return f"{subject_id}_{atlas_display}"


def resolve_cortical_region_index_map(
    seg_dir: str, atlas_display: str
) -> dict[tuple[str, str], int]:
    """Map ``(hemisphere, region_name) -> annot label index`` for one atlas.

    Parameters
    ----------
    seg_dir : str
        ``m2m_{subject}/segmentation/`` directory.
    atlas_display : str
        Atlas display name as returned by
        :meth:`MeshAtlasManager.find_all_atlases` (e.g. ``"DK40"``).

    Returns
    -------
    dict
        Empty when the atlas's ``.annot`` files cannot be read (e.g. no
        segmentation for this subject yet).
    """
    mgr = MeshAtlasManager(seg_dir)
    mapping: dict[tuple[str, str], int] = {}
    for hemi in ("lh", "rh"):
        annot_file = mgr.find_all_atlases(hemi).get(atlas_display)
        if not annot_file:
            continue
        try:
            regions = mgr.list_annot_regions(annot_file)
        except (OSError, ValueError):
            continue
        for idx, name in regions:
            mapping[(hemi, name)] = idx
    return mapping


def build_cortical_atlas_roi(
    *,
    subject_id: str,
    seg_dir: str,
    atlas_display: str,
    regions: list[tuple[str, str]],
    roi_cls: type = FlexConfig,
) -> Any:
    """Build an ``AtlasROI`` from hemisphere-prefixed cortical region names.

    Parameters
    ----------
    subject_id : str
        Subject identifier (no ``sub-`` prefix).
    seg_dir : str
        ``m2m_{subject}/segmentation/`` directory.
    atlas_display : str
        Atlas display name (e.g. ``"DK40"``).
    regions : list of (str, str)
        ``(hemisphere, region_name)`` tuples, as returned by
        :func:`parse_region_names`.
    roi_cls : type, optional
        The config class owning the ``AtlasROI`` dataclass to build.
        Defaults to :class:`~tit.opt.config.FlexConfig`.

    Returns
    -------
    roi_cls.AtlasROI
        A union across every resolved region (parallel ``atlas_path`` /
        ``hemisphere`` / ``label`` lists), scalar-collapsed for a single
        region.

    Raises
    ------
    ValueError
        If none of *regions* resolve to a known annotation label.
    """
    atlas_name = resolve_atlas_name_for_subject(atlas_display, subject_id)
    name_map = resolve_cortical_region_index_map(seg_dir, atlas_display)

    atlas_paths, hemispheres, labels = [], [], []
    for hemi, name in regions:
        index = name_map.get((hemi, name))
        if index is None:
            continue
        labels.append(index)
        hemispheres.append(hemi)
        atlas_paths.append(os.path.join(seg_dir, f"{hemi}.{atlas_name}.annot"))

    if not labels:
        raise ValueError(
            f"Could not resolve any cortical region name(s) for atlas "
            f"{atlas_name!r}; the annotation files could not be read."
        )

    return roi_cls.AtlasROI(
        atlas_path=_collapse(atlas_paths),
        label=_collapse(labels),
        hemisphere=_collapse(hemispheres),
    )


# ---------------------------------------------------------------------------
# Volumetric (subcortical) atlas resolution
# ---------------------------------------------------------------------------


def _mni_atlas_dir() -> str:
    if os.path.isdir(MNI_ATLAS_DIR):
        return MNI_ATLAS_DIR
    return str(Path(__file__).resolve().parents[2] / "resources" / "atlas")


def resolve_volume_atlas_path(
    *,
    subject_id: str,
    seg_dir: str,
    freesurfer_mri_dir: str = "",
    atlas_filename: str,
    atlas_space: str,
    fastsurfer_mri_dir: str = "",
) -> str:
    """Resolve a volumetric atlas display name/space to an absolute path.

    Mirrors ``RoiPickerWidget._selected_volume_atlas_path`` for the cases
    that do not already carry a full path (e.g. from
    :meth:`tit.atlas.voxel.VoxelAtlasManager.list_atlases`, which returns
    ``(display_name, path)`` pairs directly -- pass ``path`` straight
    through in that case, this helper is only needed for a bare filename).

    Parameters
    ----------
    subject_id : str
        Subject identifier.
    seg_dir : str
        ``m2m_{subject}/segmentation/`` directory (for ``labeling.nii.gz``).
    freesurfer_mri_dir : str, optional
        Legacy FreeSurfer ``mri/`` directory (``recon-all`` volume atlases).
    atlas_filename : str
        Bare atlas filename (e.g. ``"aparc.DKTatlas+aseg.deep.mgz"``).
    atlas_space : str
        ``"subject"`` or ``"mni"``.
    fastsurfer_mri_dir : str, optional
        FastSurfer ``mri/`` directory. Searched before *freesurfer_mri_dir*,
        matching :meth:`tit.atlas.voxel.VoxelAtlasManager.list_atlases`.
    """
    if str(atlas_space).lower() == "mni":
        return os.path.join(_mni_atlas_dir(), atlas_filename)
    if atlas_filename == "labeling.nii.gz":
        return os.path.join(seg_dir, atlas_filename)
    if fastsurfer_mri_dir:
        candidate = os.path.join(fastsurfer_mri_dir, atlas_filename)
        if os.path.isfile(candidate) or not freesurfer_mri_dir:
            return candidate
    return os.path.join(freesurfer_mri_dir, atlas_filename)


def build_subcortical_roi(
    *,
    atlas_path: str,
    labels: list[int],
    tissues: str = "GM",
    atlas_space: str = "subject",
    roi_cls: type = FlexConfig,
) -> Any:
    """Build a ``SubcorticalROI`` from a resolved atlas path and labels.

    Parameters
    ----------
    atlas_path : str
        Absolute path to the volumetric atlas/mask file.
    labels : list of int
        Integer label(s) within the atlas.
    tissues : str, optional
        ``"GM"``, ``"WM"``, or ``"both"``.
    atlas_space : str, optional
        ``"subject"`` or ``"mni"``.
    roi_cls : type, optional
        The config class owning the ``SubcorticalROI`` dataclass to build.
    """
    return roi_cls.SubcorticalROI(
        atlas_path=atlas_path,
        label=_collapse(list(labels)),
        tissues=tissues,
        atlas_space=atlas_space,
    )


def build_spherical_roi(
    *,
    centers: list[tuple[float, float, float]],
    radii: list[float],
    use_mni: bool = False,
    volumetric: bool = False,
    tissues: str = "GM",
    roi_cls: type = FlexConfig,
) -> Any:
    """Build a ``SphericalROI`` from one or more sphere centers/radii."""
    return roi_cls.SphericalROI(
        x=_collapse([c[0] for c in centers]),
        y=_collapse([c[1] for c in centers]),
        z=_collapse([c[2] for c in centers]),
        radius=_collapse(list(radii)),
        use_mni=use_mni,
        volumetric=volumetric,
        tissues=tissues if volumetric else "GM",
    )


def get_roi_spec(
    roi_type: str,
    *,
    subject_id: str,
    seg_dir: str,
    freesurfer_mri_dir: str = "",
    fastsurfer_mri_dir: str = "",
    roi_cls: type = FlexConfig,
    # spherical
    centers: list[tuple[float, float, float]] | None = None,
    radii: list[float] | None = None,
    use_mni: bool = False,
    volumetric: bool = False,
    sphere_tissues: str = "GM",
    # cortical
    atlas_display: str | None = None,
    regions: list[tuple[str, str]] | None = None,
    # subcortical
    volume_atlas_path: str | None = None,
    volume_atlas_filename: str | None = None,
    volume_atlas_space: str = "subject",
    subcortical_labels: list[int] | None = None,
    subcortical_tissues: str = "GM",
) -> Any:
    """Build the ROI dataclass matching *roi_type* from plain parameters.

    The single entry point mirroring ``RoiPickerWidget.get_roi_spec``, split
    into three dispatchable builders (:func:`build_spherical_roi`,
    :func:`build_cortical_atlas_roi`, :func:`build_subcortical_roi`) so
    callers that already know their ROI type can call the specific builder
    directly instead.

    Parameters
    ----------
    roi_type : str
        One of ``"spherical"``, ``"atlas"``/``"cortical"``, ``"subcortical"``.
    subject_id, seg_dir, freesurfer_mri_dir, fastsurfer_mri_dir : str
        Subject context (the three directory arguments are unused for the
        ``"spherical"`` type).
    roi_cls : type, optional
        The config class owning the ROI dataclasses to build. Defaults to
        :class:`~tit.opt.config.FlexConfig`.

    Returns
    -------
    roi_cls.SphericalROI or roi_cls.AtlasROI or roi_cls.SubcorticalROI

    Raises
    ------
    ValueError
        If *roi_type* is unknown, or a required parameter for that type is
        missing (mirrors the nested dataclasses' own ``__post_init__``
        errors where possible).
    """
    kind = str(roi_type).strip().lower()
    if kind == "spherical":
        if not centers or not radii:
            raise ValueError("spherical ROI requires centers and radii")
        return build_spherical_roi(
            centers=centers,
            radii=radii,
            use_mni=use_mni,
            volumetric=volumetric,
            tissues=sphere_tissues,
            roi_cls=roi_cls,
        )
    if kind in ("atlas", "cortical"):
        if not atlas_display or not regions:
            raise ValueError("cortical ROI requires atlas_display and regions")
        return build_cortical_atlas_roi(
            subject_id=subject_id,
            seg_dir=seg_dir,
            atlas_display=atlas_display,
            regions=regions,
            roi_cls=roi_cls,
        )
    if kind == "subcortical":
        if not subcortical_labels:
            raise ValueError("subcortical ROI requires subcortical_labels")
        path = volume_atlas_path
        if path is None:
            if not volume_atlas_filename:
                raise ValueError(
                    "subcortical ROI requires volume_atlas_path or "
                    "volume_atlas_filename"
                )
            path = resolve_volume_atlas_path(
                subject_id=subject_id,
                seg_dir=seg_dir,
                freesurfer_mri_dir=freesurfer_mri_dir,
                fastsurfer_mri_dir=fastsurfer_mri_dir,
                atlas_filename=volume_atlas_filename,
                atlas_space=volume_atlas_space,
            )
        return build_subcortical_roi(
            atlas_path=path,
            labels=subcortical_labels,
            tissues=subcortical_tissues,
            atlas_space=volume_atlas_space,
            roi_cls=roi_cls,
        )
    raise ValueError(
        f"Unknown roi_type {roi_type!r}; expected 'spherical', 'atlas', or "
        "'subcortical'"
    )


# ---------------------------------------------------------------------------
# LUT / label-name resolution (volumetric atlases)
# ---------------------------------------------------------------------------


def _is_custom_mask(atlas_path: str) -> bool:
    """True for a user-supplied volume in ``m2m_{subject}/masks/``."""
    return Path(atlas_path).parent.name == "masks"


def _strip_nifti_suffix(filename: str) -> str:
    if filename.endswith(".nii.gz"):
        return filename[:-7]
    return os.path.splitext(filename)[0]


def _parse_lut_line(
    line: str,
) -> tuple[str, str, tuple[str, str, str] | None] | None:
    """Parse one FreeSurfer-style LUT line, column-order agnostic."""
    parts = line.split()
    if len(parts) < 2:
        return None

    label_id = parts[0]
    if not label_id.lstrip("-").isdigit():
        return None

    rest = parts[1:]
    name_tokens = [p for p in rest if not p.lstrip("-").isdigit()]
    int_tokens = [p for p in rest if p.lstrip("-").isdigit()]
    if not name_tokens:
        return None
    label_name = " ".join(name_tokens)
    rgb = tuple(int_tokens[:3]) if len(int_tokens) >= 3 else None
    return label_id, label_name, rgb


def _find_volume_lut(atlas_path: str, atlas_space: str) -> Path | None:
    """Find a sidecar colour-table file for a volumetric atlas, if any."""
    atlas = Path(atlas_path)
    if _is_custom_mask(atlas_path):
        lut_path = atlas.with_name(f"{_strip_nifti_suffix(atlas.name)}_LUT.txt")
        return lut_path if lut_path.is_file() else None
    if str(atlas_space).lower() == "subject":
        if atlas.name == "labeling.nii.gz":
            lut_path = atlas.with_name("labeling_LUT.txt")
            return lut_path if lut_path.is_file() else None
        # FreeSurfer subject atlases (e.g. aparc.DKTatlas+aseg) resolve via
        # the bundled FreeSurferColorLUT instead (see resolve_volume_label_names).
        return None

    stem = _strip_nifti_suffix(atlas.name)
    candidates = [
        atlas.with_name(f"{stem}_LUT.txt"),
        atlas.with_name(f"{stem}_labels.txt"),
        atlas.with_name(f"{stem}.txt"),
    ]
    if stem.lower().startswith("massp"):
        candidates.append(atlas.with_name("massp2021_labels.txt"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _load_freesurfer_lut() -> dict[int, tuple[str, tuple[str, str, str] | None]]:
    """Parse the bundled standard FreeSurfer colour table.

    Returns an empty dict when the bundled table cannot be located or read.
    """
    lut_path = os.path.join(_mni_atlas_dir(), "FreeSurferColorLUT.txt")
    if not os.path.isfile(lut_path):
        return {}

    lut: dict[int, tuple[str, tuple[str, str, str] | None]] = {}
    try:
        with open(lut_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parsed = _parse_lut_line(line)
                if parsed is None:
                    continue
                label_id, label_name, rgb = parsed
                lut[int(label_id)] = (label_name, rgb)
    except OSError:
        return {}
    return lut


def resolve_volume_label_names(
    atlas_path: str, atlas_space: str = "subject"
) -> dict[int, str]:
    """Resolve ``label_id -> region name`` for a volumetric atlas.

    Reads a sidecar LUT when one exists next to *atlas_path*; otherwise
    falls back to the unique nonzero integer labels actually present in the
    volume (via nibabel), named from the bundled standard FreeSurfer colour
    table. Mirrors ``RoiPickerWidget._subcortical_id_name_map`` /
    ``_resolve_volume_label_entries``.

    Parameters
    ----------
    atlas_path : str
        Absolute path to the atlas volume (``.mgz``/``.nii``/``.nii.gz``).
    atlas_space : str, optional
        ``"subject"`` or ``"mni"`` -- only affects sidecar-LUT discovery.

    Returns
    -------
    dict
        Empty when the atlas cannot be read (e.g. nibabel not installed, or
        no subject data yet) rather than raising -- callers fall back to
        showing the bare integer label.
    """
    lut_file = _find_volume_lut(atlas_path, atlas_space)
    if lut_file is not None:
        names: dict[int, str] = {}
        try:
            with open(lut_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parsed = _parse_lut_line(line)
                    if parsed is None:
                        continue
                    label_id, label_name, _ = parsed
                    names[int(label_id)] = label_name
            return names
        except OSError:
            return {}

    try:
        import numpy as np
        import nibabel as nib
    except ImportError:
        return {}

    lut = _load_freesurfer_lut()
    if not lut and not _is_custom_mask(atlas_path):
        return {}

    try:
        img = nib.load(atlas_path)
        present = np.unique(np.asarray(img.dataobj))
    except (OSError, ValueError):
        return {}

    keep_unknown = _is_custom_mask(atlas_path)
    names = {}
    for value in present:
        label_id = int(value)
        if label_id == 0:
            continue
        info = lut.get(label_id)
        if info is None:
            if not keep_unknown:
                continue
            names[label_id] = f"Label {label_id}"
            continue
        names[label_id] = info[0]
    return names
