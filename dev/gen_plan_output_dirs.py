#!/usr/bin/env python3
"""Write tests/fixtures/plan_output_dirs.json: where the REAL server plans each group/export job.

One table, three readers:

* ``tests/test_plan_output_dirs_fixture.py`` regenerates it in-process and fails when the
  committed file no longer matches what ``POST /api/plan/{kind}`` answers (drift guard);
* ``desktop/tests/mock-server/plan-output-dirs.test.ts`` posts the same configs to the mock
  server and asserts the mock plans the same project-relative directory, and that every mock
  job of a kind logs under the Python package that holds that kind's runner;
* ``desktop/tests/unit/visual-exporter-output-hint.test.ts`` asserts the Visual Exporter's
  queued-toast hint names a path under the directory the plan reports for its mode.

Every ``output_dir`` below comes from the real FastAPI route (``tit.server.routes.plan``),
driven through ``fastapi.testclient.TestClient`` against a throwaway project; nothing is
retyped. Paths are stored relative to the project root, and configs that name an absolute
path use the ``{project}`` placeholder so each reader substitutes its own root (the mock's is
``/mnt/example``). ``module_for_kind`` is ``tit.jobs.kinds.MODULE_FOR_KIND``;
``runner_package_for_kind`` is the package that holds that module (the module itself when it is
a package), found with ``importlib.util.find_spec``.

Regenerate: ``.venv/bin/python dev/gen_plan_output_dirs.py`` (from the repository root). The
output is deterministic; ``git diff`` after a run should be empty.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "plan_output_dirs.json"
PLACEHOLDER = "{project}"
TOKEN = "plan-output-dirs"

_PAIR = [{"subject_id": "001", "simulation_name": "Thalamus"}]
_EXPLICIT = PLACEHOLDER + "/derivatives/ti-toolbox/visual_exports/custom/"

#: (id, kind, subject_ids, config). Each case pins one way the mock used to plan elsewhere.
CASES: list[tuple[str, str, list[str], dict[str, Any]]] = [
    (
        "stats_group_comparison",
        "stats",
        [],
        {
            "_type": "GroupComparisonConfig",
            "analysis_name": "p38_compare",
            "subjects": [
                {"subject_id": "001", "simulation_name": "Thalamus", "response": 1},
                {"subject_id": "002", "simulation_name": "Thalamus", "response": 0},
            ],
        },
    ),
    (
        "stats_correlation",
        "stats",
        [],
        {
            "_type": "CorrelationConfig",
            "analysis_name": "p38_correlate",
            "subjects": [
                {
                    "subject_id": "001",
                    "simulation_name": "Thalamus",
                    "effect_size": 0.1,
                },
                {
                    "subject_id": "002",
                    "simulation_name": "Thalamus",
                    "effect_size": 0.4,
                },
                {
                    "subject_id": "003",
                    "simulation_name": "Thalamus",
                    "effect_size": 0.9,
                },
            ],
        },
    ),
    (
        # No ``_type``: the server's default class for ``stats`` decides the folder.
        "stats_untyped",
        "stats",
        [],
        {
            "analysis_name": "p38_untyped",
            "subjects": [
                {"subject_id": "001", "simulation_name": "Thalamus", "response": 1},
                {"subject_id": "002", "simulation_name": "Thalamus", "response": 0},
            ],
        },
    ),
    (
        "nifti_average",
        "nifti_average",
        [],
        {
            "output_name": "p38_average",
            "subjects": [
                {"subject_id": "001", "simulation_name": "Thalamus", "group": "A"},
                {"subject_id": "002", "simulation_name": "Thalamus", "group": "B"},
            ],
        },
    ),
    (
        "nilearn_named",
        "nilearn",
        [],
        {"subject_simulation_pairs": _PAIR, "subdir_name": "p38_glass"},
    ),
    (
        # No ``subdir_name``: NilearnConfig's own default names the folder.
        "nilearn_default_subdir",
        "nilearn",
        [],
        {"subject_simulation_pairs": _PAIR},
    ),
]

_BLENDER = {
    "region_stl": {
        "_type": "RegionConfig",
        "simulation_name": "Thalamus",
        "format": "stl",
    },
    "region_ply": {
        "_type": "RegionConfig",
        "simulation_name": "Thalamus",
        "format": "ply",
    },
    "vector": {"_type": "VectorConfig", "simulation_name": "Thalamus"},
    "montage": {"_type": "MontageConfig", "simulation_name": "Thalamus"},
    "subcortical": {"_type": "SubcorticalConfig"},
    # No ``_type``: the server's default class for ``blender`` decides the folder.
    "untyped": {"simulation_name": "Thalamus"},
}
for _mode, _cfg in _BLENDER.items():
    CASES.append(
        (f"blender_{_mode}", "blender", ["001"], {"subject_id": "001", **_cfg})
    )
for _mode in ("region_stl", "vector", "montage", "subcortical"):
    CASES.append(
        (
            f"blender_{_mode}_explicit_output_dir",
            "blender",
            ["001"],
            {
                "subject_id": "001",
                **_BLENDER[_mode],
                "output_dir": _EXPLICIT + _mode,
            },
        )
    )


def _fill(value: Any, project: str) -> Any:
    """*value* with every ``{project}`` placeholder replaced by *project*."""
    if isinstance(value, str):
        return value.replace(PLACEHOLDER, project)
    if isinstance(value, list):
        return [_fill(v, project) for v in value]
    if isinstance(value, dict):
        return {k: _fill(v, project) for k, v in value.items()}
    return value


def _runner_package(module: str) -> str:
    """The package that holds *module*: itself when it is a package, else its parent."""
    spec = importlib.util.find_spec(module)
    if spec is None:
        raise RuntimeError(f"runner module {module} is not importable")
    if spec.submodule_search_locations is not None:
        return module
    return module.rsplit(".", 1)[0]


def build() -> dict[str, Any]:
    """The fixture's content, computed from the real plan route and the real kinds map."""
    from fastapi.testclient import TestClient

    from tit.jobs.kinds import MODULE_FOR_KIND
    from tit.paths import get_path_manager
    from tit.server.app import create_app
    from tit.server.settings import ServerSettings

    cases = []
    with tempfile.TemporaryDirectory(prefix="tit-plan-dirs-") as tmp:
        project = os.path.realpath(tmp)
        get_path_manager(project)
        Path(project, "dataset_description.json").write_text("{}")
        client = TestClient(
            create_app(ServerSettings(project_dir=project, token=TOKEN)),
            base_url="http://127.0.0.1:8765",
        )
        for case_id, kind, subject_ids, config in CASES:
            response = client.post(
                f"/api/plan/{kind}",
                json={"config": _fill(config, project), "subject_ids": subject_ids},
                headers={"Authorization": f"Bearer {TOKEN}"},
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"{case_id}: HTTP {response.status_code} {response.text}"
                )
            jobs = [
                {
                    "subject": job["subject"],
                    "output_dir": Path(
                        os.path.relpath(job["output_dir"], project)
                    ).as_posix(),
                }
                for job in response.json()["jobs"]
            ]
            cases.append(
                {
                    "id": case_id,
                    "kind": kind,
                    "subject_ids": subject_ids,
                    "config": config,
                    "jobs": jobs,
                }
            )
    return {
        "generated_by": "dev/gen_plan_output_dirs.py",
        "project_placeholder": PLACEHOLDER,
        "cases": cases,
        "module_for_kind": dict(sorted(MODULE_FOR_KIND.items())),
        "runner_package_for_kind": {
            kind: _runner_package(module)
            for kind, module in sorted(MODULE_FOR_KIND.items())
        },
    }


def render(table: dict[str, Any]) -> str:
    """The exact bytes written to :data:`OUT`."""
    return json.dumps(table, indent=1) + "\n"


def _stub_missing_runtime_libraries() -> None:
    """Stub the image-only libraries this host lacks, exactly as the host suite does.

    The plan routes import SimNIBS, matplotlib and friends transitively but never call them for
    these kinds. The package list is ``_MOCK_PACKAGES`` from ``tests/conftest.py``, read with
    ``ast`` rather than copied; a top-level package that is installed is left alone, so inside
    the image every real library loads.
    """
    import ast
    from unittest.mock import MagicMock

    tree = ast.parse((ROOT / "tests" / "conftest.py").read_text())
    names: list[str] = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", "") == "_MOCK_PACKAGES" for t in node.targets)
    )
    missing = {
        n.split(".")[0]
        for n in names
        if n.split(".")[0] not in sys.modules
        and importlib.util.find_spec(n.split(".")[0]) is None
    }
    for name in names:
        parts = name.split(".")
        if parts[0] not in missing:
            continue
        for depth in range(1, len(parts) + 1):
            stub = sys.modules.setdefault(".".join(parts[:depth]), MagicMock())
            if depth > 1:
                parent = sys.modules[".".join(parts[: depth - 1])]
                setattr(parent, parts[depth - 1], stub)


def main() -> int:
    sys.path.insert(0, str(ROOT))
    _stub_missing_runtime_libraries()
    OUT.write_text(render(build()))
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
