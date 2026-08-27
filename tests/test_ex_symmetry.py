"""Symmetric (bilateral) ex-search, zero-combination failures, electrode maps.

Covers:
- tit/opt/ex/logic.py: within_pairs / cross_pairs enumeration, explain_zero_combinations
- tit/opt/config.py: ExConfig symmetry validation
- tit/opt/ex/ex.py + tit/opt/mex/mex.py: zero candidates fail before the leadfield
- tit/opt/ex/results.py: montage records, run_config symmetry keys, regenerate_plots
- tit/plotting/ti_metrics.py: plot_electrode_score_heatmap / plot_montage_score_map
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# matplotlib is a MagicMock in conftest; its submodules must be registered
# explicitly for ``import matplotlib.image`` to resolve.
for _mod in ("matplotlib.image", "matplotlib.patches", "matplotlib.path"):
    sys.modules.setdefault(_mod, MagicMock())

from tit.opt.config import ExConfig, MExConfig  # noqa: E402
from tit.opt.ex.logic import (  # noqa: E402
    _electrode_combinations,
    count_combinations,
    explain_zero_combinations,
)

MIRROR = {"L1": "R1", "R1": "L1", "L2": "R2", "R2": "L2", "L3": "R3", "R3": "L3", "CZ": "CZ"}


def _write_symmetric_csv(path: Path) -> Path:
    path.write_text(
        "Electrode,-50,60,0,L1\n"
        "Electrode,50,60,0,R1\n"
        "Electrode,-50,-60,0,L2\n"
        "Electrode,50,-60,0,R2\n"
        "Electrode,-70,0,0,L3\n"
        "Electrode,70,0,0,R3\n"
        "Electrode,0,0,80,CZ\n"
    )
    return path


# ---------------------------------------------------------------------------
# logic.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSymmetricEnumeration:
    def test_within_pairs_mirrors_each_pair(self):
        combos = list(
            _electrode_combinations(
                ["L1", "L3", "CZ"], ["R1", "R3", "R2"], ["L2"], ["R2", "L1"],
                False, MIRROR, "within_pairs",
            )
        )
        assert combos == [("L1", "R1", "L2", "R2"), ("L3", "R3", "L2", "R2")]

    def test_cross_pairs_pair_two_mirrors_pair_one(self):
        combos = list(
            _electrode_combinations(
                ["L1", "L3"], ["L2"], ["R1", "R3"], ["R2"],
                False, MIRROR, "cross_pairs",
            )
        )
        assert combos == [("L1", "L2", "R1", "R2"), ("L3", "L2", "R3", "R2")]

    def test_symmetric_montages_need_four_distinct_electrodes(self):
        # within_pairs: pair 2 == pair 1 -> rejected
        combos = list(
            _electrode_combinations(
                ["L1"], ["R1"], ["L1"], ["R1"], False, MIRROR, "within_pairs"
            )
        )
        assert combos == []

    def test_midline_electrode_never_pairs_with_itself(self):
        combos = list(
            _electrode_combinations(
                ["CZ"], ["CZ"], ["L1"], ["R1"], False, MIRROR, "within_pairs"
            )
        )
        assert combos == []

    def test_unknown_pairing_raises(self):
        with pytest.raises(ValueError, match="symmetry pairing"):
            list(
                _electrode_combinations(
                    ["L1"], ["R1"], ["L2"], ["R2"], False, MIRROR, "diagonal"
                )
            )

    def test_count_matches_enumeration_times_ratios(self):
        n = count_combinations(
            ["L1", "L3"], ["R1", "R3"], ["L2"], ["R2"], [(1.0, 1.0), (1.5, 0.5)],
            False, MIRROR, "within_pairs",
        )
        assert n == 2 * 2

    def test_no_mirror_map_keeps_plain_product(self):
        n = count_combinations(["A", "B"], ["C"], ["D"], ["E"], [(1, 1)], False)
        assert n == 2


@pytest.mark.unit
class TestExplainZeroCombinations:
    def test_within_pairs_names_the_offending_bucket_and_mirror_map(self):
        msg = explain_zero_combinations(
            ["L1", "L3"], ["L2"], ["L2"], ["R2"], [(1, 1)], False, MIRROR, "within_pairs"
        )
        assert msg.startswith("symmetric_bucket=within_pairs: no electrode in e1_plus")
        assert "e1_minus" in msg
        assert "L1->R1" in msg and "L3->R3" in msg

    def test_cross_pairs_message(self):
        msg = explain_zero_combinations(
            ["L1"], ["L2"], ["L3"], ["R2"], [(1, 1)], False, MIRROR, "cross_pairs"
        )
        assert "cross_pairs" in msg
        assert "e1_plus" in msg and "e2_plus" in msg

    def test_duplicate_only_symmetric_montages(self):
        msg = explain_zero_combinations(
            ["L1"], ["R1"], ["L1"], ["R1"], [(1, 1)], False, MIRROR, "within_pairs"
        )
        assert "distinct" in msg

    def test_empty_bucket(self):
        msg = explain_zero_combinations(["A"], [], ["B"], [], [(1, 1)], False)
        assert "e1_minus, e2_minus" in msg

    def test_pool_too_small(self):
        msg = explain_zero_combinations(["A", "B"], ["A", "B"], ["A", "B"], ["A", "B"], [(1, 1)], True)
        assert "4 distinct electrodes, got 2" in msg

    def test_no_ratios(self):
        msg = explain_zero_combinations(["A"], ["B"], ["C"], ["D"], [], False)
        assert "current ratios" in msg


# ---------------------------------------------------------------------------
# ExConfig validation
# ---------------------------------------------------------------------------


def _bucket_ex_config(**overrides):
    defaults = dict(
        subject_id="001",
        leadfield_hdf="/lf/001_leadfield_net.hdf5",
        roi_name="roi.csv",
        electrodes=ExConfig.BucketElectrodes(
            e1_plus=["L1"], e1_minus=["R1"], e2_plus=["L2"], e2_minus=["R2"]
        ),
    )
    defaults.update(overrides)
    return ExConfig(**defaults)


@pytest.mark.unit
class TestExConfigSymmetry:
    def test_defaults(self):
        cfg = _bucket_ex_config()
        assert cfg.symmetric_bucket is False
        assert cfg.symmetry_eeg_csv is None
        assert cfg.symmetry_pairing == "within_pairs"

    def test_symmetric_bucket_rejects_pool_electrodes(self):
        with pytest.raises(ValueError, match="bucket electrodes"):
            _bucket_ex_config(
                electrodes=ExConfig.PoolElectrodes(electrodes=["A", "B", "C", "D"]),
                symmetric_bucket=True,
            )

    def test_rejects_unknown_symmetry_pairing(self):
        with pytest.raises(ValueError, match="symmetry_pairing"):
            _bucket_ex_config(symmetry_pairing="diagonal")

    def test_json_passthrough_builds_config(self):
        """The plain fields survive the __main__ JSON -> ExConfig path."""
        from tit.opt.ex.__main__ import _build_electrodes

        data = {
            "subject_id": "001",
            "leadfield_hdf": "/lf/001_leadfield_net.hdf5",
            "roi_name": "roi.csv",
            "electrodes": {
                "_type": "BucketElectrodes",
                "e1_plus": ["L1"], "e1_minus": ["R1"], "e2_plus": ["L2"], "e2_minus": ["R2"],
            },
            "symmetric_bucket": True,
            "symmetry_pairing": "cross_pairs",
            "symmetry_eeg_csv": "/x.csv",
        }
        electrodes = _build_electrodes(data.pop("electrodes"))
        cfg = ExConfig(electrodes=electrodes, **data)
        assert cfg.symmetric_bucket and cfg.symmetry_pairing == "cross_pairs"


# ---------------------------------------------------------------------------
# run_ex_search / run_m_ex_search: zero candidates fail fast
# ---------------------------------------------------------------------------


def _pm(tmp_path, run_attr):
    pm = MagicMock()
    pm.logs.return_value = str(tmp_path / "logs")
    getattr(pm, run_attr).return_value = str(tmp_path / "output")
    pm.rois.return_value = str(tmp_path / "rois")
    pm.m2m.return_value = str(tmp_path / "m2m_001")
    pm.leadfields.return_value = str(tmp_path / "leadfields")
    pm.eeg_positions.return_value = str(tmp_path / "eeg_positions")
    return pm


@pytest.mark.unit
class TestZeroCombinationsFailFast:
    @patch("tit.opt.ex.ex.process_and_save")
    @patch("tit.opt.ex.ex.ExSearchEngine")
    @patch("tit.opt.ex.ex.add_file_handler")
    @patch("tit.opt.ex.ex.get_path_manager")
    def test_ex_symmetric_without_mirrors(
        self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path
    ):
        from tit.opt.ex.ex import run_ex_search

        mock_gpm.return_value = _pm(tmp_path, "ex_search_run")
        csv = _write_symmetric_csv(tmp_path / "net.csv")
        config = _bucket_ex_config(
            electrodes=ExConfig.BucketElectrodes(
                e1_plus=["L1", "L3"], e1_minus=["L2"], e2_plus=["L2"], e2_minus=["R2"]
            ),
            symmetric_bucket=True,
            symmetry_eeg_csv=str(csv),
        )
        with pytest.raises(ValueError) as exc:
            run_ex_search(config)
        msg = str(exc.value)
        assert msg.startswith("ex-search has no candidate montages to evaluate: ")
        assert "symmetric_bucket=within_pairs" in msg
        assert "L1->R1" in msg
        mock_engine_cls.assert_not_called()
        mock_save.assert_not_called()
        assert not (tmp_path / "output").exists()

    @patch("tit.opt.ex.ex.process_and_save")
    @patch("tit.opt.ex.ex.ExSearchEngine")
    @patch("tit.opt.ex.ex.add_file_handler")
    @patch("tit.opt.ex.ex.get_path_manager")
    def test_ex_symmetric_success_passes_mirror_map_to_engine(
        self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path
    ):
        from tit.opt.ex.ex import run_ex_search

        mock_gpm.return_value = _pm(tmp_path, "ex_search_run")
        csv = _write_symmetric_csv(tmp_path / "net.csv")
        engine = mock_engine_cls.return_value
        engine.run.return_value = {"m": {"v": 1}}
        mock_save.return_value = {"config_json_path": "c", "csv_path": "d"}
        config = _bucket_ex_config(
            electrodes=ExConfig.BucketElectrodes(
                e1_plus=["L1"], e1_minus=["L2"], e2_plus=["R1"], e2_minus=["R2"]
            ),
            symmetric_bucket=True,
            symmetry_pairing="cross_pairs",
            symmetry_eeg_csv=str(csv),
        )
        result = run_ex_search(config)
        assert result.success
        kwargs = engine.run.call_args.kwargs
        assert kwargs["symmetry_pairing"] == "cross_pairs"
        assert kwargs["symmetry_mirror_map"]["L1"] == "R1"
        assert (tmp_path / "output").is_dir()

    @patch("tit.opt.ex.ex.process_and_save")
    @patch("tit.opt.ex.ex.ExSearchEngine")
    @patch("tit.opt.ex.ex.add_file_handler")
    @patch("tit.opt.ex.ex.get_path_manager")
    def test_ex_empty_bucket(self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path):
        from tit.opt.ex.ex import run_ex_search

        mock_gpm.return_value = _pm(tmp_path, "ex_search_run")
        config = _bucket_ex_config(
            electrodes=ExConfig.BucketElectrodes(
                e1_plus=["L1"], e1_minus=[], e2_plus=["L2"], e2_minus=["R2"]
            )
        )
        with pytest.raises(ValueError, match="empty electrode bucket\\(s\\): e1_minus"):
            run_ex_search(config)
        mock_engine_cls.assert_not_called()
        assert not (tmp_path / "output").exists()

    @patch("tit.opt.mex.mex.process_and_save")
    @patch("tit.opt.mex.mex.MExSearchEngine")
    @patch("tit.opt.mex.mex.add_file_handler")
    @patch("tit.opt.mex.mex.get_path_manager")
    def test_mex_symmetric_without_mirrors(
        self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path
    ):
        from tit.opt.mex.mex import run_m_ex_search

        mock_gpm.return_value = _pm(tmp_path, "m_ex_search_run")
        csv = _write_symmetric_csv(tmp_path / "net.csv")
        config = MExConfig(
            subject_id="001",
            leadfield_hdf="/lf/001_leadfield_net.hdf5",
            roi_name="roi.csv",
            electrodes=MExConfig.BucketElectrodes(
                e1_plus=["L1"], e1_minus=["L2"], e2_plus=["L3"], e2_minus=["R3"],
                e3_plus=["R1"], e3_minus=["R2"], e4_plus=["CZ"], e4_minus=["L1"],
            ),
            symmetric_bucket=True,
            symmetry_eeg_csv=str(csv),
        )
        with pytest.raises(ValueError) as exc:
            run_m_ex_search(config)
        msg = str(exc.value)
        assert msg.startswith("m-ex-search has no candidate montages to evaluate: ")
        assert "no electrode in e1_plus has its mirror in e1_minus" in msg
        mock_engine_cls.assert_not_called()
        assert not (tmp_path / "output").exists()

    @patch("tit.opt.mex.mex.process_and_save")
    @patch("tit.opt.mex.mex.MExSearchEngine")
    @patch("tit.opt.mex.mex.add_file_handler")
    @patch("tit.opt.mex.mex.get_path_manager")
    def test_mex_pool_too_small(self, mock_gpm, mock_afh, mock_engine_cls, mock_save, tmp_path):
        from tit.opt.mex.mex import run_m_ex_search

        mock_gpm.return_value = _pm(tmp_path, "m_ex_search_run")
        config = MExConfig(
            subject_id="001",
            leadfield_hdf="/lf/001_leadfield_net.hdf5",
            roi_name="roi.csv",
            electrodes=MExConfig.PoolElectrodes(electrodes=["A", "B", "C"]),
        )
        with pytest.raises(ValueError, match="8 distinct electrodes, got 3"):
            run_m_ex_search(config)
        mock_engine_cls.assert_not_called()
        assert not (tmp_path / "output").exists()

    def test_ex_main_exits_nonzero_on_value_error(self, tmp_path, monkeypatch):
        from tit.opt.ex import __main__ as ex_main

        config = {
            "project_dir": str(tmp_path),
            "subject_id": "001",
            "leadfield_hdf": "/lf/001_leadfield_net.hdf5",
            "roi_name": "roi.csv",
            "electrodes": {"e1_plus": ["A"], "e1_minus": [], "e2_plus": ["B"], "e2_minus": ["C"]},
        }
        path = tmp_path / "cfg.json"
        path.write_text(json.dumps(config))
        monkeypatch.setattr(sys, "argv", ["tit.opt.ex", str(path)])
        monkeypatch.setattr(ex_main, "_make_stdout_logger", lambda: None)
        with patch("tit.opt.ex.__main__.run_ex_search", side_effect=ValueError("boom")):
            with pytest.raises(SystemExit) as exc:
                ex_main.main()
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# results.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMontageRecords:
    def test_parse_montage_string_two_and_four_pairs(self):
        from tit.opt.ex.results import parse_montage_string

        assert parse_montage_string("F7_P7 <> F3_P3_I1-1.8mA_I2-0.2mA") == [
            "F7", "P7", "F3", "P3"
        ]
        assert parse_montage_string("F7_P7 <> F5_P5 <> F3_P3 <> AF7_PO7_I-1.0mA") == [
            "F7", "P7", "F5", "P5", "F3", "P3", "AF7", "PO7"
        ]

    def test_records_use_engine_tuple_when_present(self):
        from tit.opt.ex.results import montage_score_records

        results = {
            "TI_field_A_B_and_C_D_I1-1.0mA_I2-1.0mA.msh": {
                "roi_TImean_ROI": 0.5, "roi_Focality": 2.0,
                "electrodes": ("A", "B", "C", "D"),
            },
            "TI_field_E_F_and_G_H_and_I_J_and_K_L_I-1.0mA.msh": {
                "roi_TImean_ROI": 0.25, "roi_Focality": 2.0,
            },
        }
        records = montage_score_records(results, "roi")
        assert records[0]["electrodes"] == ["A", "B", "C", "D"]
        assert records[0]["composite"] == pytest.approx(1.0)
        # Fallback parses the mesh key, 8 electrodes for mex runs.
        assert records[1]["electrodes"] == ["E", "F", "G", "H", "I", "J", "K", "L"]

    def test_records_from_csv(self, tmp_path):
        from tit.opt.ex.results import montage_score_records_from_csv

        csv = tmp_path / "final_output.csv"
        csv.write_text(
            "Montage,Current_Ch1_mA,Current_Ch2_mA,TImax_ROI,TImean_ROI,TImean_GM,Focality,Composite_Index\n"
            "F7_P7 <> F3_P3_I1-1.8mA_I2-0.2mA,1.8,0.2,0.08,0.05,0.04,1.2,0.06\n"
        )
        records = montage_score_records_from_csv(csv)
        assert records[0]["electrodes"] == ["F7", "P7", "F3", "P3"]
        assert records[0]["composite"] == pytest.approx(0.06)

    def test_run_config_records_symmetry(self, tmp_path):
        from tit.opt.ex.results import save_run_config

        cfg = _bucket_ex_config(symmetric_bucket=True, symmetry_pairing="cross_pairs")
        path = save_run_config(cfg, 3, str(tmp_path), MagicMock())
        data = json.loads(Path(path).read_text())
        assert data["symmetric_bucket"] is True
        assert data["symmetry_pairing"] == "cross_pairs"
        assert data["symmetry_eeg_csv"] is None

    def test_run_config_symmetry_pairing_null_when_off(self, tmp_path):
        from tit.opt.ex.results import save_run_config

        data = json.loads(
            Path(save_run_config(_bucket_ex_config(), 1, str(tmp_path), MagicMock())).read_text()
        )
        assert data["symmetric_bucket"] is False and data["symmetry_pairing"] is None


@pytest.mark.unit
class TestRegeneratePlots:
    def _run_dir(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "final_output.csv").write_text(
            "Montage,Current_Ch1_mA,Current_Ch2_mA,TImax_ROI,TImean_ROI,TImean_GM,Focality,Composite_Index\n"
            "L1_R1 <> L2_R2_I1-1.0mA_I2-1.0mA,1,1,0.1,0.05,0.04,1.2,0.06\n"
            "L1_R1 <> L3_R3_I1-1.0mA_I2-1.0mA,1,1,0.1,0.06,0.04,1.1,0.066\n"
        )
        return run_dir

    @patch("tit.opt.ex.results.generate_electrode_maps", return_value=["a.png"])
    def test_explicit_csv(self, mock_maps, tmp_path):
        from tit.opt.ex.results import regenerate_plots

        run_dir = self._run_dir(tmp_path)
        csv = _write_symmetric_csv(tmp_path / "net.csv")
        assert regenerate_plots(run_dir, csv) == ["a.png"]
        records, eeg_csv, out_dir, _ = mock_maps.call_args.args
        assert len(records) == 2 and records[0]["electrodes"] == ["L1", "R1", "L2", "R2"]
        assert eeg_csv == csv and out_dir == str(run_dir)

    @patch("tit.opt.ex.results.generate_electrode_maps", return_value=[])
    def test_infers_csv_from_run_config(self, mock_maps, tmp_path):
        from tit.opt.ex.results import regenerate_plots

        run_dir = self._run_dir(tmp_path)
        sub = tmp_path / "sub-001"
        eeg_dir = sub / "m2m_001" / "eeg_positions"
        eeg_dir.mkdir(parents=True)
        _write_symmetric_csv(eeg_dir / "mynet.csv")
        leadfield = sub / "leadfields" / "001_leadfield_mynet.hdf5"
        (run_dir / "run_config.json").write_text(
            json.dumps({"subject_id": "001", "leadfield_hdf": str(leadfield)})
        )
        regenerate_plots(run_dir)
        assert mock_maps.call_args.args[1] == eeg_dir / "mynet.csv"

    def test_missing_csv_raises(self, tmp_path):
        from tit.opt.ex.results import regenerate_plots

        with pytest.raises(FileNotFoundError):
            regenerate_plots(tmp_path)

    @patch("tit.opt.ex.results.generate_electrode_maps", return_value=[])
    def test_cli(self, mock_maps, tmp_path):
        from tit.opt.ex.results import main

        run_dir = self._run_dir(tmp_path)
        csv = _write_symmetric_csv(tmp_path / "net.csv")
        main([str(run_dir), "--eeg-csv", str(csv)])
        mock_maps.assert_called_once()


@pytest.mark.unit
class TestProcessAndSaveElectrodeMaps:
    @patch("tit.opt.ex.results.generate_electrode_maps", return_value=["x.png"])
    @patch("tit.opt.ex.results.generate_plots", return_value=["h.png"])
    def test_maps_generated_when_csv_resolves(self, mock_plots, mock_maps, tmp_path):
        from tit.opt.ex.results import process_and_save

        results = {
            "TI_field_A_B_and_C_D_I1-1.0mA_I2-1.0mA.msh": {
                "roi.csv_TImax_ROI": 1, "roi.csv_TImean_ROI": 0.5,
                "roi.csv_TImean_GM": 0.2, "roi.csv_Focality": 2.0,
                "electrodes": ("A", "B", "C", "D"),
            }
        }
        csv = _write_symmetric_csv(tmp_path / "net.csv")
        cfg = _bucket_ex_config(symmetry_eeg_csv=str(csv))
        with patch("tit.opt.ex.results._eeg_positions_csv_for_config", return_value=csv):
            info = process_and_save(results, cfg, str(tmp_path), MagicMock())
        assert info["visualization_paths"] == ["h.png", "x.png"]
        assert mock_maps.call_args.args[0][0]["electrodes"] == ["A", "B", "C", "D"]

    @patch("tit.opt.ex.results.generate_electrode_maps")
    @patch("tit.opt.ex.results.generate_plots", return_value=[])
    def test_maps_skipped_without_csv(self, mock_plots, mock_maps, tmp_path):
        from tit.opt.ex.results import process_and_save

        results = {
            "TI_field_A_B_and_C_D.msh": {
                "roi.csv_TImax_ROI": 1, "roi.csv_TImean_ROI": 0.5,
                "roi.csv_TImean_GM": 0.2, "roi.csv_Focality": 2.0,
            }
        }
        logger = MagicMock()
        with patch("tit.opt.ex.results._eeg_positions_csv_for_config", return_value=None):
            process_and_save(results, _bucket_ex_config(), str(tmp_path), logger)
        mock_maps.assert_not_called()
        assert any(
            "Electrode maps skipped" in str(c.args[0]) for c in logger.info.call_args_list
        )


# ---------------------------------------------------------------------------
# ti_metrics.py electrode maps (matplotlib mocked)
# ---------------------------------------------------------------------------


def _records():
    return [
        {"electrodes": ["L1", "R1", "L2", "R2"], "composite": 0.9, "timean": 0.3, "focality": 3.0},
        {"electrodes": ["L1", "R1", "L3", "R3"], "composite": 0.5, "timean": 0.25, "focality": 2.0},
        {"electrodes": ["L1", "R1", "L2", "R2", "L3", "R3", "CZ", "R1"], "composite": 0.1,
         "timean": 0.1, "focality": 1.0},
        {"electrodes": ["L1", "R1", "L2", "NOPE"], "composite": 5.0, "timean": 1, "focality": 5},
    ]


@pytest.mark.unit
class TestElectrodeMapPlots:
    def _fig_ax(self):
        import matplotlib.pyplot as plt

        fig, ax = MagicMock(), MagicMock()
        plt.subplots.return_value = (fig, ax)
        return fig, ax

    def test_heatmap_sums_composite_and_counts(self, tmp_path):
        from tit.plotting.ti_metrics import plot_electrode_score_heatmap

        fig, ax = self._fig_ax()
        csv = _write_symmetric_csv(tmp_path / "net.csv")
        out = str(tmp_path / "heat.png")
        assert plot_electrode_score_heatmap(
            eeg_positions_csv=str(csv), montage_scores=_records(), output_file=out
        ) == out
        fig.savefig.assert_called_once()
        # The coloured scatter call carries the per-electrode sums and sizes.
        scatter = [c for c in ax.scatter.call_args_list if "c" in c.kwargs][0]
        sums = dict(zip(zip(scatter.args[0], scatter.args[1]), scatter.kwargs["c"]))
        # L1 (-50, 60) appears in all three plottable montages: 0.9+0.5+0.1
        assert sums[(-50.0, 60.0)] == pytest.approx(1.5)
        # R1 appears twice in the 8-electrode montage: 0.9+0.5+0.1+0.1
        assert sums[(50.0, 60.0)] == pytest.approx(1.6)
        assert len(scatter.kwargs["s"]) == 7  # L1 R1 L2 R2 L3 R3 CZ all active

    def test_heatmap_returns_none_without_plottable_montages(self, tmp_path):
        from tit.plotting.ti_metrics import plot_electrode_score_heatmap

        csv = _write_symmetric_csv(tmp_path / "net.csv")
        assert plot_electrode_score_heatmap(
            eeg_positions_csv=str(csv),
            montage_scores=[{"electrodes": ["X", "Y"], "composite": 1}],
            output_file=str(tmp_path / "h.png"),
        ) is None

    def test_score_map_draws_one_curve_per_pair(self, tmp_path):
        from tit.plotting.ti_metrics import plot_montage_score_map

        fig, ax = self._fig_ax()
        csv = _write_symmetric_csv(tmp_path / "net.csv")
        out = str(tmp_path / "map.png")
        assert plot_montage_score_map(
            eeg_positions_csv=str(csv),
            montage_scores=_records(),
            output_file=out,
            metric_key="timean",
            cmap_name=("#000000", "#ffffff"),
        ) == out
        # 3 plottable montages: 2 + 2 + 4 pairs = 8 curves
        assert ax.add_patch.call_count == 8
        # best montage (timean 0.3) has 4 electrodes highlighted + labelled
        assert ax.text.call_count == 4
        fig.savefig.assert_called_once()

    def test_template_layout_for_known_net(self, tmp_path):
        from tit.plotting.ti_metrics import _resolve_layout

        layout = _resolve_layout("/anything/EEG10-10_UI_Jurak_2007.csv")
        assert layout["template_path"] is not None
        assert "F7" in layout["positions"] and "F8" in layout["positions"]

    def test_raw_layout_for_unknown_net(self, tmp_path):
        from tit.plotting.ti_metrics import _resolve_layout

        csv = _write_symmetric_csv(tmp_path / "net.csv")
        layout = _resolve_layout(str(csv))
        assert layout["template_path"] is None
        assert layout["positions"]["L1"] == (-50.0, 60.0)
