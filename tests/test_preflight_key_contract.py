"""Preflight reads only config keys the runner's own config dataclass has (2026-10-22).

What this pins
    ``tit.jobs.preflight`` receives the raw config dict a job will run with and reads it with
    ``config.get("<key>")``. A key spelled differently from the runner's dataclass field is a
    check that silently never runs (``.get`` returns the default), so every literal key each
    checker in ``_CHECKERS`` reads -- in its own body and in every module-level helper it hands
    ``config`` to -- must be a field of the config class that kind's runner deserializes.

Where the expectations come from
    ``dataclasses.fields()`` of the runner config classes (the independent source), mapped per
    kind as the runners' ``__main__`` modules load them: sim -> SimulationConfig,
    flex* -> FlexConfig, ex -> ExConfig, mex -> MExConfig, leadfield -> LeadfieldConfig,
    analyzer -> AnalyzerConfig, source -> SourceConfig, pre -> PreprocessConfig,
    stats -> GroupComparisonConfig | CorrelationConfig, nifti_average -> NiftiAverageConfig,
    nilearn -> NilearnConfig, blender -> Montage|Vector|Region|SubcorticalConfig. The keys are
    read from preflight's source with ``ast`` (not by calling it), so a checker that is never
    exercised by a test is still covered.

Run: .venv/bin/python -m pytest tests/test_preflight_key_contract.py -q -p no:cacheprovider
"""

from __future__ import annotations

import ast
import dataclasses
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Importing tit.stats.config runs tit/stats/__init__.py -> scipy.ndimage/scipy.stats, which the
# host conftest does not mock (same local fallback as tests/test_plan_routes.py).
for _mod in ("scipy.ndimage", "scipy.stats"):
    sys.modules.setdefault(_mod, MagicMock())

import tit.jobs.preflight as preflight_module  # noqa: E402
from tit.config_io import resolve_config_class  # noqa: E402

RUNNER_CONFIGS: dict[str, tuple[str, ...]] = {
    "sim": ("SimulationConfig",),
    "flex": ("FlexConfig",),
    "flex_adaptive": ("FlexConfig",),
    "flex_pareto": ("FlexConfig",),
    "ex": ("ExConfig",),
    "mex": ("MExConfig",),
    "leadfield": ("LeadfieldConfig",),
    "analyzer": ("AnalyzerConfig",),
    "source": ("SourceConfig",),
    "pre": ("PreprocessConfig",),
    "stats": ("GroupComparisonConfig", "CorrelationConfig"),
    "nifti_average": ("NiftiAverageConfig",),
    "nilearn": ("NilearnConfig",),
    "blender": ("MontageConfig", "VectorConfig", "RegionConfig", "SubcorticalConfig"),
}

SOURCE = Path(preflight_module.__file__).read_text()
TREE = ast.parse(SOURCE)
FUNCTIONS = {n.name: n for n in TREE.body if isinstance(n, ast.FunctionDef)}


def _checkers() -> dict[str, str]:
    """``_CHECKERS``' literal kind -> function name, read from the source."""
    for node in TREE.body:
        target = getattr(node, "target", None) or (
            node.targets[0] if isinstance(node, ast.Assign) else None
        )
        if isinstance(target, ast.Name) and target.id == "_CHECKERS":
            return {
                k.value: v.id
                for k, v in zip(node.value.keys, node.value.values)
                if isinstance(k, ast.Constant) and isinstance(v, ast.Name)
            }
    raise AssertionError("_CHECKERS not found in tit/jobs/preflight.py")


def _keys_read(func: str, receiver: str, seen: set[tuple[str, str]]) -> set[str]:
    """Literal keys *func* reads from the dict named *receiver*, following helper calls."""
    if (func, receiver) in seen or func not in FUNCTIONS:
        return set()
    seen.add((func, receiver))
    keys: set[str] = set()
    node = FUNCTIONS[func]
    params = [a.arg for a in node.args.args]
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            fn = sub.func
            if (
                isinstance(fn, ast.Attribute)
                and fn.attr == "get"
                and isinstance(fn.value, ast.Name)
                and fn.value.id == receiver
                and sub.args
                and isinstance(sub.args[0], ast.Constant)
            ):
                keys.add(sub.args[0].value)
            if isinstance(fn, ast.Name) and fn.id in FUNCTIONS:
                callee_params = [a.arg for a in FUNCTIONS[fn.id].args.args]
                for i, arg in enumerate(sub.args):
                    if isinstance(arg, ast.Name) and arg.id == receiver:
                        keys |= _keys_read(fn.id, callee_params[i], seen)
        elif (
            isinstance(sub, ast.Subscript)
            and isinstance(sub.value, ast.Name)
            and sub.value.id == receiver
            and isinstance(sub.slice, ast.Constant)
        ):
            keys.add(sub.slice.value)
    assert receiver in params or func == "preflight", (func, receiver)
    return keys


def _fields(class_names: tuple[str, ...]) -> set[str]:
    names: set[str] = set()
    for class_name in class_names:
        names |= {f.name for f in dataclasses.fields(resolve_config_class(class_name))}
    return names


def test_every_checker_kind_has_a_runner_config_mapping() -> None:
    checkers = _checkers()
    assert len(checkers) >= 14  # has something to check
    assert set(checkers) == set(RUNNER_CONFIGS)


#: Known divergences outside this package's edit scope (p06 edits only the analyzer checks).
#: The shared ``_subject_ids`` helper reads ``subject_id`` before ``subject_ids``; Preprocess
#: and Source configs have no ``subject_id``, so a stray one in the dict would narrow the
#: preflight sweep to that subject while the runner (which ignores unknown keys) runs them all.
KNOWN_GAPS = {
    "pre": "_subject_ids reads subject_id, which PreprocessConfig has not",
    "source": "_subject_ids reads subject_id, which SourceConfig has not",
}


@pytest.mark.parametrize(
    "kind",
    [
        (
            pytest.param(k, marks=pytest.mark.xfail(strict=True, reason=KNOWN_GAPS[k]))
            if k in KNOWN_GAPS
            else k
        )
        for k in sorted(RUNNER_CONFIGS)
    ],
)
def test_checker_reads_only_runner_config_fields(kind: str) -> None:
    func = _checkers()[kind]
    keys = _keys_read(func, "config", set())
    assert keys, f"{func} reads no config key: the AST walk found nothing to check"
    unknown = sorted(keys - _fields(RUNNER_CONFIGS[kind]))
    assert (
        unknown == []
    ), f"{func} ({kind}) reads {unknown}, which {RUNNER_CONFIGS[kind]} does not define"


def test_the_walk_follows_helpers_into_the_analyzer_subcortical_branch() -> None:
    """Self-test: keys read only inside helpers (two calls deep) are collected."""
    keys = _keys_read("_check_analyzer", "config", set())
    assert {"atlas", "region", "coordinate_space", "field", "tissue_type"} <= keys
    planted = ast.parse(
        "def _check_x(pm, config):\n    return _h(pm, config)\n"
        "def _h(pm, cfg):\n    return cfg.get('not_a_field')\n"
    )
    saved = dict(FUNCTIONS)
    try:
        FUNCTIONS.update({n.name: n for n in planted.body})
        assert _keys_read("_check_x", "config", set()) == {"not_a_field"}
    finally:
        FUNCTIONS.clear()
        FUNCTIONS.update(saved)
