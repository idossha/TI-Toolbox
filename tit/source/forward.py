#!/usr/bin/env simnibs_python
"""Rebuild MNE-compatible EEG forward solutions from SimNIBS head models.

For a subject with an existing ``m2m_<id>`` head model, :func:`prepare_forward`
produces the three files an MNE source-reconstruction needs:

* ``sub-<id>_net-<net>-fwd.fif``   -- the forward solution (gain matrix)
* ``sub-<id>_net-<net>-src.fif``   -- the cortical source space
* ``sub-<id>_net-<net>-morph.h5``  -- a SourceMorph onto fsaverage

plus the point-electrode leadfield (``*_leadfield.hdf5``) and the head<->MRI
transform (``*-trans.fif``) they are derived from.  All outputs land under
``derivatives/SimNIBS/sub-<id>/forward/`` -- a namespace distinct from the
optimizer's ``leadfields/`` (which uses *modeled* electrodes for stimulation
dose; the EEG forward uses *point* electrodes per the SimNIBS EEG convention).

The expensive FEM leadfield is computed at most once per (subject, net): a
re-run reuses the cached HDF5 and only re-assembles the MNE files.

Runs under ``simnibs_python`` (imports both ``mne`` and ``simnibs``)::

    simnibs_python -m tit.source forward_config.json

See Also
--------
tit.source.config.ForwardConfig : Parameter object.
tit.source.fsaverage.project_fields_to_fsaverage : The companion field-mapping
    pipeline that puts simulation fields on the same fsaverage grid.
"""

from __future__ import annotations

import csv
import itertools
import logging
import multiprocessing as mp
import subprocess
from pathlib import Path

import mne
import numpy as np

from tit.paths import get_path_manager
from tit.source.config import ForwardConfig

logger = logging.getLogger(__name__)

# Leading bytes of a macOS AppleDouble (``._*``) placeholder left on some network
# / external volumes; such stand-ins masquerade as the real file and must be
# treated as missing.
_APPLEDOUBLE_MAGIC = b"\x00\x05\x16\x07"


def _is_numeric(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


def _read_simnibs_montage(
    m2m_dir: Path,
    montage_name: str,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Read electrode + fiducial positions (metres) from a SimNIBS net CSV."""
    eeg_csv = m2m_dir / "eeg_positions" / f"{montage_name}.csv"
    if not eeg_csv.exists():
        raise FileNotFoundError(f"EEG net not found: {eeg_csv}")

    electrodes: dict[str, np.ndarray] = {}
    fiducials: dict[str, np.ndarray] = {}
    with open(eeg_csv) as handle:
        reader = csv.reader(handle)
        first_row = next(reader)
        is_header = not _is_numeric(first_row[1])
        rows = reader if is_header else itertools.chain([first_row], reader)
        for row in rows:
            pos = np.array([float(row[1]), float(row[2]), float(row[3])]) / 1000.0
            if row[0].startswith("Electrode") or row[0].startswith("Reference"):
                electrodes[row[4]] = pos
            elif row[0] == "Fiducial":
                fiducials[row[4]] = pos

    required_fids = {"LPA", "Nz", "RPA"}
    missing_fids = required_fids - set(fiducials)
    if missing_fids:
        raise ValueError(f"{eeg_csv} missing fiducials: {sorted(missing_fids)}")
    if not electrodes:
        raise ValueError(f"{eeg_csv} contains no electrodes")
    return electrodes, fiducials


def _build_montage_info(
    electrodes: dict[str, np.ndarray],
    fiducials: dict[str, np.ndarray],
) -> tuple[mne.Info, mne.transforms.Transform]:
    """Build an MNE ``Info`` + head<->MRI ``trans`` from net positions.

    The net CSV positions already live in the subject's MRI/subject space, so we
    define the MNE *head* frame directly from the same fiducials.  The resulting
    head<->MRI transform is therefore (near-)identity: the forward is built with
    electrodes at their true subject-space locations, with no dependency on an
    actual EEG recording.
    """
    # An Info whose montage carries the net's own fiducials, used only to derive
    # the head frame that coregister_fiducials aligns to the MRI fiducials.
    seed_montage = mne.channels.make_dig_montage(
        ch_pos=dict(electrodes),
        nasion=fiducials["Nz"],
        lpa=fiducials["LPA"],
        rpa=fiducials["RPA"],
        coord_frame="head",
    )
    seed_info = mne.create_info(list(electrodes), sfreq=1000.0, ch_types="eeg")
    seed_info.set_montage(seed_montage)

    fid_list = [
        {"ident": 1, "kind": 1, "r": fiducials["LPA"], "coord_frame": 5},
        {"ident": 2, "kind": 1, "r": fiducials["Nz"], "coord_frame": 5},
        {"ident": 3, "kind": 1, "r": fiducials["RPA"], "coord_frame": 5},
    ]
    trans = mne.coreg.coregister_fiducials(seed_info, fid_list, tol=1e-1)
    mri_to_head = mne.transforms.invert_transform(trans)

    ch_names = list(electrodes)
    head_pos = mne.transforms.apply_trans(
        mri_to_head, np.array(list(electrodes.values()))
    )
    fid_head = {
        name: mne.transforms.apply_trans(mri_to_head, pos)
        for name, pos in fiducials.items()
    }
    montage = mne.channels.make_dig_montage(
        ch_pos={name: pos for name, pos in zip(ch_names, head_pos)},
        nasion=fid_head["Nz"],
        lpa=fid_head["LPA"],
        rpa=fid_head["RPA"],
        coord_frame="head",
    )

    info = mne.create_info(ch_names=ch_names, sfreq=256.0, ch_types="eeg")
    info.set_montage(montage)
    info["dev_head_t"] = mne.transforms.Transform("meg", "head", np.eye(4))
    return info, trans


def _run(cmd: list[str], description: str, cwd: Path | None = None) -> None:
    logger.info("Running %s", description)
    logger.info("Command: %s", " ".join(cmd))
    result = subprocess.run(cmd, check=False, cwd=None if cwd is None else str(cwd))
    if result.returncode != 0:
        raise RuntimeError(f"{description} failed with exit code {result.returncode}")


def _is_appledouble_placeholder(path: Path) -> bool:
    if not path.exists() or path.stat().st_size > 4096:
        return False
    try:
        with path.open("rb") as handle:
            return handle.read(4) == _APPLEDOUBLE_MAGIC
    except OSError:
        return False


def _exists_real(path: Path) -> bool:
    return path.exists() and not _is_appledouble_placeholder(path)


def _forward_outputs_valid(fwd_path: Path, src_path: Path, morph_path: Path) -> bool:
    if not all(_exists_real(p) for p in (fwd_path, src_path, morph_path)):
        return False
    try:
        mne.read_forward_solution(str(fwd_path), verbose=False)
        mne.read_source_spaces(str(src_path), verbose=False)
        mne.read_source_morph(str(morph_path))
    except Exception as exc:  # noqa: BLE001 - any read failure means rebuild
        logger.warning("Existing forward outputs are not readable: %s", exc)
        return False
    return True


def _find_existing_leadfield(forward_dir: Path) -> Path | None:
    """Return a reusable point-electrode leadfield HDF5, if one is present."""
    candidates = [p for p in forward_dir.glob("*.hdf5") if _exists_real(p)]
    return candidates[0] if candidates else None


def _compute_leadfield(
    m2m_dir: Path, forward_dir: Path, eeg_csv: Path, cpus: int
) -> Path:
    """Compute the point-electrode EEG leadfield in-process via SimNIBS."""
    from simnibs.eeg.forward import compute_tdcs_leadfield

    logger.info("Computing point-electrode leadfield (cpus=%d)", cpus)
    compute_tdcs_leadfield(
        m2m_dir=str(m2m_dir),
        fem_dir=str(forward_dir),
        fname_montage=str(eeg_csv),
        subsampling=None,
        point_electrodes=True,
        run_kwargs={"save_mat": False, "cpus": cpus},
    )
    leadfield = _find_existing_leadfield(forward_dir)
    if leadfield is None:
        raise FileNotFoundError(f"No HDF5 leadfield generated in {forward_dir}")
    return leadfield


def _rename_generated_outputs(forward_dir: Path, stem: str) -> tuple[Path, Path, Path]:
    """Rename ``prepare_eeg_forward`` outputs to canonical MNE-suffixed names."""
    expected_fwd = forward_dir / f"{stem}-fwd.fif"
    expected_src = forward_dir / f"{stem}-src.fif"
    expected_morph = forward_dir / f"{stem}-morph.h5"

    for pattern, target in (
        ("*-fwd.fif", expected_fwd),
        ("*-src.fif", expected_src),
        ("*-morph.h5", expected_morph),
    ):
        for candidate in forward_dir.glob(pattern):
            if candidate != target:
                candidate.replace(target)

    missing = [
        p for p in (expected_fwd, expected_src, expected_morph) if not _exists_real(p)
    ]
    if missing:
        raise FileNotFoundError(
            "Missing generated forward outputs: " + ", ".join(str(p) for p in missing)
        )
    return expected_fwd, expected_src, expected_morph


def prepare_forward(
    subject_id: str,
    cfg: ForwardConfig,
    *,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path, Path]:
    """Rebuild one subject's forward, source-space, and fsaverage morph files.

    Parameters
    ----------
    subject_id : str
        Subject identifier without the ``sub-`` prefix (e.g. ``"101"``).
    cfg : ForwardConfig
        EEG net, fsaverage spacing, FEM worker count, and overwrite flag.
    output_dir : str or pathlib.Path or None
        Destination directory.  Defaults to ``pm.forward(subject_id)``
        (``derivatives/SimNIBS/sub-<id>/forward/``).

    Returns
    -------
    tuple of pathlib.Path
        ``(fwd_path, src_path, morph_path)``.
    """
    pm = get_path_manager()
    m2m_dir = Path(pm.m2m(subject_id))
    if not m2m_dir.is_dir():
        raise FileNotFoundError(f"m2m directory not found: {m2m_dir}")

    forward_dir = (
        Path(output_dir) if output_dir is not None else Path(pm.forward(subject_id))
    )
    forward_dir.mkdir(parents=True, exist_ok=True)

    stem = f"sub-{subject_id}_net-{cfg.eeg_net}"
    expected = (
        forward_dir / f"{stem}-fwd.fif",
        forward_dir / f"{stem}-src.fif",
        forward_dir / f"{stem}-morph.h5",
    )
    if not cfg.overwrite and _forward_outputs_valid(*expected):
        logger.info("Forward outputs already present for %s; skipping.", subject_id)
        return expected

    electrodes, fiducials = _read_simnibs_montage(m2m_dir, cfg.eeg_net)
    montage_info, trans = _build_montage_info(electrodes, fiducials)

    info_path = forward_dir / f"{stem}-info.fif"
    trans_path = forward_dir / f"{stem}-trans.fif"
    mne.io.RawArray(
        np.zeros((len(montage_info.ch_names), 1)), montage_info, verbose=False
    ).save(str(info_path), overwrite=True, verbose=False)
    mne.write_trans(str(trans_path), trans, overwrite=True)

    # Redundancy guard: reuse the FEM leadfield if one is already cached.
    leadfield_hdf5 = None if cfg.overwrite else _find_existing_leadfield(forward_dir)
    if leadfield_hdf5 is not None:
        logger.info("Reusing cached leadfield: %s", leadfield_hdf5.name)
    else:
        eeg_csv = m2m_dir / "eeg_positions" / f"{cfg.eeg_net}.csv"
        leadfield_hdf5 = _compute_leadfield(m2m_dir, forward_dir, eeg_csv, cfg.cpus)

    _run(
        [
            "prepare_eeg_forward",
            "mne",
            str(m2m_dir),
            str(leadfield_hdf5),
            str(info_path),
            str(trans_path),
            "--fsaverage",
            str(cfg.fsaverage_spacing),
        ],
        f"prepare_eeg_forward for sub-{subject_id}",
        cwd=forward_dir,
    )
    return _rename_generated_outputs(forward_dir, stem)


def _ensure_fork_start_method() -> None:
    """Use ``fork`` for SimNIBS's leadfield worker pool (no-op on Linux)."""
    try:
        mp.set_start_method("fork", force=True)
    except (RuntimeError, ValueError):  # pragma: no cover - platform dependent
        pass
