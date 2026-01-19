from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

from tit.core import get_path_manager

from .config import DEFAULT_EFIELD_FILENAME_PATTERN


@dataclass(frozen=True)
class SubjectRow:
    subject_id: str
    simulation_name: str
    condition: Optional[str] = None
    target: Optional[float] = (
        None  # binary (0/1) for classification; optional for predict
    )


def is_sham_condition(condition: Optional[str], sham_value: str = "sham") -> bool:
    return (condition or "").strip().lower() == (sham_value or "").strip().lower()


def load_subject_table(
    csv_path: Path,
    *,
    target_col: str = "response",
    condition_col: Optional[str] = None,
    sham_value: str = "sham",
    task: str = "classification",
    require_target: bool = True,
) -> List[SubjectRow]:
    """
    Read the responder ML CSV.

    Required columns:
    - subject_id
    - simulation_name
    - target_col (only if require_target=True)
    - condition_col (only if provided)

    Target parsing:
    - classification: target must be 0/1
    - regression: target must be numeric (float)

    Sham handling (optional):
    - If `condition_col` is provided and the row's condition equals `sham_value`
      (case-insensitive), then an empty `simulation_name` is allowed. This supports
      including sham subjects without requiring NIfTI files (features will be set to 0).
    """
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")

        required = {"subject_id", "simulation_name"}
        if require_target:
            required.add(str(target_col))
        if condition_col:
            required.add(str(condition_col))
        missing = required.difference({h.strip() for h in reader.fieldnames if h})
        if missing:
            raise ValueError(
                f"CSV missing required columns: {', '.join(sorted(missing))}"
            )

        rows: List[SubjectRow] = []
        for i, r in enumerate(reader, start=2):
            sid = (r.get("subject_id") or "").strip()
            sim = (r.get("simulation_name") or "").strip()
            cond_raw: Optional[str] = None
            if condition_col:
                cond_raw = (r.get(str(condition_col)) or "").strip()

            if not sid:
                raise ValueError(f"Empty subject_id on line {i}")

            if not sim:
                if condition_col and is_sham_condition(cond_raw, sham_value=sham_value):
                    # Allowed: sham subjects can omit simulation_name because they do not
                    # require a NIfTI on disk (features will be set to 0).
                    sim = ""
                else:
                    raise ValueError(f"Empty simulation_name on line {i}")

            target_val: Optional[float] = None
            if require_target:
                raw = (r.get(str(target_col)) or "").strip()
                if raw == "":
                    raise ValueError(f"Empty {target_col!r} on line {i}")
                if str(task) == "classification":
                    try:
                        resp = int(raw)
                    except ValueError:
                        raise ValueError(
                            f"Invalid {target_col!r} on line {i}: {raw!r} (expected 0/1)"
                        ) from None
                    if resp not in (0, 1):
                        raise ValueError(
                            f"Invalid {target_col!r} on line {i}: {resp} (expected 0/1)"
                        )
                    target_val = float(resp)
                elif str(task) == "regression":
                    try:
                        target_val = float(raw)
                    except ValueError:
                        raise ValueError(
                            f"Invalid {target_col!r} on line {i}: {raw!r} (expected numeric)"
                        ) from None
                else:
                    raise ValueError(f"Unknown task type: {task}")

            rows.append(
                SubjectRow(
                    subject_id=sid,
                    simulation_name=sim,
                    condition=cond_raw if condition_col else None,
                    target=target_val,
                )
            )

    if not rows:
        raise ValueError("CSV contains no data rows")
    return rows


def efield_nifti_path(
    *,
    subject_id: str,
    simulation_name: str,
    efield_filename_pattern: str = DEFAULT_EFIELD_FILENAME_PATTERN,
) -> Path:
    """
    Resolve the E-field path using TI-toolbox project conventions:
      /{project_dir}/derivatives/SimNIBS/sub-{id}/Simulations/{sim}/TI/niftis/grey_{sim}_TI_MNI_MNI_TI_max.nii.gz
    """
    pm = get_path_manager()
    if not pm.project_dir:
        raise RuntimeError(
            "Project directory not resolved. Set PROJECT_DIR_NAME or PROJECT_DIR in Docker."
        )
    sim_dir = Path(
        pm.path("simulation", subject_id=subject_id, simulation_name=simulation_name)
    )
    fname = efield_filename_pattern.format(
        simulation_name=simulation_name, subject_id=subject_id
    )
    return sim_dir / "TI" / "niftis" / fname


def load_efield_images(
    subjects: Sequence[SubjectRow],
    *,
    efield_filename_pattern: str = DEFAULT_EFIELD_FILENAME_PATTERN,
    logger: Optional[Any] = None,
) -> Tuple[List["nib.Nifti1Image"], List[Optional[float]], List[SubjectRow]]:
    """
    Load E-field NIfTIs for the given subjects.

    Returns (images, y, kept_subjects). Subjects whose files are missing are skipped
    (so downstream code can still run on available subjects).
    """
    try:
        import nibabel as nib  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "nibabel is required for responder ML. Install the optional ML extra: `pip install 'tit[ml]'` "
            "(see docs/wiki/python_env for the TI-toolbox Python environment)."
        ) from e

    imgs: List[nib.Nifti1Image] = []
    y: List[Optional[float]] = []
    kept: List[SubjectRow] = []
    missing: List[Path] = []

    for s in subjects:
        p = efield_nifti_path(
            subject_id=s.subject_id,
            simulation_name=s.simulation_name,
            efield_filename_pattern=efield_filename_pattern,
        )
        if not p.is_file():
            missing.append(p)
            continue
        img = nib.load(str(p))
        imgs.append(img)
        y.append(s.target)
        kept.append(s)

    if not imgs:
        detail = ""
        if missing:
            preview = "\n".join([f"- {m}" for m in missing[:10]])
            detail = f"\nMissing files (first {min(10, len(missing))}):\n{preview}"
        if logger is not None:
            try:
                logger.error("No E-field NIfTIs could be loaded." + detail)
            except Exception:
                pass
        raise FileNotFoundError("No E-field NIfTIs could be loaded." + detail)

    if missing and logger is not None:
        try:
            preview = "\n".join([f"- {m}" for m in missing[:10]])
            logger.warning(
                f"Missing E-field NIfTIs: {len(missing)} (showing first {min(10, len(missing))}):\n{preview}"
            )
        except Exception:
            pass

    return imgs, y, kept
