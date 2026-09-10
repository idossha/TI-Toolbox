"""Project identity, cached apparent storage size and retained job activity."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any

from fastapi import APIRouter, Request

from tit.paths import PathManager, get_path_manager
from tit.server.routes.project import project
from tit.server.schemas import ProjectSummary, SummaryStorage

router = APIRouter()
logger = logging.getLogger(__name__)
_CACHE_LOCK = threading.Lock()


def scan_storage(root: Path, derivatives: Path) -> SummaryStorage:
    """Count regular-file apparent bytes, excluding symlinks and incomplete scans."""
    counts: Counter[str] = Counter()
    children: dict[str, Counter[str]] = {}
    total = 0
    deadline = time.monotonic() + 60
    try:
        root = root.resolve()
        derivatives = derivatives.resolve()
        from tit.storage import KIND_LABELS, classify, kind_prefixes

        prefixes = kind_prefixes(PathManager(str(root)))
        stack = [root]
        while stack:
            if time.monotonic() > deadline:
                raise OSError("Storage scan exceeded its one-minute budget")
            directory = stack.pop()
            if not directory.resolve().is_relative_to(root):
                raise OSError("Directory moved outside the project during scan")
            with os.scandir(directory) as entries:
                for entry in entries:
                    if time.monotonic() > deadline:
                        raise OSError("Storage scan exceeded its one-minute budget")
                    if entry.is_symlink():
                        continue
                    path = Path(entry.path)
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(path)
                    elif entry.is_file(follow_symlinks=False):
                        size = entry.stat(follow_symlinks=False).st_size
                        total += size
                        kind = classify(str(path), prefixes)
                        if (
                            path.is_relative_to(derivatives)
                            and len(path.relative_to(derivatives).parts) > 1
                        ):
                            folder = path.relative_to(derivatives).parts[0]
                            group = {
                                "freesurfer": "FreeSurfer / FastSurfer",
                                "fastsurfer": "FastSurfer",
                                "ti-toolbox": "TI-Toolbox",
                                ".qsiprep_work": "QSIPrep working data",
                                ".qsirecon_work": "QSIRecon working data",
                            }.get(folder, folder)
                            counts[group] += size
                            if folder == "SimNIBS":
                                label = (
                                    KIND_LABELS.get(kind, "Other SimNIBS data")
                                    if kind != "other"
                                    else "Other SimNIBS data"
                                )
                                children.setdefault(group, Counter())[label] += size
                        elif kind != "other":
                            counts[KIND_LABELS[kind]] += size

    except (OSError, RuntimeError):
        logger.warning("Project storage scan incomplete", exc_info=True)
        return SummaryStorage(
            state="error",
            total_bytes=None,
            other_bytes=None,
            derivatives=[],
            scanned_at=None,
        )
    return SummaryStorage(
        state="ready",
        total_bytes=total,
        other_bytes=total - sum(counts.values()),
        derivatives=[
            {
                "name": name,
                "bytes": size,
                "children": [
                    {"name": label, "bytes": value}
                    for label, value in sorted(
                        children.get(name, {}).items(),
                        key=lambda item: (
                            {
                                "Head models": 0,
                                "Flex search": 1,
                                "Ex search": 2,
                                "Simulations": 3,
                                "Analyses": 4,
                                "Leadfields": 5,
                            }.get(item[0], 6),
                            item[0],
                        ),
                    )
                ],
            }
            for name, size in sorted(
                counts.items(), key=lambda item: (item[0] != "SimNIBS", item[0])
            )
        ],
        scanned_at=datetime.now(timezone.utc).isoformat(),
    )


class StorageCache:
    """One background scan at a time; refresh at most once per five minutes."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.running = False
        self.updated = float("-inf")
        self.result = SummaryStorage(
            state="scanning",
            total_bytes=None,
            other_bytes=None,
            derivatives=[],
            scanned_at=None,
        )

    def get(self, root: Path, derivatives: Path) -> SummaryStorage:
        with self.lock:
            if not self.running and time.monotonic() - self.updated >= 300:
                self.running = True
                threading.Thread(
                    target=self._scan, args=(root, derivatives), daemon=True
                ).start()
            return (
                self.result.model_copy(update={"state": "scanning"})
                if self.running
                else self.result
            )

    def _scan(self, root: Path, derivatives: Path) -> None:
        try:
            result = scan_storage(root, derivatives)
        except Exception:
            logger.exception("Project storage worker failed")
            result = SummaryStorage(
                state="error",
                total_bytes=None,
                other_bytes=None,
                derivatives=[],
                scanned_at=None,
            )
        with self.lock:
            self.result = result
            self.updated = time.monotonic()
            self.running = False


def build_activity(
    jobs: list[dict[str, Any]], now: datetime | None = None
) -> dict[str, Any]:
    """Count each retained job once on its UTC creation date, never file mtimes."""
    now = now or datetime.now(timezone.utc)
    start = now.date() - timedelta(days=364)
    valid = []
    seen = set()
    for job in jobs:
        if job["id"] in seen:
            continue
        try:
            created = datetime.fromisoformat(job["created_at"].replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            created = created.astimezone(timezone.utc)
        except (ValueError, TypeError):
            continue
        seen.add(job["id"])
        valid.append((created, job))
    valid.sort(key=lambda pair: pair[0], reverse=True)
    activity_times = [created for created, _ in valid]
    for _, job in valid:
        for key in ("started_at", "finished_at"):
            if job.get(key):
                try:
                    value = datetime.fromisoformat(job[key].replace("Z", "+00:00"))
                    activity_times.append(
                        value.replace(tzinfo=timezone.utc)
                        if value.tzinfo is None
                        else value.astimezone(timezone.utc)
                    )
                except (ValueError, TypeError):
                    continue
    counts = Counter(
        created.date() for created, _ in valid if start <= created.date() <= now.date()
    )
    return {
        "days": [
            {
                "date": (start + timedelta(days=i)).isoformat(),
                "count": counts[start + timedelta(days=i)],
            }
            for i in range(365)
        ],
        "recent": [
            {
                key: job[key]
                for key in ("id", "kind", "state", "subject_ids", "created_at")
            }
            for _, job in valid[:10]
        ],
        "last_activity_at": max(activity_times).isoformat() if activity_times else None,
        "history_since": valid[-1][0].isoformat() if valid else None,
    }


@router.get(
    "/api/catalog/project-summary",
    response_model=ProjectSummary,
    summary="Project identity, asynchronous storage scan and retained job activity",
)
def project_summary(request: Request) -> ProjectSummary:
    """Return project facts without putting a recursive scan on the request path."""
    from tit.jobs.bootstrap import get_manager

    pm = get_path_manager()
    identity = project()
    with _CACHE_LOCK:
        cache = getattr(request.app.state, "project_storage_cache", None)
        if cache is None:
            cache = StorageCache()
            request.app.state.project_storage_cache = cache
    jobs = get_manager(request.app).list_jobs()
    return ProjectSummary(
        identity={
            "name": identity.name,
            "path": identity.host_path or identity.container_path,
            "created_at": None,
        },
        storage=cache.get(Path(pm.project_dir), Path(pm.derivatives())),
        activity=build_activity(jobs),
    )
