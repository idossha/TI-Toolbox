#!/usr/bin/env simnibs_python
"""Create a subject-space thalamic nuclei label atlas from FreeSurfer MNI data."""

from __future__ import annotations

import argparse
from pathlib import Path

import nibabel as nib
import numpy as np
from simnibs.utils import transformations


def _read_names(path: Path) -> list[tuple[int, str]]:
    labels: list[tuple[int, str]] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            label_id, name = line.split(",", 1)
            labels.append((int(label_id), name))
    return labels


def _write_discrete_mni_atlas(
    probs_path: Path, names_path: Path, output_path: Path
) -> list[tuple[int, str]]:
    labels = _read_names(names_path)
    img = nib.load(str(probs_path))
    data = np.asanyarray(img.dataobj)

    if data.ndim != 4:
        raise ValueError(f"Expected a 4D probability atlas, got shape {data.shape}")
    if data.shape[3] != len(labels):
        raise ValueError(
            f"Atlas has {data.shape[3]} probability maps but {len(labels)} labels"
        )

    label_ids = np.array([label_id for label_id, _ in labels], dtype=np.int16)
    winners = np.argmax(data, axis=3)
    max_prob = np.max(data, axis=3)
    discrete = label_ids[winners]
    discrete[max_prob <= 0] = 0

    out_img = nib.Nifti1Image(discrete.astype(np.int16), img.affine, img.header)
    out_img.header.set_data_dtype(np.int16)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(out_img, str(output_path))
    return labels


def _write_labels_file(labels: list[tuple[int, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        f.write("#No. Label_Name R G B A\n")
        for label_id, name in labels:
            f.write(f"{label_id} {name} 255 255 255 255\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", required=True, help="Subject ID without sub- prefix")
    parser.add_argument("--project", required=True, help="BIDS project root")
    parser.add_argument(
        "--atlas-dir",
        default="/ti-toolbox/resources/atlas/freesurfer_thalamus",
        help="Directory containing ThalamusProbs.MNIsymSpace files",
    )
    parser.add_argument(
        "--output-name",
        default="freesurfer_thalamic_nuclei_subject.nii.gz",
        help="Output atlas filename in m2m segmentation/",
    )
    args = parser.parse_args()

    subject = args.subject.removeprefix("sub-")
    project = Path(args.project)
    atlas_dir = Path(args.atlas_dir)
    m2m = project / "derivatives" / "SimNIBS" / f"sub-{subject}" / f"m2m_{subject}"
    seg = m2m / "segmentation"

    probs_path = atlas_dir / "ThalamusProbs.MNIsymSpace.nii.gz"
    names_path = atlas_dir / "ThalamusProbs.MNIsymSpace.names.txt"
    discrete_mni = atlas_dir / "ThalamusLabels.MNIsymSpace.nii.gz"
    subject_atlas = seg / args.output_name

    labels = _write_discrete_mni_atlas(probs_path, names_path, discrete_mni)

    transformations.warp_volume(
        str(discrete_mni),
        str(m2m),
        str(subject_atlas),
        transformation_direction="mni2subject",
        transformation_type="nonl",
        reference=str(m2m / "T1.nii.gz"),
        order=0,
    )

    stem = args.output_name
    if stem.endswith(".nii.gz"):
        stem = stem[: -len(".nii.gz")]
    else:
        stem = Path(stem).stem
    _write_labels_file(labels, seg / f"{stem}_labels.txt")

    print(subject_atlas)
    print(seg / f"{stem}_labels.txt")


if __name__ == "__main__":
    main()
