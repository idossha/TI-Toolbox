"""Prepare or run a real, bounded Flex fixture on a copied dataset.

From the repository root (host Python needs only the standard library)::

    python3 tests/smoke/prepare_flex_fixture.py \
      --container ti-toolbox-validation \
      --project-host /Users/idohaber/datasets/ti-toolbox-validation/000 \
      --source-project /Users/idohaber/datasets/000 \
      --run-name smoke-flex-fixture

The default validates inputs and prints the config without writing or solving. Add
``--execute`` only while holding the exclusive heavy-computation slot: the CLI is
outside the job queue, so the idle preflight cannot prevent concurrent submissions.
Population size 1 is a DE dimension multiplier, not a promise of one FEM solve.
This is a selection/mapping fixture, not a scientifically converged optimization.

The existing CLI creates every result. Existing output/config paths are refused;
failures retain their config and output for diagnosis. Nothing is cleaned up.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path, PurePosixPath
import re
import subprocess

PREFLIGHT = """
import json, os, sys
from tests.smoke.client import SmokeClient
from tit.config_io import deserialize_config
from tit.opt.config import FlexConfig
from tit.opt.flex.flex import _validate_flex_inputs
from tit.paths import get_path_manager
config = json.load(sys.stdin)
get_path_manager(config.pop('project_dir'))
_validate_flex_inputs(deserialize_config(FlexConfig, config, strict=True))
jobs = SmokeClient('http://127.0.0.1:8765', os.environ['TIT_SERVER_TOKEN']).jobs()
active = [j['state'] for j in jobs
          if j['state'] not in ('succeeded', 'failed', 'cancelled', 'skipped')]
if active:
    raise RuntimeError('Heavy slot is not idle: ' + repr(active))
print('Real-library input validation passed; server queue idle.')
"""

CATALOG = """
import json, sys
from tit.catalog import flex_runs
from tit.paths import get_path_manager
root, name = sys.argv[1:]
runs = flex_runs(get_path_manager(root), 'ernie') or []
match = [r for r in runs if r['name'] == name]
if len(match) != 1 or len(match[0].get('optimized') or []) != 2:
    raise RuntimeError('Catalog did not expose exactly two optimized pairs')
print(json.dumps({'catalog_name': name, 'catalog_pairs': match[0]['optimized']}))
"""


def verify_result(output: Path) -> dict:
    """Require real success, a finite objective, and four explicitly paired XYZs."""
    manifest = json.loads((output / "flex_meta.json").read_text())
    result = manifest["result"]
    objective = result["best_value"]
    if (
        result["success"] is not True
        or not isinstance(objective, (int, float))
        or not math.isfinite(objective)
    ):
        raise ValueError("Flex did not produce a successful finite objective")
    positions = json.loads((output / "electrode_positions.json").read_text())
    xyz = positions["optimized_positions"]
    channels = positions["channel_array_indices"]
    if len(xyz) != 4 or any(
        len(point) != 3
        or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in point)
        for point in xyz
    ):
        raise ValueError("Expected exactly four finite optimized XYZ positions")
    if len(channels) != 4 or any(len(pair) != 2 for pair in channels):
        raise ValueError("Expected four explicit channel/array indices")
    grouped: dict[int, set[int]] = {}
    for channel, array in channels:
        grouped.setdefault(channel, set()).add(array)
    if len(grouped) != 2 or any(len(arrays) != 2 for arrays in grouped.values()):
        raise ValueError("Expected two channels with two distinct arrays each")
    return {
        "output": str(output),
        "objective": objective,
        "xyz": xyz,
        "channels": channels,
    }


def main() -> None:
    """Validate the copied mount and optionally execute the existing Flex CLI."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--container", required=True)
    parser.add_argument("--project-host", required=True, type=Path)
    parser.add_argument("--source-project", required=True, type=Path)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    project = args.project_host.resolve(strict=True)
    source = args.source_project.resolve(strict=True)
    if (
        not project.is_dir()
        or not source.is_dir()
        or project == source
        or project in source.parents
        or source in project.parents
    ):
        raise ValueError(
            "Source and copied project must be separate, non-nested directories"
        )
    if not re.fullmatch(r"smoke-[A-Za-z0-9_-]+", args.run_name):
        raise ValueError(
            "Use a unique smoke- prefixed run name with letters, digits, underscores or hyphens"
        )
    mounts = json.loads(
        subprocess.check_output(
            ["docker", "inspect", "--format", "{{json .Mounts}}", args.container],
            text=True,
        )
    )
    copies = [
        m
        for m in mounts
        if m["Type"] == "bind" and Path(m["Source"]).resolve() == project and m["RW"]
    ]
    if len(copies) != 1:
        raise ValueError(
            "Container must bind-mount the exact copied project read/write"
        )
    container_root = PurePosixPath(copies[0]["Destination"])
    relative = Path("derivatives/SimNIBS/sub-ernie/flex-search") / args.run_name
    output = project / relative
    config_path = output.with_name(output.name + ".fixture.json")
    if not output.resolve().is_relative_to(
        project
    ) or not config_path.resolve().is_relative_to(project):
        raise ValueError("Output paths escape the copied project through a symlink")
    if (
        output.exists()
        or output.is_symlink()
        or config_path.exists()
        or config_path.is_symlink()
    ):
        raise FileExistsError(f"Refusing existing fixture output/config: {output}")
    config = json.loads(
        Path(__file__).with_name("payloads").joinpath("flex.json").read_text()
    )["config"]
    config.update(
        project_dir=str(container_root),
        output_folder=str(container_root / relative.as_posix()),
        max_iterations=1,
        population_size=1,
        cpus=1,
        n_multistart=1,
        run_final_electrode_simulation=False,
        enable_mapping=False,
    )
    config["roi"]["atlas_path"] = [
        str(
            container_root
            / "derivatives/SimNIBS/sub-ernie/m2m_ernie/segmentation/lh.ernie_DK40.annot"
        )
    ]
    prefix = [
        "docker",
        "exec",
        "-i",
        "-w",
        "/ti-toolbox",
        args.container,
        "simnibs_python",
    ]
    subprocess.run(
        [*prefix, "-c", PREFLIGHT], input=json.dumps(config), text=True, check=True
    )
    if not args.execute:
        print(json.dumps(config, indent=2))
        print("Validated only. Reserve the heavy slot, then repeat with --execute.")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("x") as handle:
        json.dump(config, handle, indent=2)
    print(f"Running real Flex; preserving all outputs at {output}", flush=True)
    subprocess.run(
        [
            *prefix,
            "-m",
            "tit.opt.flex",
            str(container_root / config_path.relative_to(project).as_posix()),
        ],
        check=True,
    )
    print(json.dumps(verify_result(output), indent=2))
    subprocess.run(
        [*prefix, "-c", CATALOG, str(container_root), args.run_name], check=True
    )


if __name__ == "__main__":
    main()
