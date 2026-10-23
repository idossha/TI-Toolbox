"""The atlases the Nilearn Visuals slice PDF outlines: label volumes TI-Toolbox ships.

Each key names a file in ``resources/atlas/``, the MNI atlases the repository already
ships for ROI picking; ``resources/atlas/manifest.json`` (read through
:mod:`tit.atlas.manifest`) records its source, licence and region count. A job reads the
file from disk, so no atlas is downloaded at image build or at run time. The keys are what
:class:`~tit.plotting.nilearn.config.NilearnConfig` accepts; saved configs name them.
"""

from __future__ import annotations

#: key -> (display name, the label volume's manifest ``id`` in ``resources/atlas/``).
ATLASES = {
    "harvard_oxford": (
        "Harvard-Oxford cortical atlas",
        "HarvardOxford-cortl-maxprob-thr25-1mm.nii.gz",
    ),
    "harvard_oxford_sub": (
        "Harvard-Oxford subcortical atlas",
        "HarvardOxford-sub-maxprob-thr25-1mm.nii.gz",
    ),
    "schaefer_2018": (
        "Schaefer 2018 atlas (400 parcels)",
        "Schaefer2018_400Parcels_7Networks_order_FSLMNI152_1mm.nii.gz",
    ),
}


def atlas_path(key: str) -> str:
    """Path to *key*'s label volume in ``resources/atlas/``.

    Raises:
        FileNotFoundError: If the manifest lists no such file on disk.
    """
    # Imported here so the table above reads without touching the filesystem
    # (NilearnConfig checks its keys when the server imports it).
    from tit.atlas.constants import mni_resources_dir
    from tit.atlas.manifest import mni_atlas_entry

    file_id = ATLASES[key][1]
    entry = mni_atlas_entry(file_id)
    if entry is None:
        raise FileNotFoundError(f"{file_id} is not in {mni_resources_dir()}")
    return entry["path"]
