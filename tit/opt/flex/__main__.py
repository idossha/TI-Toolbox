"""Entry point: simnibs_python -m tit.opt.flex config.json"""

import json
import sys

from tit.opt.config import FlexConfig
from tit.opt.flex.flex import run_flex_search

_ROI_BUILDERS = {
    "SphericalROI": FlexConfig.SphericalROI,
    "AtlasROI": FlexConfig.AtlasROI,
    "SubcorticalROI": FlexConfig.SubcorticalROI,
}


def _build_roi(data: dict | None):
    if data is None:
        return None
    data = dict(data)
    roi_type = data.pop("_type")
    return _ROI_BUILDERS[roi_type](**data)


def main() -> None:
    from tit.logger import add_stream_handler

    add_stream_handler("tit.opt.flex")

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    roi = _build_roi(data.pop("roi"))
    non_roi = _build_roi(data.pop("non_roi", None))
    electrode = FlexConfig.ElectrodeConfig(**data.pop("electrode"))

    config = FlexConfig(roi=roi, non_roi=non_roi, electrode=electrode, **data)
    result = run_flex_search(config)
    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
