#!/usr/bin/env python3
"""Build the public atlas-browser data assets from resources/atlas/ and the
bundled SimNIBS example subject (ernie).

Writes, deterministically and idempotently:
  - docs/assets/atlas/mni152_t1_1mm.nii.gz   (MNI template, uint8, 5-bit quantised)
  - docs/assets/atlas/cit168.nii.gz          (resampled onto the MNI template grid, order=0)
  - docs/assets/atlas/morel.nii.gz           (resampled onto the MNI template grid, order=0)
  - docs/assets/atlas/glasser.nii.gz         (resampled onto the MNI template grid, order=0)
  - docs/assets/atlas/massp.nii.gz           (resampled onto the MNI template grid, order=0)
  - docs/assets/atlas/ernie_t1.nii.gz        (ernie subject T1, uint8, 5-bit quantised)
  - docs/assets/atlas/ernie_charm.nii.gz     (resampled onto the ernie T1 grid, order=0)
  - docs/assets/atlas/ernie_dkt.nii.gz       (resampled onto the ernie T1 grid, order=0)
  - docs/assets/atlas/ernie_a2009s.nii.gz    (resampled onto the ernie T1 grid, order=0)
  - docs/assets/atlas/ernie_massp.nii.gz     (resampled onto the ernie T1 grid, order=0)
  - docs/_data/atlases.json                  (per-space, per-atlas metadata + per-label rows)

Every label volume is nearest-neighbour resampled (nibabel.processing.
resample_from_to, order=0) onto the exact voxel grid of that space's
template -- MNI152_T1_1mm.nii.gz for the four MNI atlases, the ernie
example subject's own T1.nii.gz for the four subject atlases -- so a
browser can overlay any atlas on its matching template with a single
shared affine. Morel already ships on the MNI template grid, and CHARM /
subject-space MASSP already ship on the ernie T1 grid; the resample is
still applied to them for a uniform code path (a no-op there).

Two known data defects in resources/atlas/ are handled explicitly, not
silently patched into the source files:

  - Morel's LUT declares labels 27 and 127 (sPf) but they have zero voxels in
    the shipped volume. Only labels actually present in the written volume
    are emitted (expected: 74, not the LUT's 76).
  - MNI_Glasser_HCP_v1.0.txt is missing the row for label 1050 (R-MIP), so
    Glasser names are sourced from HCP-Multi-Modal-Parcellation-1.0.xml
    instead (complete, 361 <label> entries). The XML's "L_"/"R_" + underscore
    naming is converted to the .txt's "L-"/"R-" + underscore convention by
    replacing only the first underscore with a hyphen -- verified to
    reproduce all 360 names already present in the .txt exactly. Colors still
    come from the .txt (the only RGB source); label 1050 has no RGB anywhere
    in the repo, so a deterministic placeholder color is synthesized for it
    and flagged in the printed report.

The four subject atlases come from the ernie example subject's own
derivatives, read directly from a local dataset (not checked into this
repo) -- override the two directories below via the TI_ATLAS_SUBJECT_M2M
and TI_ATLAS_SUBJECT_FS_MRI environment variables if your dataset lives
somewhere else. Subject-space row centroids are in the subject's own
scanner/world coordinates, not MNI; the JSON field is still named
"centroid_mni" (kept uniform for the viewer code), but each subject
atlas's "native_space" string says explicitly that these are subject-space
world-mm coordinates.

Run with the host python3 (numpy, scipy, nibabel -- no SimNIBS/nilearn
needed). Not wired into CI: assets are generated offline and committed.

    python3 dev/build_atlas_assets.py
"""

from __future__ import annotations

import colorsys
import gzip
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import nibabel as nib
import numpy as np
from nibabel.processing import resample_from_to

REPO_ROOT = Path(__file__).resolve().parents[1]
ATLAS_DIR = REPO_ROOT / "resources" / "atlas"
OUT_ASSET_DIR = REPO_ROOT / "docs" / "assets" / "atlas"
OUT_DATA_DIR = REPO_ROOT / "docs" / "_data"
OUT_JSON = OUT_DATA_DIR / "atlases.json"

# Local dataset directories for the bundled SimNIBS example subject (ernie).
# Not part of this repo -- override via env vars if your dataset lives
# elsewhere; defaults match the dev machine this script was written on.
SUBJECT_M2M_DIR = Path(
    os.environ.get(
        "TI_ATLAS_SUBJECT_M2M",
        "/Users/idohaber/datasets/000/derivatives/SimNIBS/sub-ernie/m2m_ernie",
    )
)
SUBJECT_FS_MRI_DIR = Path(
    os.environ.get(
        "TI_ATLAS_SUBJECT_FS_MRI",
        "/Users/idohaber/datasets/000/derivatives/freesurfer/sub-ernie/mri",
    )
)

TEMPLATE_FILE = "MNI152_T1_1mm.nii.gz"
SUBJECT_TEMPLATE_FILE = SUBJECT_M2M_DIR / "T1.nii.gz"
TEMPLATE_QUANT_BITS = 5
TEMPLATE_PERCENTILES = (1.0, 99.0)  # over voxels > 0, matches the measured prototype

# Order mirrors tit/atlas/constants.py MNI_ATLAS_FILES.
ATLASES = [
    dict(
        key="cit168",
        display_name="CIT168 Subcortical Atlas",
        src_path=ATLAS_DIR / "CIT168_labeling_MNI152NLin2009cAsym.nii.gz",
        lut_path=ATLAS_DIR / "CIT168_labeling_MNI152NLin2009cAsym_LUT.txt",
        out_filename="cit168.nii.gz",
        native_space="MNI152NLin2009cAsym (per source NeuroVault metadata)",
        out_dtype=np.uint8,
        expected_label_count=16,
        provenance=(
            "Pauli WM, Nili AN, Tyszka JM. A high-resolution probabilistic in vivo "
            "atlas of human subcortical brain nuclei. Scientific Data 5:180063 (2018). "
            "doi:10.1038/sdata.2018.63. Source: NeuroVault collection 3145. Deterministic "
            "label map derived locally by winner-takes-highest-probability, threshold 0.05; "
            "the probabilistic source masks are not shipped."
        ),
    ),
    dict(
        key="morel",
        display_name="Morel Thalamus Atlas",
        src_path=ATLAS_DIR / "MorelMNI152_labeling_1mm.nii.gz",
        lut_path=ATLAS_DIR / "MorelMNI152_labeling_1mm_LUT.txt",
        out_filename="morel.nii.gz",
        native_space="MNI152, FSL-aligned 182x218x182 1mm grid (same grid as the shipped template)",
        out_dtype=np.uint16,
        expected_label_count=74,
        provenance=(
            "Morel Atlas of the Human Thalamus, MNI152 space, voxelized version. Zenodo "
            "doi:10.5281/zenodo.13918589. (C) University of Zurich and ETH Zurich, Andras "
            "Jakab, Remi Blanc and Gabor Szekely. License: CC BY-NC-SA 4.0 (non-commercial, "
            "share-alike). Recommended citations: Jakab A, Blanc R, Berenyi E, Szekely G. "
            "AJNR 33(11):2110-2116 (2012); Krauth A, et al. NeuroImage 49(3):2053-2062 (2010). "
            "Labels 27 and 127 (sPf) are declared in the LUT but have zero voxels after the "
            "source atlas's overlap rule (first listed label wins) and are omitted here."
        ),
    ),
    dict(
        key="glasser",
        display_name="Glasser HCP-MMP1.0 Atlas",
        src_path=ATLAS_DIR / "MNI_Glasser_HCP_v1.0.nii.gz",
        lut_path=ATLAS_DIR / "MNI_Glasser_HCP_v1.0.txt",
        out_filename="glasser.nii.gz",
        native_space="FreeSurfer-conformed 256x256x256 1mm grid (not the MNI152 182x218x182 grid)",
        out_dtype=np.uint16,
        expected_label_count=360,
        provenance=(
            "Glasser MF, Coalson TS, Robinson EC, et al. A multi-modal parcellation of "
            "human cerebral cortex. Nature 536(7615):171-178 (2016). doi:10.1038/nature18933. "
            "Region names sourced from HCP-Multi-Modal-Parcellation-1.0.xml (complete, 360 "
            "regions) rather than MNI_Glasser_HCP_v1.0.txt, which is missing the row for "
            "label 1050 (R-MIP); that label's display color could not be recovered from any "
            "source in this repository and was synthesized."
        ),
    ),
    dict(
        key="massp",
        display_name="MASSP Subcortical Parcellation",
        src_path=ATLAS_DIR / "massp2021-parcellation_decade-18to40.nii.gz",
        lut_path=ATLAS_DIR / "massp2021_labels.txt",
        out_filename="massp.nii.gz",
        native_space="ICBM152 2009b nonlinear asymmetric, hi-res 0.5mm (per NIfTI descrip field)",
        out_dtype=np.uint8,
        expected_label_count=31,
        provenance=(
            "MASSP 2021 subcortical parcellation, decade 18-40 template "
            "(massp2021-parcellation_decade-18to40.nii.gz). No literature reference, DOI, or "
            "license is recorded anywhere in this repository for this atlas; "
            "resources/atlas/README.md documents only its filenames and a usage caveat."
        ),
    ),
]

# Subject-space atlases for the bundled SimNIBS example subject (ernie).
# Resampled onto the ernie T1 grid (see SUBJECT_TEMPLATE_FILE), not the MNI
# template grid. Row centroids are therefore in ernie's own scanner/world
# coordinates, not MNI -- each entry's native_space string says so.
SUBJECT_ATLASES = [
    dict(
        key="charm",
        display_name="CHARM tissue labeling",
        src_path=SUBJECT_M2M_DIR / "segmentation" / "labeling.nii.gz",
        lut_path=SUBJECT_M2M_DIR / "segmentation" / "labeling_LUT.txt",
        out_filename="ernie_charm.nii.gz",
        native_space="ernie subject space (world mm)",
        out_dtype=np.uint16,
        expected_label_count=56,
        provenance=(
            "CHARM tissue labeling, produced by SimNIBS `charm` for the bundled ernie "
            "example subject (derivatives/SimNIBS/sub-ernie/m2m_ernie/segmentation/"
            "labeling.nii.gz). Labels and colors from the sidecar labeling_LUT.txt."
        ),
    ),
    dict(
        key="dkt",
        display_name="Desikan-Killiany-Tourville (aparc.DKTatlas+aseg)",
        src_path=SUBJECT_FS_MRI_DIR / "aparc.DKTatlas+aseg.mgz",
        lut_path=ATLAS_DIR / "FreeSurferColorLUT.txt",
        out_filename="ernie_dkt.nii.gz",
        native_space="ernie subject space (world mm)",
        out_dtype=np.uint16,
        expected_label_count=102,
        provenance=(
            "Desikan-Killiany-Tourville cortical parcellation plus subcortical "
            "segmentation, produced by FreeSurfer `recon-all` for the bundled ernie "
            "example subject (derivatives/freesurfer/sub-ernie/mri/"
            "aparc.DKTatlas+aseg.mgz). Labels and colors from "
            "resources/atlas/FreeSurferColorLUT.txt."
        ),
    ),
    dict(
        key="a2009s",
        display_name="Destrieux (aparc.a2009s+aseg)",
        src_path=SUBJECT_FS_MRI_DIR / "aparc.a2009s+aseg.mgz",
        lut_path=ATLAS_DIR / "FreeSurferColorLUT.txt",
        out_filename="ernie_a2009s.nii.gz",
        native_space="ernie subject space (world mm)",
        out_dtype=np.uint16,
        expected_label_count=188,
        provenance=(
            "Destrieux cortical parcellation plus subcortical segmentation, produced by "
            "FreeSurfer `recon-all` for the bundled ernie example subject "
            "(derivatives/freesurfer/sub-ernie/mri/aparc.a2009s+aseg.mgz). Labels and "
            "colors from resources/atlas/FreeSurferColorLUT.txt."
        ),
    ),
    dict(
        key="massp",
        display_name="MASSP subcortical (subject space)",
        src_path=SUBJECT_M2M_DIR / "segmentation" / "massp2021_subject.nii.gz",
        lut_path=ATLAS_DIR / "massp2021_labels.txt",
        out_filename="ernie_massp.nii.gz",
        native_space="ernie subject space (world mm)",
        out_dtype=np.uint8,
        expected_label_count=31,
        provenance=(
            "MASSP subcortical parcellation, warped from MNI into the bundled ernie "
            "example subject's native space by SimNIBS `charm` (derivatives/SimNIBS/"
            "sub-ernie/m2m_ernie/segmentation/massp2021_subject.nii.gz). Labels and "
            "colors from resources/atlas/massp2021_labels.txt."
        ),
    ),
]


# ---------------------------------------------------------------------------
# LUT parsing -- mirrors tit/gui/components/roi_picker.py::_parse_lut_line
# exactly (column-order agnostic: parts[0] is the integer id, every non-
# integer remaining token is part of the name, the first three integer
# tokens are RGB), so this script and the GUI agree on every label name.
# ---------------------------------------------------------------------------


def _is_int_token(token: str) -> bool:
    return token.lstrip("-").isdigit()


def _parse_lut_line(line: str) -> tuple[int, str, tuple[int, int, int] | None] | None:
    parts = line.split()
    if len(parts) < 2:
        return None
    if not _is_int_token(parts[0]):
        return None
    rest = parts[1:]
    name_tokens = [p for p in rest if not _is_int_token(p)]
    int_tokens = [p for p in rest if _is_int_token(p)]
    if not name_tokens:
        return None
    label_name = " ".join(name_tokens)
    rgb = tuple(int(p) for p in int_tokens[:3]) if len(int_tokens) >= 3 else None
    return int(parts[0]), label_name, rgb


def _load_lut(path: Path) -> dict[int, tuple[str, tuple[int, int, int] | None]]:
    lut: dict[int, tuple[str, tuple[int, int, int] | None]] = {}
    for line in path.read_text().splitlines():
        parsed = _parse_lut_line(line)
        if parsed is None:
            continue
        label_id, name, rgb = parsed
        lut[label_id] = (name, rgb)
    return lut


def _glasser_xml_names(xml_path: Path) -> dict[int, str]:
    """Region names for every Glasser label, from the complete XML atlas metadata.

    The XML spells names "L_V1" / "R_MIP"; the sidecar .txt LUT spells them
    "L-V1" / "R-MIP" (hyphen after the hemisphere letter, underscores kept in
    the rest of the abbreviation). Replacing only the first underscore
    reproduces the .txt name exactly for all 360 labels present in both files
    -- verified before writing this script.
    """
    names: dict[int, str] = {}
    for label in ET.parse(xml_path).getroot().iter("label"):
        label_id = int(label.get("index"))
        if label_id == 0:
            continue  # background placeholder "*.*.*.*.*"
        names[label_id] = (label.text or "").strip().replace("_", "-", 1)
    return names


def _glasser_label_table(atlas_dir: Path) -> dict[int, tuple[str, tuple[int, int, int] | None]]:
    names = _glasser_xml_names(atlas_dir / "HCP-Multi-Modal-Parcellation-1.0.xml")
    colors = _load_lut(atlas_dir / "MNI_Glasser_HCP_v1.0.txt")
    return {
        label_id: (name, colors.get(label_id, (None, None))[1])
        for label_id, name in names.items()
    }


def _synthesize_rgb(label_id: int) -> tuple[int, int, int]:
    """Deterministic placeholder color for a label with no RGB in any source file.

    Only ever used for Glasser label 1050 (R-MIP), whose row is entirely
    absent from MNI_Glasser_HCP_v1.0.txt. Golden-ratio hue stepping keeps the
    color visually distinct from its neighbours; the function is a pure
    function of label_id so re-running this script is idempotent.
    """
    hue = (label_id * 0.6180339887498949) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.55, 0.85)
    return int(round(r * 255)), int(round(g * 255)), int(round(b * 255))


def _round_num(value: float, decimals: int = 1) -> float | int:
    rounded = round(float(value), decimals)
    return int(rounded) if float(rounded).is_integer() else rounded


# ---------------------------------------------------------------------------
# Volume builders
# ---------------------------------------------------------------------------


def _write_gz_nifti(img: nib.Nifti1Image, out_path: Path) -> int:
    raw = img.to_bytes()
    payload = gzip.compress(raw, 9, mtime=0)  # mtime=0 keeps output byte-identical across runs
    out_path.write_bytes(payload)
    return len(payload)


def build_template(tpl_img: nib.Nifti1Image, out_path: Path) -> int:
    data = np.asanyarray(tpl_img.dataobj).astype(np.float32)
    lo, hi = np.percentile(data[data > 0], TEMPLATE_PERCENTILES)
    levels = 2**TEMPLATE_QUANT_BITS
    clipped = np.clip((data - lo) / (hi - lo), 0.0, 1.0)
    quantized = np.round(clipped * (levels - 1)).astype(np.uint8)

    out_img = nib.Nifti1Image(quantized, tpl_img.affine)
    out_img.set_data_dtype(np.uint8)
    qform_code = int(tpl_img.header["qform_code"])
    sform_code = int(tpl_img.header["sform_code"])
    out_img.header.set_qform(tpl_img.affine, code=qform_code)
    out_img.header.set_sform(tpl_img.affine, code=sform_code)
    out_img.header["cal_min"] = 0
    out_img.header["cal_max"] = levels - 1

    return _write_gz_nifti(out_img, out_path)


def build_atlas(spec: dict, tpl_img: nib.Nifti1Image, out_dir: Path) -> dict:
    src_img = nib.load(spec["src_path"])
    resampled = resample_from_to(src_img, (tpl_img.shape, tpl_img.affine), order=0)
    data = np.rint(np.nan_to_num(np.asanyarray(resampled.dataobj))).astype(np.int64)
    data[data < 0] = 0

    if spec["key"] == "glasser":
        label_table = _glasser_label_table(ATLAS_DIR)
    else:
        label_table = _load_lut(spec["lut_path"])

    present_ids = sorted(int(i) for i in np.unique(data) if i > 0)
    # Voxel volume from the determinant of the 3x3 direction block, NOT from
    # its diagonal. ernie's T1 is PSR-oriented, so its affine is a permutation
    # matrix with zeros on the diagonal and a diagonal product of 0, which
    # silently zeroed every subject-space volume. The determinant is correct
    # for any orientation, including oblique acquisitions.
    voxel_vol = float(abs(np.linalg.det(tpl_img.affine[:3, :3])))

    rows = []
    unresolved: list[int] = []
    for label_id in present_ids:
        entry = label_table.get(label_id)
        name, rgb = entry if entry is not None else (None, None)
        if name is None:
            name = f"label_{label_id}"
            unresolved.append(label_id)
        if rgb is None:
            rgb = _synthesize_rgb(label_id)
            if label_id not in unresolved:
                unresolved.append(label_id)

        mask = data == label_id
        voxels = int(mask.sum())
        centroid_vox = np.argwhere(mask).mean(axis=0)
        centroid_mni = tpl_img.affine @ np.append(centroid_vox, 1.0)
        rows.append(
            {
                "id": label_id,
                "index": len(rows) + 1,
                "name": name,
                "r": int(rgb[0]),
                "g": int(rgb[1]),
                "b": int(rgb[2]),
                "voxels": voxels,
                "volume_mm3": _round_num(voxels * voxel_vol),
                "centroid_mni": [_round_num(v) for v in centroid_mni[:3]],
            }
        )

    # Remap the published volume to compact 1..N indices, ordered by original
    # label id. NiiVue's label colormap is uploaded as a texture whose width is
    # the HIGHEST label index, so a sparse scheme costs far more than it looks:
    # Destrieux tops out at 12175, needing a 12176-wide texture, and
    # MAX_TEXTURE_SIZE is only 8192 on some drivers (measured on SwiftShader).
    # It then fails silently — the overlay simply never appears, and whether it
    # does depends on the viewer's GPU. Compacting caps every LUT at N+1
    # entries (188 for the worst atlas here) and shrinks the volumes too.
    #
    # These display volumes therefore do NOT carry the original label values.
    # Each row records both: "id" is the true atlas label, "index" is the value
    # in the published volume. The shipped atlases in resources/atlas/ are
    # untouched.
    remap = np.zeros(int(data.max()) + 1, dtype=np.int64)
    for row in rows:
        remap[row["id"]] = row["index"]
    data = remap[data]

    n_labels = len(rows)
    out_dtype = np.uint8 if n_labels <= 255 else np.uint16
    out_img = nib.Nifti1Image(data.astype(out_dtype), tpl_img.affine)
    out_img.set_data_dtype(out_dtype)
    qform_code = int(tpl_img.header["qform_code"])
    sform_code = int(tpl_img.header["sform_code"])
    out_img.header.set_qform(tpl_img.affine, code=qform_code)
    out_img.header.set_sform(tpl_img.affine, code=sform_code)

    bytes_written = _write_gz_nifti(out_img, out_dir / spec["out_filename"])
    total_voxels = sum(r["voxels"] for r in rows)

    return {
        "rows": rows,
        "n_labels": len(present_ids),
        "bytes_written": bytes_written,
        "unresolved_ids": unresolved,
        "total_voxels": total_voxels,
        "total_volume_mm3": _round_num(total_voxels * voxel_vol),
    }


def build_space(
    space_key: str,
    template_src: Path,
    template_out_name: str,
    atlas_specs: list[dict],
    out_dir: Path,
) -> tuple[Path, list[tuple[Path, int]], dict[str, dict]]:
    """Build one space's template plus all of its atlases.

    Returns the template's output path (for later disk-based verification),
    this space's byte-report rows, and this space's atlases.json sub-dict
    (keyed by atlas key).
    """
    tpl_img = nib.load(template_src)

    report_rows: list[tuple[Path, int]] = []
    tpl_out = out_dir / template_out_name
    report_rows.append((tpl_out, build_template(tpl_img, tpl_out)))

    atlases_json: dict[str, dict] = {}

    print(f"[{space_key}] build report (label counts computed while writing)")
    print("-" * 72)
    for spec in atlas_specs:
        result = build_atlas(spec, tpl_img, out_dir)
        report_rows.append((out_dir / spec["out_filename"], result["bytes_written"]))

        expected = spec["expected_label_count"]
        actual = result["n_labels"]
        status = "OK" if actual == expected else "MISMATCH"
        print(f"  {spec['key']:10s} {actual:4d} labels (expected {expected:4d})  [{status}]")
        if result["unresolved_ids"]:
            print(
                f"  {spec['key']:10s} WARNING: no LUT name/color for ids "
                f"{result['unresolved_ids']} -- name/color synthesized"
            )

        atlases_json[spec["key"]] = {
            "display_name": spec["display_name"],
            "filename": spec["out_filename"],
            "native_space": spec["native_space"],
            "voxel_count": result["total_voxels"],
            "volume_mm3": result["total_volume_mm3"],
            "provenance": spec["provenance"],
            "rows": result["rows"],
        }
    print()

    return tpl_out, report_rows, atlases_json


def verify_written_outputs(
    space_key: str, tpl_out: Path, atlas_specs: list[dict], out_dir: Path
) -> list[str]:
    """Re-load every written file from disk (not the in-memory build arrays)
    and check label counts, shape, and affine against that space's own
    written template. Returns human-readable problem strings; empty means
    everything checked out.
    """
    problems: list[str] = []
    tpl_img = nib.load(tpl_out)

    print(f"[{space_key}] verification (re-loaded from the written files on disk)")
    print("-" * 72)
    for spec in atlas_specs:
        img = nib.load(out_dir / spec["out_filename"])
        shape_ok = img.shape == tpl_img.shape
        affine_ok = bool(np.allclose(img.affine, tpl_img.affine, atol=1e-4))
        data = np.asanyarray(img.dataobj)
        actual = int(len(np.unique(data[data > 0])))
        expected = spec["expected_label_count"]
        count_ok = actual == expected
        # The published volumes are compacted to 1..N, so the highest value
        # must equal the label count. If it does not, the LUT texture would be
        # sized by a sparse maximum and can blow past MAX_TEXTURE_SIZE, which
        # makes the overlay vanish on some GPUs and not others.
        max_idx = int(data.max())
        compact_ok = max_idx == actual
        status = "OK" if (shape_ok and affine_ok and count_ok and compact_ok) else "MISMATCH"
        print(
            f"  {spec['key']:10s} {actual:4d} labels (expected {expected:4d})  "
            f"max_index={max_idx} compact={compact_ok} "
            f"shape={img.shape} affine_ok={affine_ok}  [{status}]"
        )
        if not compact_ok:
            problems.append(
                f"[{space_key}] {spec['key']}: volume not compacted "
                f"(max index {max_idx}, {actual} labels)"
            )
        if not shape_ok:
            problems.append(
                f"{space_key}/{spec['key']}: written shape {img.shape} != "
                f"template shape {tpl_img.shape}"
            )
        if not affine_ok:
            problems.append(f"{space_key}/{spec['key']}: written affine != template affine")
        if not count_ok:
            problems.append(
                f"{space_key}/{spec['key']}: {actual} labels in the written file "
                f"(expected {expected})"
            )
    print()
    return problems


def main() -> int:
    if not ATLAS_DIR.is_dir():
        print(f"ERROR: atlas source directory not found: {ATLAS_DIR}")
        return 2
    if not SUBJECT_M2M_DIR.is_dir():
        print(f"ERROR: subject m2m directory not found: {SUBJECT_M2M_DIR}")
        return 2
    if not SUBJECT_FS_MRI_DIR.is_dir():
        print(f"ERROR: subject FreeSurfer mri directory not found: {SUBJECT_FS_MRI_DIR}")
        return 2

    OUT_ASSET_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    report_rows: list[tuple[Path, int]] = []

    mni_tpl_out, mni_report_rows, mni_atlases_json = build_space(
        "mni", ATLAS_DIR / TEMPLATE_FILE, "mni152_t1_1mm.nii.gz", ATLASES, OUT_ASSET_DIR
    )
    report_rows += mni_report_rows

    subj_tpl_out, subj_report_rows, subj_atlases_json = build_space(
        "subject", SUBJECT_TEMPLATE_FILE, "ernie_t1.nii.gz", SUBJECT_ATLASES, OUT_ASSET_DIR
    )
    report_rows += subj_report_rows

    atlases_json = {
        "mni": {
            "template": {
                "filename": "mni152_t1_1mm.nii.gz",
                "label": "MNI152 T1 1mm",
                "note": (
                    "MNI152 T1-weighted 1mm template, requantised to 5-bit (32 grayscale "
                    "levels) for the browser; source resources/atlas/MNI152_T1_1mm.nii.gz."
                ),
            },
            "atlases": mni_atlases_json,
        },
        "subject": {
            "template": {
                "filename": "ernie_t1.nii.gz",
                "label": "ernie T1 (subject space)",
                "note": (
                    "T1-weighted anatomical image for the SimNIBS example subject ernie, "
                    "requantised to 5-bit (32 grayscale levels) for the browser; source "
                    "derivatives/SimNIBS/sub-ernie/m2m_ernie/T1.nii.gz."
                ),
            },
            "atlases": subj_atlases_json,
        },
    }

    json_bytes = json.dumps(atlases_json, separators=(",", ":")).encode("utf-8")
    OUT_JSON.write_bytes(json_bytes)
    report_rows.append((OUT_JSON, len(json_bytes)))

    print("Byte report")
    print("-" * 72)
    total = 0
    for path, size in report_rows:
        rel = path.relative_to(REPO_ROOT)
        print(f"  {str(rel):50s} {size:10,d} B  ({size / 1e6:6.3f} MB)")
        total += size
    print("-" * 72)
    print(f"  {'TOTAL':50s} {total:10,d} B  ({total / 1e6:6.3f} MB)")
    print()

    problems = verify_written_outputs("mni", mni_tpl_out, ATLASES, OUT_ASSET_DIR)
    problems += verify_written_outputs("subject", subj_tpl_out, SUBJECT_ATLASES, OUT_ASSET_DIR)

    if problems:
        print("FAILED: one or more written outputs did not match expectations.")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("OK: all label counts, shapes, and affines matched their expected values.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
