"""Reject a job config the runner could not deserialise, at submit time instead of at run time.

Background (the regression this exists for): a client POSTed ``{"__mock_fast": true}`` as a
``sim`` config. ``POST /api/jobs`` accepted it, the manager wrote ``config.json``, and the job
only failed minutes later inside the runner with

    TypeError: SimulationConfig.__init__() missing 2 required positional arguments:
    'subject_id' and 'montages'

which reaches the user as a dead job with a stack trace rather than a rejected request. The
runners for these kinds call :func:`tit.config_io.deserialize_config` directly and have no
fallback, so exactly the same call made here at submit time turns that into a 422.

Only kinds whose ``__main__`` deserialises one class with no fallback are listed. ``pre``,
``analyzer`` and ``source`` deliberately tolerate a config ``deserialize_config`` rejects (they
fall back to a filtered constructor), so pre-validating them here would reject configs those
runners can genuinely run.
"""

from __future__ import annotations

from typing import Any

#: kind -> :data:`tit.config_io.CONFIG_CLASS_REGISTRY` key.
CONFIG_CLASS_FOR_KIND: dict[str, str] = {
    "sim": "SimulationConfig",
    "flex": "FlexConfig",
    "flex_adaptive": "FlexConfig",
    "flex_pareto": "FlexConfig",
    "ex": "ExConfig",
    "mex": "MExConfig",
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
    # Mirrors the runner: `project_dir` is popped before deserialising, and unknown keys are
    # ignored (strict=False). What is left is the required/typed-field check.
    data = {k: v for k, v in config.items() if k != "project_dir"}
    try:
        deserialize_config(cls, data)
    except Exception as exc:
        raise ValueError(
            f"config is not a valid {class_name} for kind {kind!r}: {exc}"
        ) from exc
