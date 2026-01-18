from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Optional, Sequence, Tuple

from tit.core import get_path_manager

from .config import DEFAULT_EFIELD_FILENAME_PATTERN


@dataclass(frozen=True)
class SubjectRow:
    subject_id: str
    simulation_name: str
    target: Optional[float] = (
        None  # binary (0/1) for classification; float for regression; optional for predict
    )


def load_subject_table(
    csv_path: Path,
    *,
    task: Literal["classification", "regression"] = "classification",
    target_col: str = "response",
    require_target: bool = True,
) -> List[SubjectRow]:
    """
    Read the responder ML CSV.

    Required columns:
    - subject_id
    - simulation_name
    - target_col (only if require_target=True)

    Target parsing:
    - task="classification": target must be 0/1
    - task="regression": target is parsed as float
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
        missing = required.difference({h.strip() for h in reader.fieldnames if h})
        if missing:
            raise ValueError(
                f"CSV missing required columns: {', '.join(sorted(missing))}"
            )

        rows: List[SubjectRow] = []
        for i, r in enumerate(reader, start=2):
            sid = (r.get("subject_id") or "").strip()
            sim = (r.get("simulation_name") or "").strip()
            if not sid or not sim:
                raise ValueError(f"Empty subject_id or simulation_name on line {i}")

            target_val: Optional[float] = None
            if require_target:
                raw = (r.get(str(target_col)) or "").strip()
                if raw == "":
                    raise ValueError(f"Empty {target_col!r} on line {i}")
                if task == "classification":
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
                else:
                    try:
                        target_val = float(raw)
                    except ValueError:
                        raise ValueError(
                            f"Invalid {target_col!r} on line {i}: {raw!r} (expected float)"
                        ) from None

            rows.append(
                SubjectRow(subject_id=sid, simulation_name=sim, target=target_val)
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
        raise FileNotFoundError("No E-field NIfTIs could be loaded." + detail)

    return imgs, y, kept
