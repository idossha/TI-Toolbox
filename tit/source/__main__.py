"""CLI entry point for the source package.

Usage::

    simnibs_python -m tit.source config.json

The JSON config is dispatched on its ``"mode"`` field:

* ``"forward"``   -> :func:`tit.source.forward.prepare_forward` per subject
* ``"fsavg_map"`` -> :func:`tit.source.fsaverage.project_fields_to_fsaverage`

See Also
--------
tit.source.config : ``SourceConfig``, ``ForwardConfig``, and ``FsavgMapConfig``.
"""

import json
import logging
import os
import sys
from contextlib import nullcontext

from tit.paths import get_path_manager
from tit.source.config import ForwardConfig, FsavgMapConfig, SourceConfig, SourceMode


def _hold_locks(kind: str, subject_ids: list[str], config_dict: dict):
    """Best-effort lock scaffold: a no-op unless running as a ``tit.jobs`` job."""
    try:
        from tit.jobs import locks
        from tit.jobs.runner import ENV_JOB_ID
    except ImportError:
        return nullcontext()
    job_id = os.environ.get(ENV_JOB_ID)
    if not job_id:
        return nullcontext()
    requests = locks.keys_for(kind, subject_ids, config_dict)
    return locks.hold(get_path_manager().project_dir, job_id, requests)


def _build_config_legacy(data: dict) -> SourceConfig:
    """Old, pre-``SourceConfig`` dict layout -- read verbatim.

    Kept for one release: a caller sending the flat, mode-specific dict
    this entry point accepted before :class:`~tit.source.config.SourceConfig`
    existed still works.
    """
    mode = data.get("mode", "forward")
    if mode == "forward":
        return SourceConfig(
            mode=mode,
            subject_ids=data.get("subject_ids", []),
            forward=ForwardConfig(
                eeg_net=data.get("eeg_net", "GSN-HydroCel-185"),
                fsaverage_spacing=data.get("fsaverage_spacing", 5),
                cpus=data.get("cpus", 1),
                overwrite=data.get("overwrite", False),
            ),
        )
    from tit.source.config import SourcePair

    pairs = [SourcePair(**p) for p in data.get("pairs", [])]
    default_fields = FsavgMapConfig().fields
    return SourceConfig(
        mode=mode,
        pairs=pairs,
        fsavg_map=FsavgMapConfig(
            fields=tuple(data.get("fields", default_fields)),
            fsaverage_spacing=data.get("fsaverage_spacing", 5),
            workers=data.get("workers", 1),
            overwrite=data.get("overwrite", False),
        ),
    )


def _build_config(data: dict) -> SourceConfig:
    """Build a :class:`SourceConfig`, preferring ``deserialize_config``.

    Falls back to :func:`_build_config_legacy` when *data* does not carry
    the new nested ``"forward"``/``"fsavg_map"`` shape -- see the
    module-level "old dict layout for one release" note. The nested key's
    presence is checked explicitly (not just "did ``deserialize_config``
    raise"): both ``ForwardConfig`` and ``FsavgMapConfig`` fields all have
    defaults, so an old flat-keyed dict missing the nested key entirely
    would otherwise deserialize *successfully* into an all-defaults
    sub-config instead of raising, silently dropping every flat key.
    """
    mode = data.get("mode", "forward")
    nested_key = "forward" if mode == "forward" else "fsavg_map"
    if nested_key not in data:
        return _build_config_legacy(data)

    from tit.config_io import deserialize_config

    try:
        return deserialize_config(SourceConfig, data)
    except (TypeError, ValueError, KeyError) as exc:
        logging.getLogger("tit.source").debug(
            f"deserialize_config(SourceConfig, ...) failed ({exc}); "
            "falling back to the legacy dict layout"
        )
        return _build_config_legacy(data)


def main() -> None:
    """Parse config JSON and dispatch to the forward or fsavg-map pipeline."""
    from tit.logger import add_stream_handler, setup_logging
    from tit.jobs import events

    setup_logging("INFO")
    add_stream_handler("tit.source")

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    get_path_manager(data.pop("project_dir"))

    try:
        config = _build_config(data)
    except (TypeError, ValueError) as exc:
        print(f"Invalid source config: {exc}", file=sys.stderr)
        sys.exit(1)

    if config.mode is SourceMode.FORWARD:
        subject_ids = config.subject_ids
    else:
        subject_ids = [p.subject_id for p in config.pairs]
    lock_cm = _hold_locks("source", subject_ids, data)

    print(f"Starting source {config.mode.value} pipeline...", flush=True)

    exit_code = 1
    try:
        with lock_cm:
            events.emit_stage(config.mode.value)
            if config.mode is SourceMode.FORWARD:
                exit_code = _run_forward(config)
            else:
                exit_code = _run_fsavg_map(config)
    finally:
        events.emit_exit(exit_code)

    if exit_code == 0:
        print("✓ Source pipeline complete.", flush=True)
    sys.exit(exit_code)


def _run_forward(config: SourceConfig) -> int:
    """Build forward solutions for one or more subjects."""
    from tit.jobs import events
    from tit.source.forward import _ensure_fork_start_method, prepare_forward

    _ensure_fork_start_method()

    subject_ids = config.subject_ids
    cfg = config.forward
    total = len(subject_ids)
    print(
        f"Forward: {total} subject(s), net={cfg.eeg_net}, "
        f"fsaverage={cfg.fsaverage_spacing}, cpus={cfg.cpus}",
        flush=True,
    )

    failed: list[str] = []
    for idx, subject_id in enumerate(subject_ids, 1):
        events.emit_stage(f"sub-{subject_id}", i=idx, n=total)
        print(f"[{idx}/{total}] sub-{subject_id}", flush=True)
        try:
            fwd, src, morph = prepare_forward(subject_id, cfg)
            for path in (fwd, src, morph):
                events.emit_artifact(str(path), kind="file", label=path.name)
            print(f"  ✓ {fwd.name}, {src.name}, {morph.name}", flush=True)
        except Exception as exc:  # noqa: BLE001 - report and continue across subjects
            print(f"  ✗ FAILED: {exc}", flush=True)
            failed.append(subject_id)
        events.emit_progress(100.0 * idx / total if total else 100.0)

    events.emit_result({"n_subjects": total, "failed": failed})
    if failed:
        print(f"Forward failed for: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


def _run_fsavg_map(config: SourceConfig) -> int:
    """Project field outputs to fsaverage for (subject, simulation) pairs."""
    from tit.jobs import events
    from tit.source.fsaverage import project_fields_to_fsaverage

    pairs = [(p.subject_id, p.simulation) for p in config.pairs]
    cfg = config.fsavg_map
    print(
        f"fsaverage map: {len(pairs)} pair(s), fields={list(cfg.fields)}, "
        f"fsaverage={cfg.fsaverage_spacing}, workers={cfg.workers}",
        flush=True,
    )

    results = project_fields_to_fsaverage(pairs, cfg)
    failed = sorted({sid for sid, status, _ in results if status == "failed"})
    events.emit_result({"n_pairs": len(pairs), "failed": failed})
    if failed:
        print(f"fsaverage map failed for: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    main()
