"""Dead Python stays dead, ``tit.jobs`` grows no orphan module, and ``tit.stats`` docstrings cite real names.

What this pins (2026-10-22, the p43 dead-code sweep):

* The helpers that sweep deleted (each had no caller in tit, dev, desktop, agent-plugin,
  docs/wiki, examples or loader.*) -- and the uncalled server routes and helpers the 2026-10-26
  pass deleted -- are not defined again in their modules, and their distinctive names do not
  reappear in shipped code or user docs.
* Every module under ``tit/jobs/`` is imported by another module in ``tit/`` -- the check that
  would have caught ``tit/jobs/client.py``, a notebook client nothing ever imported.
* Every ``tit.<module>[.<name>]`` that a ``tit/stats`` docstring cites resolves to a module file
  and a name bound in it (``tit/stats/nifti.py`` used to cite ``tit.stats.comparison``).
* Behaviour the sweep kept on purpose: ``load_montages`` still accepts ``include_flex`` but no
  longer appends montages from ``$FLEX_MONTAGES_FILE``; an old simulation ``config.json`` with
  ``map_to_vol``/``tissues_in_niftis``/``open_in_gmsh`` still loads with those values; the
  analyzer's legacy-layout fallback says so in the job log.

Where the expected values come from: the source tree read off disk (``ast``), never imported for
the structural checks; the behaviour checks use inputs written here. Each checker is also driven
red on a planted violation in ``tmp_path``.

Reproduce: ``.venv/bin/python -m pytest tests/test_stale_python_guard.py -q``.
Deliberately elsewhere: the desktop comments and PARITY.md files that still cite
``build_simulation_config_for_job`` / ``get_selectable_output_field_specs`` (p46 owns them), so
``desktop/`` is not scanned for those names.
"""

from __future__ import annotations

import ast
import json
import logging
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------------------------
# 1. Deleted helpers stay deleted
# ---------------------------------------------------------------------------------------------

#: module file -> top-level names deleted from it (``Class.method`` for a method).
DELETED_DEFINITIONS: dict[str, tuple[str, ...]] = {
    "tit/sim/utils.py": (
        "ensure_eeg_net_entry",
        "load_flex_montages",
        "parse_flex_montage",
        "transform_to_nifti",
        "convert_t1_to_mni",
        "build_simulation_config_for_job",
    ),
    "tit/constants.py": (
        "ENV_FLEX_MONTAGES_FILE",
        "TISSUE_PROPERTIES",
        "EEG_NETS",
        "VALIDATION_BOUNDS",
        "DEFAULT_ELECTRODE",
        "DEFAULT_OPTIMIZATION",
        "DEFAULT_STATISTICS",
        "DEFAULT_PERCENTILES",
        "DEFAULT_FOCALITY_CUTOFFS",
        "VERSION_FILE",
        "get_fields_by_kind",
        "output_fields_help_text",
        "get_selectable_output_field_specs",
        "GM_TISSUE_TAG",
        "TELEMETRY_CONFIG_DIR",
    ),
    "tit/paths.py": (
        "mask_cache_dir_for",
        "PathManager.stats_data",
        "PathManager.cache_root",
        "PathManager.scene_cache",
        "PathManager.mask_cache",
    ),
    "tit/opt/ex/logic.py": ("generate_montage_combinations",),
    "tit/tools/electrode_overlay.py": (
        "simulation_config_has_xyz_electrodes",
        "_extract_xyz_positions",
    ),
    "tit/launch.py": ("run",),
    "tit/jobs/api.py": ("get_status",),
    "tit/jobs/spec.py": ("LockConflict", "EVENT_TYPES"),
    "tit/jobs/docker_engine.py": (
        "LogFrameDecoder",
        "NdjsonDecoder",
        "ContainerCreateSpec",
        "run_job_container",
        "run_qsiprep_example",
        "DockerEngineClient.pull_image",
        "DockerEngineClient.create_container",
        "DockerEngineClient.start_container",
        "DockerEngineClient.wait_container",
        "DockerEngineClient.kill_container",
        "DockerEngineClient.remove_container",
        "DockerEngineClient.logs",
        "DockerEngineClient.events",
        "DockerEngineClient.ping",
        "DockerEngineClient.info",
    ),
    "tit/pre/qsi/dti_extractor.py": ("check_dti_tensor_exists",),
    "tit/pre/qsi/qsirecon.py": ("list_available_recon_specs", "list_available_atlases"),
    # 2026-10-26 server dead-code pass: routes no client called, and their only helpers.
    "tit/server/routes/viewers.py": (
        "view_args",
        "_jail_viewspec_layers",
        "_reject_option_like_args",
        "viewer_preset_dir",
        "_preset_slug",
        "_PRESET_SUFFIX",
        "viewer_presets",
        "save_viewer_preset",
        "delete_viewer_preset",
    ),
    "tit/server/routes/viewer_library.py": (
        "composition_dir",
        "_COMPOSITION_SUFFIX",
        "list_compositions",
        "save_composition",
        "delete_composition",
    ),
    "tit/server/routes/catalog_v1.py": (
        "electrode_overlays",
        "ex_run_results",
        "subject_info",
    ),
    "tit/catalog.py": ("electrode_overlays", "ex_run_results", "subject_info_matrix"),
    "tit/server/routes/jobs.py": ("rerun_job",),
    "tit/jobs/manager.py": ("JobManager.rerun",),
    "tit/server/routes/scene.py": ("volume_legend",),
    "tit/scene/build.py": ("volume_legend",),
    "tit/server/routes/files.py": ("csv_file",),
    "tit/server/routes/schema.py": ("schema_by_name",),
    "tit/jobs/runner.py": ("ENV_LOCK_KEYS",),
    "tit/jobs/tailer.py": ("line_count",),
    "tit/scene/guide.py": ("part_ids", "atlas_ids", "net_names", "iter_assets"),
    "tit/server/routes/kernels.py": ("_project_root",),
    "tit/blender/io.py": ("deduplicate_vertices",),
    "tit/pre/qsi/docker_builder.py": ("DockerCommandBuilder.get_output_dir",),
    "tit/pre/qsi/config.py": (
        "ReconSpec.from_string",
        "ReconSpec.list_all",
        "QSIAtlas.from_string",
        "QSIAtlas.list_all",
    ),
    "tit/figures/roi_plate.py": ("Region.span_mm",),
    "tit/atlas/constants.py": ("LEGACY_FREESURFER_ATLAS_FILES",),
    # 2026-10-26 envelope API: tit.calc is exactly five functions; tit.fields folded in.
    "tit/calc.py": (
        "get_TI_vectors",
        "get_TI_avg",
        "get_TI_dir",
        "hf_rms",
        "hf_peak_is_exact",
        "EXACT_SIGN_ENUM_MAX_FIELDS",
        "_mti_modulation_depth",
        "_fibonacci_sphere",
        "_pairwise_products",
        "_envelope_from_PQ",
        "_fused_sweep_kernel",
    ),
}

DELETED_FILES = (
    "tit/jobs/client.py",
    "tit/analyzer/spheres.py",
    "tit/stats/visualization.py",
    "tit/stats/example_subjects.csv",
    "tit/stats/example_subjects_continuous.csv",
    "tit/blender/helpers/extract_metadata.py",
    "tit/blender/helpers/inspect_blend.py",
    "tit/blender/helpers/render_blend.sh",
    "tit/blender/helpers/install_blender_docker.sh",
    "tit/fields.py",
    "tit/_mti_kernel.py",
)

#: Names distinctive enough to grep for anywhere in shipped code and user docs.
DISTINCTIVE_NAMES = (
    "ensure_eeg_net_entry",
    "load_flex_montages",
    "parse_flex_montage",
    "FLEX_MONTAGES_FILE",
    "transform_to_nifti",
    "convert_t1_to_mni",
    "build_simulation_config_for_job",
    "get_selectable_output_field_specs",
    "output_fields_help_text",
    "simulation_config_has_xyz_electrodes",
    "parse_sphere_row",
    "parse_sphere_rows",
    "check_dti_tensor_exists",
    "list_available_recon_specs",
    "run_qsiprep_example",
    "run_job_container",
    "JobClientError",
    "resume_session",
    "subject_info_matrix",
    "ex_run_results",
    "viewer_preset_dir",
    "_jail_viewspec_layers",
    "_reject_option_like_args",
    "msh2cortex_path",
    "ENV_LOCK_KEYS",
    "iter_assets",
    "deduplicate_vertices",
    "LEGACY_FREESURFER_ATLAS_FILES",
    # the pre-2026-10-26 envelope API (tit.calc is five functions; tit.fields folded in)
    "get_TI_vectors",
    "get_TI_avg",
    "get_TI_dir",
    "hf_peak_is_exact",
    "EXACT_SIGN_ENUM_MAX_FIELDS",
    "TIT_MTI_KERNEL",
    "_mti_kernel",
    "tit.fields",
    "tit/fields",
)

#: Shipped code and user-facing docs (desktop is p46's; tests would self-match).
SCANNED = (
    "tit",
    "dev",
    "agent-plugin",
    "examples",
    "docs/wiki",
    "container",
    "loader.sh",
    "loader.py",
)
SCANNED_SUFFIXES = {
    ".py",
    ".md",
    ".sh",
    ".ipynb",
    ".json",
    ".toml",
    ".yml",
    ".yaml",
    ".txt",
}


def defined_names(source: str) -> set[str]:
    """Top-level names bound in *source*, plus ``Class.method`` for every method."""
    names: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        names.add(f"{node.name}.{item.name}")
        elif isinstance(node, ast.Assign):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def resurrected(root: Path, table: dict[str, tuple[str, ...]]) -> list[str]:
    """``path: name`` for every deleted name that *root*'s module defines again."""
    found = []
    for rel, names in table.items():
        bound = defined_names((root / rel).read_text(encoding="utf-8"))
        found += [f"{rel}: {name}" for name in names if name in bound]
    return found


def mentions(
    root: Path, names: tuple[str, ...], scanned: tuple[str, ...] = SCANNED
) -> list[str]:
    """``path:line: name`` for every word-boundary mention of *names* under *scanned*."""
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b")
    hits = []
    for entry in scanned:
        base = root / entry
        files = (
            [base]
            if base.is_file()
            else sorted(base.rglob("*")) if base.is_dir() else []
        )
        for path in files:
            if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for number, line in enumerate(text.splitlines(), 1):
                for match in pattern.finditer(line):
                    hits.append(f"{path.relative_to(root)}:{number}: {match.group(1)}")
    return hits


def test_deleted_helpers_are_not_defined_again():
    assert sum(map(len, DELETED_DEFINITIONS.values())) >= 40
    assert resurrected(REPO, DELETED_DEFINITIONS) == []


def test_deleted_files_stay_deleted():
    assert [rel for rel in DELETED_FILES if (REPO / rel).exists()] == []


def test_deleted_names_are_not_mentioned_in_shipped_code_or_user_docs():
    scanned = [entry for entry in SCANNED if (REPO / entry).exists()]
    assert len(scanned) >= 6, scanned
    assert mentions(REPO, DISTINCTIVE_NAMES) == []


def test_the_checkers_find_a_planted_resurrection(tmp_path):
    module = tmp_path / "tit" / "jobs" / "docker_engine.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "class DockerEngineClient:\n"
        "    def version(self):\n        return {}\n"
        "    def pull_image(self, image):\n        return None\n"
        "def discover():\n    return None\n"
    )
    table = {
        "tit/jobs/docker_engine.py": (
            "DockerEngineClient.pull_image",
            "discover",
            "run_job_container",
        )
    }
    assert resurrected(tmp_path, table) == [
        "tit/jobs/docker_engine.py: DockerEngineClient.pull_image",
        "tit/jobs/docker_engine.py: discover",
    ]
    (tmp_path / "docs" / "wiki").mkdir(parents=True)
    (tmp_path / "docs" / "wiki" / "scripting.md").write_text(
        "use\nload_flex_montages(path)\n"
    )
    assert mentions(tmp_path, ("load_flex_montages",), ("docs/wiki",)) == [
        "docs/wiki/scripting.md:2: load_flex_montages"
    ]


# ---------------------------------------------------------------------------------------------
# 2. No orphan module under tit/jobs/
# ---------------------------------------------------------------------------------------------


def _module_name(root: Path, path: Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def imported_modules(root: Path, path: Path) -> set[str]:
    """Every absolute module name *path* imports (relative imports resolved, ``from a import b``
    counted as both ``a`` and ``a.b``)."""
    name = _module_name(root, path)
    package = name if path.name == "__init__.py" else name.rpartition(".")[0]
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                anchor = package.split(".")[
                    : len(package.split(".")) - (node.level - 1)
                ]
                base = ".".join(anchor + ([node.module] if node.module else []))
            found.add(base)
            found |= {f"{base}.{alias.name}" for alias in node.names}
    return found


def orphaned_jobs_modules(root: Path) -> tuple[int, list[str]]:
    """``(modules checked, modules under tit/jobs no other tit module imports)``."""
    jobs = sorted(
        p.stem for p in (root / "tit" / "jobs").glob("*.py") if p.stem != "__init__"
    )
    importers: dict[str, set[str]] = {stem: set() for stem in jobs}
    for path in (root / "tit").rglob("*.py"):
        importer = _module_name(root, path)
        for module in imported_modules(root, path):
            parts = module.split(".")
            if (
                parts[:2] == ["tit", "jobs"]
                and len(parts) > 2
                and parts[2] in importers
            ):
                if importer != f"tit.jobs.{parts[2]}":
                    importers[parts[2]].add(importer)
    return len(jobs), [stem for stem in jobs if not importers[stem]]


def test_every_jobs_module_is_imported_by_another_tit_module():
    checked, orphans = orphaned_jobs_modules(REPO)
    assert checked >= 15, f"only {checked} tit/jobs modules found"
    assert orphans == []


def test_the_orphan_check_finds_a_module_nothing_imports(tmp_path):
    jobs = tmp_path / "tit" / "jobs"
    jobs.mkdir(parents=True)
    (tmp_path / "tit" / "__init__.py").write_text("")
    (jobs / "__init__.py").write_text("")
    (jobs / "manager.py").write_text("from . import spec\nfrom .events import emit\n")
    (jobs / "spec.py").write_text("X = 1\n")
    (jobs / "events.py").write_text("def emit():\n    pass\n")
    (jobs / "client.py").write_text("import json\n")
    (jobs / "self_only.py").write_text("from tit.jobs import self_only\n")
    (tmp_path / "tit" / "server.py").write_text("import tit.jobs.manager\n")
    assert orphaned_jobs_modules(tmp_path) == (5, ["client", "self_only"])


# ---------------------------------------------------------------------------------------------
# 3. tit/stats docstrings cite names that exist
# ---------------------------------------------------------------------------------------------

_REF = re.compile(r"(?<![\w.])tit(?:\.[A-Za-z_]\w*)+")


def _bindings(tree: ast.Module) -> dict[str, ast.AST]:
    bound: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound[node.name] = node
        elif isinstance(node, ast.Assign):
            bound.update({t.id: node for t in node.targets if isinstance(t, ast.Name)})
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            bound[node.target.id] = node
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound[(alias.asname or alias.name).split(".")[0]] = node
        elif isinstance(node, (ast.If, ast.Try)):
            bound.update(_bindings(ast.Module(body=node.body, type_ignores=[])))
    return bound


def resolves(root: Path, reference: str) -> bool:
    """Whether ``tit.a.b[.name[.attr]]`` names a module file under *root* and a name bound in it.

    The longest dotted prefix that is a module file wins; the next part must be bound at the
    module's top level (def, class, assignment or import); a part after a class must be bound
    in the class body. Past an import, or two levels into a class, the rest is not followed.
    """
    parts = reference.split(".")
    for cut in range(len(parts), 0, -1):
        base = root.joinpath(*parts[:cut])
        for candidate in (base.with_suffix(".py"), base / "__init__.py"):
            if candidate.is_file():
                rest = parts[cut:]
                if not rest:
                    return True
                bound = _bindings(ast.parse(candidate.read_text(encoding="utf-8")))
                node = bound.get(rest[0])
                if node is None:
                    return False
                if len(rest) > 1 and isinstance(node, ast.ClassDef):
                    members = _bindings(ast.Module(body=node.body, type_ignores=[]))
                    return rest[1] in members
                return True
    return False


def unresolved_doc_refs(root: Path, package: str) -> tuple[int, list[str]]:
    """``(references checked, "file: reference" for each that does not resolve)``."""
    refs: set[tuple[str, str]] = set()
    for path in sorted((root / package).glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(
                node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                doc = ast.get_docstring(node, clean=False) or ""
                refs |= {(path.name, ref) for ref in _REF.findall(doc)}
    bad = sorted(f"{name}: {ref}" for name, ref in refs if not resolves(root, ref))
    return len(refs), bad


def test_every_module_a_stats_docstring_cites_exists():
    checked, bad = unresolved_doc_refs(REPO, "tit/stats")
    assert (
        checked >= 10
    ), f"only {checked} tit.* references found in tit/stats docstrings"
    assert bad == []


def test_the_docstring_check_flags_a_planted_bad_reference(tmp_path):
    stats = tmp_path / "tit" / "stats"
    stats.mkdir(parents=True)
    (tmp_path / "tit" / "__init__.py").write_text("")
    (stats / "__init__.py").write_text(
        "from .permutation import run_group_comparison\n"
    )
    (stats / "permutation.py").write_text(
        '"""See Also\n--------\ntit.stats.permutation.run_group_comparison : ok.\n"""\n'
        "class Engine:\n    def run(self):\n        pass\n"
        "def run_group_comparison():\n    pass\n"
    )
    (stats / "nifti.py").write_text(
        '"""See Also\n--------\ntit.stats.comparison : gone.\n'
        "tit.stats.run_group_comparison : re-exported.\n"
        "tit.stats.permutation.Engine.run : a method.\n"
        'tit.stats.permutation.Engine.walk : no such method.\n"""\n'
    )
    assert unresolved_doc_refs(tmp_path, "tit/stats") == (
        5,
        [
            "nifti.py: tit.stats.comparison",
            "nifti.py: tit.stats.permutation.Engine.walk",
        ],
    )


# ---------------------------------------------------------------------------------------------
# 4. What the sweep kept on purpose still behaves
# ---------------------------------------------------------------------------------------------


@pytest.mark.unit
def test_load_montages_accepts_include_flex_and_appends_nothing_from_the_env(
    tmp_project, init_pm, tmp_path, monkeypatch
):
    """Seeded notebooks pass include_flex; the env-var loader it once switched on is gone."""
    from tit.sim.utils import load_montages, upsert_montage

    upsert_montage(
        eeg_net="GSN-256.csv",
        montage_name="m1",
        electrode_pairs=[["E1", "E2"], ["E3", "E4"]],
        mode="U",
    )
    flex_file = tmp_path / "flex.json"
    flex_file.write_text(
        json.dumps(
            [
                {
                    "name": "stray",
                    "type": "flex_mapped",
                    "pairs": [["E5", "E6"], ["E7", "E8"]],
                }
            ]
        )
    )
    monkeypatch.setenv("FLEX_MONTAGES_FILE", str(flex_file))

    for kwargs in ({}, {"include_flex": True}, {"include_flex": False}):
        montages = load_montages(["m1"], "GSN-256.csv", **kwargs)
        assert [(m.name, m.electrode_pairs) for m in montages] == [
            ("m1", [["E1", "E2"], ["E3", "E4"]])
        ], kwargs


@pytest.mark.unit
def test_an_old_simulation_config_with_the_unused_fields_still_loads():
    """map_to_vol / tissues_in_niftis / open_in_gmsh change nothing but must still deserialise."""
    from tit.config_io import deserialize_config, serialize_config
    from tit.sim.config import SimulationConfig

    old = {
        "subject_id": "ernie",
        "montages": [
            {
                "name": "L_Insula",
                "mode": "net",
                "electrode_pairs": [["E010", "E011"], ["E012", "E013"]],
                "eeg_net": "GSN-HydroCel-185.csv",
            }
        ],
        "map_to_vol": True,
        "tissues_in_niftis": "1,2",
        "open_in_gmsh": False,
    }
    config = deserialize_config(SimulationConfig, old)
    assert (config.map_to_vol, config.tissues_in_niftis, config.open_in_gmsh) == (
        True,
        "1,2",
        False,
    )
    again = serialize_config(config)
    assert (again["map_to_vol"], again["tissues_in_niftis"], again["open_in_gmsh"]) == (
        True,
        "1,2",
        False,
    )
    assert deserialize_config(SimulationConfig, again) == config


@pytest.mark.unit
def test_the_analyzer_legacy_fallback_is_logged_as_a_warning(caplog):
    from tit.analyzer.__main__ import _build_config

    data = {
        "mode": "single",
        "subject_id": "001",
        "simulation": "L_Insula",
        "space": "mesh",
        "analysis_type": "spherical",
        "center": [-31.0, 3.5, 2.0],
        "radius": 5.0,
        "subject_ids": "001",  # text, not an array: the typed path refuses it
    }
    with caplog.at_level(logging.WARNING, logger="tit.analyzer"):
        config = _build_config(data)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "legacy dict layout" in warnings[0].getMessage()
    assert "subject_ids" in warnings[0].getMessage()
    assert (config.subject_id, config.center, config.radius) == (
        "001",
        [-31.0, 3.5, 2.0],
        5.0,
    )
