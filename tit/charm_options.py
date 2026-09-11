"""Validated, optional overrides for installed SimNIBS CHARM settings."""

import math


def validate_charm_options(options: dict | None) -> dict | None:
    """Validate supported overrides while leaving installed defaults untouched."""
    if options is None:
        return None
    if not isinstance(options, dict):
        raise ValueError("charm_options must be an object")
    ranges = {
        "segmentation_final_resolution": (0.5, 2.0),
        "skin_facet_size": (0.5, 10.0),
    }
    allowed = {"denoise", *ranges}
    unknown = set(options) - allowed
    if unknown:
        raise ValueError(f"Unknown CHARM options: {', '.join(sorted(unknown))}")
    result = {}
    for key, value in options.items():
        if value is None:
            continue
        if key == "denoise":
            if type(value) is not bool:
                raise ValueError("CHARM denoise must be a boolean")
        else:
            low, high = ranges[key]
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or not low <= value <= high
            ):
                raise ValueError(f"CHARM {key} must be between {low} and {high} mm")
        result[key] = value
    return result
