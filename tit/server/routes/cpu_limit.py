"""``GET``/``PUT /api/cpu-limit``: the user's global CPU limit (Settings ▸ Performance).

User-wide, not per project: stored in the user config dir by :mod:`tit.cpu`, which the scheduler
budget and every "use all the cores" default read. A change applies to jobs admitted after it;
running jobs keep the CPUs they were admitted with.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from tit import cpu

router = APIRouter()


class CpuLimitUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    percent: int = Field(strict=True, ge=cpu.MIN_CPU_LIMIT_PERCENT, le=100)


class CpuLimit(BaseModel):
    percent: int = Field(
        description="percent of the container's cores TI-Toolbox may use"
    )
    cores: int = Field(
        description="the resulting core count, floor(percent x available), >= 1"
    )
    available_cores: int = Field(description="cores available to the container")
    default_percent: int


def _read() -> CpuLimit:
    return CpuLimit(
        percent=cpu.cpu_limit_percent(),
        cores=cpu.cpu_limit(),
        available_cores=cpu.effective_cpus(),
        default_percent=cpu.DEFAULT_CPU_LIMIT_PERCENT,
    )


@router.get("/api/cpu-limit", summary="Global CPU limit for all jobs")
def get_cpu_limit() -> CpuLimit:
    return _read()


@router.put("/api/cpu-limit", summary="Set the global CPU limit")
def put_cpu_limit(body: CpuLimitUpdate) -> CpuLimit:
    try:
        cpu.save_cpu_limit_percent(body.percent)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _read()
