"""Reject a job config the runner could not deserialise, at submit time instead of at run time.

Background (the regression this exists for): a client POSTed ``{"__mock_fast": true}`` as a
``sim`` config. ``POST /api/jobs`` accepted it, the manager wrote ``config.json``, and the job
only failed minutes later inside the runner with

    TypeError: SimulationConfig.__init__() missing 2 required positional arguments:
    'subject_id' and 'montages'

which reaches the user as a dead job with a stack trace rather than a rejected request. The
runners for these kinds call :func:`tit.config_io.deserialize_config` directly and have no
fallback, so exactly the same call made here at submit time turns that into a 422.

Only kinds whose ``__main__`` deserialises one class with no fallback are listed. ``analyzer``
and ``source`` deliberately tolerate a config ``deserialize_config`` rejects (they fall back to a
filtered constructor), so pre-validating them here would reject configs those runners can
genuinely run. ``pre`` lost its fallback (it accepted ``subject_ids: "001"`` as three subjects).

The check is strict, as ``POST /api/validate`` is: a key that is not a field of the class (or of
a nested one) is refused instead of silently ignored by the runner. ``pre`` keys from before the
FastSurfer stage are translated first, as its runner does (``migrate_legacy_keys``). The
unknown-key rule for the kinds not listed here is
:func:`tit.server.routes.validate.refuse_unknown_keys`.
"""

from __future__ import annotations

from typing import Any

from tit.jobs.kinds import FLEX_KINDS

#: kind -> :data:`tit.config_io.CONFIG_CLASS_REGISTRY` key.
CONFIG_CLASS_FOR_KIND: dict[str, str] = {
    "sim": "SimulationConfig",
    "flex": "FlexConfig",
    "flex_adaptive": "FlexConfig",
    "flex_pareto": "FlexConfig",
    "ex": "ExConfig",
    "mex": "MExConfig",
    "pre": "PreprocessConfig",
}


def check_job_config(kind: str, config: dict[str, Any]) -> None:
    """Raise :class:`ValueError` if *config* is not a deserialisable config for *kind*.

    A no-op for a kind with no entry in :data:`CONFIG_CLASS_FOR_KIND`, and a no-op when the
    config class cannot be imported in this environment (a host without SimNIBS, say) — this is
    a guard against a bad request, never a new hard dependency on the submit path.
    """
    class_name = CONFIG_CLASS_FOR_KIND.get(kind)
    if class_name is None:
        return
    try:
        from tit.config_io import deserialize_config, resolve_config_class

        cls = resolve_config_class(class_name)
    except Exception:  # pragma: no cover - environment without the runner's deps
        return
    # Mirrors the runner: `project_dir` is popped before deserialising. Unlike the runner,
    # unknown keys are refused (strict=True): the runner would silently ignore them.
    data = {k: v for k, v in config.items() if k != "project_dir"}
    if kind == "pre":
        from tit.pre.config import migrate_legacy_keys

        data = migrate_legacy_keys(data)
        if "subject_ids" not in data:
            # The job's own subjects, which the manager writes into config.json
            # (`JobManager._runner_config_path`); only the other fields are checked here.
            data["subject_ids"] = ["subject"]
    if kind in FLEX_KINDS:
        # The manager writes the kind as `mode` into the runner's config.json
        # (JobManager._runner_config_path), so validate the config the runner will read:
        # FlexConfig's mode/goal and per-mode threshold rules depend on it.
        data["mode"] = kind
        if kind == "flex":
            # A single run ignores the adaptive / multi-threshold driver settings, so
            # they cannot stand in for the thresholds it needs.
            data["adaptive"] = data["pareto"] = None
    try:
        deserialize_config(cls, data, strict=True)
    except Exception as exc:
        raise ValueError(
            f"config is not a valid {class_name} for kind {kind!r}: {exc}"
        ) from exc
