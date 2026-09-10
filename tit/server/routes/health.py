"""``GET /api/health`` — liveness, no auth."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

from tit.server.schemas import Health

router = APIRouter()


@router.get("/api/health", response_model=Health, summary="Liveness (no auth)")
def health(request: Request) -> Health:
    started = request.app.state.started_at
    return Health(status="ok", uptime_s=round(time.monotonic() - started, 3))
