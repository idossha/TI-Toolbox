"""``POST /api/validate/{kind}`` accepts the ``project_dir`` the runner config carries.

What this pins
--------------
The exact body the UI submits must validate. ``tit.jobs.manager._runner_config_path`` writes
``project_dir`` into every runner's ``config.json``, every runner's ``__main__`` pops it, and
``tit.config_io.deserialize_config`` documents it by name as a key that is "silently ignored".
The validate route nevertheless deserialized with ``strict=True`` on the raw body, so a config
the server itself accepted at ``POST /api/jobs`` was reported invalid at
``POST /api/validate/pre``.

Where the numbers come from
---------------------------
Observed on the dev container 2026-09-03 while running the Level A smoke harness
(``dev/smoke.sh pre_dicom``)::

    POST /api/validate/pre -> {"ok": false, "errors": [{"path": "replace_existing_outputs",
      "message": "PreprocessConfig: unknown key(s) ['project_dir']; expected one of [...]"}]}

for the same config shape as the maintainer's succeeded job ``d0036f3cad7b4be9``
(``code/ti-toolbox/jobs/d0036f3cad7b4be9/spec.json`` carries ``"project_dir": "/mnt/000"``).

Reproduce: ``python3 -m pytest -q tests/test_validate_envelope_keys.py``.

Deliberately elsewhere: the rest of the route's kind -> dataclass resolution
(``tests/test_plan_routes.py``); the strictness of nested dataclasses (``tests/test_config_io.py``).

Written 2026-09-03 (lane S1).
"""

from __future__ import annotations

import pytest

from tit.server.routes import validate as validate_route


def _validate(kind: str, config: dict):
    return validate_route.validate(kind, validate_route.ValidateRequest(config=config))


#: The maintainer's succeeded `pre` job spec, verbatim minus the fields the server adds.
PRE_CONFIG = {
    "project_dir": "/mnt/000",
    "subject_ids": ["101"],
    "convert_dicom": True,
    "create_m2m": False,
    "run_fastsurfer": False,
    "fastsurfer_threads": None,
    "run_tissue_analysis": False,
    "run_qsiprep": False,
    "run_qsirecon": False,
    "qsiprep_config": None,
    "qsi_recon_config": None,
    "extract_dti": False,
    "skip_existing_outputs": False,
    "replace_existing_outputs": True,
}


def test_project_dir_does_not_make_a_runnable_config_invalid():
    result = _validate("pre", PRE_CONFIG)
    assert result.ok, [e.message for e in result.errors]


def test_project_dir_is_accepted_for_another_kind_too():
    """Not a `pre` special case: the manager injects project_dir for every module kind.

    The analyzer config is the maintainer's succeeded job 02a18de1d3d047e3 with project_dir
    added, so the only thing that could fail here is the envelope key.
    """
    result = _validate(
        "analyzer",
        {
            "project_dir": "/mnt/000",
            "subject_id": "ernie",
            "simulation": "docs_example",
            "space": "mesh",
            "analysis_type": "spherical",
            "coordinate_space": "subject",
            "center": [-40.0, -10.0, 10.0],
            "radius": 10.0,
        },
    )
    assert result.ok, [e.message for e in result.errors]


def test_a_genuinely_unknown_key_is_still_reported():
    """The strictness that catches a renamed or misspelled field must survive the fix."""
    result = _validate("pre", dict(PRE_CONFIG, convrt_dicom=True))
    assert not result.ok
    assert "convrt_dicom" in result.errors[0].message


def test_envelope_keys_are_named_and_minimal():
    """Only keys the server itself injects may be stripped -- an ever-growing allow-list here
    would turn strict validation back off one key at a time."""
    assert validate_route.ENVELOPE_KEYS == frozenset({"project_dir"})


@pytest.mark.parametrize("kind", ["pre", "analyzer", "sim"])
def test_envelope_strip_never_mutates_the_request_body(kind: str):
    """Only light kinds: `stats`/`nifti_average` pull scipy in at import time, which this
    suite mocks away -- their envelope handling is the same code path as these three."""
    body = {"project_dir": "/mnt/000"}
    _validate(kind, dict(body))
    assert body == {"project_dir": "/mnt/000"}
