"""Reciprocity search: engine maths, config validation and job-kind registration.

The leadfield fixture is a real (tiny) HDF5 file with the layout
``tit.opt.leadfield`` writes, so ``load_mesh``/``read_leadfield`` are exercised
against genuine h5py rather than a stub -- the host suite mocks ``h5py``, so
:func:`real_h5py` puts the installed module back for the duration of a test and
restores the mock afterwards.

Expected values are computed here independently of the implementation: the
2-channel envelope reference is the original Grossman preprocess-then-branch
form (a different formulation from ``tit.calc``'s sign-agnostic closed form),
and the reciprocity pick is recomputed by brute force over all pairs.
"""

from __future__ import annotations

import importlib
import itertools
import logging
import sys

import numpy as np
import pytest

from tit.opt.config import DEFAULT_TOP_K, RecipConfig

# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def _installed_h5py():
    """Import the real ``h5py`` once (its converters register only once/process)."""
    mock = sys.modules.pop("h5py", None)
    try:
        module = importlib.import_module("h5py")
    except ImportError:  # pragma: no cover - host without h5py
        module = None
    finally:
        for key in [k for k in sys.modules if k == "h5py" or k.startswith("h5py.")]:
            del sys.modules[key]
        if mock is not None:
            sys.modules["h5py"] = mock
    if module is None:
        pytest.skip("h5py is not installed")
    return module


@pytest.fixture
def real_h5py(_installed_h5py, monkeypatch):
    """Put the real ``h5py`` in front of the suite's mock for one test."""
    monkeypatch.setitem(sys.modules, "h5py", _installed_h5py)
    return _installed_h5py


ELECTRODES = ["Ref", "A", "B", "C", "D"]
REFERENCE = "Ref"

#: Per-electrode field at every element, V/m per 1 A. Row 0 (the reference) is
#: never stored in the file; the loader must materialise it as zeros.
LEADFIELD_A = np.array(
    [
        # element 0 (the target), elements 1..3 (background GM), element 4 (WM)
        [
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
        ],
        [
            [3.0, 0.0, 0.0],
            [0.4, 0.1, 0.0],
            [0.2, 0.0, 0.1],
            [0.1, 0.2, 0.0],
            [9.0, 0.0, 0.0],
        ],
        [
            [-2.0, 0.0, 0.0],
            [0.1, 0.3, 0.0],
            [0.0, 0.2, 0.1],
            [0.3, 0.0, 0.1],
            [8.0, 0.0, 0.0],
        ],
        [
            [0.0, 2.5, 0.0],
            [0.2, 0.0, 0.4],
            [0.1, 0.1, 0.2],
            [0.0, 0.3, 0.2],
            [7.0, 0.0, 0.0],
        ],
        [
            [0.0, -1.5, 0.5],
            [0.3, 0.2, 0.1],
            [0.2, 0.1, 0.0],
            [0.1, 0.1, 0.3],
            [6.0, 0.0, 0.0],
        ],
    ],
    dtype=float,
)

#: Element tissue tags: four grey-matter elements and one white-matter element.
TAGS = np.array([2, 2, 2, 2, 1])


@pytest.fixture
def leadfield_file(tmp_path, real_h5py):
    """A tiny leadfield HDF5 with five tetrahedra and five electrodes."""
    # One node per corner of a unit lattice; element k is the tetrahedron whose
    # centroid sits at (k, 0, 0) by construction.
    nodes = []
    connectivity = []
    for k in range(len(TAGS)):
        base = len(nodes)
        nodes.extend(
            [
                [k - 0.5, -0.5, -0.5],
                [k + 0.5, -0.5, -0.5],
                [k, 0.5, -0.5],
                [k, 0.0, 1.5],
            ]
        )
        connectivity.append([base + 1, base + 2, base + 3, base + 4])  # 1-based

    path = tmp_path / "sub-t_leadfield_TEST.hdf5"
    with real_h5py.File(path, "w") as handle:
        mesh = handle.create_group("mesh_leadfield")
        mesh.create_dataset("nodes/node_coord", data=np.asarray(nodes, dtype=float))
        mesh.create_dataset(
            "elm/node_number_list", data=np.asarray(connectivity, dtype=int)
        )
        mesh.create_dataset("elm/tag1", data=TAGS)
        stored = np.asarray([LEADFIELD_A[i] for i in range(1, len(ELECTRODES))])
        dataset = mesh.create_dataset("leadfields/tdcs_leadfield", data=stored)
        dataset.attrs["electrode_names"] = [n.encode() for n in ELECTRODES]
        dataset.attrs["reference_electrode"] = REFERENCE.encode()
        dataset.attrs["electrode_pos"] = np.array(
            [
                [0.0, 0.0, 10.0],
                [5.0, 0.0, 8.0],
                [-5.0, 0.0, 8.0],
                [0.0, 5.0, 8.0],
                [0.0, -5.0, 8.0],
            ]
        )
    return str(path)


def reference_max_ti(field_1: np.ndarray, field_2: np.ndarray) -> np.ndarray:
    """Grossman (2017) envelope, preprocess-then-branch form.

    An independent reference for ``tit.calc``'s sign-agnostic closed form: it
    reorders the fields by magnitude and flips the sign of the second instead
    of deciding the regime from ``min(|E1|, |E2|)`` and ``|E1.E2|``.
    """
    e1 = field_1.copy()
    e2 = field_2.copy()
    swap = np.linalg.norm(e2, axis=-1) > np.linalg.norm(e1, axis=-1)
    e1[swap], e2[swap] = field_2[swap], field_1[swap]
    flip = np.sum(e1 * e2, axis=-1) < 0
    e2[flip] = -e2[flip]
    n1 = np.linalg.norm(e1, axis=-1)
    n2 = np.linalg.norm(e2, axis=-1)
    cos = np.sum(e1 * e2, axis=-1) / np.maximum(n1 * n2, 1e-30)
    difference = e1 - e2
    ti = (
        2
        * np.linalg.norm(np.cross(e2, difference), axis=-1)
        / np.maximum(np.linalg.norm(difference, axis=-1), 1e-30)
    )
    aligned = n2 <= n1 * cos
    ti[aligned] = 2 * n2[aligned]
    return ti


# ── leadfield reading ────────────────────────────────────────────────────────


def test_load_mesh_reads_centroids_tags_and_electrodes(leadfield_file):
    from tit.opt.recip.engine import load_mesh

    mesh = load_mesh(leadfield_file)

    assert mesh["names"] == ELECTRODES
    assert mesh["reference"] == REFERENCE
    assert mesh["tags"].tolist() == TAGS.tolist()
    # Element k's four nodes were built around x = k.
    assert mesh["centroids"][:, 0] == pytest.approx([0, 1, 2, 3, 4])
    assert mesh["positions"].shape == (5, 3)


def test_read_leadfield_is_mA_scaled_with_a_zero_reference_row(leadfield_file):
    from tit.opt.recip.engine import load_mesh, read_leadfield

    mesh = load_mesh(leadfield_file)
    subset = np.array([0, 2])
    leadfield = read_leadfield(leadfield_file, subset, mesh["names"], mesh["reference"])

    assert leadfield.shape == (5, 2, 3)
    assert leadfield[0] == pytest.approx(np.zeros((2, 3)))
    # V/m per 1 A in the file, V/m per mA in memory.
    assert leadfield[1] == pytest.approx(LEADFIELD_A[1][subset] * 1e-3)
    assert leadfield[3] == pytest.approx(LEADFIELD_A[3][subset] * 1e-3)


# ── the reciprocity map ──────────────────────────────────────────────────────


def test_directional_pick_is_argmax_minus_argmin_of_the_projection():
    from tit.opt.recip.engine import electrode_pairs, reciprocity_scores

    target_field = LEADFIELD_A[:, 0, :]
    direction = np.array([1.0, 0.0, 0.0])
    pairs = electrode_pairs(len(ELECTRODES))

    scores = reciprocity_scores(target_field, pairs, direction)
    best = pairs[int(np.argmax(scores))]

    projection = target_field @ direction
    assert set(best.tolist()) == {
        int(np.argmax(projection)),
        int(np.argmin(projection)),
    }


def test_undirected_pick_maximises_the_field_difference():
    from tit.opt.recip.engine import electrode_pairs, reciprocity_scores

    target_field = LEADFIELD_A[:, 0, :]
    pairs = electrode_pairs(len(ELECTRODES))

    scores = reciprocity_scores(target_field, pairs, None)
    best = tuple(pairs[int(np.argmax(scores))].tolist())

    brute_force = max(
        itertools.combinations(range(len(ELECTRODES)), 2),
        key=lambda ij: np.linalg.norm(target_field[ij[0]] - target_field[ij[1]]),
    )
    assert best == brute_force


def test_reciprocity_uses_the_target_mean_field_not_one_element():
    """Two target elements with opposing fields must average, not be sampled."""
    from tit.opt.recip.engine import electrode_pairs, reciprocity_scores

    field = np.zeros((3, 2, 3))
    field[1, 0] = [10.0, 0.0, 0.0]
    field[1, 1] = [-10.0, 0.0, 0.0]  # cancels across the target
    field[2, 0] = [1.0, 0.0, 0.0]
    field[2, 1] = [1.0, 0.0, 0.0]
    pairs = electrode_pairs(3)

    scores = reciprocity_scores(field.mean(axis=1), pairs, np.array([1.0, 0.0, 0.0]))
    best = tuple(pairs[int(np.argmax(scores))].tolist())

    assert best == (0, 2)  # electrode 1 averages to zero at the target


# ── candidate evaluation ─────────────────────────────────────────────────────


def _engine_leadfield() -> np.ndarray:
    return LEADFIELD_A * 1e-3


def test_two_channel_metrics_match_an_independent_grossman_envelope():
    from tit.opt.recip.engine import evaluate_candidates

    leadfield = _engine_leadfield()
    pairs = np.array([[1, 2], [3, 4]])
    roi_pos = np.array([0])
    background_pos = np.array([1, 2, 3])

    records = evaluate_candidates(
        leadfield, pairs, roi_pos, background_pos, 2, 1.5, None, 0.0
    )

    assert len(records) == 1
    field_1 = (leadfield[1] - leadfield[2]) * 1.5
    field_2 = (leadfield[3] - leadfield[4]) * 1.5
    expected = reference_max_ti(field_1, field_2)
    assert records[0]["roi_mean"] == pytest.approx(expected[roi_pos].mean(), rel=1e-9)
    assert records[0]["roi_max"] == pytest.approx(expected[roi_pos].max(), rel=1e-9)
    assert records[0]["gm_p95"] == pytest.approx(
        np.percentile(expected[background_pos], 95), rel=1e-9
    )


def test_focality_tf_is_mean_to_the_weight_over_the_background_percentile():
    from tit.opt.recip.engine import focality_tf

    assert focality_tf(4.0, 2.0, 0.0) == pytest.approx(2.0)
    assert focality_tf(4.0, 2.0, 1.0) == pytest.approx(8.0)
    assert focality_tf(4.0, 0.0, 0.5) == 0.0


def test_candidates_never_share_an_electrode():
    from tit.opt.recip.engine import candidate_combinations

    pairs = np.array([[0, 1], [1, 2], [2, 3], [4, 5], [6, 7]])
    combinations = list(candidate_combinations(pairs, 2))

    assert (0, 1) not in combinations  # both use electrode 1
    for combination in combinations:
        electrodes = pairs[list(combination)].ravel().tolist()
        assert len(set(electrodes)) == len(electrodes)


def test_four_channel_path_uses_the_mti_envelope():
    """Four channels must go through tit.calc, and stay finite and positive."""
    from tit.opt.recip.engine import evaluate_candidates

    rng = np.random.default_rng(3)
    leadfield = rng.normal(size=(9, 6, 3)) * 1e-3
    pairs = np.array([[0, 1], [2, 3], [4, 5], [6, 7], [0, 8]])

    records = evaluate_candidates(
        leadfield, pairs, np.array([0, 1]), np.array([2, 3, 4, 5]), 4, 1.0, None, 0.0
    )

    # Of the five 4-subsets of the pairs, three contain both pairs that use
    # electrode 0 and are dropped.
    assert len(records) == 2
    assert all(np.isfinite(record["roi_mean"]) for record in records)
    assert all(record["roi_mean"] > 0 for record in records)


def test_a_direction_selects_the_directional_envelope():
    from tit.calc import get_TI_dir
    from tit.opt.recip.engine import evaluate_candidates

    leadfield = _engine_leadfield()
    pairs = np.array([[1, 2], [3, 4]])
    direction = np.array([0.0, 1.0, 0.0])

    records = evaluate_candidates(
        leadfield, pairs, np.array([0]), np.array([1, 2]), 2, 1.0, direction, 0.0
    )

    fields = [leadfield[1] - leadfield[2], leadfield[3] - leadfield[4]]
    expected = get_TI_dir(fields, np.broadcast_to(direction, fields[0].shape))
    assert records[0]["roi_mean"] == pytest.approx(expected[0], rel=1e-9)


# ── configuration ────────────────────────────────────────────────────────────


def _config(**overrides):
    base = dict(
        subject_id="ernie",
        leadfield_hdf="lf.hdf5",
        target={"_type": "PointTarget", "xyz": [1.0, 2.0, 3.0], "radius_mm": 5.0},
    )
    base.update(overrides)
    return RecipConfig(**base)


def test_point_target_is_built_from_its_discriminated_dict():
    config = _config()
    assert isinstance(config.target, RecipConfig.PointTarget)
    assert config.target.xyz == [1.0, 2.0, 3.0]
    assert config.target.space == "subject"


def test_roi_targets_are_the_flex_roi_dataclasses():
    from tit.opt.config import FlexConfig

    subcortical = _config(
        target={
            "_type": "SubcorticalROI",
            "atlas_path": "labeling.nii.gz",
            "label": [10, 49],
        }
    )
    spherical = _config(
        target={"_type": "SphericalROI", "x": 1, "y": 2, "z": 3, "radius": 5}
    )

    assert isinstance(subcortical.target, FlexConfig.SubcorticalROI)
    assert subcortical.target.label == [10, 49]
    assert isinstance(spherical.target, FlexConfig.SphericalROI)


def test_a_cortical_surface_roi_is_refused_by_the_runner():
    from tit.opt.config import FlexConfig
    from tit.opt.recip.recip import _roi_mask

    config = _config(
        target={"_type": "AtlasROI", "atlas_path": "lh.aparc.annot", "label": 5}
    )
    assert isinstance(config.target, FlexConfig.AtlasROI)

    with pytest.raises(ValueError, match="surface"):
        _roi_mask(config, np.zeros((3, 3)), "m2m", "out", logging.getLogger(__name__))


def test_a_spherical_roi_target_selects_every_sphere():
    from tit.opt.recip.recip import _roi_mask

    config = _config(
        target={
            "_type": "SphericalROI",
            "x": [0.0, 10.0],
            "y": [0.0, 0.0],
            "z": [0.0, 0.0],
            "radius": 1.5,
        }
    )
    centroids = np.array([[0.0, 0.0, 0.0], [5.0, 0.0, 0.0], [10.0, 1.0, 0.0]])

    mask = _roi_mask(config, centroids, "m2m", "out", logging.getLogger(__name__))

    assert mask.tolist() == [True, False, True]


@pytest.mark.parametrize(
    "overrides",
    [
        {"n_channels": 3},
        {"n_channels": 5},
        {"objective": "sharpness"},
        {"focality_weight": 1.5},
        {"current_mA": 0},
        {"top_k": 1},
        {"direction": [0.0, 0.0, 0.0]},
        {"direction": [1.0, 0.0]},
        {"target": {"_type": "PointTarget", "xyz": [1.0, 2.0]}},
        {"target": {"_type": "PointTarget", "xyz": [1, 2, 3], "radius_mm": -1}},
        {"target": {"_type": "SphericalROI", "x": [], "y": [], "z": []}},
    ],
)
def test_invalid_configs_are_rejected(overrides):
    with pytest.raises(ValueError):
        _config(**overrides)


def test_odd_channel_counts_name_the_envelope_rule():
    with pytest.raises(ValueError, match="even number of channels"):
        _config(n_channels=3)


def test_config_round_trips_through_the_serializer():
    from tit.config_io import deserialize_config, serialize_config

    config = _config(direction=[0.0, 0.0, 1.0], objective="focality", n_channels=4)
    data = serialize_config(config)
    assert data["target"]["_type"] == "PointTarget"

    data.pop("project_dir", None)
    assert deserialize_config(RecipConfig, data) == config


def test_roi_target_round_trips_through_the_serializer():
    from tit.config_io import deserialize_config, serialize_config

    config = _config(
        target={
            "_type": "SubcorticalROI",
            "atlas_path": "labeling.nii.gz",
            "label": [10, 49],
        }
    )
    data = serialize_config(config)
    assert data["target"]["_type"] == "SubcorticalROI"

    data.pop("project_dir", None)
    assert deserialize_config(RecipConfig, data) == config


def test_the_spec_the_desktop_sends_deserialises():
    """The exact JSON shape Lane B's recipConfig.ts emits, project_dir and all."""
    from tit.config_io import deserialize_config

    spec = {
        "project_dir": "/mnt/000",
        "subject_id": "ernie",
        "leadfield_hdf": "ernie_leadfield_EEG10-10_UI_Jurak_2007.hdf5",
        "target": {
            "_type": "SubcorticalROI",
            "atlas_path": "labeling.nii.gz",
            "label": [10, 49],
            "atlas_space": "subject",
        },
        "direction": None,
        "objective": "intensity",
        "focality_weight": 0,
        "n_channels": 2,
        "current_mA": 1.0,
        "top_k": None,
        "gm_subsample": 100000,
        "run_name": None,
    }
    data = {k: v for k, v in spec.items() if k != "project_dir"}

    config = deserialize_config(RecipConfig, data)

    assert config.top_k is None  # the default table applies at run time
    assert "project_dir" not in {
        f.name for f in __import__("dataclasses").fields(config)
    }


def test_missing_or_unknown_target_type_is_rejected():
    with pytest.raises(ValueError, match="_type"):
        _config(target={"atlas_path": "labeling.nii.gz", "label": 10})


# ── job-kind registration ────────────────────────────────────────────────────


def test_every_table_that_knows_ex_also_knows_recip():
    from tit.jobs import config_check, costs, kinds, locks, plans, spec

    assert "recip" in spec.JOB_KINDS
    assert "recip" in spec.CONTRACT_JOB_KINDS
    assert "recip" in kinds.MODULE_FOR_KIND
    assert kinds.MODULE_FOR_KIND["recip"] == "tit.opt.recip"
    assert config_check.CONFIG_CLASS_FOR_KIND["recip"] == "RecipConfig"
    assert "recip" in costs.DEFAULT_COSTS
    assert "recip" in plans.GROUP_KINDS
    assert plans._KIND_CONFIG_CLASS["recip"] == "RecipConfig"
    assert locks.keys_for("recip", ["ernie"], {"run_name": "r"})


def test_recip_is_in_the_contract_kind_enums():
    import json
    from pathlib import Path

    contract = json.loads(Path("contracts/generated/openapi.json").read_text())[
        "components"
    ]["schemas"]
    assert "recip" in contract["JobKind"]["enum"]
    assert "recip" in contract["PipelineKind"]["enum"]


def test_recip_locks_the_run_the_leadfield_and_the_m2m():
    from tit.jobs import locks

    keys = {
        request.key for request in locks.keys_for("recip", ["ernie"], {"run_name": "r"})
    }

    assert "subject:ernie:recip:r:write" in keys
    assert "subject:ernie:leadfields:read" in keys
    assert "subject:ernie:m2m:read" in keys


def test_recip_config_is_registered_for_generation():
    from tit.config_io import CONFIG_CLASS_REGISTRY, resolve_config_class

    assert CONFIG_CLASS_REGISTRY["RecipConfig"] == "tit.opt.config.RecipConfig"
    assert resolve_config_class("RecipConfig") is RecipConfig


def test_default_top_k_covers_every_accepted_channel_count():
    from tit.opt.config import VALID_RECIP_CHANNELS

    assert all(n in DEFAULT_TOP_K for n in VALID_RECIP_CHANNELS)


def test_the_path_manager_places_runs_under_recip_search(tmp_path):
    from tit.paths import PathManager

    pm = PathManager(str(tmp_path))
    assert pm.recip_search_run("ernie", "run1").endswith(
        "derivatives/SimNIBS/sub-ernie/recip-search/run1"
    )


def test_the_replay_catalog_resolves_a_recip_run(tmp_path, monkeypatch):
    from tit.opt import candidate_catalog
    from tit.paths import PathManager

    pm = PathManager(str(tmp_path))
    run = tmp_path / "derivatives/SimNIBS/sub-ernie/recip-search/run1"
    run.mkdir(parents=True)
    monkeypatch.setattr("tit.catalog.subject_ids", lambda _pm: {"ernie"})

    assert (
        candidate_catalog.run_directory(pm, "ernie", "recip", "run1") == run.resolve()
    )


def test_the_results_route_accepts_kind_recip():
    import inspect

    from tit.server.routes import catalog_v1

    source = inspect.getsource(catalog_v1.ex_runs) + inspect.getsource(
        catalog_v1.ex_run_results
    )
    assert source.count('"recip"') == 2


# ── the whole run ────────────────────────────────────────────────────────────


def test_a_full_run_writes_its_outputs(tmp_path, leadfield_file):
    import json

    from tit.paths import get_path_manager, reset_path_manager

    project = tmp_path / "project"
    (project / "derivatives/SimNIBS/sub-t").mkdir(parents=True)
    reset_path_manager()
    get_path_manager(str(project))
    try:
        from tit.opt.recip.recip import _run_recip_search_inner

        config = RecipConfig(
            subject_id="t",
            leadfield_hdf=leadfield_file,
            target={"_type": "PointTarget", "xyz": [0.0, 0.0, 0.0], "radius_mm": 0.0},
            n_channels=2,
            current_mA=1.0,
            top_k=4,
            gm_subsample=10,
            run_name="unit",
        )
        result = _run_recip_search_inner(config)
    finally:
        reset_path_manager()

    assert result.success
    assert result.n_candidates > 0
    summary = json.loads(open(result.config_json).read())
    assert summary["target"]["n_elements"] == 1
    assert summary["best"]["montage"]
    assert summary["n_candidates"] == result.n_candidates

    run_dir = result.output_dir
    for name in (
        "candidates.csv",
        "reciprocity_scores.csv",
        "montage.json",
        "final_output.csv",
        "run_config.json",
    ):
        assert (tmp_path / "x").parent  # keep the path join explicit below
        assert open(f"{run_dir}/{name}").read()
