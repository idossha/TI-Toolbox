"""Mask output identity shared by planning and analysis (no image imports)."""

import hashlib
from pathlib import Path


def mask_region_name(path: str, space: str) -> str:
    """Keep same-named masks and coordinate spaces in distinct result folders."""
    stem = Path(path).name.removesuffix(".gz").removesuffix(".nii")
    digest = hashlib.sha256(f"{path}:{space}".encode()).hexdigest()[:10]
    return f"mask_{stem}_{space}_{digest}"


def validate_mask_path(config) -> None:
    """Reject inaccessible mask paths before a plan promises a runnable job."""
    if config.analysis_type == "mask" and not Path(config.mask_path).is_file():
        raise ValueError(
            f"mask_path: mask is not accessible in the container: {config.mask_path}. "
            "Import it through the NIfTI mask picker, or use an existing path inside the container."
        )
