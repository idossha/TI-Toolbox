"""Fake job runner for ``tit.jobs`` tests.

Stands in for a real ``simnibs_python -m tit.<module> spec.json`` runner: reads its own
``spec.json``, emits ``stage``/``progress``/``log``/``artifact``/``result``/``exit`` events to
``TIT_EVENTS_FILE`` in the shape ``tit.jobs.events`` itself writes (``contracts/events.schema.json``
-- flat ``artifact`` fields, ``result.outputs``/``result.artifacts``, ``exit.code``; see
``contracts/SCHEMA-CHANGES.md``'s 2026-08-27 entry, item 8) -- this script writes the file
directly rather than depending on :mod:`tit.jobs.events`, so B1's scheduler/manager tests never
block on B4's own module import chain. Honours ``SIGTERM`` promptly (checked every ~20ms during
its paced sleep, not just between stages/steps -- a job cancelled mid-``duration_s`` exits in
about one check interval, not after the sleep completes) and can optionally hold real locks so
lock-conflict admission can be exercised end to end.

Behaviour is controlled by ``config["__fake"]``:

- ``stages``: list of stage names to walk through (default ``["run"]``)
- ``duration_s``: total time spent across every stage/step (default ``0.05``)
- ``progress_steps``: progress ticks per stage (default ``1``)
- ``fail``: exit non-zero instead of succeeding (default ``False``)
- ``exit_code``: exact exit code (default ``0`` on success, ``1`` on ``fail``)
- ``term_exit_code``: exit code to report after a ``SIGTERM`` (default ``-15``)
- ``hold_locks``: hold ``tit.jobs.locks.keys_for(kind, subject_ids, config)`` for the run
- ``project_dir``: project dir to hold locks under (default: current working directory)
- ``artifact``: a path to report as a produced artifact (own ``artifact`` event, then folded
  into the final ``result`` event's ``artifacts`` list -- exactly as a real ``emit_artifact()``
  call followed by ``emit_result()`` would)
- ``outputs``: the ``result`` event's ``outputs`` object (default ``{}``)

Runnable directly: ``python tests/fake_runner.py <spec.json>``.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from contextlib import nullcontext
from typing import Any


def _emit(events_file: str, event: dict[str, Any]) -> None:
    event.setdefault("ts", time.time())
    with open(events_file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


class _Terminated(Exception):
    pass


#: How often the paced sleep below re-checks the SIGTERM flag. Small relative to any
#: ``duration_s``/``grace_s`` a test uses, so cancelling a running fake job never depends on a
#: race against how far it happened to get into a single long ``time.sleep()`` call (the actual
#: cause of two multi-second "real sleeps" this file used to have in test_jobs_manager.py's
#: cancel tests -- a signal handler that only sets a flag does not interrupt Python's
#: automatically-retried ``time.sleep()``, PEP 475).
_POLL_S = 0.02


def _paced_sleep(duration: float, stopped: dict[str, bool]) -> None:
    """Sleep ``duration`` seconds total, in small chunks, raising :class:`_Terminated` the
    moment ``stopped["flag"]`` is set instead of only checking it between stages/steps.
    """
    deadline = time.monotonic() + duration
    while True:
        if stopped["flag"]:
            raise _Terminated()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(_POLL_S, remaining))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: fake_runner.py <spec.json>", file=sys.stderr)
        return 2

    with open(argv[0], encoding="utf-8") as fh:
        spec = json.load(fh)
    # The manager hands module kinds a *config* file (config fields + project_dir), exactly like
    # the real runners get; a raw job record (with a ``config`` key) is accepted too.
    if "config" in spec and isinstance(spec.get("config"), dict):
        kind = spec.get("kind", "tools")
        config = spec.get("config") or {}
        subject_ids = spec.get("subject_ids") or []
    else:
        kind = os.environ.get("TIT_JOB_KIND", "tools")
        config = {
            k: v for k, v in spec.items() if k not in ("project_dir", "subject_ids")
        }
        subject_ids = spec.get("subject_ids") or [
            sid for sid in os.environ.get("TIT_JOB_SUBJECT_IDS", "").split(",") if sid
        ]
    fake = config.get("__fake") or {}

    events_file = os.environ.get("TIT_EVENTS_FILE")
    if not events_file:
        print("TIT_EVENTS_FILE not set", file=sys.stderr)
        return 2

    stopped = {"flag": False}
    signal.signal(
        signal.SIGTERM, lambda signum, frame: stopped.__setitem__("flag", True)
    )

    if fake.get("hold_locks"):
        from tit.jobs.locks import hold, keys_for

        project_dir = fake.get("project_dir") or os.getcwd()
        requests = keys_for(kind, subject_ids, config)
        lock_ctx = hold(project_dir, os.environ.get("TIT_JOB_ID", "fake"), requests)
    else:
        lock_ctx = nullcontext()

    stages = fake.get("stages") or ["run"]
    duration_s = float(fake.get("duration_s", 0.05))
    per_stage = duration_s / max(len(stages), 1)
    steps = max(int(fake.get("progress_steps", 1)), 1)

    exit_code = 0
    print(f"fake_runner: starting kind={kind} stages={stages}")
    try:
        with lock_ctx:
            for i, stage in enumerate(stages):
                if stopped["flag"]:
                    raise _Terminated()
                _emit(
                    events_file,
                    {"type": "stage", "stage": stage, "i": i, "n": len(stages)},
                )
                _emit(
                    events_file,
                    {
                        "type": "log",
                        "level": "info",
                        "logger": "fake_runner",
                        "msg": f"stage {stage}",
                    },
                )
                for step in range(steps):
                    if stopped["flag"]:
                        raise _Terminated()
                    pct = 100.0 * (step + 1) / steps
                    _emit(
                        events_file,
                        {
                            "type": "progress",
                            "stage": stage,
                            "i": step,
                            "n": steps,
                            "pct": pct,
                        },
                    )
                    _paced_sleep(per_stage / steps, stopped)

            if fake.get("fail"):
                exit_code = int(fake.get("exit_code", 1))
            else:
                artifact = fake.get("artifact")
                artifacts: list[dict[str, str]] = []
                if artifact:
                    item = {"path": artifact, "kind": "txt"}
                    # A standalone "artifact" event per produced file (the real
                    # tit.jobs.events.emit_artifact shape) -- accumulated below into the
                    # "result" event's own `artifacts` field, exactly as emit_result() does.
                    _emit(events_file, {"type": "artifact", **item})
                    artifacts.append(item)
                result_event: dict[str, Any] = {
                    "type": "result",
                    "outputs": fake.get("outputs", {}),
                }
                if artifacts:
                    result_event["artifacts"] = artifacts
                _emit(events_file, result_event)
                exit_code = int(fake.get("exit_code", 0))
    except _Terminated:
        exit_code = int(fake.get("term_exit_code", -15))
        _emit(
            events_file,
            {
                "type": "log",
                "level": "warning",
                "logger": "fake_runner",
                "msg": "terminated",
            },
        )
    finally:
        _emit(events_file, {"type": "exit", "code": exit_code})

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
