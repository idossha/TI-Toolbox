"""CLI entry point for the source package.

Usage::

    simnibs_python -m tit.source config.json

The JSON config is dispatched on its ``"mode"`` field:

* ``"forward"``   -> :func:`tit.source.forward.prepare_forward` per subject
* ``"fsavg_map"`` -> :func:`tit.source.fsaverage.project_fields_to_fsaverage`

See Also
--------
tit.source.config : ``ForwardConfig`` and ``FsavgMapConfig``.
"""

import json
import sys

from tit.paths import get_path_manager


def main() -> None:
    """Parse config JSON and dispatch to the forward or fsavg-map pipeline."""
    from tit.logger import add_stream_handler, setup_logging

    setup_logging("INFO")
    add_stream_handler("tit.source")

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    get_path_manager(data.pop("project_dir"))

    mode = data.pop("mode", "forward")
    print(f"Starting source {mode} pipeline...", flush=True)

    if mode == "forward":
        _run_forward(data)
    elif mode == "fsavg_map":
        _run_fsavg_map(data)
    else:
        raise SystemExit(f"Unknown mode: {mode!r} (expected 'forward' or 'fsavg_map')")

    print("✓ Source pipeline complete.", flush=True)


def _run_forward(data: dict) -> None:
    """Build forward solutions for one or more subjects."""
    from tit.source.config import ForwardConfig
    from tit.source.forward import _ensure_fork_start_method, prepare_forward

    _ensure_fork_start_method()

    subject_ids = data["subject_ids"]
    cfg = ForwardConfig(
        eeg_net=data.get("eeg_net", "GSN-HydroCel-185"),
        fsaverage_spacing=data.get("fsaverage_spacing", 5),
        cpus=data.get("cpus", 1),
        overwrite=data.get("overwrite", False),
    )
    print(
        f"Forward: {len(subject_ids)} subject(s), net={cfg.eeg_net}, "
        f"fsaverage={cfg.fsaverage_spacing}, cpus={cfg.cpus}",
        flush=True,
    )

    failed: list[str] = []
    for idx, subject_id in enumerate(subject_ids, 1):
        print(f"[{idx}/{len(subject_ids)}] sub-{subject_id}", flush=True)
        try:
            fwd, src, morph = prepare_forward(subject_id, cfg)
            print(f"  ✓ {fwd.name}, {src.name}, {morph.name}", flush=True)
        except Exception as exc:  # noqa: BLE001 - report and continue across subjects
            print(f"  ✗ FAILED: {exc}", flush=True)
            failed.append(subject_id)

    if failed:
        raise SystemExit(f"Forward failed for: {', '.join(failed)}")


def _run_fsavg_map(data: dict) -> None:
    """Project field outputs to fsaverage for (subject, simulation) pairs."""
    from tit.source.config import FsavgMapConfig
    from tit.source.fsaverage import project_fields_to_fsaverage

    pairs = [(p["subject_id"], p["simulation"]) for p in data["pairs"]]
    cfg = FsavgMapConfig(
        fields=tuple(data.get("fields", FsavgMapConfig().fields)),
        fsaverage_spacing=data.get("fsaverage_spacing", 5),
        workers=data.get("workers", 1),
        overwrite=data.get("overwrite", False),
    )
    print(
        f"fsaverage map: {len(pairs)} pair(s), fields={list(cfg.fields)}, "
        f"fsaverage={cfg.fsaverage_spacing}, workers={cfg.workers}",
        flush=True,
    )

    results = project_fields_to_fsaverage(pairs, cfg)
    failed = [sid for sid, status, _ in results if status == "failed"]
    if failed:
        raise SystemExit(f"fsaverage map failed for: {', '.join(sorted(set(failed)))}")


if __name__ == "__main__":
    main()
