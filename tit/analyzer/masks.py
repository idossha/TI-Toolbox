"""Output identity shared by planning and analysis: masks and atlas regions (no image imports)."""

import hashlib
from pathlib import Path


def mask_region_name(path: str, space: str) -> str:
    """Keep same-named masks and coordinate spaces in distinct result folders."""
    stem = Path(path).name.removesuffix(".gz").removesuffix(".nii")
    digest = hashlib.sha256(f"{path}:{space}".encode()).hexdigest()[:10]
    return f"mask_{stem}_{space}_{digest}"


def analysis_region_key(region) -> str:
    """The region part of an atlas analysis's folder name, from the request alone.

    The requested names (or labels) in their order, each once, joined with ``+`` -- what the
    plan and the Analyzer both name the folder by. A mesh analysis of a bare name such as
    ``"insula"`` still analyses both hemispheres; its folder keeps the name it was asked by,
    because the hemisphere split is only known once the atlas is read.
    """
    regions = region if isinstance(region, (list, tuple)) else [region]
    names = (str(r) for r in regions if r is not None and str(r) != "")
    return "+".join(dict.fromkeys(names))


def validate_mask_path(config) -> None:
    """Reject inaccessible mask paths before a plan promises a runnable job."""
    if config.analysis_type == "mask" and not Path(config.mask_path).is_file():
        raise ValueError(
            f"mask_path: mask is not accessible in the container: {config.mask_path}. "
            "Import it through the NIfTI mask picker, or use an existing path inside the container."
        )
