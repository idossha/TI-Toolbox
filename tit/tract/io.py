"""Tractogram files: TRX/TCK through DIPY's ``StatefulTractogram`` (positions in RAS mm)."""

from __future__ import annotations

import os
import tempfile

import numpy as np


def _reference(ref):
    """A NIfTI image (or its path) as the tractogram's spatial reference."""
    import nibabel as nib

    return nib.load(ref) if isinstance(ref, (str, os.PathLike)) else ref


def save_tractogram(
    path: str,
    streamlines,
    ref,
    data_per_vertex: dict[str, np.ndarray] | None = None,
    data_per_streamline: dict[str, np.ndarray] | None = None,
) -> str:
    """Write *streamlines* (world RAS mm) to ``.trx``/``.tck``/``.trk`` at *path*.

    *data_per_vertex* arrays are (P,) over the concatenated points (stored float32);
    *data_per_streamline* arrays are (S,) (float32, or int32 for integer input). The file
    is written beside *path* and renamed into place, so a reader never sees half a file.
    """
    from dipy.io.stateful_tractogram import Space, StatefulTractogram
    from dipy.io.streamline import save_tractogram as dipy_save

    counts = np.cumsum([len(s) for s in streamlines])[:-1]
    dpp = {
        k: np.split(np.asarray(v, np.float32).reshape(-1, 1), counts)
        for k, v in (data_per_vertex or {}).items()
    }
    dps = {}
    for k, v in (data_per_streamline or {}).items():
        v = np.asarray(v)
        dtype = np.int32 if np.issubdtype(v.dtype, np.integer) else np.float32
        dps[k] = v.astype(dtype).reshape(-1, 1)
    sft = StatefulTractogram(
        [np.asarray(s, np.float32) for s in streamlines],
        _reference(ref),
        Space.RASMM,
        data_per_point=dpp,
        data_per_streamline=dps,
    )
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    suffix = os.path.splitext(path)[1]
    fd, tmp = tempfile.mkstemp(suffix=suffix, dir=folder)
    os.close(fd)
    try:
        dipy_save(sft, tmp, bbox_valid_check=False)
        os.chmod(tmp, 0o644)  # mkstemp creates 0600; the file is a shared output
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return path


def load_streamlines(path: str) -> list[np.ndarray]:
    """Streamlines of a ``.trx``/``.tck``/``.trk`` file, world RAS mm, float64."""
    if path.endswith(".trx"):
        from dipy.io.streamline import load_tractogram

        sft = load_tractogram(path, "same", bbox_valid_check=False)
        sft.to_rasmm()
        return [np.asarray(s, np.float64) for s in sft.streamlines]
    import nibabel as nib

    return [np.asarray(s, np.float64) for s in nib.streamlines.load(path).streamlines]


def save_nifti(data: np.ndarray, affine: np.ndarray, path: str) -> str:
    """Save a NIfTI; ``.nii.gz`` goes through a plain ``.nii`` and stdlib gzip (bind mounts)."""
    from pathlib import Path

    from tit.pre.qsi.dti_extractor import _save_nifti_gz

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    _save_nifti_gz(data, affine, Path(path))
    return path
