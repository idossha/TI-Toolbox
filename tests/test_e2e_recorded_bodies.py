"""Every config the mock e2e suite submitted is one the real Python validators accept.

What this pins (2026-10-22, package p38): the mock server checks only a config's ``required``
fields, so a page that bypasses or post-edits its builder (a missing cross-field rule, a key the
dataclass does not have, a value its ``__post_init__`` refuses) stays green in mock e2e and is
refused -- or crashes a runner -- on the real server. With ``TIT_E2E_BODIES_LOG=<file>`` the mock
appends one JSON line ``{kind, config}`` per job it accepted (``POST /api/jobs`` bodies and every
config ``POST /api/jobs/groups`` generated, ``__mock_*`` test jobs excluded). This test hands each
to the real class for its kind, exactly as ``POST /api/validate/{kind}`` does: ``cls_for`` (the
``_type`` of ``stats``/``blender`` included), the server-owned envelope keys dropped, legacy
``pre`` keys migrated, then ``deserialize_config(..., strict=True)`` including ``__post_init__``.
That covers ``AnalyzerConfig`` and ``PreprocessConfig``, which ``tit.jobs.config_check`` skips.

Expected verdicts come from the real dataclass validators, not from the mock or the pages.

Run after a mock e2e run:
``TIT_E2E_BODIES_LOG=/tmp/bodies.jsonl`` exported for the Playwright run (the mock inherits it),
then ``TIT_E2E_BODIES_LOG=/tmp/bodies.jsonl .venv/bin/python -m pytest
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


def _records() -> list[dict]:
    lines = Path(LOG).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _refusal(kind: str, config: dict) -> str | None:
    """The real validator's refusal of *config* for *kind*, or None when it is accepted."""
    from tit.config_io import deserialize_config
    from tit.server.routes.validate import ENVELOPE_KEYS, KindNotConfigurable, cls_for

    try:
        cls = cls_for(kind, config)
    except KindNotConfigurable as exc:
        return str(exc)
    data = {k: v for k, v in config.items() if k not in ENVELOPE_KEYS}
    if kind == "pre":
        from tit.pre.config import migrate_legacy_keys

        data = migrate_legacy_keys(data, warnings=[])
    try:
        deserialize_config(cls, data, strict=True)
    except (ValueError, TypeError, KeyError) as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def test_every_recorded_submission_is_a_valid_config() -> None:
    from tit.server.routes.validate import ALL_KINDS

    records = _records()
    assert (
        records
    ), f"{LOG} holds no submissions: did the e2e run export it to the mock?"
    checked = [r for r in records if r["kind"] in ALL_KINDS]
    assert checked, "has configs to check"
    refusals = {}
    for i, record in enumerate(checked):
        reason = _refusal(record["kind"], record["config"])
        if reason:
            refusals.setdefault((record["kind"], reason), []).append(i)
    report = "\n".join(
        f"{kind}: {reason} (records {indexes[:5]}{'...' if len(indexes) > 5 else ''})"
        for (kind, reason), indexes in sorted(refusals.items())
    )
    assert not refusals, f"{len(refusals)} distinct refusals:\n{report}"
