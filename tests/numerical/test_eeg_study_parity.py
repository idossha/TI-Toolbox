"""2026-09-13: optional frozen-study compatibility under real libraries.

TIT_STUDY_CHECKOUTS=/path/sleepTI:/path/Dose-response_SW_TI python -m pytest
 tests/numerical/test_eeg_study_parity.py -q

The oracle is each checkout's v1.0-preliminary Git tag, never the migrated code.
Only synthetic arrays are used. A clean child avoids host-suite MNE mocks.
No participant data, downloads or hard-coded maintainer paths are required.
"""

import os
from pathlib import Path
import subprocess
import sys
import pytest


def test_frozen_study_arrays_match_migrated_adapters():
    configured = os.environ.get("TIT_STUDY_CHECKOUTS")
    if not configured:
        pytest.skip(
            "set TIT_STUDY_CHECKOUTS to tagged study checkouts for frozen-source compatibility"
        )
    roots = configured.split(os.pathsep)
    if not all(Path(p).is_dir() for p in roots):
        pytest.skip("a TIT_STUDY_CHECKOUTS path is unavailable")
    probe = Path(__file__).with_name("eeg_study_parity_probe.py")
    result = subprocess.run(
        [sys.executable, str(probe), *roots], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    import json

    report = json.loads(result.stdout)
    assert report["passed"] == 18 * len(roots)
    assert not report["dataset_rerun"]
