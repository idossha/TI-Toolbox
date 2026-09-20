#!/usr/bin/env python3
"""Run the local release checks serially; preserve logs and exact candidate identities.

See docs/dev/TESTING.md. This does not publish or replace platform installer acceptance.
"""

import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def run_stage(
    name: str,
    command: list[str],
    directory: Path,
    output: Path,
    env: dict[str, str],
    records: list[dict] | None = None,
) -> dict:
    """Record a command's actual exit code; failures never produce a passed stage."""
    start = time.monotonic()
    print(f"{name}: running (log: {output / (name + '.log')})", flush=True)
    with (output / (name + ".log")).open("w") as log:
        try:
            result = subprocess.run(
                command,
                cwd=directory,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
            code = result.returncode
        except OSError as exc:
            log.write(f"Cannot start stage: {exc}\n")
            code = 127
    record = {
        "stage": name,
        "command": command,
        "exit_code": code,
        "seconds": round(time.monotonic() - start, 2),
    }
    if records is not None:
        records.append(record)
    print(f"{name}: exit {code}", flush=True)
    if code:
        raise subprocess.CalledProcessError(code, command)
    return record


def main() -> int:
    """Execute explicit local fixtures without changing or publishing the candidate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image", required=True, help="Locally available candidate image"
    )
    parser.add_argument(
        "--container",
        required=True,
        help="Existing source-mounted copied-project stack",
    )
    parser.add_argument(
        "--notebook-project",
        required=True,
        type=Path,
        help="Disposable notebook project",
    )
    parser.add_argument(
        "--package", required=True, type=Path, help="Built unpacked installer/app"
    )
    parser.add_argument(
        "--real-spec",
        action="append",
        required=True,
        help="Applicable real E2E spec; repeatable",
    )
    parser.add_argument(
        "--smoke-row",
        action="append",
        required=True,
        help="Applicable full-computation smoke row; repeatable",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="New evidence directory outside tracked source",
    )
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("native quiet-monitor certification currently requires macOS")
    for key in ("TIT_E2E_PROJECT_HOST", "TIT_E2E_SERVER_URL", "TIT_E2E_TOKEN"):
        if not os.environ.get(key):
            parser.error(f"{key} must identify the copied real test project/session")
    if subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    ).strip():
        parser.error(
            "commit candidate changes first; a dirty checkout cannot be a release receipt"
        )
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    image = subprocess.check_output(
        ["docker", "image", "inspect", args.image, "--format", "{{.Id}}"], text=True
    ).strip()
    container = json.loads(
        subprocess.check_output(
            [
                "docker",
                "inspect",
                args.container,
                "--format",
                '{"id":{{json .Id}},"image_id":{{json .Image}},"mounts":{{json .Mounts}}}',
            ],
            text=True,
        )
    )
    mounts = container["mounts"]
    if not any(
        m.get("Destination") == "/ti-toolbox"
        and Path(m.get("Source", "")).resolve() == ROOT
        for m in mounts
    ):
        parser.error("real test container must mount this checkout at /ti-toolbox")
    env = dict(os.environ, TIT_E2E_OFFSCREEN="1", TIT_SMOKE_CONTAINER=container["id"])
    env.pop("VITE_SCENE_HOOKS", None)
    env.pop("VITE_INCLUDE_GALLERY", None)
    mock_env = {
        k: v for k, v in env.items() if k not in ("TIT_E2E_SERVER_URL", "TIT_E2E_TOKEN")
    }
    python = str(ROOT / ".venv/bin/python")
    desktop = ROOT / "desktop"
    stages = [
        (
            "host",
            [python, "-m", "pytest", "tests/", "-q", "--ignore=tests/numerical"],
            ROOT,
            env,
        ),
        ("typecheck", ["npm", "run", "typecheck"], desktop, env),
        ("lint", ["npm", "run", "lint"], desktop, env),
        ("units", ["npx", "vitest", "run"], desktop, env),
        ("documentation", [python, "dev/documentation_policy.py"], ROOT, env),
        ("routes", [python, "dev/route_import_guard.py"], ROOT, env),
        ("contracts", [python, "dev/contracts_check.py"], ROOT, env),
        # A fresh interpreter prevents host mock state from contaminating science tests.
        (
            "numerical",
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "simnibs_python",
                "-v",
                f"{ROOT}:/ti-toolbox:ro",
                "-w",
                "/ti-toolbox",
                image,
                "-m",
                "pytest",
                "tests/numerical",
                "-q",
                "-p",
                "no:cacheprovider",
            ],
            ROOT,
            env,
        ),
        ("mock-e2e", ["npm", "run", "e2e:quiet"], desktop, mock_env),
        (
            "real-e2e",
            [
                "bash",
                "scripts/e2e-quiet-check.sh",
                "npx",
                "playwright",
                "test",
                "--project=real",
                *args.real_spec,
            ],
            desktop,
            env,
        ),
        ("smoke", ["bash", "dev/smoke.sh", "--full", *args.smoke_row], ROOT, env),
        (
            "notebook",
            [
                "bash",
                "dev/run_example_notebook.sh",
                "--image",
                image,
                "--project",
                str(args.notebook_project.resolve()),
                "--out",
                str(output / "notebook"),
            ],
            ROOT,
            env,
        ),
        (
            "package",
            ["node", "scripts/verify-package.mjs", str(args.package.resolve())],
            desktop,
            env,
        ),
    ]
    receipt = {
        "source_sha": source,
        "image_id": image,
        "container": container,
        "real_specs": args.real_spec,
        "smoke_rows": args.smoke_row,
        "status": "failed",
        "stages": [],
    }
    # Same advisory lock used by manual E2E runs; nonblocking avoids an invisible wait.
    with open("/tmp/tit-e2e.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            for name, command, directory, stage_env in stages:
                run_stage(
                    name, command, directory, output, stage_env, receipt["stages"]
                )
            receipt["status"] = "passed"
        except subprocess.CalledProcessError as exc:
            receipt["failed_exit_code"] = exc.returncode
        finally:
            try:
                run_stage(
                    "final-build",
                    ["npm", "run", "build"],
                    desktop,
                    output,
                    env,
                    receipt["stages"],
                )
            except subprocess.CalledProcessError as exc:
                receipt["status"] = "failed"
                receipt["final_build_exit_code"] = exc.returncode
            if (
                subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip()
                != source
                or subprocess.check_output(
                    ["git", "status", "--porcelain"], cwd=ROOT, text=True
                ).strip()
            ):
                receipt["status"] = "failed"
                receipt["source_changed"] = True
            (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
