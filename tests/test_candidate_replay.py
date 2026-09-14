"""Candidate replay pins analytic rigid poses, channel order and signed currents.

Distinct quarter-turn rotations catch copying the first pair's orientation onto
later pairs. Expected y-directions are authored coordinates, not a replay helper.
"""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from tit.sim.config import Montage, MontageMode, SimulationConfig

CENTRES = [[11, 23, 37], [-13, 29, 41], [17, -31, 43], [19, 47, -53]]
ROTATIONS = [
    [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
    [[0, -1, 0], [1, 0, 0], [0, 0, 1]],
    [[-1, 0, 0], [0, -1, 0], [0, 0, 1]],
    [[0, 1, 0], [-1, 0, 0], [0, 0, 1]],
]
EXPECTED_Y = [[11, 43, 37], [-33, 29, 41], [17, -51, 43], [39, 47, -53]]


def make_montage(pair_count=2):
    centres = deepcopy(CENTRES * (pair_count // 2))
    rotations = ROTATIONS * (pair_count // 2)
    poses = [
        [row + [centre[i]] for i, row in enumerate(rotation)] + [[0, 0, 0, 1]]
        for centre, rotation in zip(centres, rotations)
    ]
    return Montage(
        name="candidate",
        mode=MontageMode.FLEX_FREE,
        electrode_pairs=[tuple(centres[i : i + 2]) for i in range(0, len(centres), 2)],
        electrode_poses=poses,
        provenance={"candidate_id": "authored"},
    )


class FakeTdcs:
    def __init__(self):
        self.electrode = []
        self.cond = []

    def add_electrode(self):
        electrode = SimpleNamespace()
        self.electrode.append(electrode)
        return electrode


class FakeSession:
    def __init__(self):
        self.poslists = []

    def add_tdcslist(self, tdcs=None):
        tdcs = tdcs if tdcs is not None else FakeTdcs()
        self.poslists.append(tdcs)
        return tdcs


def build_session(pair_count, session):
    from tit.sim.TI import TISimulation
    from tit.sim.mTI import mTISimulation

    cls = TISimulation if pair_count == 2 else mTISimulation
    sim = object.__new__(cls)
    sim.montage = make_montage(pair_count)
    sim.config = SimulationConfig(
        subject_id="fixture",
        montages=[sim.montage],
        intensities=[1.0, 3.0, 2.0, 4.0][:pair_count],
        electrode_shape="rect",
        electrode_dimensions=[12.0, 8.0],
        gel_thickness=5.0,
        rubber_thickness=2.0,
    )
    sim._init_session = lambda output_dir: session
    return sim._build_session("unused")


def assert_session(session, pair_count):
    expected_currents = [
        [0.001, -0.001],
        [0.003, -0.003],
        [0.002, -0.002],
        [0.004, -0.004],
    ]
    assert len(session.poslists) == pair_count
    for pair_index, tdcs in enumerate(session.poslists):
        assert list(tdcs.currents) == expected_currents[pair_index]
        for electrode_index, electrode in enumerate(tdcs.electrode):
            index = (2 * pair_index + electrode_index) % 4
            assert list(electrode.centre) == CENTRES[index]
            assert list(electrode.pos_ydir) == EXPECTED_Y[index]
            assert electrode.channelnr == electrode_index + 1
            assert electrode.shape == "rect"
            assert list(electrode.dimensions) == [12.0, 8.0]
            assert list(electrode.thickness) == [5.0, 2.0]


@pytest.mark.parametrize("pair_count", [2, 4])
def test_every_pair_keeps_its_own_pose_current_and_geometry(pair_count):
    assert_session(build_session(pair_count, FakeSession()), pair_count)


@pytest.mark.parametrize(
    "bad_pose",
    [
        None,
        [[0] * 4] * 3,
        [None] * 4,
        [[1, 0, 0, 11], [0, 1, 0, 23], [0, 0, -1, 37], [0, 0, 0, 1]],
        [[1, 1, 0, 11], [0, 1, 0, 23], [0, 0, 1, 37], [0, 0, 0, 1]],
        [[1, 0, 0, float("nan")], [0, 1, 0, 23], [0, 0, 1, 37], [0, 0, 0, 1]],
        [[1, 0, 0, 11], [0, 1, 0, 23], [0, 0, 1, 37], [0, 0, 0, 2]],
        [[1, 0, 0, "11"], [0, 1, 0, 23], [0, 0, 1, 37], [0, 0, 0, 1]],
    ],
)
def test_malformed_or_reflected_pose_is_rejected(bad_pose):
    montage = make_montage()
    montage.electrode_poses[0] = bad_pose
    with pytest.raises(ValueError):
        montage.__post_init__()


@pytest.mark.parametrize("coordinate", [999.0, float("nan"), float("inf")])
def test_mismatched_or_nonfinite_centre_is_rejected(coordinate):
    montage = make_montage()
    montage.electrode_pairs[0][0][0] = coordinate
    with pytest.raises(ValueError):
        montage.__post_init__()


@pytest.mark.parametrize("poses", [3, "poses", []])
def test_pose_collection_must_match_xyz_electrodes(poses):
    montage = make_montage()
    montage.electrode_poses = poses
    with pytest.raises(ValueError, match="one pose per XYZ electrode"):
        montage.__post_init__()
