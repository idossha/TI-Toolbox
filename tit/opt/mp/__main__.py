"""Entry point: simnibs_python -m tit.opt.mp config.json"""

import json
import sys

from tit.opt.config import FlexConfig, MultiPolarConfig
from tit.opt.mp.engine import run_mp_search

_ROI_BUILDERS = {
    "SphericalROI": FlexConfig.SphericalROI,
    "SubcorticalROI": FlexConfig.SubcorticalROI,
    "CorticalROI": FlexConfig.CorticalROI,
}


def _build_roi(data: dict | None):
    """Deserialize an ROI dict to the appropriate dataclass.

    Supports ``_type`` discriminator field. Falls back to field-based
    inference: ``x`` -> SphericalROI, ``atlas_path`` -> SubcorticalROI.
    CorticalROI shares the ``atlas_path`` field with SubcorticalROI, so it
    always relies on the ``_type`` discriminator (present on every config
    serialized by ``tit.config_io``); the fallback only exists for
    hand-written / pre-CorticalROI JSON.
    """
    if data is None:
        return None
    data = dict(data)

    roi_type = data.pop("_type", None)
    if roi_type is None:
        # Infer from fields
        if "x" in data:
            roi_type = "SphericalROI"
        elif "atlas_path" in data:
            roi_type = "SubcorticalROI"
        else:
            raise ValueError(f"Cannot infer ROI type from fields: {list(data.keys())}")

    builder = _ROI_BUILDERS.get(roi_type)
    if builder is None:
        raise ValueError(f"Unsupported ROI type for mp search: {roi_type}")
    return builder(**data)


def main() -> None:
    from tit.logger import add_stream_handler, setup_logging

    setup_logging()
    add_stream_handler("tit.opt.mp")

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    from tit.paths import get_path_manager

    get_path_manager(data.pop("project_dir"))

    roi = _build_roi(data.pop("roi"))
    non_roi = _build_roi(data.pop("non_roi", None))

    config = MultiPolarConfig(roi=roi, non_roi=non_roi, **data)
    result = run_mp_search(config)

    print(f"\nMulti-polar DE search {'succeeded' if result.success else 'failed'}")
    print(f"  Focality: {result.best_focality:.4f}")
    print(f"  Iterations: {result.n_iterations_run}")
    print(f"  Output: {result.output_dir}")
    print(f"  Montage:")
    for plus_name, minus_name, mA in result.best_montage:
        print(f"    {plus_name} -> {minus_name}  ({mA:.1f} mA)")

    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
