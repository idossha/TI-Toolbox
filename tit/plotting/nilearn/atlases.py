"""The nilearn atlases the Nilearn Visuals slice PDF outlines, and the step that bundles them.

``container/blueprint/Dockerfile.ti-toolbox`` runs this file as a script with
``NILEARN_DATA=/opt/nilearn_data``, so the image carries every atlas below and a job reads
them from disk with no network (nilearn's fetchers download only what is missing). The
script exits non-zero when a downloaded file's sha256 differs from the one recorded here, so
an upstream change fails the build instead of changing figures silently. Run it the same
way to pre-fetch the atlases outside the image.

Imports nothing from ``tit``: the build runs it before the package is installed, in a
layer that does not change with the rest of the source.
"""

from __future__ import annotations

import hashlib
import os
import sys

#: key -> (display name, nilearn fetcher, its arguments, the result field holding the label
#: image's path, sha256 of that file). Checksums: nilearn 0.14.1's download on 2026-10-21,
#: printed by ``python atlases.py``.
ATLASES = {
    "harvard_oxford": (
        "Harvard-Oxford cortical atlas",
        "fetch_atlas_harvard_oxford",
        {"atlas_name": "cort-maxprob-thr25-2mm"},
        "filename",
        "586d76a7defd278fcea4d83d301994d7e096aa8272d26e3c7539b4f8ebd588c1",
    ),
    "harvard_oxford_sub": (
        "Harvard-Oxford subcortical atlas",
        "fetch_atlas_harvard_oxford",
        {"atlas_name": "sub-maxprob-thr25-2mm"},
        "filename",
        "b7e0c54535885de6f3f04d17461a2959aa1df50bfbe9bd53b713925aabc6f330",
    ),
    "schaefer_2018": (
        "Schaefer 2018 atlas (100 parcels)",
        "fetch_atlas_schaefer_2018",
        {"n_rois": 100},
        "maps",
        "23d54226fc7fe5a1b20844a1c8f8d8e23b59888f6442d7590eb983dd8e682e9a",
    ),
}


def atlas_path(key: str) -> str:
    """Path to *key*'s label image, from nilearn's data directory (fetched if absent)."""
    # Imported here so the table above reads without nilearn (NilearnConfig checks its keys).
    from nilearn import datasets

    _, fetcher, kwargs, field, _ = ATLASES[key]
    return str(getattr(datasets, fetcher)(**kwargs)[field])


def _sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


if __name__ == "__main__":
    keep, mismatched = set(), []
    for key, (*_, expected) in ATLASES.items():
        path = os.path.realpath(atlas_path(key))
        keep.add(path)
        digest = _sha256(path)
        print(f"{key}: {path} sha256={digest}")
        if digest != expected:
            mismatched.append(key)
    if mismatched:
        sys.exit(f"atlas checksum mismatch: {', '.join(mismatched)}")
    if "--prune" in sys.argv[1:]:
        # Image build only: drop every other NIfTI the archives unpacked under NILEARN_DATA
        # (the Harvard-Oxford tarball alone brings ~28 MB of maps no figure reads). Label
        # files are not NIfTIs, so the fetchers still find everything they check for. Also
        # drop empty directories: a download that failed over to nilearn's backup URL leaves
        # its empty sandbox behind, and the next fetch tries to delete it -- a write, which
        # fails on a read-only cache.
        for root, _, files in os.walk(os.environ["NILEARN_DATA"], topdown=False):
            for name in files:
                path = os.path.realpath(os.path.join(root, name))
                if name.endswith((".nii", ".nii.gz")) and path not in keep:
                    os.remove(path)
            if not os.listdir(root):
                os.rmdir(root)
