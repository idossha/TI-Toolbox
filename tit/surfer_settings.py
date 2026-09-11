"""User-wide reconstruction resource preferences, shared by plans and runners."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tit import constants as const
from tit.charm_options import validate_charm_options
from tit.paths import PathManager

Surfer = Literal["fastsurfer", "freesurfer", "charm", "qsiprep", "qsirecon"]
THREAD_TOOLS = ("fastsurfer", "freesurfer", "charm", "qsiprep", "qsirecon")
RESOURCE_KEYS = tuple(f"{tool}_threads" for tool in THREAD_TOOLS) + (
    "qsiprep_memory_gb",
    "qsirecon_memory_gb",
    "qsiprep_omp_threads",
    "qsirecon_omp_threads",
)


class QSIPrepPreferences(BaseModel):
    """User defaults for processing, separate from resource allocation."""

    model_config = ConfigDict(extra="forbid", strict=True)
    output_resolution: float = Field(
        default=const.QSI_DEFAULT_OUTPUT_RESOLUTION, gt=0, allow_inf_nan=False
    )
    image_tag: str = Field(
        default=const.QSI_QSIPREP_IMAGE_TAG, pattern=r"^[\w][\w.-]{0,127}$"
    )
    skip_bids_validation: bool = True
    denoise_method: Literal["dwidenoise", "patch2self", "none"] = "dwidenoise"
    unringing_method: Literal["mrdegibbs", "rpg", "none"] = "mrdegibbs"


class QSIReconPreferences(BaseModel):
    """User defaults for reconstruction, separate from resource allocation."""

    model_config = ConfigDict(extra="forbid", strict=True)
    recon_specs: list[str] = Field(
        default_factory=lambda: [const.QSI_DEFAULT_RECON_SPEC], min_length=1
    )
    atlases: list[str] | None = None
    use_gpu: bool = False
    image_tag: str = Field(
        default=const.QSI_QSIRECON_IMAGE_TAG, pattern=r"^[\w][\w.-]{0,127}$"
    )
    skip_odf_reports: bool = True

    @field_validator("recon_specs")
    @classmethod
    def valid_specs(cls, values: list[str]) -> list[str]:
        if any(value not in const.QSI_RECON_SPECS for value in values):
            raise ValueError("Unknown reconstruction specification")
        return list(dict.fromkeys(values))

    @field_validator("atlases")
    @classmethod
    def valid_atlases(cls, values: list[str] | None) -> list[str] | None:
        if values is not None and any(
            value not in const.QSI_ATLASES for value in values
        ):
            raise ValueError("Unknown connectivity atlas")
        return list(dict.fromkeys(values)) if values is not None else None


QSI_MODELS = {
    "qsiprep_config": QSIPrepPreferences,
    "qsi_recon_config": QSIReconPreferences,
}


def default_preferences() -> dict[str, Any]:
    return {
        **dict.fromkeys(RESOURCE_KEYS),
        **{key: model().model_dump() for key, model in QSI_MODELS.items()},
        "charm_options": None,
        "freesurfer_recon_all": True,
        "freesurfer_subregions": ["thalamus", "hippo-amygdala"],
    }


def get_container_resource_limits() -> tuple[int | None, int | None]:
    """Load container probes only while resolving resources, never on route import."""
    from tit.pre.qsi.utils import get_container_resource_limits as probe

    return probe()


def available_threads() -> int:
    """Count CPUs usable by this process, including container quotas and affinity."""
    count = os.cpu_count() or 1
    if hasattr(os, "sched_getaffinity"):
        count = min(count, len(os.sched_getaffinity(0)))
    limit, _ = get_container_resource_limits()
    return max(1, min(count, limit) if limit else count)


def settings_path() -> Path:
    return Path(PathManager.user_config_dir()) / "surfer-settings.json"


def load_preferences() -> dict[str, Any]:
    result = default_preferences()
    try:
        data = json.loads(settings_path().read_text())
    except (OSError, ValueError):
        return result
    if isinstance(data, dict):
        for key in RESOURCE_KEYS:
            value = data.get(key)
            if type(value) is int and 1 <= value <= 4096:
                result[key] = value
        if type(data.get("freesurfer_recon_all")) is bool:
            result["freesurfer_recon_all"] = data["freesurfer_recon_all"]
        regions = data.get("freesurfer_subregions")
        if isinstance(regions, list) and all(
            v in ("thalamus", "hippo-amygdala") for v in regions
        ):
            result["freesurfer_subregions"] = list(dict.fromkeys(regions))
        try:
            result["charm_options"] = validate_charm_options(data.get("charm_options"))
        except ValueError:
            pass
        for key, model in QSI_MODELS.items():
            if key in data:
                try:
                    result[key] = model.model_validate(data[key]).model_dump()
                except ValueError:
                    pass
    return result


def save_preferences(values: dict[str, Any]) -> None:
    """Atomically replace validated user preferences."""
    current = load_preferences()
    for key, model in QSI_MODELS.items():
        if key in values:
            if not isinstance(values[key], dict):
                raise ValueError(f"{key} must be an object")
            values = {
                **values,
                key: model.model_validate({**current[key], **values[key]}).model_dump(),
            }
    values = {**current, **values}
    values["charm_options"] = validate_charm_options(values["charm_options"])
    for key in RESOURCE_KEYS:
        value = values[key]
        if value is not None and (type(value) is not int or not 1 <= value <= 4096):
            raise ValueError(f"{key} must be null or an integer from 1 to 4096")
    if type(values["freesurfer_recon_all"]) is not bool:
        raise ValueError("freesurfer_recon_all must be boolean")
    regions = values["freesurfer_subregions"]
    if not isinstance(regions, list) or any(
        v not in ("thalamus", "hippo-amygdala") for v in regions
    ):
        raise ValueError("Invalid FreeSurfer subregions")
    if not values["freesurfer_recon_all"] and not regions:
        raise ValueError("Choose at least one FreeSurfer operation")
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        tmp = Path(stream.name)
        json.dump(values, stream)
    try:
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def effective_threads(surfer: Surfer, explicit: int | None = None) -> int:
    """Preserve script overrides; apply capacity limits to user preferences."""
    if explicit is not None:
        return max(1, int(explicit))
    if surfer == "fastsurfer":
        try:
            override = int(os.environ.get("TIT_FASTSURFER_THREADS", ""))
        except ValueError:
            pass
        else:
            return max(1, override)
    capacity = available_threads()
    preferred = load_preferences()[f"{surfer}_threads"]
    return min(capacity, preferred or max(1, capacity - 1))


def read_settings() -> dict[str, Any]:
    capacity = available_threads()
    return {
        **load_preferences(),
        "available_threads": capacity,
        # Leave one core for the server and the host desktop.
        "default_threads": max(1, capacity - 1),
        **{
            f"effective_{tool}_threads": effective_threads(tool)
            for tool in THREAD_TOOLS
        },
    }


def resolve_job_threads(config: dict) -> dict:
    """Snapshot defaults so queued jobs keep the CPU reservation they were planned with."""
    result = dict(config)
    for surfer in ("fastsurfer", "freesurfer"):
        if result.get(f"run_{surfer}"):
            key = f"{surfer}_threads"
            result[key] = effective_threads(surfer, result.get(key))
    if result.get("create_m2m"):
        result["charm_threads"] = effective_threads(
            "charm", result.get("charm_threads")
        )
    preferences = load_preferences()
    if result.get("create_m2m") and result.get("charm_options") is None:
        result["charm_options"] = preferences["charm_options"]
    for tool, field in (
        ("qsiprep", "qsiprep_config"),
        ("qsirecon", "qsi_recon_config"),
    ):
        if not result.get(f"run_{tool}"):
            continue
        resources = dict(result.get(field) or {})
        resources["cpus"] = effective_threads(tool, resources.get("cpus"))
        for resource in ("memory_gb", "omp_threads"):
            if resources.get(resource) is None:
                value = preferences[f"{tool}_{resource}"]
                if value is not None:
                    resources[resource] = (
                        min(value, resources["cpus"])
                        if resource == "omp_threads"
                        else value
                    )
        result[field] = resources
    return result
