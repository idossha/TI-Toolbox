#!/usr/bin/env python3
"""Snapshot Dataset 000's catalog for the desktop builders' real-data tests.

What it writes: ``desktop/tests/fixtures/realdata/dataset000_catalog.json`` -- what the server's
catalog endpoints answer for every subject of a Dataset 000 copy (subjects, montages, EEG nets
with their electrode labels, flex runs with their mappings and optimised XYZ, free-hand
placements, leadfields, simulations with their field names), plus the cap coordinates of every
electrode a saved montage names (``tit.sim.utils._load_eeg_position_csv``, the reader the
simulator resolves montage coordinates with). ``desktop/tests/unit/realdata-builders.test.ts``
drives the real desktop builders over it; ``tests/test_desktop_realdata_snapshot.py`` fails when
the committed snapshot no longer equals what this script builds from the dataset.

Read-only: it calls only ``tit.catalog`` readers -- never the flex mapping route
(``/api/catalog/flex-runs/{run}/mapping`` caches a file beside the run), never a writer.
Absolute paths are written under the placeholder root ``/dataset000``.

Usage::

    TIT_DATASET_000=/path/to/000 python dev/regen_desktop_realdata_fixture.py [--check]

``--check`` exits 1 when the committed snapshot differs instead of writing it. The catalog's
readers only parse JSON and CSV, but the packages they live in import SimNIBS, matplotlib and
the like at module level; on an interpreter without them (the host venv) those are replaced by
empty stand-ins before the import, which changes nothing this script reads.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:  # this checkout's tit, not whichever one is installed
    sys.path.insert(0, str(REPO))
OUT = REPO / "desktop" / "tests" / "fixtures" / "realdata" / "dataset000_catalog.json"
PLACEHOLDER = "/dataset000"
#: Manifest keys the Simulator reads (``flexCurrents``) or a reader needs to tell runs apart.
MANIFEST_KEYS = (
    "goal",
    "current_mA",
    "current_split",
    "optimize_current_ratio",
    "ratio_total_mA",
)


#: Every module the readers below import, including the ones ``tit.catalog`` imports lazily.
_MODULES = ("tit.paths", "tit.sim.utils", "tit.opt.flex.manifest", "tit.catalog")


def _import_all() -> list:
    """Import ``_MODULES``, standing in an empty module for any third-party package missing."""
    for _ in range(64):
        try:
            return [importlib.import_module(m) for m in _MODULES]
        except ModuleNotFoundError as exc:
            missing = exc.name or ""
            if not missing or missing.split(".")[0] == "tit" or missing in sys.modules:
                raise
            parts = missing.split(".")
            for i in range(1, len(parts) + 1):
                sys.modules.setdefault(".".join(parts[:i]), MagicMock())
            for name in [k for k in sys.modules if k == "tit" or k.startswith("tit.")]:
                del sys.modules[name]
    raise ImportError(f"could not import {_MODULES}")


def _relative(value, root: str):
    """*value* with the dataset root replaced by the placeholder, recursively."""
    if isinstance(value, str):
        return value.replace(root, PLACEHOLDER)
    if isinstance(value, list):
        return [_relative(v, root) for v in value]
    if isinstance(value, dict):
        return {k: _relative(v, root) for k, v in value.items()}
    return value


def build(dataset: str) -> dict:
    """The snapshot for the Dataset 000 copy at *dataset* (read-only)."""
    paths, sim_utils, _, catalog = _import_all()
    pm = paths.get_path_manager(dataset)
    root = os.path.realpath(dataset)

    montages = catalog.get_montages(pm)["nets"]
    labels_used: dict[str, set[str]] = {}
    for net, buckets in montages.items():
        for bucket in buckets.values():
            for pairs in bucket.values():
                labels_used.setdefault(net, set()).update(e for p in pairs for e in p)

    subjects: dict[str, dict] = {}
    #: net -> labels, once: every subject carries the same caps, and a cap whose labels differ
    #: between subjects is a finding this snapshot refuses to hide.
    electrodes: dict[str, list[str]] = {}
    for sid in catalog.subject_ids(pm):
        nets = catalog.eeg_nets(pm, sid) or []
        for net in nets:
            if (
                electrodes.setdefault(net["name"], net["electrodes"])
                != net["electrodes"]
            ):
                raise ValueError(f"{net['name']} has different labels for sub-{sid}")
        positions = {}
        for net in nets:
            if net["name"] not in labels_used:
                continue
            path = os.path.join(pm.eeg_positions(sid), net["name"])
            xyz = sim_utils._load_eeg_position_csv(path)
            positions[net["name"]] = {
                label: xyz[label]
                for label in sorted(labels_used[net["name"]])
                if label in xyz
            }
        subjects[sid] = {
            "eeg_nets": [net["name"] for net in nets],
            "montage_electrode_positions": positions,
            "flex_runs": [
                {
                    "name": run["name"],
                    "manifest": {
                        k: run["manifest"][k]
                        for k in MANIFEST_KEYS
                        if k in run["manifest"]
                    },
                    "mappings": [
                        {"eeg_net": m["eeg_net"], "pairs": m["pairs"]}
                        for m in run["mappings"]
                    ],
                    "optimized": run["optimized"],
                }
                for run in catalog.flex_runs(pm, sid) or []
            ],
            "freehand": catalog.freehand_configs(pm, sid) or [],
            "leadfields": [
                {"net": lf["net"], "path": lf["path"], "exists": lf["exists"]}
                for lf in catalog.list_leadfields(pm, sid) or []
            ],
            "simulations": [
                {"name": s["name"], "fields": s.get("fields", [])}
                for s in catalog.list_simulations(pm, sid) or []
            ],
        }
    return _relative(
        {
            "_about": (
                "Dataset 000's catalog as the server answers it, for "
                "desktop/tests/unit/realdata-builders.test.ts. Written by "
                "dev/regen_desktop_realdata_fixture.py; checked current by "
                "tests/test_desktop_realdata_snapshot.py."
            ),
            "electrodes": electrodes,
            "montages": montages,
            "subjects": subjects,
        },
        root,
    )


def render(snapshot: dict) -> str:
    """The snapshot as committed: sorted keys, one level of indentation, trailing newline."""
    return json.dumps(snapshot, indent=1, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--check", action="store_true", help="exit 1 if the committed file differs"
    )
    args = parser.parse_args()
    dataset = os.environ.get("TIT_DATASET_000", "")
    if not os.path.isdir(dataset):
        print("TIT_DATASET_000 must name a Dataset 000 copy", file=sys.stderr)
        return 2
    text = render(build(dataset))
    if args.check:
        current = OUT.read_text() if OUT.is_file() else ""
        if current != text:
            print(f"{OUT.relative_to(REPO)} is stale: rerun without --check")
            return 1
        print(f"{OUT.relative_to(REPO)} is current")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(REPO)} ({len(text)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
