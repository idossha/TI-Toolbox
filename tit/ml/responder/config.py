from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from tit.core import get_path_manager


DEFAULT_EFIELD_FILENAME_PATTERN = "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"
DEFAULT_GLASSER_ATLAS_FILENAME = "MNI_Glasser_HCP_v1.0.nii.gz"
DEFAULT_GLASSER_LABELS_FILENAME = "MNI_Glasser_HCP_v1.0.tsv"


def _find_resources_atlas_dir() -> Optional[Path]:
    """
    Best-effort locator for `resources/atlas/`.

    In a source checkout, `resources/atlas/` is located at repo root.
    In a Docker image, that layout typically remains, but users may also copy
    atlases into the project directory.

    Search order:
    1) <PROJECT_DIR>/resources/atlas
    2) walk up from this file to find a sibling `resources/atlas`
    """
    pm = get_path_manager()
    if pm.project_dir:
        p = Path(pm.project_dir) / "resources" / "atlas"
        if p.is_dir():
            return p

    here = Path(__file__).resolve()
    for parent in [here, *here.parents][:8]:
        cand = parent / "resources" / "atlas"
        if cand.is_dir():
            return cand
    return None


def default_glasser_atlas_path() -> Optional[Path]:
    atlas_dir = _find_resources_atlas_dir()
    if not atlas_dir:
        return None
    p = atlas_dir / DEFAULT_GLASSER_ATLAS_FILENAME
    return p if p.is_file() else None


def default_glasser_labels_path() -> Optional[Path]:
    atlas_dir = _find_resources_atlas_dir()
    if not atlas_dir:
        return None
    p = atlas_dir / DEFAULT_GLASSER_LABELS_FILENAME
    return p if p.is_file() else None


def default_output_dir(run_name: str) -> Path:
    """Default output directory: <PROJECT_DIR>/derivatives/ti-toolbox/responder/<run_name>/."""
    pm = get_path_manager()
    if not pm.project_dir:
        raise RuntimeError(
            "Project directory not resolved. Set PROJECT_DIR_NAME or PROJECT_DIR in Docker."
        )
    return Path(pm.path("ti_responder_run", run_name=run_name))


def default_subjects_csv_path() -> Path:
    """Default location for the responder ML input table: <PROJECT_DIR>/derivatives/ti-toolbox/responder/inputs/subjects.csv."""
    pm = get_path_manager()
    if not pm.project_dir:
        raise RuntimeError(
            "Project directory not resolved. Set PROJECT_DIR_NAME or PROJECT_DIR in Docker."
        )
    return Path(pm.path("ti_responder_inputs")) / "subjects.csv"


@dataclass(frozen=True)
class ResponderMLConfig:
    csv_path: Path
    # Task mode:
    # - classification: binary target (0/1)
    # - regression: continuous target (float)
    task: Literal["classification", "regression"] = "classification"
    # Name of the target column in the CSV (defaults to the historical "response").
    target_col: str = "response"
    atlas_path: Optional[Path] = None
    atlas_labels_path: Optional[Path] = None
    efield_filename_pattern: str = DEFAULT_EFIELD_FILENAME_PATTERN
    run_name: str = "run"
    output_dir: Optional[Path] = None

    # Model/CV defaults (kept conservative for small N)
    outer_splits: int = 5
    inner_splits: int = 4
    random_state: int = 42
    n_jobs: int = 1

    # Optional bootstrap for coefficient stability (0 disables)
    bootstrap_samples: int = 0

    # Print progress + enable sklearn verbose output for GridSearchCV
    verbose: bool = False
