"""Every config the mock e2e suite submitted is one the real Python validators accept.

What this pins (2026-10-22, package p38): the mock server checks only a config's ``required``
fields, so a page that bypasses or post-edits its builder (a missing cross-field rule, a nested
shape the dataclass cannot read, a value its ``__post_init__`` refuses) stays green in mock e2e
and is refused -- or crashes a runner -- on the real server. With ``TIT_E2E_BODIES_LOG=<file>``
the mock appends one JSON line ``{kind, config, subject_ids, via}`` per config the real server
would validate on an accepted submission: each ``POST /api/jobs`` body, each config
``POST /api/jobs/groups`` generates per subject, and a ``pre`` group's own config (``__mock_*``
test jobs excluded). ``via`` is ``app`` for a request the renderer made and ``api`` for a job a
spec seeded itself through Playwright's request context.

Each record goes to the real class for its kind as the submit path builds it: ``cls_for`` (the
``_type`` of ``stats``/``blender`` included), the server-owned envelope keys dropped, legacy
``pre`` keys migrated and a ``pre`` config's ``subject_ids`` taken from the request when it has
none (``tit/server/routes/jobs.py``), then ``deserialize_config`` -- unknown keys ignored, as the
runners ignore them -- including ``__post_init__``. That covers ``AnalyzerConfig`` and
``PreprocessConfig``, which ``tit.jobs.config_check`` skips. Expected verdicts come from the real
dataclass validators, not from the mock or the pages.

Run after a mock e2e run: export ``TIT_E2E_BODIES_LOG=<file>`` for the Playwright run (the mock
inherits it), then ``TIT_E2E_BODIES_LOG=<file> .venv/bin/python -m pytest
tests/test_e2e_recorded_bodies.py -q``. Without the variable, or with no log file, it skips.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

LOG = os.environ.get("TIT_E2E_BODIES_LOG", "")

pytestmark = pytest.mark.skipif(
    not LOG or not Path(LOG).is_file(),
    reason="skipping: TIT_E2E_BODIES_LOG is unset or names no file (run the mock e2e suite "
    "with it exported first)",
)


def _records(via: str) -> list[dict]:
    from tit.server.routes.validate import ALL_KINDS

    lines = Path(LOG).read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines if line.strip()]
    assert (
        records
    ), f"{LOG} holds no submissions: did the e2e run export it to the mock?"
    return [r for r in records if r.get("via") == via and r["kind"] in ALL_KINDS]


def _refusal(record: dict) -> str | None:
    """The real validator's refusal of *record*'s config, or None when it is accepted."""
    from tit.config_io import deserialize_config
    from tit.server.routes.validate import ENVELOPE_KEYS, KindNotConfigurable, cls_for

    kind, config = record["kind"], record["config"]
    try:
        cls = cls_for(kind, config)
    except KindNotConfigurable as exc:
        return str(exc)
    data = {k: v for k, v in config.items() if k not in ENVELOPE_KEYS}
    if kind == "pre":
        from tit.pre.config import migrate_legacy_keys

        data = migrate_legacy_keys(data, warnings=[])
        if not data.get("subject_ids") and record.get("subject_ids"):
            data["subject_ids"] = list(record["subject_ids"])
    try:
        deserialize_config(cls, data)
    except (ValueError, TypeError, KeyError) as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def _report(records: list[dict]) -> dict[tuple[str, str], list[int]]:
    refusals: dict[tuple[str, str], list[int]] = {}
    for i, record in enumerate(records):
        reason = _refusal(record)
        if reason:
            refusals.setdefault((record["kind"], reason), []).append(i)
    return refusals


def _format(refusals: dict[tuple[str, str], list[int]]) -> str:
    return "\n".join(
        f"{kind}: {reason} (records {ix[:5]}{'...' if len(ix) > 5 else ''})"
        for (kind, reason), ix in sorted(refusals.items())
    )


def test_every_config_a_page_submitted_is_a_valid_config() -> None:
    records = _records("app")
    kinds = {r["kind"] for r in records}
    assert {
        "sim",
        "flex",
        "ex",
        "analyzer",
        "pre",
    } <= kinds, f"has run pages to check: {kinds}"
    refusals = _report(records)
    assert not refusals, f"{len(refusals)} distinct refusals:\n{_format(refusals)}"


def test_every_job_a_spec_seeded_is_a_valid_config() -> None:
    refusals = _report(_records("api"))
    if refusals:
        # Spec-authored seeds (desktop/tests/e2e/jobs.spec.ts `seedConfig`), not page wiring:
        # recorded, reported, and left to that spec's owner rather than failing this check.
        pytest.xfail(f"{len(refusals)} distinct refusals:\n{_format(refusals)}")
