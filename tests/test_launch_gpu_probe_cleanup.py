"""The Python launcher's GPU probe keeps its verdict when removing the probe container fails.

Same defect class as the desktop's ``probeContainerGpu`` (desktop/tests/unit/gpu.test.ts): the GPU
is optional ("CPU remains available"), so a ``docker rm --force`` that times out or cannot run must
not replace the probe's answer with an exception and abort ``tit launch``. No Docker: the
``subprocess.run`` boundary is replaced by an authored sequence of results (2026-10-22).
Run: python -m pytest tests/test_launch_gpu_probe_cleanup.py -q
"""

import subprocess
from unittest.mock import patch

import pytest

from tit.launch import probe_container_gpu

CLEANUP_FAILURES = [
    subprocess.TimeoutExpired(["docker", "rm", "--force", "ti-gpu-probe-x"], 15),
    FileNotFoundError(2, "No such file or directory", "docker"),
]


@pytest.mark.parametrize("cleanup_error", CLEANUP_FAILURES, ids=["timeout", "oserror"])
@pytest.mark.parametrize("code,available", [(0, True), (1, False)])
def test_failed_cleanup_keeps_the_probe_verdict(code, available, cleanup_error):
    with patch("tit.launch.subprocess.run") as run:
        run.side_effect = [
            subprocess.CompletedProcess([], code, "", "no CUDA-capable device"),
            cleanup_error,
        ]
        messages: list[str] = []
        assert probe_container_gpu("local:test", messages.append) is available
    assert [call.args[0][:3] for call in run.call_args_list] == [
        ["docker", "run", "--name"],
        ["docker", "rm", "--force"],
    ]
    probe_name = run.call_args_list[0].args[0][3]
    warnings = [m for m in messages if m.startswith("Warning:")]
    assert len(warnings) == 1
    assert probe_name in warnings[0] and str(cleanup_error) in warnings[0]
    # The verdict line is still the one the probe earned (the warning may come before or after it).
    (verdict,) = [m for m in messages if not m.startswith("Warning:")]
    if available:
        assert verdict == "CUDA GPU verified; GPU access enabled for FastSurfer."
    else:
        assert verdict.startswith("Container GPU unavailable (no CUDA-capable device)")


def test_successful_cleanup_prints_no_warning():
    with patch("tit.launch.subprocess.run") as run:
        run.side_effect = [
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 0, "", ""),
        ]
        messages: list[str] = []
        assert probe_container_gpu("local:test", messages.append) is True
    assert not [m for m in messages if m.startswith("Warning:")]
