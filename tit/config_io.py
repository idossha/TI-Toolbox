"""JSON serialisation for config dataclasses.

Provides helpers to serialise typed config dataclasses (with Enum fields,
nested dataclasses, and union-typed ROI/electrode specs) to JSON files and
read them back.

Public API
----------
serialize_config
    Convert a config dataclass to a JSON-serialisable dict (with
    ``project_dir`` injection).
write_config_json
    Serialise a config dataclass to a temporary JSON file.
read_config_json
    Read a JSON config file and return the parsed dict.
deserialize_config
    Rebuild a config dataclass instance from its serialized dict form --
    the symmetric inverse of ``serialize_config``.
json_schema
    Build a draft 2020-12 JSON Schema for a config dataclass, with the
    same ``_type`` discriminator conventions ``serialize_config`` /
    ``deserialize_config`` use.

Examples
--------
>>> from tit.config_io import write_config_json, read_config_json
>>> path = write_config_json(my_flex_config, prefix="flex")
>>> data = read_config_json(path)

See Also
--------
tit.opt.config : ``FlexConfig`` and ``ExConfig`` dataclasses.
tit.sim.config : ``Montage`` dataclass.
"""

import importlib
import json
import os
import tempfile
import types
import typing
from dataclasses import asdict, fields, is_dataclass
from enum import Enum
from typing import Any

from tit.opt.config import ExConfig, FlexConfig, MExConfig
from tit.sim.config import Montage

# Mapping from class to discriminator string.
# Blender configs are registered lazily (see _get_discriminator_map) to avoid
# importing tit.blender at module load time — that package pulls in heavy deps
# (trimesh, simnibs, bpy) which are only available inside Docker.
_TYPE_DISCRIMINATED: dict[type, str] = {
    FlexConfig.SphericalROI: "SphericalROI",
    FlexConfig.AtlasROI: "AtlasROI",
    FlexConfig.SubcorticalROI: "SubcorticalROI",
    ExConfig.PoolElectrodes: "PoolElectrodes",
    ExConfig.BucketElectrodes: "BucketElectrodes",
    MExConfig.PoolElectrodes: "PoolElectrodes",
    MExConfig.BucketElectrodes: "BucketElectrodes",
    Montage: "Montage",
}

# Blender config types are matched by class name to avoid importing
# tit.blender.__init__ (which pulls in heavy deps like trimesh/bpy).
# The config module itself is pure Python, but the package __init__
# re-exports the heavy exporters.
_TYPE_DISCRIMINATED_BY_NAME: dict[str, str] = {
    "MontageConfig": "MontageConfig",
    "VectorConfig": "VectorConfig",
    "RegionConfig": "RegionConfig",
    "SubcorticalConfig": "SubcorticalConfig",
}


def serialize_config(config: Any) -> dict[str, Any]:
    """Convert a config dataclass to a JSON-serialisable dict.

    Handles Enum fields (via ``.value``), nested dataclasses (recursed),
    union-typed ROI / electrode specs (injects a ``_type`` discriminator),
    and *None* values (preserved as JSON ``null``).

    Also injects ``project_dir`` from the active :class:`~tit.paths.PathManager`
    so that subprocess entry points can initialise their own singleton.

    Parameters
    ----------
    config : dataclass instance
        Any config dataclass (e.g., ``FlexConfig``, ``ExConfig``).

    Returns
    -------
    dict
        JSON-serialisable dictionary representation of *config*.

    See Also
    --------
    write_config_json : Serialise and write to a temp file in one step.
    read_config_json : Read a JSON config back into a dict.
    """
    data = _serialize(config)
    # Inject project_dir for subprocess entry points
    from tit.paths import get_path_manager

    data["project_dir"] = get_path_manager().project_dir
    return data


def write_config_json(config: Any, prefix: str = "config") -> str:
    """Serialise a config dataclass to a temporary JSON file.

    Parameters
    ----------
    config : dataclass instance
        Config object to serialise.
    prefix : str, optional
        Filename prefix for the temp file.  Default is ``"config"``.

    Returns
    -------
    str
        Absolute path to the created JSON file.

    See Also
    --------
    serialize_config : Convert to dict without writing to disk.
    read_config_json : Read a JSON config file.
    """
    data = serialize_config(config)
    fd, path = tempfile.mkstemp(prefix=f"{prefix}_", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    return path


def read_config_json(path: str) -> dict[str, Any]:
    """Read a JSON config file and return the parsed dict.

    Parameters
    ----------
    path : str
        Path to the JSON file.

    Returns
    -------
    dict
        Parsed JSON contents.

    See Also
    --------
    write_config_json : Create a config JSON file from a dataclass.
    """
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _serialize(obj: Any) -> Any:
    """Recursively serialise a value to a JSON-compatible type."""
    if obj is None:
        return None
    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj):
        result: dict[str, Any] = {}
        # Add _type discriminator for union-typed / top-level config classes
        obj_type = type(obj)
        if obj_type in _TYPE_DISCRIMINATED:
            result["_type"] = _TYPE_DISCRIMINATED[obj_type]
        elif obj_type.__name__ in _TYPE_DISCRIMINATED_BY_NAME:
            result["_type"] = _TYPE_DISCRIMINATED_BY_NAME[obj_type.__name__]
        for fld in fields(obj):
            result[fld.name] = _serialize(getattr(obj, fld.name))
        return result
    if isinstance(obj, (list, tuple)):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    # Primitive types (int, float, str, bool) pass through
    return obj


def _discriminator_for(cls: type) -> str | None:
    """The ``_type`` value :func:`serialize_config` writes for *cls*, if any.

    Looks *cls* up by identity in :data:`_TYPE_DISCRIMINATED` first (the
    common case), then by bare name in :data:`_TYPE_DISCRIMINATED_BY_NAME`
    (the blender configs, matched by name so importing them here -- which
    would import ``tit.blender`` and its heavy ``bpy``/``trimesh``/
    ``simnibs`` dependencies -- is never required). Returns ``None`` for a
    class that ``serialize_config`` never tags, e.g. ``ExConfig.AtlasROI``
    or ``MExConfig.AtlasROI``, which share the bare name ``"AtlasROI"``
    with the tagged ``FlexConfig.AtlasROI`` but are never used
    polymorphically (each appears only in a plain ``list[AtlasROI]``
    field, disambiguated by its declared type alone).
    """
    return _TYPE_DISCRIMINATED.get(cls) or _TYPE_DISCRIMINATED_BY_NAME.get(cls.__name__)


# ---------------------------------------------------------------------------
# Registry of every config dataclass with a generated JSON Schema
# ---------------------------------------------------------------------------

#: ``name -> "package.module.ClassName"`` for every config dataclass that
#: participates in :func:`json_schema` / :func:`deserialize_config` and the
#: generated ``contracts/generated/config.schema.json`` (see ``dev/build_schema.py``). Kept as
#: strings, not imported class objects, so importing ``tit.config_io`` never
#: pulls in a per-module heavy dependency (SimNIBS, bpy, trimesh) that some
#: registered class's *package* needs merely to import -- callers resolve
#: only the classes they actually need via :func:`resolve_config_class`. The
#: dotted paths double as the ``"x-tit-classes"`` index in
#: ``contracts/generated/config.schema.json``.
CONFIG_CLASS_REGISTRY: dict[str, str] = {
    "SimulationConfig": "tit.sim.config.SimulationConfig",
    "Montage": "tit.sim.config.Montage",
    "FlexConfig": "tit.opt.config.FlexConfig",
    "ExConfig": "tit.opt.config.ExConfig",
    "MExConfig": "tit.opt.config.MExConfig",
    "AnalyzerConfig": "tit.analyzer.config.AnalyzerConfig",
    "PreprocessConfig": "tit.pre.config.PreprocessConfig",
    "QSIPrepConfig": "tit.pre.qsi.config.QSIPrepConfig",
    "QSIReconConfig": "tit.pre.qsi.config.QSIReconConfig",
    "QSIPrepSettings": "tit.pre.config.QSIPrepSettings",
    "QSIReconSettings": "tit.pre.config.QSIReconSettings",
    "GroupComparisonConfig": "tit.stats.config.GroupComparisonConfig",
    "CorrelationConfig": "tit.stats.config.CorrelationConfig",
    "SourceConfig": "tit.source.config.SourceConfig",
    "LeadfieldConfig": "tit.opt.leadfield_config.LeadfieldConfig",
    "MontageConfig": "tit.blender.config.MontageConfig",
    "VectorConfig": "tit.blender.config.VectorConfig",
    "RegionConfig": "tit.blender.config.RegionConfig",
    "SubcorticalConfig": "tit.blender.config.SubcorticalConfig",
    "NiftiAverageConfig": "tit.stats.nifti_average_config.NiftiAverageConfig",
    "NilearnConfig": "tit.plotting.nilearn.config.NilearnConfig",
}


def resolve_config_class(name: str) -> type:
    """Import and return the class registered under *name*.

    Parameters
    ----------
    name : str
        A key of :data:`CONFIG_CLASS_REGISTRY`.

    Returns
    -------
    type
        The resolved dataclass.

    Raises
    ------
    KeyError
        If *name* is not registered.
    """
    dotted = CONFIG_CLASS_REGISTRY[name]
    module_path, class_name = dotted.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


# ---------------------------------------------------------------------------
# deserialize_config -- the symmetric inverse of serialize_config
# ---------------------------------------------------------------------------


def deserialize_config(cls: type, data: dict[str, Any], *, strict: bool = False) -> Any:
    """Rebuild a config dataclass instance from its serialized dict form.

    The symmetric inverse of :func:`serialize_config`: walks *cls*'s own
    ``dataclasses.fields()`` (resolving each field's type -- including
    forward-referenced nested-class unions such as ``FlexConfig.roi`` --
    with ``typing.get_type_hints``) and converts every value back into
    whatever ``serialize_config`` produced it from: nested dataclasses
    (a single required type, or a union disambiguated by ``_type``), lists
    of dataclasses, ``Enum`` members, tuples (including tuples nested
    inside lists, e.g. ``Montage.electrode_pairs``), dict values whose declared
    key type isn't ``str`` (JSON object keys are always strings, so e.g.
    ``SimulationConfig.tissue_conductivities: dict[int, float]`` round-trips
    as ``{"1": 2.5}`` and is coerced back to ``{1: 2.5}``), and ``Optional``
    values. By default, keys in *data* that are not fields of *cls* (e.g.
    ``"project_dir"``, which the runners pop themselves -- see
    ``tit.sim.__main__.main`` -- or ``"_type"`` on an ambiguous kind's
    top-level config, see ``tit.server.routes.validate``) are silently
    ignored; pass *strict* to change that.

    Parameters
    ----------
    cls : type
        A dataclass, e.g. one of :data:`CONFIG_CLASS_REGISTRY`'s values.
    data : dict
        Parsed JSON as produced by :func:`serialize_config` (directly, or
        round-tripped through :func:`write_config_json` /
        :func:`read_config_json`).
    strict : bool, optional
        If True, raise instead of silently ignoring a key in *data* that
        is not one of *cls*'s own fields (recursively, for every nested
        dataclass reached along the way) -- catching a misspelled or
        renamed field at validation time instead of it becoming a silent
        no-op. ``"_type"`` is never flagged as unknown even in strict mode
        (every discriminated dataclass and every ambiguous top-level kind
        uses it without it being a real field). Off by default: a caller
        with its own legacy flat-dict layout (e.g.
        ``tit.analyzer.__main__``'s pre-``AnalyzerConfig`` fallback) is
        unaffected unless it opts in.

    Returns
    -------
    Any
        A *cls* instance.

    Raises
    ------
    TypeError
        If *cls* is not a dataclass.
    ValueError
        If *data* carries a ``_type`` that does not match *cls* itself, if
        a union-typed field's value is missing its ``_type`` tag or
        carries one not registered for that union's members, or (only
        when *strict* is True) if *data* carries a key that is not one of
        *cls*'s fields.

    See Also
    --------
    serialize_config : The inverse conversion.
    json_schema : Describes the same shape as a JSON Schema, including the
        ``additionalProperties: false`` this function's *strict* mode
        enforces at runtime.
    """
    if not is_dataclass(cls):
        raise TypeError(f"{cls!r} is not a dataclass")

    type_tag = data.get("_type")
    if type_tag is not None:
        expected = _discriminator_for(cls)
        if expected is not None and type_tag != expected:
            raise ValueError(
                f"_type={type_tag!r} does not match {cls.__name__} "
                f"(expected {expected!r})"
            )

    if strict:
        known = {fld.name for fld in fields(cls)}
        unknown = sorted(set(data) - known - {"_type"})
        if unknown:
            raise ValueError(
                f"{cls.__name__}: unknown key(s) {unknown}; expected one of "
                f"{sorted(known)}"
            )

    hints = typing.get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for fld in fields(cls):
        if not fld.init or fld.name not in data:
            continue
        kwargs[fld.name] = _deserialize_value(
            data[fld.name], hints.get(fld.name), strict=strict
        )
    return cls(**kwargs)


def _is_dataclass_type(tp: Any) -> bool:
    return isinstance(tp, type) and is_dataclass(tp)


_UNION_ORIGINS = (typing.Union, types.UnionType)


def _deserialize_value(value: Any, tp: Any, *, strict: bool = False) -> Any:
    """Convert one JSON value back to *tp*, recursing through generics.

    *strict* is threaded through every recursive call so an unknown key
    is caught no matter how deep the dataclass nesting (unions, lists,
    dicts) that reaches it -- see :func:`deserialize_config`.
    """
    if value is None:
        return None
    if tp is None:
        return value

    origin = typing.get_origin(tp)
    if origin in _UNION_ORIGINS:
        branches = [a for a in typing.get_args(tp) if a is not type(None)]
        return _deserialize_union(value, branches, strict=strict)
    if origin is list:
        (item_t,) = typing.get_args(tp) or (None,)
        return [_deserialize_value(v, item_t, strict=strict) for v in value]
    if origin is tuple:
        args = typing.get_args(tp)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_deserialize_value(v, args[0], strict=strict) for v in value)
        return tuple(
            _deserialize_value(v, t, strict=strict) for v, t in zip(value, args)
        )
    if origin is dict:
        # JSON object keys are always strings (e.g. SimulationConfig.tissue_conductivities:
        # dict[int, float] round-trips as {"1": 2.5, ...}); coerce back to the declared key
        # type when it isn't already str, and recurse into values.
        key_t, val_t = typing.get_args(tp) or (None, None)
        if key_t is not None and key_t is not str:
            return {
                key_t(k): _deserialize_value(v, val_t, strict=strict)
                for k, v in value.items()
            }
        return {
            k: _deserialize_value(v, val_t, strict=strict) for k, v in value.items()
        }
    if origin is not None:
        # Literal, etc. -- JSON already has the right shape.
        return value

    if _is_dataclass_type(tp):
        return deserialize_config(tp, value, strict=strict)
    if isinstance(tp, type) and issubclass(tp, Enum):
        return tp(value)
    return value


def _deserialize_union(value: Any, branches: list, *, strict: bool = False) -> Any:
    """Deserialize *value* against a Union's non-``None`` *branches*.

    A single remaining branch (an ``Optional[X]`` with ``value is not
    None``) recurses into it directly -- covering generics like
    ``list[str] | None`` (``ExConfig.roi_names``), not just dataclasses. Multiple dataclass
    branches (e.g. ``BucketElectrodes | PoolElectrodes``) are disambiguated
    by *value*'s ``"_type"`` key, exactly as ``serialize_config`` wrote it.
    Multiple non-dataclass branches (e.g. ``float | list[float]``) are
    disambiguated by matching *value*'s own JSON shape (a JSON array
    selects the ``list``/``tuple`` branch).
    """
    if len(branches) == 1:
        return _deserialize_value(value, branches[0], strict=strict)

    dataclass_branches = [b for b in branches if _is_dataclass_type(b)]
    if dataclass_branches:
        if not isinstance(value, dict):
            names = [b.__name__ for b in dataclass_branches]
            raise ValueError(
                f"Expected an object with '_type' for union {names}, got "
                f"{type(value).__name__}"
            )
        by_tag = {_discriminator_for(b): b for b in dataclass_branches}
        tag = value.get("_type")
        if tag is None or tag not in by_tag:
            known = sorted(t for t in by_tag if t is not None)
            raise ValueError(
                f"Missing or unknown '_type' discriminator {tag!r} for union "
                f"of {[b.__name__ for b in dataclass_branches]}; expected one "
                f"of {known}"
            )
        return deserialize_config(by_tag[tag], value, strict=strict)

    for branch in branches:
        if typing.get_origin(branch) in (list, tuple) and isinstance(value, list):
            return _deserialize_value(value, branch, strict=strict)
    return value


# ---------------------------------------------------------------------------
# json_schema -- draft 2020-12 JSON Schema generation
# ---------------------------------------------------------------------------

#: Bare ``$defs`` names reused by more than one class across the full set of
#: :data:`CONFIG_CLASS_REGISTRY` classes: ``FlexConfig``, ``ExConfig`` and
#: ``MExConfig`` each define their own nested ``AtlasROI``; ``ExConfig`` and
#: ``MExConfig`` each define their own ``PoolElectrodes`` and
#: ``BucketElectrodes``; ``GroupComparisonConfig`` and ``CorrelationConfig``
#: each define their own ``Subject``. A flat ``dict`` union-merge of many
#: classes' schemas (``dev/build_schema.py``) would let one definition
#: silently clobber another under the bare name, so :func:`json_schema`
#: renames every one of them, in every class that defines it, to
#: ``"<top-level class name><bare name>"`` -- e.g. ``"FlexConfigAtlasROI"``,
#: ``"ExConfigAtlasROI"``, ``"MExConfigAtlasROI"`` -- making the merge safe
#: without needing to import every *other* registered class merely to
#: detect the collision.
_COLLIDING_DEFS_NAMES = frozenset(
    {"AtlasROI", "PoolElectrodes", "BucketElectrodes", "Subject"}
)


def _iter_nested_dataclasses(cls: type) -> dict[str, type]:
    """Every dataclass reachable from *cls*'s own fields, keyed by bare name.

    Excludes *cls* itself. Walks generics (``Union``/``X | Y``, ``list``,
    ``tuple``, ...) via ``typing.get_origin``/``get_args`` so a dataclass
    nested inside e.g. ``list[AtlasROI] | None`` is still found. Used to
    drive both the collision-safe ``$defs`` renaming and the ``_type``
    discriminator injection in :func:`json_schema` -- within one class's
    own schema, pydantic's ``$defs`` keys are exactly these classes' bare
    names (dataclasses reachable from a single root never collide with
    *each other*; only across the 16 registered top-level classes' merged
    ``$defs`` can two different classes share a bare name).
    """
    seen: set[type] = {cls}
    found: dict[str, type] = {}

    def walk(dc: type) -> None:
        hints = typing.get_type_hints(dc)
        for fld in fields(dc):
            _walk_type(hints.get(fld.name), seen, found, walk)

    walk(cls)
    return found


def _walk_type(tp: Any, seen: set, found: dict[str, type], walk) -> None:
    if tp is None:
        return
    if _is_dataclass_type(tp):
        if tp not in seen:
            seen.add(tp)
            found[tp.__name__] = tp
            walk(tp)
        return
    for arg in typing.get_args(tp):
        _walk_type(arg, seen, found, walk)


def _inject_type_property(schema_obj: dict, type_value: str) -> None:
    """Add ``"_type": {"const": type_value}`` to one object schema's
    ``properties``/``required`` (either the schema's own top level, for the
    class :func:`json_schema` was called with, or one of its ``$defs``
    entries, for a nested discriminated member)."""
    props = schema_obj.setdefault("properties", {})
    props["_type"] = {"const": type_value}
    required = schema_obj.setdefault("required", [])
    if "_type" not in required:
        required.append("_type")


def _rename_refs(node: Any, rename: dict[str, str]) -> None:
    """In place: ``"#/$defs/<old>"`` -> ``"#/$defs/<rename[old]>"``, recursively."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            old_name = ref[len("#/$defs/") :]
            if old_name in rename:
                node["$ref"] = f"#/$defs/{rename[old_name]}"
        for v in node.values():
            _rename_refs(v, rename)
    elif isinstance(node, list):
        for item in node:
            _rename_refs(item, rename)


def _close_object_schemas(schema: dict) -> None:
    """Set ``"additionalProperties": false`` on every fixed-shape object schema.

    Applies to the top-level schema and every ``$defs`` entry that has its
    own ``"properties"`` -- i.e. every dataclass-derived object, matching
    exactly what :func:`deserialize_config`'s ``strict=True`` rejects at
    runtime. A schema *without* ``"properties"`` (e.g. a free-form mapping
    field such as ``SimulationConfig.tissue_conductivities: dict[int, float]``,
    which pydantic instead scopes with its own
    ``"additionalProperties": {"type": "number"}``) is left untouched, so
    this can never turn a legitimate dynamic-key field into a fixed one.
    Never overrides a schema that already sets ``"additionalProperties"``
    itself.
    """
    if "properties" in schema and "additionalProperties" not in schema:
        schema["additionalProperties"] = False
    for defn in schema.get("$defs", {}).values():
        if "properties" in defn and "additionalProperties" not in defn:
            defn["additionalProperties"] = False


def _rewrite_discriminated_unions(schema: dict) -> None:
    """Rewrite every ``anyOf`` of discriminated-member ``$ref``s (plus an
    optional ``{"type": "null"}`` branch, for ``Optional[...]`` fields) to
    ``oneOf`` + ``discriminator: {"propertyName": "_type"}``, recursively
    over the whole schema. A member only counts as "discriminated" once its
    ``$defs`` entry already carries the ``"_type"`` const property injected
    by :func:`_inject_type_property` -- so this must run after that
    injection (and after the collision-safe rename, so it resolves the
    *final* ``$defs`` names)."""
    defs = schema.get("$defs", {})

    def is_discriminated_ref(member: Any) -> bool:
        if not (isinstance(member, dict) and set(member) == {"$ref"}):
            return False
        name = member["$ref"].rsplit("/", 1)[-1]
        target = defs.get(name, {})
        return "_type" in target.get("properties", {})

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            any_of = node.get("anyOf")
            if isinstance(any_of, list):
                refs = [m for m in any_of if "$ref" in m]
                others = [m for m in any_of if "$ref" not in m]
                only_null = all(m == {"type": "null"} for m in others)
                if (
                    len(refs) >= 2
                    and only_null
                    and all(map(is_discriminated_ref, refs))
                ):
                    node["oneOf"] = node.pop("anyOf")
                    node["discriminator"] = {"propertyName": "_type"}
            for v in node.values():
                visit(v)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(schema)


def json_schema(cls: type) -> dict[str, Any]:
    """Build a draft 2020-12 JSON Schema for a config dataclass.

    Wraps ``pydantic.TypeAdapter(cls).json_schema()`` with this project's
    discriminated-union conventions, so the result matches exactly what
    :func:`serialize_config` emits and :func:`deserialize_config` accepts:

    - every reachable class ``serialize_config`` tags with a ``_type``
      discriminator (:data:`_TYPE_DISCRIMINATED` /
      :data:`_TYPE_DISCRIMINATED_BY_NAME`) gets ``"_type": {"const": ...}``
      injected into its properties and required list -- whether that class
      is *cls* itself (e.g. ``json_schema(Montage)``) or a nested ``$defs``
      entry (e.g. ``FlexConfig``'s ``SphericalROI``/``AtlasROI``/
      ``SubcorticalROI``);
    - every ``anyOf`` whose members are all ``$ref``s to such discriminated
      classes (plus an optional ``null`` branch for ``Optional[...]``) is
      rewritten to ``oneOf`` + ``discriminator: {"propertyName": "_type"}``;
    - ``$defs`` entries whose bare name collides with another registered
      class's (:data:`_COLLIDING_DEFS_NAMES`: ``AtlasROI`` on three
      classes, ``PoolElectrodes``/``BucketElectrodes`` on two, ``Subject``
      on two) are renamed to ``"<cls.__name__><bare name>"``, so merging
      many classes' schemas into one document
      (see ``dev/build_schema.py``) can never let one definition silently
      clobber another's under the same key;
    - every fixed-shape object schema (the top level and each ``$defs``
      entry with its own ``"properties"``) gets
      ``"additionalProperties": false`` (:func:`_close_object_schemas`),
      matching what :func:`deserialize_config`'s ``strict=True`` rejects
      at runtime -- a misspelled or renamed field fails schema validation
      (e.g. at ``POST /api/validate/{kind}``) instead of silently
      vanishing. A free-form mapping field (e.g.
      ``SimulationConfig.tissue_conductivities: dict[int, float]``) has no
      ``"properties"`` of its own and is left open.

    Parameters
    ----------
    cls : type
        A dataclass, e.g. one of :data:`CONFIG_CLASS_REGISTRY`'s values.

    Returns
    -------
    dict
        A JSON Schema document: *cls*'s own shape at the top level, nested
        types under ``$defs``.

    See Also
    --------
    deserialize_config : Accepts exactly the data this schema validates.
    """
    from pydantic import TypeAdapter

    schema = TypeAdapter(cls).json_schema()
    nested = _iter_nested_dataclasses(cls)

    own_type = _discriminator_for(cls)
    if own_type is not None:
        _inject_type_property(schema, own_type)

    defs = schema.get("$defs", {})
    for name, member in nested.items():
        member_type = _discriminator_for(member)
        if member_type is not None and name in defs:
            _inject_type_property(defs[name], member_type)

    rename = {
        name: f"{cls.__name__}{name}"
        for name in nested
        if name in _COLLIDING_DEFS_NAMES and name in defs
    }
    if rename:
        for old, new in rename.items():
            defs[new] = defs.pop(old)
        _rename_refs(schema, rename)

    _close_object_schemas(schema)
    _rewrite_discriminated_unions(schema)
    return schema
