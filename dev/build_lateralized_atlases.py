#!/usr/bin/env python3
"""Write the two lateralized MNI atlases shipped in ``resources/atlas/``.

Why this exists (docs/dev/DECISIONS.md § 2026-09-23): the Harvard-Oxford
cortical maxprob map and the CIT168 labeling each gave a structure ONE label
value covering both hemispheres, so picking "Putamen" targeted both putamens.
Every shipped MNI atlas now names one side per label, except true midline
structures (vermis, brainstem, third/fourth ventricle, fornix) --
``tests/test_atlas_laterality.py`` enforces that.

1. Harvard-Oxford cortical, lateralized: FSL's own
   ``HarvardOxford-cortl-maxprob-thr25-1mm.nii.gz`` copied byte-identical out of
   the sha256-pinned NeuroDebian package, and a FreeSurfer-style LUT generated
   from its ``HarvardOxford-Cortical-Lateralized.xml`` (value = XML index + 1;
   odd = Left, even = Right, as FSL orders them).
2. CIT168, lateralized: the 16-label bilateral CIT168 map (sha256-pinned; it is
   in git history at 2dd933cb:resources/atlas/) split at world x = 0 of its own
   MNI152NLin2009cAsym grid. Label k becomes 2k-1 (Left, x < 0) and 2k
   (Right, x >= 0), the same odd/even convention as FSL's cortl.
   ponytail: the voxel plane at exactly x = 0 goes Right; a probabilistic
   re-split from the per-nucleus maps would be the upgrade if that plane matters.

LUT colours are TI-Toolbox's own: HLS golden-angle hue per label value,
lightness 0.64, saturation 0.86.

Usage (stdlib + numpy + nibabel; host is fine)::

    git show 2dd933cb:resources/atlas/CIT168_labeling_MNI152NLin2009cAsym.nii.gz > /tmp/cit.nii.gz
    git show 2dd933cb:resources/atlas/CIT168_labeling_MNI152NLin2009cAsym_LUT.txt > /tmp/cit_LUT.txt
    curl -LO http://neuro.debian.net/debian/pool/non-free/f/fsldata/fsl-harvard-oxford-cortical-lateralized-atlas_5.0.7-2_all.deb
    python dev/build_lateralized_atlases.py \\
        --fsl-deb fsl-harvard-oxford-cortical-lateralized-atlas_5.0.7-2_all.deb \\
        --cit168 /tmp/cit.nii.gz --cit168-lut /tmp/cit_LUT.txt

Output is byte-deterministic (gzip mtime 0); rerunning must leave ``git status`` clean.
"""

from __future__ import annotations

import argparse
import colorsys
import gzip
import hashlib
import io
import lzma
import re
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "resources" / "atlas"

FSL_DEB_URL = (
    "http://neuro.debian.net/debian/pool/non-free/f/fsldata/"
    "fsl-harvard-oxford-cortical-lateralized-atlas_5.0.7-2_all.deb"
)
FSL_DEB_SHA256 = "a7c63c121878b7cb1696eb38a90df64bff019d14b5b490701b477c62bd78be51"
FSL_MEMBER = "usr/share/data/harvard-oxford-atlases/HarvardOxford/HarvardOxford-cortl-maxprob-thr25-1mm.nii.gz"
FSL_XML = "usr/share/data/harvard-oxford-atlases/HarvardOxford-Cortical-Lateralized.xml"
HO_OUT = "HarvardOxford-cortl-maxprob-thr25-1mm.nii.gz"

CIT168_SHA256 = "48b6187e4a051aedb7f32d058fd3211df2e96fbe369c80793e6f7b293ff98a23"
CIT168_LUT_SHA256 = "bc983f3d9152608ea8fead0eb25f77837883c140d7795894aab972fda0cbaf6c"
CIT168_OUT = "CIT168_labeling_lateralized_MNI152NLin2009cAsym.nii.gz"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def colour(value: int) -> tuple[int, int, int]:
    r, g, b = colorsys.hls_to_rgb(((value - 1) * 0.61803398875) % 1, 0.64, 0.86)
    return round(r * 255), round(g * 255), round(b * 255)


def write_lut(path: Path, header: list[str], names: dict[int, str]) -> None:
    lines = [f"# {line}" for line in header]
    lines += ["# No. LabelName R G B A", "0 Background 0 0 0 0"]
    for value in sorted(names):
        r, g, b = colour(value)
        lines.append(f"{value} {names[value]} {r} {g} {b} 0")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def deb_members(deb: bytes) -> dict[str, bytes]:
    """The files of a .deb's data.tar.xz (a .deb is an ``ar`` archive)."""
    assert deb[:8] == b"!<arch>\n", "not an ar archive"
    pos = 8
    while pos < len(deb):
        name = deb[pos : pos + 16].decode().strip()
        size = int(deb[pos + 48 : pos + 58].decode().strip())
        body = deb[pos + 60 : pos + 60 + size]
        pos += 60 + size + (size % 2)
        if name.startswith("data.tar"):
            with tarfile.open(fileobj=io.BytesIO(lzma.decompress(body))) as tar:
                return {
                    m.name.lstrip("./"): tar.extractfile(m).read()
                    for m in tar.getmembers()
                    if m.isfile()
                }
    raise SystemExit("no data.tar in the .deb")


def build_harvard_oxford(deb_path: Path) -> None:
    deb = deb_path.read_bytes()
    if sha256(deb) != FSL_DEB_SHA256:
        raise SystemExit(f"{deb_path} sha256 is not {FSL_DEB_SHA256}")
    files = deb_members(deb)
    (OUT / HO_OUT).write_bytes(files[FSL_MEMBER])
    root = ET.fromstring(files[FSL_XML])
    names = {
        int(label.get("index")) + 1: re.sub(r"\s+", "-", label.text.strip())
        for label in root.iter("label")
    }
    write_lut(
        OUT / HO_OUT.replace(".nii.gz", "_LUT.txt"),
        [
            f"FreeSurfer-style colour lookup table for {HO_OUT}",
            "Source: FSL HarvardOxford-Cortical-Lateralized.xml (NeuroDebian fsldata 5.0.7-2); label value = XML index + 1, 0 = background.",
            "Names are FSL's, spaces replaced by hyphens. Colours are TI-Toolbox's own (dev/build_lateralized_atlases.py).",
        ],
        names,
    )


def build_cit168(source: Path, lut: Path) -> None:
    import nibabel as nib
    import numpy as np

    if sha256(source.read_bytes()) != CIT168_SHA256:
        raise SystemExit(f"{source} is not the pinned bilateral CIT168 map")
    if sha256(lut.read_bytes()) != CIT168_LUT_SHA256:
        raise SystemExit(f"{lut} is not the pinned CIT168 LUT")
    image = nib.load(str(source))
    data = np.asarray(image.dataobj)
    i = np.arange(data.shape[0])
    x = image.affine[0, 0] * i + image.affine[0, 3]  # the grid has no rotation
    assert np.allclose(image.affine[0, 1:3], 0), "CIT168 grid is not axis-aligned"
    left = (x < 0)[:, None, None]
    out = np.where(data > 0, np.where(left, 2 * data - 1, 2 * data), 0).astype(data.dtype)
    header = image.header.copy()
    split = nib.Nifti1Image(out, image.affine, header)
    raw = split.to_bytes()
    (OUT / CIT168_OUT).write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))

    names: dict[int, str] = {}
    for line in lut.read_text().splitlines():
        parts = line.split()
        if not parts or not parts[0].isdigit() or parts[0] == "0":
            continue
        k = int(parts[0])
        names[2 * k - 1] = f"Left-{parts[1]}"
        names[2 * k] = f"Right-{parts[1]}"
    write_lut(
        OUT / CIT168_OUT.replace(".nii.gz", "_LUT.txt"),
        [
            f"FreeSurfer color lookup table for {CIT168_OUT}",
            "Source: CIT168_labeling_MNI152NLin2009cAsym.nii.gz (NeuroVault collection 3145, Pauli et al. 2018, Scientific Data 5:180063),",
            "split at world x = 0 by dev/build_lateralized_atlases.py: label k -> 2k-1 Left (x < 0), 2k Right (x >= 0).",
            "Colours are TI-Toolbox's own.",
        ],
        names,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fsl-deb", type=Path, required=True)
    parser.add_argument("--cit168", type=Path, required=True)
    parser.add_argument("--cit168-lut", type=Path, required=True)
    args = parser.parse_args()
    build_harvard_oxford(args.fsl_deb)
    build_cit168(args.cit168, args.cit168_lut)
    for name in (HO_OUT, CIT168_OUT):
        print(name, sha256((OUT / name).read_bytes()))


if __name__ == "__main__":
    main()
