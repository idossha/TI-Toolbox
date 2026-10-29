"""Guards over the config registry: unions are tagged, ambiguous kinds match their runners,
and the run pages' defaults are fields the classes still have.

What this pins (2026-10-22)
    1. Every ``Union`` of two or more dataclasses reachable from a class in
       :data:`tit.config_io.CONFIG_CLASS_REGISTRY` has a non-None, pairwise-distinct ``_type``
       tag per branch (:func:`tit.config_io._discriminator_for`). Without one,
       ``deserialize_config`` cannot tell the branches apart and a config the app wrote reads
       back as the wrong class (or not at all).
    2. The server's table of ambiguous kinds (:mod:`tit.server.routes.validate`) names exactly
       the classes the runners dispatch on: ``stats`` = ``tit.stats.__main__.MODE_FOR_TYPE``
       (and its ``mode`` table is that one read backwards), ``blender`` = the keys of the
       ``dispatch`` dict in ``tit.blender.__main__.main``, read off the source with ``ast``.
    3. Every kind in :data:`tit.server.app_defaults.APP_DEFAULTS` deserialises *strictly* into
       its class once the fields the class requires are added, so renaming a field cannot
       silently turn an agent's default into an ignored key.

    Each guard is a pure function over a class, a table or a source string; a planted
    violation drives each one red below.

Where the expectations come from
    The runners' own tables (read from their modules or source), the registry itself, and
    authored minimal configs (the fields each class's ``__init__`` requires, nothing else).

Run: .venv/bin/python -m pytest tests/test_config_registry_guards.py -q -p no:cacheprovider
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import types
import typing
from pathlib import Path

import pytest

from tit import config_io
from tit.config_io import (
    CONFIG_CLASS_REGISTRY,
    deserialize_config,
    resolve_config_class,
)

REPO = Path(__file__).resolve().parents[1]
_UNION_ORIGINS = (typing.Union, types.UnionType)


# ---------------------------------------------------------------------------------------------
# Guard 1: every union of dataclasses carries distinct _type tags
# ---------------------------------------------------------------------------------------------


def _is_dataclass_type(tp) -> bool:
    return isinstance(tp, type) and dataclasses.is_dataclass(tp)


def union_tag_report(root: type) -> tuple[list[str], list[str]]:
    """(unions checked, violations) for every dataclass union reachable from *root*.

    Walks each dataclass's resolved field types (``typing.get_type_hints``) through unions,
    lists, tuples and dicts into nested dataclasses, each class once.
    """
    checked: list[str] = []
    violations: list[str] = []
    seen: set[type] = set()

    def visit_type(tp, where: str) -> None:
        origin = typing.get_origin(tp)
        args = typing.get_args(tp)
        if origin in _UNION_ORIGINS:
            branches = [a for a in args if _is_dataclass_type(a)]
            if len(branches) >= 2:
                tags = [config_io._discriminator_for(b) for b in branches]
                checked.append(where)
                names = [b.__qualname__ for b in branches]
                if any(t is None for t in tags):
                    untagged = [n for n, t in zip(names, tags) if t is None]
                    violations.append(f"{where}: untagged branch(es) {untagged}")
                elif len(set(tags)) != len(tags):
                    violations.append(f"{where}: duplicate tags {tags} for {names}")
        for arg in args:
            visit_type(arg, where)
        if _is_dataclass_type(tp):
            visit_class(tp)

    def visit_class(cls: type) -> None:
        if cls in seen:
            return
        seen.add(cls)
        for name, tp in typing.get_type_hints(cls).items():
            if name in {f.name for f in dataclasses.fields(cls)}:
                visit_type(tp, f"{cls.__qualname__}.{name}")

    visit_class(root)
    return checked, violations


def test_every_registered_union_has_distinct_type_tags() -> None:
    checked: set[str] = set()
    violations: list[str] = []
    for name in sorted(CONFIG_CLASS_REGISTRY):
        found, bad = union_tag_report(resolve_config_class(name))
        checked.update(found)
        violations.extend(bad)
    # Has unions to check: the four the registry carries today (2026-10-22), at least.
    assert {
        "FlexConfig.roi",
        "FlexConfig.non_roi",
        "ExConfig.electrodes",
        "MExConfig.electrodes",
    } <= checked
    assert violations == []


@dataclasses.dataclass
class _PlantedA:
    a: int = 0


@dataclasses.dataclass
class _PlantedB:
    b: int = 0


@dataclasses.dataclass
class _PlantedHolder:
    pick: _PlantedA | _PlantedB | None = None
    many: list[_PlantedA | _PlantedB] = dataclasses.field(default_factory=list)


def test_union_guard_flags_an_untagged_union() -> None:
    checked, violations = union_tag_report(_PlantedHolder)
    assert checked == ["_PlantedHolder.pick", "_PlantedHolder.many"]
    assert len(violations) == 2
    assert all("untagged" in v for v in violations)


def test_union_guard_flags_two_branches_sharing_a_tag(monkeypatch) -> None:
    monkeypatch.setitem(config_io._TYPE_DISCRIMINATED, _PlantedA, "Shared")
    monkeypatch.setitem(config_io._TYPE_DISCRIMINATED, _PlantedB, "Shared")
    _, violations = union_tag_report(_PlantedHolder)
    assert violations and all("duplicate tags" in v for v in violations)


# ---------------------------------------------------------------------------------------------
# Guard 2: the server's ambiguous-kind tables are the runners' own dispatch tables
# ---------------------------------------------------------------------------------------------


def dispatch_keys_in_source(source: str, function: str = "main") -> set[str]:
    """String keys of the ``dispatch = {...}`` dict assigned inside *function* in *source*."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function:
            for stmt in ast.walk(node):
                if (
                    isinstance(stmt, ast.Assign)
                    and any(
                        isinstance(t, ast.Name) and t.id == "dispatch"
                        for t in stmt.targets
                    )
                    and isinstance(stmt.value, ast.Dict)
                ):
                    return {
                        k.value
                        for k in stmt.value.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)
                    }
    return set()


def table_mismatch(server: set[str], runner: set[str]) -> list[str]:
    """What one side names and the other does not, in words; empty when they agree."""
    out = [f"server only: {sorted(server - runner)}"] if server - runner else []
    if runner - server:
        out.append(f"runner only: {sorted(runner - server)}")
    return out


def test_stats_tables_are_the_runners_mode_table() -> None:
    from tit.server.routes.validate import AMBIGUOUS_KIND_CLASSES, STATS_MODE_CLASSES
    from tit.stats.__main__ import MODE_FOR_TYPE

    assert MODE_FOR_TYPE  # has entries to compare
    assert (
        table_mismatch(set(AMBIGUOUS_KIND_CLASSES["stats"]), set(MODE_FOR_TYPE)) == []
    )
    # The server's mode table is the runner's _type -> mode table read backwards.
    assert STATS_MODE_CLASSES == {mode: t for t, mode in MODE_FOR_TYPE.items()}
    # And each tag names the registry class of that name.
    for tag, registry_key in AMBIGUOUS_KIND_CLASSES["stats"].items():
        assert resolve_config_class(registry_key).__name__ == tag


def test_blender_table_is_the_runners_dispatch() -> None:
    from tit.server.routes.validate import AMBIGUOUS_KIND_CLASSES

    source = (REPO / "tit" / "blender" / "__main__.py").read_text()
    runner = dispatch_keys_in_source(source)
    assert len(runner) >= 4  # has a dispatch table to compare
    assert table_mismatch(set(AMBIGUOUS_KIND_CLASSES["blender"]), runner) == []


def test_dispatch_guard_flags_a_runner_with_a_mode_the_server_lacks() -> None:
    planted = (
        "def main():\n"
        "    dispatch = {'MontageConfig': a, 'VectorConfig': b, 'GlbConfig': c}\n"
        "    return dispatch\n"
    )
    runner = dispatch_keys_in_source(planted)
    assert runner == {"MontageConfig", "VectorConfig", "GlbConfig"}
    assert table_mismatch({"MontageConfig", "VectorConfig"}, runner) == [
        "runner only: ['GlbConfig']"
    ]
    assert table_mismatch(
        {"MontageConfig", "VectorConfig", "X"}, {"MontageConfig"}
    ) == ["server only: ['VectorConfig', 'X']"]


def test_dispatch_reader_finds_nothing_without_a_dispatch_dict() -> None:
    # The blender check above asserts a non-empty table, so a refactor that renames the dict
    # fails it rather than comparing two empty sets.
    assert dispatch_keys_in_source("def main():\n    table = {'A': 1}\n") == set()


# ---------------------------------------------------------------------------------------------
# Guard 3: APP_DEFAULTS are strict fields of their classes
# ---------------------------------------------------------------------------------------------

_ROI = {
    "_type": "SphericalROI",
    "x": [-42.0],
    "y": [-20.0],
    "z": [55.0],
    "radius": [10.0],
}

#: Authored: the fields each kind's class requires beyond APP_DEFAULTS (its __init__ arguments
#: without defaults, and what its __post_init__ demands), and the ``mode`` the job manager writes
#: into a flex runner's config.json.
MINIMAL: dict[str, dict] = {
    "pre": {"subject_ids": ["001"]},
    "sim": {
        "subject_id": "001",
        "montages": [
            {
                "_type": "Montage",
                "name": "M1",
                "mode": "net",
                "electrode_pairs": [["E1", "E2"], ["E3", "E4"]],
                "eeg_net": "GSN-HydroCel-185.csv",
            }
        ],
    },
    "flex": {"subject_id": "001", "roi": _ROI, "mode": "flex"},
    "flex_adaptive": {
        "subject_id": "001",
        "roi": _ROI,
        "non_roi_method": "everything_else",
        "mode": "flex_adaptive",
    },
    "flex_pareto": {
        "subject_id": "001",
        "roi": _ROI,
        "non_roi_method": "everything_else",
        "mode": "flex_pareto",
    },
    "leadfield": {"subject_id": "001"},
    "ex": {
        "subject_id": "001",
        "leadfield_hdf": "001_leadfield_GSN-HydroCel-185.hdf5",
        "roi_name": "target.csv",
        "electrodes": {
            "_type": "PoolElectrodes",
            "electrodes": ["E1", "E2", "E3", "E4"],
        },
    },
}


def app_default_failures(defaults: dict[str, dict]) -> dict[str, str]:
    """kind -> why its defaults do not deserialise strictly (empty when every kind does)."""
    from tit.server.routes.validate import cls_for

    failures: dict[str, str] = {}
    for kind, values in defaults.items():
        if kind not in MINIMAL:
            failures[kind] = "no minimal config authored for this kind"
            continue
        config = {**MINIMAL[kind], **copy.deepcopy(values)}
        try:
            deserialize_config(cls_for(kind, config), config, strict=True)
        except (TypeError, ValueError, KeyError) as exc:
            failures[kind] = str(exc)
    return failures


def test_every_app_default_is_a_strict_field_of_its_class() -> None:
    from tit.server.app_defaults import APP_DEFAULTS

    assert set(APP_DEFAULTS) >= {"pre", "sim", "flex", "ex"}  # has defaults to check
    assert app_default_failures(APP_DEFAULTS) == {}


def test_app_defaults_guard_flags_a_renamed_field() -> None:
    from tit.server.app_defaults import APP_DEFAULTS

    planted = copy.deepcopy(APP_DEFAULTS)
    planted["flex"]["current_ma"] = planted["flex"].pop("current_mA")
    planted["sim"]["output_field"] = planted["sim"].pop("output_fields")
    failures = app_default_failures(planted)
    assert set(failures) == {"flex", "sim"}
    assert "current_ma" in failures["flex"]
    assert "output_field" in failures["sim"]


def test_app_defaults_guard_flags_a_kind_without_a_minimal_config() -> None:
    assert app_default_failures({"mex": {"run_name": "x"}}) == {
        "mex": "no minimal config authored for this kind"
    }
