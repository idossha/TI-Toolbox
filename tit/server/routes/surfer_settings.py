"""User-wide FastSurfer and FreeSurfer preferences."""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat

from tit.surfer_settings import (
    QSIPrepPreferences,
    QSIReconPreferences,
    read_settings,
    save_preferences,
)

router = APIRouter()


class SurferPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    charm_options: dict[str, StrictBool | StrictFloat | None] | None = None
    qsiprep_config: QSIPrepPreferences = Field(default_factory=QSIPrepPreferences)
    qsi_recon_config: QSIReconPreferences = Field(default_factory=QSIReconPreferences)
    fastsurfer_threads: int | None = Field(default=None, strict=True, ge=1, le=4096)
    freesurfer_threads: int | None = Field(default=None, strict=True, ge=1, le=4096)

    charm_threads: int | None = Field(default=None, strict=True, ge=1, le=4096)
    qsiprep_threads: int | None = Field(default=None, strict=True, ge=1, le=4096)
    qsirecon_threads: int | None = Field(default=None, strict=True, ge=1, le=4096)
    qsiprep_memory_gb: int | None = Field(default=None, strict=True, ge=1, le=4096)
    qsirecon_memory_gb: int | None = Field(default=None, strict=True, ge=1, le=4096)
    qsiprep_omp_threads: int | None = Field(default=None, strict=True, ge=1, le=4096)
    qsirecon_omp_threads: int | None = Field(default=None, strict=True, ge=1, le=4096)
    freesurfer_recon_all: bool = Field(default=True, strict=True)
    freesurfer_subregions: list[Literal["thalamus", "hippo-amygdala"]] = Field(
        default_factory=lambda: ["thalamus", "hippo-amygdala"]
    )


class SurferSettings(SurferPreferences):
    effective_charm_threads: int
    effective_qsiprep_threads: int
    effective_qsirecon_threads: int
    available_threads: int
    default_threads: int
    effective_fastsurfer_threads: int
    effective_freesurfer_threads: int


@router.get("/api/surfer-settings")
def get_surfer_settings() -> SurferSettings:
    return SurferSettings.model_validate(read_settings())


@router.put("/api/surfer-settings")
def put_surfer_settings(body: SurferPreferences) -> SurferSettings:
    try:
        save_preferences(body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return get_surfer_settings()
