"""Write ``tests/fixtures/pre_stages.json``: the server planner's stage columns per flag combination.

For each of the 256 combinations of ``PreprocessConfig``'s eight step flags, the ordered unique
``tags[0]`` of :func:`tit.jobs.plans.plan_preprocessing` for one subject -- the stage ids the
Pre-processing page's plan matrix must show as columns (``plannedStageIds`` in
``desktop/src/renderer/pages/preprocess/index.tsx``). The planner is the source of truth; the
desktop test (``desktop/tests/unit/preprocess-stage-parity.test.ts``) reads this file, and
``tests/test_preprocess_stage_parity.py`` fails when it is stale.

Usage::

    .venv/bin/python dev/gen_pre_stages.py          # rewrite the fixture
    .venv/bin/python dev/gen_pre_stages.py --check  # exit 1 when the fixture is stale
"""

from __future__ import annotations

import importlib.abc
import importlib.util
import itertools
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "pre_stages.json"


class _AbsentLibraryStub(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Empty stand-ins for SimNIBS-era libraries a host venv lacks.

    ``tit.jobs.plans`` imports ``tit.config_io``, whose import chain reaches ``simnibs``; planning
    itself never calls into it, so on a host without SimNIBS the import is satisfied with a stub.
    Only consulted for a top-level package that is not installed.
    """

    def __init__(self, roots: set[str]) -> None:
        self.roots = roots

    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in self.roots:
            return importlib.util.spec_from_loader(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return MagicMock(name=spec.name)

    def exec_module(self, module) -> None:
        return None


def _importable_planner() -> None:
    """Import ``tit`` from this checkout, stubbing heavy libraries the host does not have."""
    sys.path.insert(0, str(REPO))
    missing = {
        root
        for root in ("simnibs", "nibabel", "scipy", "h5py", "matplotlib", "mne")
        if importlib.util.find_spec(root) is None
    }
    if missing:
        sys.meta_path.append(_AbsentLibraryStub(missing))


#: ``PreprocessConfig``'s step flags, in the order the page lists its steps.
FLAGS = (
    "convert_dicom",
    "create_m2m",
    "run_fastsurfer",
    "run_freesurfer",
    "run_tissue_analysis",
    "run_qsiprep",
    "run_qsirecon",
    "extract_dti",
)


def planned_stages(flags: dict[str, bool]) -> list[str]:
    """The ordered unique first tag of every job the planner makes for one subject."""
    from tit.jobs.plans import plan_preprocessing
    from tit.pre.config import PreprocessConfig

    jobs = plan_preprocessing(PreprocessConfig(subject_ids=["s"], **flags), ["s"])
    return list(dict.fromkeys(job.tags[0] for job in jobs))


def build() -> str:
    """The fixture's text: one entry per flag combination, in binary-count order."""
    entries = []
    for values in itertools.product((False, True), repeat=len(FLAGS)):
        flags = dict(zip(FLAGS, values))
        entries.append({"flags": flags, "stages": planned_stages(flags)})
    return json.dumps(entries, indent=1) + "\n"


def main(argv: list[str]) -> int:
    _importable_planner()
    text = build()
    if "--check" in argv:
        if not FIXTURE.exists() or FIXTURE.read_text() != text:
            print(f"{FIXTURE} is stale; run dev/gen_pre_stages.py", file=sys.stderr)
            return 1
        return 0
    FIXTURE.write_text(text)
    print(f"wrote {FIXTURE} ({text.count('flags')} combinations)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
