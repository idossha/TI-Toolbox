"""GPU access requires successful isolated computation, not a host hardware name."""

import subprocess
from unittest.mock import patch

import pytest

from tit.launch import probe_container_gpu


@pytest.mark.parametrize("code,available", [(0, True), (1, False), (125, False)])
def test_probe_checks_computation_and_cleans_up(code, available):
    with patch("tit.launch.subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess(
            [], code, "", "driver unavailable"
        )
        assert probe_container_gpu("local:test", lambda _: None) is available
        argv = run.call_args_list[0].args[0]
        assert argv[argv.index("--gpus") + 1] == "all"
        assert argv[argv.index("--network") + 1] == "none"
        assert "--volume" not in argv
        assert "torch.cuda.synchronize()" in argv[-1]
        assert run.call_args_list[-1].args[0][:3] == ["docker", "rm", "--force"]


def test_probe_timeout_is_cleaned_up_and_reported():
    with patch("tit.launch.subprocess.run") as run:
        run.side_effect = [
            subprocess.TimeoutExpired("docker", 60),
            subprocess.CompletedProcess([], 0),
        ]
        messages = []
        assert not probe_container_gpu("local:test", messages.append)
        assert "CPU remains available" in messages[-1]
        assert run.call_args_list[-1].args[0][:3] == ["docker", "rm", "--force"]
