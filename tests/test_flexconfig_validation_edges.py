"""FlexConfig refuses at config time what the flex runner, the builder or SimNIBS would refuse later.

What this pins (package p08, 2026-10-22): every rule below used to surface only after a job had
started -- in ``run_flex_search`` (min distance, restarts), in the builder after the ROI was
confirmed (an unequal ellipse), or inside SimNIBS (a focality run without a threshold) -- or not
at all (NaN currents, reversed thresholds). Each case is refused by ``FlexConfig.__post_init__``
with a message naming the field, so ``check_job_config`` turns it into a 422 at submit.

Where the expected outcomes come from (never from the code under test):

* thresholds -- the Optimizer's help text ("One value: non-ROI max = ROI min. Two: non-ROI max,
  ROI min. In V/m.") and SimNIBS's ``measures.ROC`` docstring, read from the v3.1.1 image:
  "Either a single value or two values can be given. If two values are given, the first threshold
  may not be exceeded in the non-ROI and the second value should be exceeded in the ROI in the
  sense of a safety gap" -- so a third value was silently ignored and a reversed pair breaks the
  gap. A single focality run with no threshold fails in SimNIBS with "Please define
  TESoptimze.threshold for focality optimization!"
  (``resources/map-electrodes/tes_flex_optimization.py`` lines 510-515, which the image installs).
  ``None``/``""``/``"dynamic"``/``"auto"`` are the documented "unset" spellings.
* currents, radii, sizes, distances: physics (a current, a radius, a size, a distance is > 0 and
  finite); ``run_flex_search`` already refused ``min_electrode_distance <= 0`` at run time.
* ellipse: the builder's own sentence -- SimNIBS's flex electrode is a disc with one radius.
* atlas space: ``SubcorticalROI`` documents ``"subject"`` or ``"mni"``; ``confirm_roi`` lowercases.
* run names: ``tit.paths.NAME_RE``'s documented grammar (letters, digits, ``.``, ``_``, ``-``,
  inner spaces; no leading dot or space); a folder outside it makes ``catalog.flex_runs`` raise
  for the whole subject (audit_flex #3).

Reproduce: ``.venv/bin/python -m pytest tests/test_flexconfig_validation_edges.py -q``.
Deliberately elsewhere: the desktop half of the same bounds (``desktop/tests/unit/
flex-form-gates.test.ts``), the per-mode threshold rules with the drivers
(``tests/test_flex_focality_modes.py``), and listing a badly named run that already exists
(``tests/test_flex_run_name_listing.py``).
"""

from __future__ import annotations

import pytest

from tit.jobs.config_check import check_job_config
from tit.opt.config import FlexConfig

SPHERE = {"x": -42.0, "y": -20.0, "z": 55.0, "radius": 10.0}


def _cfg(**overrides) -> FlexConfig:
    fields = dict(
        subject_id="001",
        goal="mean",
        postproc="max_TI",
        current_mA=1.0,
        electrode=FlexConfig.ElectrodeConfig(),
        roi=FlexConfig.SphericalROI(**SPHERE),
    )
    fields.update(overrides)
    return FlexConfig(**fields)


def _wire(**overrides) -> dict:
    """A minimal flex job config as the desktop sends it (JSON, no mode)."""
    body = {
        "subject_id": "001",
        "goal": "mean",
        "postproc": "max_TI",
        "current_mA": 1.0,
        "electrode": {"shape": "ellipse", "dimensions": [8, 8], "gel_thickness": 4},
        "roi": {"_type": "SphericalROI", "x": [-42.0], "y": [-20.0], "z": [55.0]},
    }
    body.update(overrides)
    return body


# -- thresholds ------------------------------------------------------------------------------


@pytest.mark.parametrize("unset", [None, "", "   ", "dynamic", "auto", "AUTO"])
def test_unset_threshold_spellings_are_stored_as_none_where_none_are_needed(unset):
    # A goal that ignores thresholds, and the adaptive driver, which derives them.
    assert _cfg(goal="mean", thresholds=unset).thresholds is None
    assert (
        _cfg(goal="focality", mode="flex_adaptive", thresholds=unset).thresholds is None
    )


@pytest.mark.parametrize("unset", [None, "", "dynamic", "auto"])
def test_a_single_focality_run_without_thresholds_is_refused(unset):
    with pytest.raises(ValueError, match="requires thresholds"):
        _cfg(goal="focality", thresholds=unset)


@pytest.mark.parametrize(
    "text",
    [
        "0.1,",  # a trailing comma: an empty second value
        "nan",
        "inf",
        "nan,inf",
        "-0.1",
        "0",
        "0.1,0.2,0.3",  # SimNIBS reads two values at most
        "0.5,0.1",  # non-ROI max above ROI min: no safety gap
        "abc",
    ],
)
def test_malformed_thresholds_are_refused_naming_the_field(text):
    with pytest.raises(ValueError, match="thresholds") as exc:
        _cfg(goal="focality", thresholds=text)
    assert "could not convert" not in str(exc.value)


@pytest.mark.parametrize("text", ["0.2", "0.1,0.3", "0.2,0.2", " 0.1 , 0.3 "])
def test_one_or_two_ordered_positive_thresholds_are_accepted(text):
    assert _cfg(goal="focality", thresholds=text).thresholds == text


# -- physical quantities ---------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_current_must_be_a_positive_finite_number(value):
    with pytest.raises(ValueError, match="current_mA"):
        _cfg(current_mA=value)


@pytest.mark.parametrize("radius", [0, -5, float("nan"), [10.0, 0.0]])
def test_sphere_radius_must_be_positive(radius):
    with pytest.raises(ValueError, match="radius"):
        FlexConfig.SphericalROI(x=[0.0, 1.0], y=[0.0, 1.0], z=[0.0, 1.0], radius=radius)


@pytest.mark.parametrize("axis", ["x", "y", "z"])
@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_sphere_centre_must_be_finite(axis, bad):
    centre = {"x": 1.0, "y": 2.0, "z": 3.0, axis: bad}
    with pytest.raises(ValueError, match=f"SphericalROI {axis}"):
        FlexConfig.SphericalROI(**centre)


@pytest.mark.parametrize("value", [0, -1, float("nan")])
def test_min_electrode_distance_must_be_positive(value):
    with pytest.raises(ValueError, match="min_electrode_distance"):
        _cfg(min_electrode_distance=value)


def test_min_electrode_distance_zero_is_refused_at_submit_not_in_the_runner():
    with pytest.raises(ValueError, match="min_electrode_distance"):
        check_job_config("flex", _wire(min_electrode_distance=0))
    check_job_config("flex", _wire(min_electrode_distance=0.5))


@pytest.mark.parametrize(
    ("field", "value"), [("n_multistart", 0), ("cpus", 0), ("n_multistart", 1.5)]
)
def test_restart_and_cpu_counts_are_whole_numbers_of_at_least_one(field, value):
    with pytest.raises(ValueError, match=field):
        _cfg(**{field: value})


def test_unequal_ellipse_is_refused_but_a_rectangle_may_differ():
    with pytest.raises(ValueError, match="circular electrodes only"):
        FlexConfig.ElectrodeConfig(shape="ellipse", dimensions=[8, 10])
    rect = FlexConfig.ElectrodeConfig(shape="rect", dimensions=[10, 6])
    assert rect.dimensions == [10.0, 6.0]
    with pytest.raises(ValueError, match="circular electrodes only"):
        check_job_config(
            "flex",
            _wire(
                electrode={
                    "shape": "ellipse",
                    "dimensions": [8, 10],
                    "gel_thickness": 4,
                }
            ),
        )


@pytest.mark.parametrize(
    ("electrode", "field"),
    [
        ({"dimensions": [0, 8]}, "dimensions"),
        ({"dimensions": [8]}, "dimensions"),
        ({"gel_thickness": 0}, "gel_thickness"),
        ({"gel_thickness": float("nan")}, "gel_thickness"),
        ({"shape": "triangle"}, "shape"),
    ],
)
def test_electrode_sizes_must_be_positive(electrode, field):
    with pytest.raises(ValueError, match=field):
        FlexConfig.ElectrodeConfig(**electrode)


# -- regions ---------------------------------------------------------------------------------


@pytest.mark.parametrize(("given", "stored"), [("MNI", "mni"), ("Subject", "subject")])
def test_subcortical_atlas_space_has_one_spelling(given, stored):
    roi = FlexConfig.SubcorticalROI(atlas_path="a.nii.gz", label=10, atlas_space=given)
    assert roi.atlas_space == stored


def test_subcortical_atlas_space_outside_subject_and_mni_is_refused():
    with pytest.raises(ValueError, match="atlas_space"):
        FlexConfig.SubcorticalROI(atlas_path="a.nii.gz", label=10, atlas_space="native")


@pytest.mark.parametrize("goal", ["focality", "focality_tf"])
def test_a_non_roi_identical_to_the_roi_is_refused_under_a_focality_goal(goal):
    extra = {"thresholds": "0.1,0.2"} if goal == "focality" else {}
    with pytest.raises(ValueError, match="identical"):
        _cfg(
            goal=goal,
            non_roi_method="specific",
            non_roi=FlexConfig.SphericalROI(**SPHERE),
            **extra,
        )
    # A different region is fine.
    _cfg(
        goal=goal,
        non_roi_method="specific",
        non_roi=FlexConfig.SphericalROI(**{**SPHERE, "x": 42.0}),
        **extra,
    )


# -- messages and names ----------------------------------------------------------------------


def test_detailed_results_with_observe_background_names_observe_background():
    with pytest.raises(ValueError) as exc:
        _cfg(detailed_results=True, observe_background=True)
    message = str(exc.value)
    assert "observe_background=True" in message
    assert "optimize_current_ratio" not in message


@pytest.mark.parametrize(
    "folder",
    [
        "/p/derivatives/SimNIBS/sub-001/flex-search/Thalamus (L)",
        "/p/derivatives/SimNIBS/sub-001/flex-search/.hidden",
        "/p/derivatives/SimNIBS/sub-001/flex-search/ lead",
        "/p/derivatives/SimNIBS/sub-001/flex-search/a+b",
        "/p/derivatives/SimNIBS/sub-001/flex-search/ü",
    ],
)
def test_an_output_folder_whose_run_name_breaks_the_name_rule_is_refused(folder):
    with pytest.raises(ValueError, match="run name"):
        _cfg(output_folder=folder)


@pytest.mark.parametrize(
    "folder",
    [
        "/p/derivatives/SimNIBS/sub-001/flex-search/Thalamus_L",
        "/p/derivatives/SimNIBS/sub-001/flex-search/run 2",
        "/p/derivatives/SimNIBS/sub-001/flex-search/20261022_120000_000_mean-sphere/",
        "insula_mean",
    ],
)
def test_run_names_inside_the_name_rule_are_accepted(folder):
    assert _cfg(output_folder=folder).output_folder == folder


# -- driver settings stand in for thresholds only where a driver runs ------------------------


def test_adaptive_settings_without_a_mode_are_a_driver_config():
    """/api/validate, /api/plan and group planning see the desktop's body without ``mode``
    (the kind supplies it); the adaptive settings it carries mean a driver derives the
    thresholds, so the body is valid there -- and the submit guard, which knows the kind,
    refuses the same body as a single run, which ignores those settings."""
    body = _wire(
        goal="focality", adaptive={"roi_percentage": 80, "nonroi_percentage": 20}
    )
    cfg = _cfg(goal="focality", adaptive=FlexConfig.AdaptiveFocalityConfig())
    assert cfg.thresholds is None
    check_job_config("flex_adaptive", body)
    with pytest.raises(ValueError, match="requires thresholds"):
        check_job_config("flex", body)
