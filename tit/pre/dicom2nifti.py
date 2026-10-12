#!/usr/bin/env python
"""Source-image ingestion with BIDS-compliant naming.

Converts each modality found under ``sourcedata/sub-{id}/`` into a
BIDS-named NIfTI (``sub-{id}_{suffix}.nii.gz``). DICOM series are
converted with ``dcm2niix``; a modality folder that already holds a
NIfTI is copied into place instead.

Public API
----------
run_dicom_to_nifti
    Ingest every supported modality for a subject.
MODALITIES
    Supported modalities and their BIDS datatype directories.
bids_outputs
    The files a conversion of one modality wrote.
pe_direction_label
    The BIDS ``dir-`` label of a phase-encoding direction in a NIfTI.

See Also
--------
tit.pre.structural.run_pipeline : Full preprocessing pipeline.
"""

import gzip
import json
import os
import shutil
import struct
import subprocess
import tarfile
import zipfile
from pathlib import Path
from typing import Iterator

from tit.paths import get_path_manager
from .utils import CommandRunner, PreprocessError

_ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz")
_DICOM_SUFFIXES = (".dcm", ".dicom")
_NIFTI_SUFFIXES = (".nii.gz", ".nii")
_SIDECAR_SUFFIXES = (".json", ".bval", ".bvec")
_SERIES_SUFFIXES = _NIFTI_SUFFIXES + _SIDECAR_SUFFIXES
_EXTRACTED_ARCHIVES_DIR = "extracted_archives"

# Source folder name (also the BIDS suffix) -> BIDS datatype directory.
#
# Single source of truth: tit.pre.preflight derives its rerun/cleanup list
# from this table, so a modality only has to be added here.
#
# ``ct`` is a deliberate local extension. BIDS has no CT datatype and no CT
# suffix -- BEP024 has been an unmerged draft since 2018 -- so no CT layout
# validates today. We write anat/sub-{id}_ct.nii.gz because that matches both
# BEP024's proposed suffix (making a future migration a directory move with no
# rename) and the majority of published OpenNeuro datasets carrying a head CT.
# tit.pre.utils.ensure_bidsignore keeps the validator quiet about it.
MODALITIES: tuple[tuple[str, str], ...] = (
    ("T1w", "anat"),
    ("T2w", "anat"),
    ("ct", "anat"),
    ("dwi", "dwi"),
    ("fmap", "fmap"),
)

# BIDS suffix where it is not the source folder's name. ``fmap`` holds the DWI's
# reverse phase-encoding (e.g. PA) series: a BIDS "pepolar" fieldmap, written as
# fmap/sub-{id}_dir-{label}_epi -- the layout QSIPrep documents for it. BIDS makes
# ``dir-`` REQUIRED for ``_epi`` files, so the label is derived from the data
# (pe_direction_label) and the series is converted under ``sub-{id}_epi`` first.
_BIDS_SUFFIX = {"fmap": "epi"}

# RAS+ world axis -> ``dir-`` label for phase encoding travelling toward its
# negative / positive end (BIDS: "dir-PA ... in RAS+ orientation SHOULD have
# PhaseEncodingDirection j").
_DIR_LABELS = (("RL", "LR"), ("AP", "PA"), ("SI", "IS"))


def _bids_name(subject_id: str, modality: str) -> str:
    """The stem *modality* is converted under, e.g. ``sub-01_T1w``."""
    return f"sub-{subject_id}_{_BIDS_SUFFIX.get(modality, modality)}"


def bids_outputs(output_dir: Path, subject_id: str, modality: str) -> list[Path]:
    """Files a conversion of *modality* wrote into *output_dir*.

    ``sub-{id}_{suffix}`` and ``sub-{id}_dir-{label}_{suffix}`` with their
    sidecars, NIfTIs first.
    """
    suffix = _BIDS_SUFFIX.get(modality, modality)
    stems = (f"sub-{subject_id}_{suffix}", f"sub-{subject_id}_dir-*_{suffix}")
    return [
        path
        for extension in _SERIES_SUFFIXES
        for stem in stems
        for path in sorted(Path(output_dir).glob(f"{stem}{extension}"))
    ]


def _sform_column(nifti: Path, axis: int) -> tuple[float, float, float] | None:
    """World (RAS+) vector of voxel *axis* from a NIfTI-1 sform, or ``None``.

    Read from the raw header: nibabel is not needed for three rows of floats.
    """
    # ponytail: sform only (dcm2niix always writes one); a qform-only or NIfTI-2
    # file gets no label and the user is told to name it. Add the qform when one turns up.
    try:
        opener = gzip.open if nifti.name.lower().endswith(".gz") else open
        with opener(nifti, "rb") as handle:  # type: ignore[operator]
            header = handle.read(348)
    except (OSError, EOFError, gzip.BadGzipFile):
        return None
    if len(header) < 348:
        return None
    for endian in "<>":
        if struct.unpack(endian + "i", header[:4])[0] == 348:
            break
    else:
        return None
    if struct.unpack(endian + "h", header[254:256])[0] <= 0:  # sform_code
        return None
    rows = [
        struct.unpack(endian + "4f", header[at : at + 16]) for at in (280, 296, 312)
    ]
    return rows[0][axis], rows[1][axis], rows[2][axis]


def pe_direction_label(nifti: Path, phase_encoding_direction) -> str | None:
    """BIDS ``dir-`` label (AP, PA, LR, RL, SI, IS) for a phase-encoding direction.

    ``PhaseEncodingDirection`` names a voxel axis of *nifti* and travels from index
    0 to the last index unless it ends in ``-``. The label is the world direction
    of that travel, taken from the NIfTI's sform and rounded to the closest
    cardinal axis, as BIDS asks of ``AP``/``PA``-style labels. ``None`` when the
    direction or the sform is missing -- a label is never guessed.
    """
    if phase_encoding_direction not in ("i", "i-", "j", "j-", "k", "k-"):
        return None
    column = _sform_column(nifti, "ijk".index(phase_encoding_direction[0]))
    if column is None or not any(column):
        return None
    sign = -1.0 if phase_encoding_direction.endswith("-") else 1.0
    world = [sign * value for value in column]
    dominant = max(range(3), key=lambda index: abs(world[index]))
    return _DIR_LABELS[dominant][world[dominant] > 0]


def _series_label(output_dir: Path, stem: str) -> str | None:
    """``dir-`` label of the converted series *stem*, from its sidecar and sform."""
    try:
        meta = json.loads((output_dir / f"{stem}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict):
        return None
    for suffix in _NIFTI_SUFFIXES:
        nifti = output_dir / f"{stem}{suffix}"
        if nifti.exists():
            return pe_direction_label(nifti, meta.get("PhaseEncodingDirection"))
    return None


def _rename_series(output_dir: Path, old_stem: str, new_stem: str) -> None:
    for suffix in _SERIES_SUFFIXES:
        source = output_dir / f"{old_stem}{suffix}"
        if source.exists():
            source.rename(output_dir / f"{new_stem}{suffix}")


def _has_suffix(name: str, suffixes: tuple[str, ...]) -> bool:
    """Return ``True`` when *name* ends with any of *suffixes* (case-insensitive)."""
    lowered = name.lower()
    return any(lowered.endswith(suffix) for suffix in suffixes)


def _iter_files(directory: Path) -> Iterator[Path]:
    """Yield regular files under *directory*, skipping dotfiles and unreadable entries.

    Dotfiles are filtered by name *before* any ``stat`` call, which is what
    makes this safe rather than merely tidy. macOS seeds bind mounts with
    AppleDouble ``._*`` siblings whose ``stat`` raises ``EPERM`` inside Docker,
    and Python 3.11's ``Path.is_file`` only swallows ENOENT/ENOTDIR/EBADF/ELOOP
    -- ``EPERM`` propagates and aborts the whole scan. ``dcm2niix`` skips
    dotfiles by the same rule, and BIDS reserves them for system use.

    The ``OSError`` guards cover the rest: filesystems that report
    ``DT_UNKNOWN`` make ``os.scandir`` fall back to a real ``stat`` syscall,
    so an unreadable non-dot entry must not abort the scan either.

    Symlinked directories are followed -- researchers routinely point
    sourcedata at a shared DICOM store -- but each real directory is visited
    only once, so a cycle cannot yield the same file repeatedly.
    """
    seen: set[Path] = set()
    stack = [directory]
    while stack:
        current = stack.pop()
        try:
            resolved = current.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir():
                    stack.append(Path(entry.path))
                elif entry.is_file():
                    yield Path(entry.path)
            except OSError:
                continue


def _find_files(directory: Path, suffixes: tuple[str, ...]) -> list[Path]:
    """Return sorted files under *directory* whose name ends with one of *suffixes*."""
    return sorted(
        path for path in _iter_files(directory) if _has_suffix(path.name, suffixes)
    )


def _safe_target(base_dir: Path, member_name: str) -> Path:
    """Resolve an archive member target and reject path traversal."""
    target = (base_dir / member_name).resolve()
    base = base_dir.resolve()
    if target != base and base not in target.parents:
        raise PreprocessError(f"Unsafe archive member path: {member_name}")
    return target


def _extract_zip(archive: Path, destination: Path) -> int:
    """Safely extract *archive* zip members into *destination*."""
    count = 0
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            target = _safe_target(destination, member.filename)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            count += 1
    return count


def _extract_tar(archive: Path, destination: Path) -> int:
    """Safely extract *archive* tar members into *destination*."""
    count = 0
    with tarfile.open(archive, "r:*") as tf:
        for member in tf.getmembers():
            target = _safe_target(destination, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                continue
            with src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            count += 1
    return count


def _extract_archive(archive: Path, destination: Path) -> int:
    """Safely extract a supported archive into *destination*."""
    destination.mkdir(parents=True, exist_ok=True)
    if archive.name.lower().endswith(".zip"):
        return _extract_zip(archive, destination)
    return _extract_tar(archive, destination)


def _extract_archives(modality_dir: Path, logger) -> None:
    """Extract every archive under *modality_dir* beside itself.

    Each archive extracts to ``<its own folder>/extracted_archives/<name>``
    rather than to one shared folder, so two archives that happen to share a
    basename (``series1/data.zip`` and ``series2/data.zip``) cannot collide.
    """
    for archive in _find_files(modality_dir, _ARCHIVE_SUFFIXES):
        # Never re-extract our own output, or extraction would recurse. The
        # check is relative to modality_dir: an absolute path could otherwise
        # contain an unrelated ancestor of that name.
        try:
            relative_parts = archive.relative_to(modality_dir).parts
        except ValueError:
            continue
        if _EXTRACTED_ARCHIVES_DIR in relative_parts:
            continue
        destination = archive.parent / _EXTRACTED_ARCHIVES_DIR / archive.name
        if destination.exists() and any(_iter_files(destination)):
            logger.info(f"Using previously extracted {archive.name} at {destination}")
            continue
        try:
            extracted = _extract_archive(archive, destination)
        except (tarfile.TarError, zipfile.BadZipFile, OSError, PreprocessError) as exc:
            logger.warning(f"Could not extract {archive}: {exc}")
            continue
        logger.info(
            f"Extracted {extracted} file(s) from {archive.name} to {destination}"
        )


def _modality_source_dir(sourcedata_dir: Path, modality: str) -> Path:
    """Return the source folder for *modality*, matching its name case-insensitively.

    Users name the folder ``CT`` as readily as ``ct``, and ``DWI`` as ``dwi``.
    A folder holding something wins over an empty one: on a case-sensitive
    filesystem the empty ``ct/`` that :func:`tit.pre.utils.ensure_subject_dirs`
    scaffolds would otherwise shadow the user's populated ``CT/``.
    """
    candidates: list[Path] = []
    try:
        entries = sorted(os.scandir(sourcedata_dir), key=lambda entry: entry.name)
    except OSError:
        return sourcedata_dir / modality
    for entry in entries:
        if entry.name.startswith(".") or entry.name.lower() != modality.lower():
            continue
        try:
            if entry.is_dir():
                candidates.append(Path(entry.path))
        except OSError:
            continue
    for candidate in candidates:
        if any(_iter_files(candidate)):
            return candidate
    return candidates[0] if candidates else sourcedata_dir / modality


def _nifti_stem(path: Path) -> str:
    """Return *path*'s name without its NIfTI extension (``.nii`` or ``.nii.gz``)."""
    for suffix in _NIFTI_SUFFIXES:
        if path.name.lower().endswith(suffix):
            return path.name[: -len(suffix)]
    return path.stem


def _collision_stems(output_dir: Path, base: str) -> list[str]:
    """*base* and dcm2niix's names for further series under it (``basea``, ...)."""
    return sorted(
        {
            _nifti_stem(path)
            for path in output_dir.glob(f"{base}*.nii*")
            if _nifti_stem(path)[len(base) :].isalpha() or _nifti_stem(path) == base
        }
    )


def _copy_sidecars(
    source: Path, output_dir: Path, bids_name: str, modality: str, logger
) -> None:
    """Copy the sidecars sitting beside *source* under the BIDS name.

    ``.bval``/``.bvec`` only travel with a diffusion series or a DWI fieldmap --
    they are what make a copied DWI usable, since QSIPrep rejects one without
    them, and BIDS lets an ``_epi`` fieldmap for a DWI carry them -- but they
    are not valid BIDS beside an anatomical image.
    """
    suffixes = _SIDECAR_SUFFIXES if modality in ("dwi", "fmap") else (".json",)
    stem = _nifti_stem(source)
    for suffix in suffixes:
        sidecar = source.with_name(f"{stem}{suffix}")
        if not sidecar.exists():
            if modality == "dwi":
                # Silence here would surface an hour into QSIPrep as an opaque
                # DSI Studio error. The sidecar has to share the NIfTI's stem:
                # an FSL-style `bvals`/`bvecs` pair beside `dwi.nii.gz` is not
                # matched, and neither is a differently named series.
                logger.warning(
                    f"No {stem}{suffix} beside {source.name}, so no "
                    f"{bids_name}{suffix} was written. QSIPrep cannot preprocess "
                    "a DWI without its gradient table, and the table must carry "
                    "the same basename as the NIfTI."
                )
            continue
        shutil.copyfile(sidecar, output_dir / f"{bids_name}{suffix}")
        logger.info(f"Copied {sidecar.name} -> {bids_name}{suffix}")


def _copy_nifti(
    source: Path, output_dir: Path, bids_name: str, modality: str, logger
) -> bool:
    """Copy an existing NIfTI *source* into *output_dir* under its BIDS name."""
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{bids_name}.nii.gz"
    if source.name.lower().endswith(".gz"):
        shutil.copyfile(source, target)
    else:
        # Compress with stdlib gzip: nibabel's gzip save is unreliable on
        # Docker bind mounts, and this avoids loading the volume into memory.
        with source.open("rb") as src, gzip.open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
    logger.info(f"Copied {source.name} -> {target.name}")
    _copy_sidecars(source, output_dir, bids_name, modality, logger)
    return True


def _reject_existing_output(output_dir: Path, subject_id: str, modality: str) -> None:
    """Raise if *modality* has already been ingested.

    Both extensions are checked: we always write ``.nii.gz``, but a
    hand-placed ``.nii`` counts too, and leaving it would make the subject
    carry the same BIDS entity twice. ``dir-`` variants count as well.
    """
    for path in bids_outputs(output_dir, subject_id, modality):
        if _has_suffix(path.name, _NIFTI_SUFFIXES):
            raise PreprocessError(
                f"Output already exists for {path.name}. "
                "Remove the files manually before rerunning."
            )


def _check_dcm2niix_outputs(
    output_dir: Path, bids_name: str, modality: str, logger
) -> bool:
    """Confirm dcm2niix produced the expected NIfTI and flag extra series."""
    produced = sorted(path.name for path in output_dir.glob(f"{bids_name}*"))
    expected = f"{bids_name}.nii.gz"
    if expected not in produced:
        logger.warning(
            f"dcm2niix produced no {expected} "
            f"(found: {', '.join(produced) if produced else 'nothing'})"
        )
        return False
    # dcm2niix writes extra files under names we did not ask for: a bare
    # letter per colliding series (sub-01_T1wa.nii.gz), and a suffix per
    # derived volume (_Tilt_1 for gantry tilt, _Eq_1 for resliced). None are
    # BIDS names, so every downstream step ignores them.
    extra = [name for name in produced if not name.startswith(f"{bids_name}.")]
    if modality == "dwi":
        # Further diffusion series (they have a gradient table) are named or
        # reported by _name_dwi_series.
        extra = [
            name
            for name in extra
            if not any(
                (output_dir / f"{name[: -len(suffix)]}.bval").exists()
                for suffix in _SERIES_SUFFIXES
                if name.endswith(suffix)
            )
        ]
    if modality == "fmap":
        # Further fieldmap series are named or reported by _name_fieldmap.
        collisions = set(_collision_stems(output_dir, bids_name))
        extra = [name for name in extra if name.split(".", 1)[0] not in collisions]
    if extra:
        logger.warning(
            f"dcm2niix wrote files beyond {expected}: {', '.join(extra)}. These "
            f"are extra series, or derived volumes such as _Tilt_1 (gantry tilt) "
            f"and _Eq_1 (resliced). Only {expected} is used downstream — if one "
            f"of the others is the volume you want, rename it by hand."
        )

    # A gradient table is written only for a series dcm2niix recognises as
    # diffusion-weighted. Its absence means the series that won the plain BIDS
    # name is not the diffusion acquisition -- typically a derived ADC or
    # TRACEW map, with the real series pushed onto one of the `extra` names
    # above. Left alone this surfaces an hour into QSIPrep as a DSI Studio
    # "cannot find bval/bvec file".
    if modality == "dwi":
        missing = [
            suffix
            for suffix in (".bval", ".bvec")
            if f"{bids_name}{suffix}" not in produced
        ]
        if missing:
            logger.warning(
                f"dcm2niix wrote {expected} but no {', '.join(missing)}. The "
                f"series that became {expected} is not diffusion-weighted "
                f"(derived ADC/TRACEW/FA maps carry no gradient table). QSIPrep "
                f"will reject this subject — check the other converted series "
                f"and rename the diffusion one to {bids_name}."
            )

    logger.info(f"Created {expected}")
    return True


def _run_dcm2niix(
    input_dir: Path,
    output_dir: Path,
    bids_name: str,
    modality: str,
    logger,
    runner: CommandRunner | None,
) -> bool:
    """Convert the DICOMs under *input_dir* into ``{bids_name}.nii.gz``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Converting DICOMs from {input_dir}")
    cmd = [
        "dcm2niix",
        "-z",
        "y",
        "-b",
        "y",
        # Search depth: dcm2niix defaults to 5, which a deep archive layout can
        # exceed. 9 is its maximum. It skips dotfiles on its own.
        "-d",
        "9",
        "-f",
        bids_name,
        "-o",
        str(output_dir),
        str(input_dir),
    ]

    if runner:
        exit_code = runner.run(cmd, logger=logger)
    else:
        result = subprocess.run(cmd, capture_output=True, text=True)
        exit_code = result.returncode

    if exit_code != 0:
        logger.warning(f"dcm2niix failed for {bids_name} (exit code {exit_code})")
        return False

    return _check_dcm2niix_outputs(output_dir, bids_name, modality, logger)


def _ingest_modality(
    modality_dir: Path,
    output_dir: Path,
    subject_id: str,
    modality: str,
    logger,
    runner: CommandRunner | None,
) -> bool:
    """Ingest one modality folder into its BIDS destination.

    DICOMs win when both are present: they carry the metadata dcm2niix needs
    to write a full sidecar, so a stray NIfTI never shadows the real series.
    """
    name = _bids_name(subject_id, modality)

    _extract_archives(modality_dir, logger)

    dicom_files = _find_files(modality_dir, _DICOM_SUFFIXES)
    nifti_files = _find_files(modality_dir, _NIFTI_SUFFIXES)
    if dicom_files:
        logger.info(f"Found {len(dicom_files)} DICOM file(s) under {modality_dir}")
        _reject_existing_output(output_dir, subject_id, modality)
        converted = _run_dcm2niix(
            modality_dir, output_dir, name, modality, logger, runner
        )
    elif nifti_files:
        _reject_existing_output(output_dir, subject_id, modality)
        if len(nifti_files) > 1:
            logger.warning(
                f"Found {len(nifti_files)} NIfTI files under {modality_dir}; "
                f"using {nifti_files[0].name} and ignoring the rest."
            )
        converted = _copy_nifti(nifti_files[0], output_dir, name, modality, logger)
    else:
        logger.info(
            f"No DICOM (.dcm/.dicom) or NIfTI (.nii/.nii.gz) files found under "
            f"{modality_dir}; skipping {modality}"
        )
        return False

    if converted and modality == "fmap":
        return _name_fieldmap(output_dir, subject_id, logger)
    if converted and modality == "dwi":
        _name_dwi_series(output_dir, subject_id, logger)
    return converted


def _name_fieldmap(output_dir: Path, subject_id: str, logger) -> bool:
    """Give the converted fieldmap series their BIDS names and point them at the DWI.

    BIDS: ``fmap/sub-{id}_dir-{label}_epi`` with ``dir-`` REQUIRED and
    ``PhaseEncodingDirection`` and ``TotalReadoutTime`` in the sidecar (the
    latter is checked, and derived from the sidecar when it can be, before
    QSIPrep runs). ``IntendedFor`` lists the subject's DWI series as paths
    relative to the subject folder: QSIPrep 26.0.0 reads neither BIDS URIs nor
    ``B0FieldIdentifier``. An existing ``IntendedFor`` is kept. A series holding
    both polarities (GE ``epi_pepolar``) comes out of dcm2niix as ``sub-{id}_epi``
    plus the collision name ``sub-{id}_epia``; each half is named by its direction.
    """
    stems = _collision_stems(output_dir, _bids_name(subject_id, "fmap"))
    labels = [_series_label(output_dir, stem) for stem in stems]
    if None in labels or len(set(labels)) != len(labels):
        logger.warning(
            f"Could not name {', '.join(f'{stem}.nii.gz' for stem in stems)}: BIDS "
            "requires a distinct dir-<label> entity for each reverse phase-encoding "
            "fieldmap, and it is taken from the sidecar's PhaseEncodingDirection and "
            "the image's sform; one is missing, or two series share a direction. "
            f"Rename the files to sub-{subject_id}_dir-<label>_epi (e.g. dir-PA) and "
            "add PhaseEncodingDirection to the JSON by hand."
        )
        return False

    dwi_names = sorted(
        path.name
        for path in (output_dir.parent / "dwi").glob("*_dwi.nii*")
        if not path.name.startswith(".")
    )
    for stem, label in zip(stems, labels):
        new_stem = f"sub-{subject_id}_dir-{label}_epi"
        _rename_series(output_dir, stem, new_stem)
        logger.info(f"Named the reverse phase-encoding fieldmap {new_stem}")
        sidecar = output_dir / f"{new_stem}.json"
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        if dwi_names and "IntendedFor" not in meta:
            meta["IntendedFor"] = [f"dwi/{name}" for name in dwi_names]
            sidecar.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
            logger.info(f"Added IntendedFor={meta['IntendedFor']} to {sidecar.name}")
    return True


def _name_dwi_series(output_dir: Path, subject_id: str, logger) -> None:
    """Name DWI series that dcm2niix wrote side by side ``dir-<label>``.

    Two diffusion series in one source folder come out as ``sub-{id}_dwi`` and
    dcm2niix's collision name ``sub-{id}_dwia``, which is not BIDS. When each
    one has a gradient table and its own phase-encoding direction, they become
    ``sub-{id}_dir-AP_dwi`` / ``sub-{id}_dir-PA_dwi``, the layout QSIPrep pairs
    for TOPUP. Anything else is left as converted, with a pointer to ``fmap/``.
    """
    base = _bids_name(subject_id, "dwi")
    stems = [
        stem
        for stem in _collision_stems(output_dir, base)
        if (output_dir / f"{stem}.bval").exists()
    ]
    if len(stems) < 2:
        return
    labels = [_series_label(output_dir, stem) for stem in stems]
    if None in labels or len(set(labels)) != len(labels):
        logger.warning(
            f"dcm2niix wrote {len(stems)} diffusion series "
            f"({', '.join(f'{stem}.nii.gz' for stem in stems)}) "
            "that could not be told apart by phase-encoding direction, so only "
            f"{base} is used. If one is the reverse phase-encoding (e.g. PA) "
            "scan for distortion correction, put its DICOMs in "
            f"sourcedata/sub-{subject_id}/fmap/ instead of dwi/, remove the "
            f"{base}* files and convert again."
        )
        return
    for stem, label in zip(stems, labels):
        _rename_series(output_dir, stem, f"sub-{subject_id}_dir-{label}_dwi")
    named = ", ".join(f"sub-{subject_id}_dir-{label}_dwi" for label in labels)
    logger.warning(
        f"Named {len(stems)} diffusion series by phase-encoding direction: {named}. "
        "QSIPrep uses opposite-direction DWI series for TOPUP and preprocesses each "
        "as a DWI run. If one is a short reverse phase-encoding scan rather than a "
        "full diffusion series, QSIPrep wants it in fmap/: put its DICOMs in "
        f"sourcedata/sub-{subject_id}/fmap/, remove these files and convert again."
    )


def run_dicom_to_nifti(
    project_dir: str,
    subject_id: str,
    *,
    logger,
    runner: CommandRunner | None = None,
) -> None:
    """Ingest a subject's source images into BIDS-named NIfTI files.

    Looks for a ``T1w``, ``T2w``, ``ct``, ``dwi`` and ``fmap`` folder under
    ``sourcedata/sub-{subject_id}/`` (folder names are matched
    case-insensitively) and ingests each one that exists. Anatomical images
    and CT go to the subject's ``anat/`` folder, diffusion images to ``dwi/``
    (with their ``.bval``/``.bvec`` sidecars), and the DWI's reverse
    phase-encoding series to ``fmap/sub-{id}_dir-{label}_epi.nii.gz`` with an
    ``IntendedFor`` naming the DWI. Two diffusion series in ``dwi`` with
    different phase encoding become ``sub-{id}_dir-{label}_dwi``. The label
    (``AP``, ``PA``, ...) comes from :func:`pe_direction_label`.

    Each modality folder is searched recursively. Supported archives
    (``.zip``, ``.tar``, ``.tar.gz``, ``.tgz``) are safely extracted to
    ``extracted_archives/`` first. DICOM files (``.dcm``/``.dicom``) are then
    converted with ``dcm2niix``; if the folder holds no DICOMs but does hold a
    NIfTI, that file is copied into place instead (compressing a bare ``.nii``
    on the way). Dotfiles are ignored throughout.

    CT is written as ``anat/sub-{id}_ct.nii.gz``. This is a local convention,
    not BIDS -- see :data:`MODALITIES`.

    Parameters
    ----------
    project_dir : str
        BIDS project root directory.
    subject_id : str
        Subject identifier without the ``sub-`` prefix.
    logger : logging.Logger
        Logger for progress messages.
    runner : CommandRunner or None, optional
        Subprocess runner for streaming output.

    Raises
    ------
    PreprocessError
        If an output NIfTI already exists for a modality.

    See Also
    --------
    run_pipeline : Full preprocessing pipeline.
    MODALITIES : Supported modalities and their BIDS datatype directories.
    """
    from tit.telemetry import track_operation
    from tit import constants as _const

    with track_operation(_const.TELEMETRY_OP_PRE_DICOM):
        pm = get_path_manager(project_dir)
        sourcedata_dir = Path(pm.sourcedata_subject(subject_id))

        converted = False
        for modality, datatype in MODALITIES:
            modality_dir = _modality_source_dir(sourcedata_dir, modality)
            if not modality_dir.exists():
                continue
            output_dir = Path(pm.bids_datatype(subject_id, datatype))
            if _ingest_modality(
                modality_dir, output_dir, subject_id, modality, logger, runner
            ):
                converted = True

        if not converted:
            logger.warning("No DICOM or NIfTI files found or converted")
