"""What the desktop run pages start with, where it differs from or adds to the config class's
own defaults -- one table per job kind (ARCHITECTURE §6, "App defaults").

Three readers, one source:

- ``dev/build_schema.py`` writes :data:`APP_DEFAULTS` into
  ``contracts/generated/config.schema.json`` as ``"x-app-defaults"``, which ``GET /api/schema``
  serves; the Pre-processing, Simulator and Optimizer pages initialise their forms from it, over
  the schema's own ``default`` values (``desktop/src/renderer/forms/appDefaults.tsx``);
- the server fills it into a config sent with ``created_by: "agent"`` (``POST /api/validate``,
  ``/api/plan``, ``/api/jobs/preflight``, ``/api/jobs``, ``/api/jobs/groups``) and into every
  proposal step (:mod:`tit.server.proposals`), so an agent sends only the fields it chose and
  still runs what the app would;
- the agent plugin shows it in ``get_config_schema``.

A kind with no entry (``mex``: the page starts at ``MExConfig``'s own defaults) takes the
dataclass defaults only. Fields the agent sends always win; the merge is one level deep, so an
``electrode`` the agent sends replaces the table's whole ``electrode``.

``pre`` also takes what the Pre-processing page fills from the user's saved Settings
(:mod:`tit.surfer_settings`, the page's ``toSubmitConfig``): the FreeSurfer operations, and for a
QSIPrep or QSIRecon step that settings dict -- processing preferences plus the per-process thread
limit -- under the fields the agent sent in it. Charm options and the other resource limits are
filled for every caller when the job is planned (``resolve_job_threads``).
"""

from __future__ import annotations

import copy
from typing import Any

_FLEX: dict[str, Any] = {
    "goal": "mean",
    "postproc": "max_TI",
    "current_mA": 1.0,
    "electrode": {"shape": "ellipse", "dimensions": [8, 8], "gel_thickness": 4},
    "max_iterations": 500,
    "population_size": 13,
    "tolerance": 0.1,
    "mutation": "0.01,0.5",
    "recombination": 0.7,
}

APP_DEFAULTS: dict[str, dict[str, Any]] = {
    "pre": {
        "convert_dicom": True,
        "run_fastsurfer": True,
        "freesurfer_subregions": ["thalamus", "hippo-amygdala"],
        "create_m2m": True,
        "skip_existing_outputs": True,
    },
    "sim": {
        "map_to_fsavg": False,
        # The dataclass's own default_factory values, which the generated schema cannot carry.
        "electrode_dimensions": [8, 8],
        "output_fields": ["TI_max"],
    },
    "flex": _FLEX,
    # The Optimizer's focality modes: adaptive (its default) and multi-threshold.
    "flex_adaptive": {
        **_FLEX,
        "goal": "focality",
        "adaptive": {"nonroi_percentage": 20, "roi_percentage": 80},
    },
    "flex_pareto": {
        **_FLEX,
        "goal": "focality",
        "pareto": {"roi_pcts": [80], "nonroi_pcts": [20, 30, 40]},
    },
    "ex": {"current_step": 0.2, "channel_limit": 1.6},
}


def with_app_defaults(kind: str, config: Any) -> Any:
    """*config* over the table's entry for *kind* (a copy); anything but a dict is returned
    unchanged, for the caller's own validation to reject."""
    if not isinstance(config, dict):
        return config
    filled = {**copy.deepcopy(APP_DEFAULTS.get(kind, {})), **config}
    return _with_saved_preferences(filled, config) if kind == "pre" else filled


#: QSI step flag -> its settings field and the tool name its preferences are saved under.
_QSI_STEPS = (
    ("run_qsiprep", "qsiprep_config", "qsiprep"),
    ("run_qsirecon", "qsi_recon_config", "qsirecon"),
)


def _with_saved_preferences(
    filled: dict[str, Any], sent: dict[str, Any]
) -> dict[str, Any]:
    """The user's saved choices the Pre-processing page sends, where the agent sent none."""
    from tit.surfer_settings import effective_threads, load_preferences

    preferences = load_preferences()
    for key in ("freesurfer_recon_all", "freesurfer_subregions"):
        if key not in sent:
            filled[key] = copy.deepcopy(preferences[key])
    for flag, field, tool in _QSI_STEPS:
        own = sent.get(field)
        if not filled.get(flag) or not (own is None or isinstance(own, dict)):
            continue
        settings = {**preferences[field], **(own or {})}
        if "omp_threads" not in settings:
            # The page's rule: the saved per-process limit, else every thread the job gets.
            settings["omp_threads"] = preferences[f"{tool}_omp_threads"] or (
                effective_threads(tool, settings.get("cpus"))
            )
        filled[field] = settings
    return filled
