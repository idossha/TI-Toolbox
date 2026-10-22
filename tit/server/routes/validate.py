"""``POST /api/validate/{kind}`` -- field-level config validation, no side effects.

Deserializes ``config`` through :func:`tit.config_io.deserialize_config` for the dataclass that
*kind* maps to (see :func:`cls_for`), catching exactly what a config dataclass's own
``__post_init__`` (or a bad ``_type``/field shape) can raise, and reports it as
``{ok, errors: [{path, message}]}`` -- the UI never re-implements these rules (design rule R1);
this route only surfaces them. Exhaustive-search mask paths are also checked for
accessibility before a plan or costly leadfield load can proceed.

Kind -> config-class resolution
--------------------------------
Most kinds map to exactly one dataclass in :data:`tit.config_io.CONFIG_CLASS_REGISTRY`
(:data:`SIMPLE_KIND_CLASS`). Two kinds do not: ``stats`` (``GroupComparisonConfig`` or
``CorrelationConfig``) and ``blender`` (``MontageConfig``/``VectorConfig``/``RegionConfig``/``SubcorticalConfig``) --
the frozen ``PipelineConfig`` union in ``contracts/openapi.yaml`` lists all of them under the
same ``kind``/path parameter with no other discriminant on the object itself. This module resolves
the ambiguity with a ``config["_type"]`` key (see :data:`AMBIGUOUS_KIND_CLASSES`), the same
discriminator convention :mod:`tit.config_io` already uses for union-typed *fields* (ROIs,
electrodes, montages) -- just applied here to the top-level kind/class choice. ``_type`` is not a
field of any of these dataclasses, so :func:`~tit.config_io.deserialize_config` silently ignores
it (documented behavior: "keys in *data* that are not fields of *cls* ... are ignored"), making
this additive rather than a contract change. The tag is read exactly as each runner dispatches:
``blender`` requires it (``tit.blender.__main__`` has no default), and ``stats`` lets the older
``mode`` key win over it (``tit.stats.__main__``), so the server never plans one class while
the runner runs another. ``NO_SCHEMA_KINDS`` is empty as of the runners
lane registering ``NiftiAverageConfig``/``NilearnConfig`` in
:data:`~tit.config_io.CONFIG_CLASS_REGISTRY` -- kept as a (currently-empty) frozenset rather
than removed outright since ``contracts/generated/config.schema.json`` has not been regenerated with these two
``$defs`` yet (a B4/F1b follow-up: ``docker exec tit-v3-spike simnibs_python
dev/build_schema.py``), so the desktop's generated types don't know about them even though
this route already validates/plans them for real.

This is a documented design decision by this track (B3), not something ``contracts/openapi.yaml``
specifies -- flagged in the B3 report for F1a/the orchestrator in case a future contract revision
wants an explicit discriminant instead.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# NOTE: tit.config_io is imported lazily inside cls_for()/validate() below, not at module
# level. tit.config_io imports tit.opt.config, and importing any submodule of the tit.opt
# package runs tit/opt/__init__.py, which imports SimNIBS-backed engines eagerly (e.g.
# tit.opt.ex.engine imports simnibs.utils.TI_utils). A module-level import here would make
# this route module -- and therefore the whole server, since routes are auto-discovered at
# startup -- unimportable without SimNIBS installed, breaking
# ``python3 -m tit.server --dump-openapi`` on the host. Deferring the import to call time
# keeps route *registration* (schema generation, OpenAPI) SimNIBS-free while the actual
# validate/plan work (which does need the real config dataclasses) still runs fine inside
# the SimNIBS container where these handlers are actually invoked.

#: kind -> the one CONFIG_CLASS_REGISTRY key it always uses.
SIMPLE_KIND_CLASS: dict[str, str] = {
    "pre": "PreprocessConfig",
    "sim": "SimulationConfig",
    "flex": "FlexConfig",
    "flex_adaptive": "FlexConfig",
    "flex_pareto": "FlexConfig",
    "ex": "ExConfig",
    "mex": "MExConfig",
    "leadfield": "LeadfieldConfig",
    "analyzer": "AnalyzerConfig",
    "source": "SourceConfig",
    "nifti_average": "NiftiAverageConfig",
    "nilearn": "NilearnConfig",
}

#: kind -> {"_type" value -> CONFIG_CLASS_REGISTRY key}, for kinds the frozen contract's
#: PipelineConfig union leaves ambiguous (see module docstring).
AMBIGUOUS_KIND_CLASSES: dict[str, dict[str, str]] = {
    "stats": {
        "GroupComparisonConfig": "GroupComparisonConfig",
        "CorrelationConfig": "CorrelationConfig",
    },
    "blender": {
        "MontageConfig": "MontageConfig",
        "VectorConfig": "VectorConfig",
        "RegionConfig": "RegionConfig",
        "SubcorticalConfig": "SubcorticalConfig",
    },
}

#: The class ``x-kind-classes`` (``dev/build_schema.py``) shows for an ambiguous kind. ``stats``
#: also resolves to it when the config names neither ``_type`` nor ``mode``, as its runner does;
#: ``blender`` never does -- :func:`cls_for` refuses a blender config without ``_type``, because
#: ``tit.blender.__main__`` dispatches on ``_type`` alone and exits 1 without it.
AMBIGUOUS_KIND_DEFAULT: dict[str, str] = {
    "stats": "GroupComparisonConfig",
    "blender": "MontageConfig",
}

#: Ambiguous kinds whose runner has no default class: ``_type`` is required.
TYPE_REQUIRED_KINDS: frozenset[str] = frozenset({"blender"})

#: ``stats`` only: the older top-level ``mode`` key -> the class it runs. ``tit.stats.__main__``
#: pops ``mode`` and lets it win over ``_type`` (its ``MODE_FOR_TYPE`` read backwards), and
#: ``tit.jobs.locks.keys_for`` files the run under ``project:stats:<mode>/``. Any other value
#: would run as a group comparison under a lock key naming another folder, so it is refused.
STATS_MODE_CLASSES: dict[str, str] = {
    "group_comparison": "GroupComparisonConfig",
    "correlation": "CorrelationConfig",
}

#: Keys an ambiguous kind's runner pops before it deserialises the config (``stats``:
#: ``mode``), so strict validation does not report them as unknown fields.
DISPATCH_KEYS: dict[str, frozenset[str]] = {"stats": frozenset({"mode"})}

#: Keys the *server* owns on a runner config, not the config dataclass: ``tit.jobs.manager.
#: _runner_config_path`` writes ``project_dir`` into every runner's config.json (and the GUI has
#: always carried it too -- see the maintainer's own succeeded ``pre`` job d0036f3cad7b4be9,
#: whose ``spec.config`` contains it), and every runner's ``__main__`` pops it before building
#: its dataclass. :func:`tit.config_io.deserialize_config` documents it by name as a key that is
#: "silently ignored"; validating with ``strict=True`` without removing it first therefore
#: rejected exactly the body the UI submits and the runner then ran successfully (measured
#: 2026-09-03: ``POST /api/validate/pre`` -> ``PreprocessConfig: unknown key(s)
#: ['project_dir']`` for a config that ``POST /api/jobs/groups`` accepted). Stripped here, not
#: in ``deserialize_config``, so nested dataclasses stay strictly checked.
ENVELOPE_KEYS: frozenset[str] = frozenset({"project_dir"})

#: Kinds with no dataclass in CONFIG_CLASS_REGISTRY -- validate/plan treat them as "nothing to
#: check yet". Empty today (``nifti_average``/``nilearn`` moved to SIMPLE_KIND_CLASS once the
#: runners lane registered their dataclasses); kept as a named set, not deleted, since it is
#: part of cls_for's/plan's public contract for a future kind that lands without a config
#: dataclass yet.
NO_SCHEMA_KINDS: frozenset[str] = frozenset()

#: Every kind ``PipelineKind`` (``contracts/openapi.yaml``) accepts.
ALL_KINDS: frozenset[str] = frozenset(
    {*SIMPLE_KIND_CLASS, *AMBIGUOUS_KIND_CLASSES, *NO_SCHEMA_KINDS}
)


class KindNotConfigurable(ValueError):
    """Raised by :func:`cls_for` when an ambiguous kind's config names no class it can run."""


def cls_for(kind: str, config_body: dict[str, Any]) -> type | None:
    """Resolve *kind* (and, for an ambiguous kind, the config's own tag) to a dataclass.

    An ambiguous kind is read the way its runner dispatches it: ``stats`` by its ``mode`` key
    when present (:data:`STATS_MODE_CLASSES`), else by ``_type``, else
    ``GroupComparisonConfig``; ``blender`` by ``_type`` only.

    Parameters
    ----------
    kind : str
        A :data:`ALL_KINDS` member (callers should 404 first for anything else).
    config_body : dict
        The request's raw ``config`` object (read for ``_type`` -- and, for ``stats``,
        ``mode`` -- only when *kind* is ambiguous; never mutated).

    Returns
    -------
    type or None
        ``None`` for a :data:`NO_SCHEMA_KINDS` member (nothing to validate against yet).

    Raises
    ------
    KindNotConfigurable
        If *kind* is ambiguous and ``_type`` (or its default) does not name one of its
        known classes, a ``blender`` config has no ``_type``, or a ``stats`` config's
        ``mode`` is unknown or contradicts its ``_type``.
    """
    from tit.config_io import resolve_config_class

    if kind in NO_SCHEMA_KINDS:
        return None
    if kind in SIMPLE_KIND_CLASS:
        return resolve_config_class(SIMPLE_KIND_CLASS[kind])

    choices = AMBIGUOUS_KIND_CLASSES.get(kind)
    if choices is not None:
        type_tag = config_body.get("_type")
        if kind == "stats" and config_body.get("mode"):
            type_tag = _stats_mode_class(config_body["mode"], type_tag)
        if not type_tag and kind in TYPE_REQUIRED_KINDS:
            raise KindNotConfigurable(
                f"kind={kind!r} config._type is required, one of {sorted(choices)}: "
                "the runner picks the export by it and has no default"
            )
        type_tag = type_tag or AMBIGUOUS_KIND_DEFAULT[kind]
        registry_key = choices.get(type_tag)
        if registry_key is None:
            raise KindNotConfigurable(
                f"kind={kind!r} config._type must be one of {sorted(choices)}, "
                f"got {type_tag!r}"
            )
        return resolve_config_class(registry_key)

    raise KindNotConfigurable(f"unknown kind: {kind!r}")


def _stats_mode_class(mode: Any, type_tag: Any) -> str:
    """The class a stats config's ``mode`` runs, checked against its ``_type`` if it has one."""
    cls_name = STATS_MODE_CLASSES.get(mode) if isinstance(mode, str) else None
    if cls_name is None:
        raise KindNotConfigurable(
            f"kind='stats' config.mode must be one of {sorted(STATS_MODE_CLASSES)}, "
            f"got {mode!r}"
        )
    if type_tag and type_tag != cls_name:
        raise KindNotConfigurable(
            f"kind='stats' config.mode={mode!r} runs {cls_name}, but config._type is "
            f"{type_tag!r}; send one of them"
        )
    return cls_name


def refuse_unknown_keys(kind: str, config: dict[str, Any]) -> None:
    """Raise :class:`ValueError` when *config* has a key ``/api/validate/{kind}`` calls unknown.

    The submission routes (``POST /api/jobs``, ``/api/jobs/groups``, rerun, an approved
    proposal) read configs leniently, as the runners do, so a misspelled or renamed key used
    to be accepted and silently ignored. This applies the validate route's strictness, with the
    same envelope (``project_dir``) and dispatch (stats ``mode``) keys set aside, to that one
    rule: a config that is invalid for another reason is left to ``check_job_config``, the
    preflight and the runner (the analyzer and source runners still read their older layouts).
    Kinds with no config class (``tools``, ``project_init``) have nothing to check. A ``pre``
    key from before the FastSurfer stage (``tit.pre.config.LEGACY_KEYS``) is not unknown here:
    the runner and ``POST /api/plan/pre`` translate it (``migrate_legacy_keys``), and
    ``check_job_config`` checks the translated config. ``/api/validate`` itself still flags it.

    Raises
    ------
    ValueError
        Naming the unknown key(s) and the class's fields.
    """
    from tit.config_io import deserialize_config

    if kind not in ALL_KINDS:
        return
    try:
        cls = cls_for(kind, config)
    except KindNotConfigurable:
        return  # refused by the overwrite check's own cls_for, with its own message
    if cls is None:
        return
    ignored = ENVELOPE_KEYS | DISPATCH_KEYS.get(kind, frozenset())
    if kind == "pre":
        from tit.pre.config import LEGACY_KEYS

        ignored |= frozenset(LEGACY_KEYS)
    data = {k: v for k, v in config.items() if k not in ignored}
    try:
        deserialize_config(cls, data, strict=True)
    except (ValueError, TypeError, KeyError) as strict_error:
        try:
            deserialize_config(cls, data)
        except (ValueError, TypeError, KeyError):
            return  # invalid regardless of its keys: not this check's to judge
        # Strict adds only the unknown-key rule, so that is what failed.
        raise ValueError(str(strict_error)) from None


#: dataclass field names are always identifiers; a message quoting or bareword-mentioning one
#: is very likely talking about that field (see _guess_field_path's docstring for the caveat).
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _guess_field_path(message: str, cls: type) -> str:
    """Best-effort field path for a ``__post_init__`` error message.

    ``__post_init__`` raises ``ValueError``/``TypeError`` with free-text messages (there is no
    structured field information to read back), so this is a heuristic: every identifier-shaped
    token in *message* is checked against *cls*'s own ``dataclasses.fields()`` names, longest
    match first (``"ratio_total_mA"`` should win over a coincidental shorter prefix), and the
    first hit is returned. When nothing matches, ``""`` is returned -- meaning "the whole config",
    which the UI can still show as a form-level error banner.

    Parameters
    ----------
    message : str
        The exception's ``str()``.
    cls : type
        The dataclass *message* came from validating.

    Returns
    -------
    str
        A field name, or ``""``.
    """
    import dataclasses

    field_names = sorted(
        (f.name for f in dataclasses.fields(cls)), key=len, reverse=True
    )
    tokens = set(_IDENTIFIER_RE.findall(message))
    for name in field_names:
        if name in tokens:
            return name
    return ""


class ValidateRequest(BaseModel):
    config: dict[str, Any]
    #: ``"agent"`` fills the run pages' defaults into ``config`` (:mod:`tit.server.app_defaults`).
    created_by: str | None = None


class ValidateError(BaseModel):
    path: str
    message: str


class ValidateResult(BaseModel):
    ok: bool
    errors: list[ValidateError]


@router.post(
    "/api/validate/{kind}",
    response_model=ValidateResult,
    summary="Field-level validation of a config, no side effects",
)
def validate(kind: str, body: ValidateRequest) -> ValidateResult:
    from tit.config_io import deserialize_config

    if kind not in ALL_KINDS:
        raise HTTPException(status_code=404, detail=f"unknown kind: {kind}")

    try:
        cls = cls_for(kind, body.config)
    except KindNotConfigurable as exc:
        return ValidateResult(
            ok=False, errors=[ValidateError(path="_type", message=str(exc))]
        )

    if cls is None:
        # No dataclass registered for this kind yet -- nothing to check (see module docstring).
        return ValidateResult(ok=True, errors=[])

    if body.created_by == "agent":
        from tit.server.app_defaults import with_app_defaults

        body.config = with_app_defaults(kind, body.config)
    from tit.jobs.config_check import runner_view

    ignored = ENVELOPE_KEYS | DISPATCH_KEYS.get(kind, frozenset())
    config = {k: v for k, v in body.config.items() if k not in ignored}
    try:
        parsed = deserialize_config(cls, runner_view(kind, config), strict=True)
        if kind in {"ex", "mex", "flex", "flex_adaptive", "flex_pareto"}:
            from tit.opt.masks import validate_mask_paths

            validate_mask_paths(parsed)
        elif kind == "analyzer":
            from tit.analyzer.masks import validate_mask_path

            validate_mask_path(parsed)
    except (ValueError, TypeError, KeyError) as exc:
        return ValidateResult(
            ok=False,
            errors=[
                ValidateError(path=_guess_field_path(str(exc), cls), message=str(exc))
            ],
        )

    return ValidateResult(ok=True, errors=[])
