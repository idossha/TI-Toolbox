"""The committed Dataset 000 catalog snapshot is what the catalog answers today, read read-only.

What this pins: ``desktop/tests/fixtures/realdata/dataset000_catalog.json`` -- the input of
``desktop/tests/unit/realdata-builders.test.ts``, which drives the real desktop builders over
every real montage, flex run, free-hand placement, simulation and leadfield -- equals what
``dev/regen_desktop_realdata_fixture.py`` builds from a Dataset 000 copy right now, and building
it writes nothing into the dataset (every file's and directory's mtime and size are unchanged).

Where the expected values come from: the dataset itself, through ``tit.catalog``'s readers.
Env-gated: set ``TIT_DATASET_000`` to a Dataset 000 copy; without it the test skips with a
reason. Reproduce: ``TIT_DATASET_000=/path/to/000 .venv/bin/python -m pytest
tests/test_desktop_realdata_snapshot.py -q -p no:cacheprovider``. Regenerate: run the dev script.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "dev" / "regen_desktop_realdata_fixture.py"
SNAPSHOT = (
    REPO / "desktop" / "tests" / "fixtures" / "realdata" / "dataset000_catalog.json"
)
DATASET = os.environ.get("TIT_DATASET_000", "")

pytestmark = pytest.mark.skipif(
    not os.path.isdir(DATASET),
    reason="TIT_DATASET_000 is unset or not a directory (Dataset 000 copy)",
)


def _regen_module():
    spec = importlib.util.spec_from_file_location("regen_desktop_realdata", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tree_state(root: str) -> dict[str, tuple[int, int]]:
    """``path -> (mtime_ns, size)`` for every file and directory under *root*."""
    state = {}
    for current, dirs, files in os.walk(root):
        for name in [*dirs, *files]:
            path = os.path.join(current, name)
            st = os.lstat(path)
            state[path] = (st.st_mtime_ns, st.st_size)
    return state


def test_snapshot_is_current_and_building_it_writes_nothing() -> None:
    regen = _regen_module()
    before = _tree_state(DATASET)
    built = regen.render(regen.build(DATASET))
    after = _tree_state(DATASET)
    assert after == before, "building the snapshot changed the dataset"
    assert built == SNAPSHOT.read_text(), (
        f"{SNAPSHOT.relative_to(REPO)} is stale: rerun "
        "dev/regen_desktop_realdata_fixture.py with TIT_DATASET_000 set"
    )


def test_snapshot_covers_every_subject_and_every_cap_of_the_dataset() -> None:
    """Independent of the script: the subjects and caps on disk are the ones in the snapshot."""
    snapshot = json.loads(SNAPSHOT.read_text())
    simnibs = Path(DATASET) / "derivatives" / "SimNIBS"
    on_disk = sorted(
        p.name.removeprefix("sub-")
        for p in simnibs.glob("sub-*")
        if (p / f"m2m_{p.name.removeprefix('sub-')}").is_dir()
    )
    assert sorted(snapshot["subjects"]) == on_disk
    for sid, entry in snapshot["subjects"].items():
        caps_dir = simnibs / f"sub-{sid}" / f"m2m_{sid}" / "eeg_positions"
        caps = sorted(
            p.name
            for p in caps_dir.glob("*.csv")
            if any(
                line.lower().startswith("electrode,")
                for line in p.read_text().splitlines()
            )
        )
        assert sorted(entry["eeg_nets"]) == caps, sid
