"""Apptainer launcher argv and generated Slurm licensing, 2026-09-20.

A recording runtime runs generated scripts without Apptainer or a license key.
Run: pytest tests/test_apptainer_license.py -q. Full image build is separate.
"""

import os
from pathlib import Path
import subprocess
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "container/blueprint/apptainer_run.sh"
# HPC images use Bash 4+; macOS /bin/bash 3.2 rejects empty arrays under nounset.
BASH = shutil.which("bash", path="/opt/homebrew/bin:/usr/local/bin") or shutil.which(
    "bash"
)


@pytest.fixture
def runtime(tmp_path):
    executable = tmp_path / "apptainer"
    executable.write_text('#!/bin/bash\nprintf "ARG=%s\\n" "$@"\n')
    executable.chmod(0o755)
    image = tmp_path / "toolbox.sif"
    image.touch()
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
    }
    env.pop("FS_LICENSE", None)
    env.pop("FREESURFER_HOME", None)
    env.update(SLURM_JOB_ID="1", SLURM_CPUS_PER_TASK="1", SLURM_MEM_PER_NODE="1024")
    return tmp_path, image, env


@pytest.mark.parametrize("mode", ["exec", "slurm-template"])
@pytest.mark.parametrize("override", [False, True])
def test_launcher_and_slurm_use_image_license_unless_overridden(
    runtime, mode, override
):
    directory, image, env = runtime
    args = [BASH, str(LAUNCHER), "--sif", str(image), "--mode", mode]
    if mode == "exec":
        args += ["--cmd", "true"]
    if override:
        license_path = directory / "administrator-override.txt"
        license_path.write_text("synthetic override")
        env["FS_LICENSE"] = str(license_path)
    generated = subprocess.run(
        args, env=env, text=True, capture_output=True, check=True
    )
    output = generated.stdout
    if mode == "slurm-template":
        assert "/path/to/license.txt" not in output
        output = subprocess.run(
            [BASH], input=output, env=env, text=True, capture_output=True, check=True
        ).stdout
    arguments = [
        line.removeprefix("ARG=")
        for line in output.splitlines()
        if line.startswith("ARG=")
    ]
    assert arguments[0] == "exec"
    mounts = [
        arg for arg in arguments if ":/usr/local/freesurfer/license.txt:ro" in arg
    ]
    assert mounts == (
        [f"{license_path}:/usr/local/freesurfer/license.txt:ro"] if override else []
    )
    assert "commands will fail" not in output
    assert "Register" not in output


def test_image_provisions_direct_freesurfer_license_from_package(runtime):
    import hashlib

    directory, _, env = runtime
    resources = ROOT / "tit/resources/freesurfer"
    python = directory / "simnibs_python"
    python.write_text(f'#!/bin/bash\nprintf "%s\\n" "{resources}"\n')
    python.chmod(0o755)
    installed = directory / "freesurfer"
    installed.mkdir()
    env["FREESURFER_HOME"] = str(installed)
    definition = (ROOT / "container/blueprint/apptainer.def").read_text()
    start = definition.index("    toolbox_fs_resources=")
    end = definition.index("\n    # =====", start)
    subprocess.run(
        [BASH, "-e"], input=definition[start:end], env=env, text=True, check=True
    )
    assert (
        hashlib.sha256((installed / "license.txt").read_bytes()).digest()
        == hashlib.sha256((resources / "license.txt").read_bytes()).digest()
    )
    assert (installed / "TI-Toolbox-FreeSurfer-TERMS.txt").stat().st_size > 0
    assert (installed / "TI-Toolbox-FreeSurfer-NOTICE.md").stat().st_size > 0
