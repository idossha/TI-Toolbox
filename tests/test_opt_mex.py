"""Tests for tit/opt/mex/ -- multipolar (4-pair, 8-electrode) exhaustive search.

Covers candidate generation (logic.py), the electrode mirror map and
generalized bucket loader (ex/buckets.py), MExConfig round trips through
config_io, the engine's ROI metric computation, and the carrier-grouping
(``channels``) behavior that replaces the rejected recursive mTI dispatch.
"""

import csv
import json
import math
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Ensure simnibs.utils.TI_utils is mocked before tit.opt.mex.engine (or
# tit.opt.ex.engine, which it subclasses) is imported.
for mod_name in ("simnibs.utils.TI_utils",):
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()


# ---------------------------------------------------------------------------
# tit.opt.mex.logic -- candidate generation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenerateMultipolarCombinations:
    def test_bucket_cartesian_filters_non_distinct_electrodes(self):
        from tit.opt.mex.logic import generate_multipolar_combinations

        # e1_plus has two options; one ("X") collides with e4_minus, so only
        # the combination built from "A" survives the all-distinct filter.
        buckets = {
            "e1_plus": ["A", "X"],
            "e1_minus": ["B"],
            "e2_plus": ["C"],
            "e2_minus": ["D"],
            "e3_plus": ["E"],
            "e3_minus": ["F"],
            "e4_plus": ["G"],
            "e4_minus": ["X"],
        }
        combos = list(generate_multipolar_combinations(buckets, all_combinations=False))
        assert combos == [("A", "B", "C", "D", "E", "F", "G", "X")]

    def test_pool_mode_generates_permutations(self):
        from tit.opt.mex.logic import (
            count_multipolar_combinations,
            generate_multipolar_combinations,
        )

        pool = [f"E{i}" for i in range(1, 9)]
        count = count_multipolar_combinations(pool, all_combinations=True)
        assert count == math.factorial(8)

        combos = list(generate_multipolar_combinations(pool, all_combinations=True))
        assert len(combos) == count
        # Every candidate uses each pool electrode exactly once.
        for combo in combos[:50]:
            assert len(combo) == 8
            assert set(combo) == set(pool)

    def test_symmetric_within_pairs_collapses_cartesian_to_linear(self):
        """|e1+| x |e1-| candidates collapse to ~|e1+| under symmetric mode."""
        from tit.opt.mex.logic import count_multipolar_combinations

        # Every bucket's electrodes need a mirror partner: the within-pair
        # matcher requires all four pairs to resolve simultaneously (it is a
        # product across pairs), not just e1.
        mirror_map = {
            "L1": "R1",
            "R1": "L1",
            "L2": "R2",
            "R2": "L2",
            "X": "Y",
            "Y": "X",
            "P": "Q",
            "Q": "P",
            "M": "N",
            "N": "M",
        }
        buckets = {
            "e1_plus": ["L1", "L2"],
            "e1_minus": ["R1", "R2"],
            "e2_plus": ["X"],
            "e2_minus": ["Y"],
            "e3_plus": ["P"],
            "e3_minus": ["Q"],
            "e4_plus": ["M"],
            "e4_minus": ["N"],
        }

        # Unrestricted: full 2x2 cartesian product of e1_plus x e1_minus.
        unrestricted = count_multipolar_combinations(buckets, all_combinations=False)
        assert unrestricted == 4

        # Symmetric: only mirrored (L1,R1) and (L2,R2) pairs survive -- linear
        # in |e1+|, not |e1+| x |e1-|.
        symmetric = count_multipolar_combinations(
            buckets, all_combinations=False, symmetry_mirror_map=mirror_map
        )
        assert symmetric == len(buckets["e1_plus"])
        assert symmetric == 2


# ---------------------------------------------------------------------------
# tit.opt.ex.buckets -- build_electrode_mirror_map
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildElectrodeMirrorMap:
    def test_maps_left_right_pairs_and_midline_to_self(self, tmp_path):
        from tit.opt.ex.buckets import build_electrode_mirror_map

        csv_path = tmp_path / "net.csv"
        csv_path.write_text(
            "L1,-30,10,5\n"
            "R1,30,10,5\n"
            "L2,-20,-40,5\n"
            "R2,20,-40,5\n"
            "CZ,0,50,80\n"
        )

        mirror = build_electrode_mirror_map(csv_path)

        assert mirror["L1"] == "R1"
        assert mirror["R1"] == "L1"
        assert mirror["L2"] == "R2"
        assert mirror["R2"] == "L2"
        assert mirror["CZ"] == "CZ"


# ---------------------------------------------------------------------------
# tit.opt.ex.buckets -- generalized bucket loader (4-key default, 8-key mex)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGeneralizedBucketLoader:
    def test_default_4key_json_roundtrip_unchanged(self, tmp_path):
        from tit.opt.ex.buckets import BUCKET_KEYS, load_bucket_file, save_bucket_file

        buckets = {
            "e1_plus": ["A", "B"],
            "e1_minus": ["C"],
            "e2_plus": ["D"],
            "e2_minus": ["E", "F"],
        }
        path = tmp_path / "buckets.json"
        save_bucket_file(path, buckets)
        loaded = load_bucket_file(path)

        assert loaded == buckets
        assert set(loaded) == set(BUCKET_KEYS)

    def test_default_4key_aliases_still_curated(self):
        """Existing 4-key callers keep the hand-curated BUCKET_ALIASES table."""
        from tit.opt.ex.buckets import normalize_buckets

        result = normalize_buckets({"e1_": ["Z"], "E2+": ["Y"]})
        assert result["e1_minus"] == ["Z"]
        assert result["e2_plus"] == ["Y"]

    def test_8key_json_roundtrip(self, tmp_path):
        from tit.opt.ex.buckets import load_bucket_file, save_bucket_file
        from tit.opt.mex.logic import MEX_BUCKET_KEYS

        buckets = {key: [f"{key}_A", f"{key}_B"] for key in MEX_BUCKET_KEYS}
        path = tmp_path / "mex_buckets.json"
        save_bucket_file(path, buckets, keys=MEX_BUCKET_KEYS)
        loaded = load_bucket_file(path, keys=MEX_BUCKET_KEYS)

        assert loaded == buckets
        assert set(loaded) == set(MEX_BUCKET_KEYS)

    def test_8key_csv_roundtrip_with_symbol_aliases(self, tmp_path):
        from tit.opt.ex.buckets import load_bucket_file
        from tit.opt.mex.logic import MEX_BUCKET_KEYS

        csv_path = tmp_path / "mex_buckets.csv"
        csv_path.write_text(
            "e1+,A,B\n"
            "e1-,C\n"
            "e2+,D\n"
            "e2-,E\n"
            "e3+,F\n"
            "e3-,G\n"
            "e4+,H\n"
            "e4-,I\n"
        )
        loaded = load_bucket_file(csv_path, keys=MEX_BUCKET_KEYS)

        assert loaded["e1_plus"] == ["A", "B"]
        assert loaded["e3_minus"] == ["G"]
        assert loaded["e4_plus"] == ["H"]


# ---------------------------------------------------------------------------
# MExConfig -- construction and config_io round trip
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMExConfigValidation:
    def _bucket_electrodes(self, **overrides):
        defaults = dict(
            e1_plus=["A"],
            e1_minus=["B"],
            e2_plus=["C"],
            e2_minus=["D"],
            e3_plus=["E"],
            e3_minus=["F"],
            e4_plus=["G"],
            e4_minus=["H"],
        )
        defaults.update(overrides)
        from tit.opt.config import MExConfig

        return MExConfig.BucketElectrodes(**defaults)

    def test_defaults(self):
        from tit.opt.config import MExConfig

        config = MExConfig(
            subject_id="001",
            leadfield_hdf="lf.hdf5",
            roi_name="target",
            electrodes=self._bucket_electrodes(),
        )
        assert config.roi_name == "target.csv"
        assert config.current_mA == 2.0
        assert config.channels is None
        assert config.symmetric_bucket is False

    def test_rejects_non_positive_current(self):
        from tit.opt.config import MExConfig

        with pytest.raises(ValueError):
            MExConfig(
                subject_id="001",
                leadfield_hdf="lf.hdf5",
                roi_name="target",
                electrodes=self._bucket_electrodes(),
                current_mA=0.0,
            )

    def test_symmetric_bucket_rejects_pool_electrodes(self):
        from tit.opt.config import MExConfig

        with pytest.raises(ValueError):
            MExConfig(
                subject_id="001",
                leadfield_hdf="lf.hdf5",
                roi_name="target",
                electrodes=MExConfig.PoolElectrodes(electrodes=["E1"] * 8),
                symmetric_bucket=True,
            )

    def test_rejects_unknown_symmetry_pairing(self):
        from tit.opt.config import MExConfig

        with pytest.raises(ValueError):
            MExConfig(
                subject_id="001",
                leadfield_hdf="lf.hdf5",
                roi_name="target",
                electrodes=self._bucket_electrodes(),
                symmetry_pairing="diagonal",
            )


@pytest.mark.unit
class TestMExConfigConfigIO:
    def test_bucket_electrodes_roundtrip(self, tmp_path):
        from tit.config_io import read_config_json, write_config_json
        from tit.opt.config import MExConfig

        config = MExConfig(
            subject_id="001",
            leadfield_hdf="net_leadfield.hdf5",
            roi_name="target",
            electrodes=MExConfig.BucketElectrodes(
                e1_plus=["A"],
                e1_minus=["B"],
                e2_plus=["C"],
                e2_minus=["D"],
                e3_plus=["E"],
                e3_minus=["F"],
                e4_plus=["G"],
                e4_minus=["H"],
            ),
            current_mA=1.5,
            channels=[([0, 2], [1, 3])],
        )
        path = write_config_json(config, prefix="mex_test")
        try:
            data = read_config_json(path)
            assert data["electrodes"]["_type"] == "BucketElectrodes"
            assert data["electrodes"]["e3_minus"] == ["F"]
            assert data["roi_name"] == "target.csv"
            assert data["current_mA"] == 1.5
            assert data["channels"] == [[[0, 2], [1, 3]]]
        finally:
            os.unlink(path)

    def test_pool_electrodes_and_channels_survive_main_rebuild(self):
        from tit.config_io import serialize_config
        from tit.opt.config import MExConfig
        from tit.opt.mex.__main__ import _build_channels, _build_electrodes

        config = MExConfig(
            subject_id="001",
            leadfield_hdf="net_leadfield.hdf5",
            roi_name="target",
            electrodes=MExConfig.PoolElectrodes(
                electrodes=[f"E{i}" for i in range(1, 9)]
            ),
            channels=[([0, 2], [1, 3])],
        )
        data = json.loads(json.dumps(serialize_config(config)))

        electrodes = _build_electrodes(data.pop("electrodes"))
        channels = _build_channels(data.pop("channels"))

        assert isinstance(electrodes, MExConfig.PoolElectrodes)
        assert electrodes.electrodes == [f"E{i}" for i in range(1, 9)]
        assert channels == [([0, 2], [1, 3])]

    def test_absent_channels_rebuild_to_none(self):
        from tit.config_io import serialize_config
        from tit.opt.config import MExConfig
        from tit.opt.mex.__main__ import _build_channels

        config = MExConfig(
            subject_id="001",
            leadfield_hdf="lf.hdf5",
            roi_name="target",
            electrodes=MExConfig.PoolElectrodes(electrodes=["E1"] * 8),
        )
        data = json.loads(json.dumps(serialize_config(config)))
        assert _build_channels(data.get("channels")) is None


# ---------------------------------------------------------------------------
# tit.opt.ex.results.save_run_config -- ExConfig/MExConfig polymorphism
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSaveRunConfigPolymorphism:
    """save_run_config (unchanged elsewhere) was generalized to accept either
    ExConfig's total_current/current_step/channel_limit or MExConfig's flat
    current_mA, and to build electrode_info from dataclass fields instead of
    a hard-coded 4-key dict.
    """

    def test_ex_config_bucket_mode_unaffected(self, tmp_path):
        from tit.opt.config import ExConfig
        from tit.opt.ex.results import save_run_config

        config = ExConfig(
            subject_id="001",
            leadfield_hdf="lf.hdf5",
            roi_name="roi",
            electrodes=ExConfig.BucketElectrodes(
                e1_plus=["A"], e1_minus=["B"], e2_plus=["C"], e2_minus=["D"]
            ),
            total_current=2.0,
            current_step=0.5,
        )
        path = save_run_config(config, 4, str(tmp_path), MagicMock())
        data = json.loads(Path(path).read_text())

        assert data["electrodes"] == {
            "e1_plus": ["A"],
            "e1_minus": ["B"],
            "e2_plus": ["C"],
            "e2_minus": ["D"],
        }
        assert data["total_current_mA"] == 2.0
        assert "current_mA" not in data

    def test_mex_config_bucket_mode_has_eight_keys_and_current_mA(self, tmp_path):
        from tit.opt.config import MExConfig
        from tit.opt.ex.results import save_run_config

        config = MExConfig(
            subject_id="001",
            leadfield_hdf="lf.hdf5",
            roi_name="roi",
            electrodes=MExConfig.BucketElectrodes(
                e1_plus=["A"],
                e1_minus=["B"],
                e2_plus=["C"],
                e2_minus=["D"],
                e3_plus=["E"],
                e3_minus=["F"],
                e4_plus=["G"],
                e4_minus=["H"],
            ),
            current_mA=2.0,
        )
        path = save_run_config(config, 8, str(tmp_path), MagicMock())
        data = json.loads(Path(path).read_text())

        assert set(data["electrodes"]) == {
            "e1_plus",
            "e1_minus",
            "e2_plus",
            "e2_minus",
            "e3_plus",
            "e3_minus",
            "e4_plus",
            "e4_minus",
        }
        assert data["current_mA"] == 2.0
        assert "total_current_mA" not in data


# ---------------------------------------------------------------------------
# tit.calc.get_mTI_vectors -- channels grouping changes the field (critical
# correctness requirement: no recursive-envelope dispatch was reintroduced)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestChannelsGroupingAffectsField:
    def test_shared_carrier_channels_differ_from_independent_pairs(self):
        from tit.calc import get_mTI_vectors

        rng = np.random.default_rng(0)
        fields = [rng.normal(size=(20, 3)) for _ in range(4)]

        independent = get_mTI_vectors(fields, channels=None)
        shared_carrier = get_mTI_vectors(fields, channels=[([0, 2], [1, 3])])

        assert independent.shape == (20, 3)
        assert shared_carrier.shape == (20, 3)
        assert not np.allclose(independent, shared_carrier)

    def test_no_recursive_mti_dispatch_reintroduced(self):
        """MExSearchEngine must not depend on compute_mti_metric_field/MTIMetric."""
        import tit.calc as calc_mod
        import tit.opt.config as config_mod
        import tit.opt.mex.engine as engine_mod

        assert not hasattr(calc_mod, "compute_mti_metric_field")
        assert not hasattr(config_mod, "MTIMetric")
        assert not hasattr(config_mod.MExConfig, "MTIMetric")
        assert not hasattr(engine_mod, "compute_mti_metric_field")


# ---------------------------------------------------------------------------
# MExSearchEngine.compute_mti_field -- ROI metric keys
# ---------------------------------------------------------------------------


def _make_mex_engine(channels=None, logger=None):
    if logger is None:
        logger = MagicMock()
    from tit.opt.mex.engine import MExSearchEngine

    return MExSearchEngine(
        leadfield_hdf="/fake/leadfield.hdf5",
        roi_file="/fake/roi.csv",
        roi_name="TestROI",
        logger=logger,
        channels=channels,
    )


def _setup_engine_fields(engine):
    engine.leadfield = MagicMock()
    engine.idx_lf = MagicMock()
    engine.mesh = MagicMock()
    engine.roi_indices = np.array([0, 1, 2])
    engine.roi_volumes = np.array([1.0, 1.0, 1.0])
    engine.gm_indices = np.array([0, 1, 2, 3, 4])
    engine.gm_volumes = np.array([1.0, 1.0, 1.0, 1.0, 1.0])


@pytest.mark.unit
class TestMExSearchEngineInit:
    def test_stores_channels(self):
        engine = _make_mex_engine(channels=[([0, 2], [1, 3])])
        assert engine.channels == [([0, 2], [1, 3])]
        assert engine.roi_name == "TestROI"

    def test_defaults_to_no_channels(self):
        engine = _make_mex_engine()
        assert engine.channels is None


@pytest.mark.unit
class TestComputeMtiField:
    def test_computes_expected_roi_metric_keys(self):
        import tit.opt.mex.engine as engine_mod

        engine = _make_mex_engine(channels=[([0, 2], [1, 3])])
        _setup_engine_fields(engine)

        engine_mod.TI.get_field = MagicMock(
            side_effect=[np.zeros((5, 3)) for _ in range(4)]
        )
        metric_vectors = np.array(
            [
                [0.1, 0.0, 0.0],
                [0.2, 0.0, 0.0],
                [0.3, 0.0, 0.0],
                [0.15, 0.0, 0.0],
                [0.25, 0.0, 0.0],
            ]
        )
        engine_mod.get_mTI_vectors = MagicMock(return_value=metric_vectors)

        electrodes = ("A1", "A2", "B1", "B2", "C1", "C2", "D1", "D2")
        result = engine.compute_mti_field(electrodes, current_mA=2.0)

        expected_keys = {
            "TestROI_TImax_ROI",
            "TestROI_TImean_ROI",
            "TestROI_TImean_GM",
            "TestROI_Focality",
            "TestROI_n_elements",
            "current_ch1_mA",
            "current_ch2_mA",
            "current_ch3_mA",
            "current_ch4_mA",
        }
        assert set(result) == expected_keys
        # roi_indices=[0,1,2] -> field_roi norms=[0.1,0.2,0.3]
        assert result["TestROI_TImax_ROI"] == pytest.approx(0.3)
        assert result["TestROI_TImean_ROI"] == pytest.approx(0.2)
        assert result["TestROI_n_elements"] == 3
        for i in range(1, 5):
            assert result[f"current_ch{i}_mA"] == 2.0

        assert engine_mod.TI.get_field.call_count == 4
        engine_mod.TI.get_field.assert_any_call(
            ["A1", "A2", 0.002], engine.leadfield, engine.idx_lf
        )
        engine_mod.TI.get_field.assert_any_call(
            ["D1", "D2", 0.002], engine.leadfield, engine.idx_lf
        )

        call = engine_mod.get_mTI_vectors.call_args
        assert call.kwargs["channels"] == [([0, 2], [1, 3])]
        assert len(call.args[0]) == 4

    def test_zero_roi_elements_returns_zeros(self):
        import tit.opt.mex.engine as engine_mod

        engine = _make_mex_engine()
        _setup_engine_fields(engine)
        engine.roi_indices = np.array([], dtype=int)
        engine.roi_volumes = np.array([])

        engine_mod.TI.get_field = MagicMock(
            side_effect=[np.zeros((5, 3)) for _ in range(4)]
        )
        engine_mod.get_mTI_vectors = MagicMock(return_value=np.zeros((5, 3)))

        electrodes = ("A1", "A2", "B1", "B2", "C1", "C2", "D1", "D2")
        result = engine.compute_mti_field(electrodes, current_mA=1.0)

        assert result["TestROI_TImax_ROI"] == 0.0
        assert result["TestROI_TImean_ROI"] == 0.0
        assert result["TestROI_n_elements"] == 0


# ---------------------------------------------------------------------------
# run_m_ex_search -- volumetric atlas ROI + MNI coordinate space
# ---------------------------------------------------------------------------


def _mex_pool_config(**overrides):
    from tit.opt.config import MExConfig

    defaults = dict(
        subject_id="001",
        leadfield_hdf="net_leadfield.hdf5",
        roi_name="motor.csv",
        electrodes=MExConfig.PoolElectrodes(electrodes=[f"E{i}" for i in range(1, 9)]),
    )
    defaults.update(overrides)
    return MExConfig(**defaults)


@pytest.mark.unit
class TestRunMExSearchAtlasAndMni:
    def _pm(self, tmp_path):
        pm = MagicMock()
        pm.logs.return_value = str(tmp_path / "logs")
        pm.m_ex_search_run.return_value = str(tmp_path / "output")
        pm.rois.return_value = str(tmp_path / "rois")
        pm.m2m.return_value = str(tmp_path / "m2m_001")
        return pm

    @patch("tit.opt.mex.mex.process_and_save")
    @patch("tit.opt.mex.mex.MExSearchEngine")
    @patch("tit.opt.mex.mex.add_file_handler")
    @patch("tit.opt.mex.mex.get_path_manager")
    def test_atlas_targets_build_a_roi_list(
        self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path
    ):
        pm = self._pm(tmp_path)
        mock_gpm.return_value = pm

        engine = MagicMock()
        mock_engine_cls.return_value = engine
        engine.run.return_value = {"m1": {}}
        mock_save.return_value = {"config_json_path": "/j", "csv_path": "/c"}

        from tit.opt.mex.mex import run_m_ex_search

        config = _mex_pool_config(
            roi_atlas=[{"atlas_path": "/atlas/aseg.mgz", "label": 53}]
        )
        run_m_ex_search(config)

        roi_arg = mock_engine_cls.call_args[0][1]
        assert roi_arg == [
            os.path.join(str(tmp_path / "rois"), "motor.csv"),
            ("/atlas/aseg.mgz", 53),
        ]

    @patch("tit.opt.mex.mex.process_and_save")
    @patch("tit.opt.mex.mex.MExSearchEngine")
    @patch("tit.opt.mex.mex.add_file_handler")
    @patch("tit.opt.mex.mex.get_path_manager")
    def test_atlas_only_target_reads_no_sphere_csv(
        self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path
    ):
        """roi_names=[] must drop the sphere CSV, leaving an atlas-only target.

        This is what lets the GUI offer Atlas ROI in mTI mode. Previously mex.py
        built the sphere path from roi_name unconditionally, so a multipolar run
        always needed a spherical ROI; roi_name is now only a naming label when
        roi_names is empty, and no CSV is opened.
        """
        pm = self._pm(tmp_path)
        mock_gpm.return_value = pm

        engine = MagicMock()
        mock_engine_cls.return_value = engine
        engine.run.return_value = {"m1": {}}
        mock_save.return_value = {"config_json_path": "/j", "csv_path": "/c"}

        from tit.opt.mex.mex import run_m_ex_search

        config = _mex_pool_config(
            roi_name="Left-Hippocampus",
            roi_names=[],
            roi_atlas=[{"atlas_path": "/atlas/aseg.mgz", "label": 17}],
        )
        run_m_ex_search(config)

        roi_arg = mock_engine_cls.call_args[0][1]
        assert roi_arg == [("/atlas/aseg.mgz", 17)]
        # the label still names the run, it just is not a file to read
        assert mock_engine_cls.call_args[0][2] == "Left-Hippocampus.csv"

    @patch("tit.opt.mex.mex.process_and_save")
    @patch("tit.opt.mex.mex.MExSearchEngine")
    @patch("tit.opt.mex.mex.add_file_handler")
    @patch("tit.opt.mex.mex.get_path_manager")
    def test_atlas_only_target_skips_the_mni_transform(
        self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path
    ):
        """With no sphere centers there is nothing to transform.

        Guards the ``if roi_names and ...`` condition: dropping the roi_names
        half would send an empty list through simnibs.mni2subject_coords.
        """
        pm = self._pm(tmp_path)
        mock_gpm.return_value = pm

        engine = MagicMock()
        mock_engine_cls.return_value = engine
        engine.run.return_value = {"m1": {}}
        mock_save.return_value = {"config_json_path": "/j", "csv_path": "/c"}

        from tit.opt.mex.mex import run_m_ex_search

        config = _mex_pool_config(
            roi_names=[],
            roi_coordinate_space="mni",
            roi_atlas=[{"atlas_path": "/atlas/aseg.mgz", "label": 17}],
        )
        with patch("simnibs.mni2subject_coords") as mock_transform:
            run_m_ex_search(config)

        mock_transform.assert_not_called()
        assert mock_engine_cls.call_args[0][1] == [("/atlas/aseg.mgz", 17)]

    @patch("tit.opt.mex.mex.process_and_save")
    @patch("tit.opt.mex.mex.MExSearchEngine")
    @patch("tit.opt.mex.mex.add_file_handler")
    @patch("tit.opt.mex.mex.get_path_manager")
    def test_no_roi_atlas_passes_bare_roi_file_string(
        self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path
    ):
        """A default (spherical) config passes exactly one ROI target.

        mex.py used to hand the engine a bare string here and a list only when
        atlas entries existed. It now always passes a list, mirroring
        tit/opt/ex/ex.py -- ``ExSearchEngine`` (which ``MExSearchEngine``
        extends) accepts either, and one shape means one code path.
        """
        pm = self._pm(tmp_path)
        mock_gpm.return_value = pm

        engine = MagicMock()
        mock_engine_cls.return_value = engine
        engine.run.return_value = {}
        mock_save.return_value = {"config_json_path": "/j", "csv_path": "/c"}

        from tit.opt.mex.mex import run_m_ex_search

        run_m_ex_search(_mex_pool_config())

        roi_arg = mock_engine_cls.call_args[0][1]
        assert roi_arg == [os.path.join(str(tmp_path / "rois"), "motor.csv")]

    @patch("tit.opt.mex.mex.process_and_save")
    @patch("tit.opt.mex.mex.MExSearchEngine")
    @patch("tit.opt.mex.mex.add_file_handler")
    @patch("tit.opt.mex.mex.get_path_manager")
    def test_mni_space_transforms_roi_center(
        self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path
    ):
        rois_dir = tmp_path / "rois"
        rois_dir.mkdir()
        with open(rois_dir / "motor.csv", "w", newline="") as f:
            csv.writer(f).writerow([5.0, 6.0, 7.0])

        pm = self._pm(tmp_path)
        mock_gpm.return_value = pm

        engine = MagicMock()
        mock_engine_cls.return_value = engine
        engine.run.return_value = {}
        mock_save.return_value = {"config_json_path": "/j", "csv_path": "/c"}

        from tit.opt.mex.mex import run_m_ex_search

        config = _mex_pool_config(roi_coordinate_space="mni")

        with patch(
            "simnibs.mni2subject_coords",
            return_value=np.array([[9.0, 8.0, 7.0]]),
        ) as mock_transform:
            run_m_ex_search(config)

        mock_transform.assert_called_once()
        assert mock_transform.call_args[0][1] == str(tmp_path / "m2m_001")

        [roi_arg] = mock_engine_cls.call_args[0][1]
        assert roi_arg != str(rois_dir / "motor.csv")
        with open(roi_arg) as f:
            row = next(csv.reader(f))
        assert [float(v) for v in row] == pytest.approx([9.0, 8.0, 7.0])

    @patch("tit.opt.mex.mex.process_and_save")
    @patch("tit.opt.mex.mex.MExSearchEngine")
    @patch("tit.opt.mex.mex.add_file_handler")
    @patch("tit.opt.mex.mex.get_path_manager")
    def test_subject_space_does_not_call_transform(
        self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path
    ):
        pm = self._pm(tmp_path)
        mock_gpm.return_value = pm

        engine = MagicMock()
        mock_engine_cls.return_value = engine
        engine.run.return_value = {}
        mock_save.return_value = {"config_json_path": "/j", "csv_path": "/c"}

        from tit.opt.mex.mex import run_m_ex_search

        with patch("simnibs.mni2subject_coords") as mock_transform:
            run_m_ex_search(_mex_pool_config())

        mock_transform.assert_not_called()
