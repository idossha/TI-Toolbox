import json
import logging

from tit.opt.config import FlexConfig
from tit.opt.flex.flex import _export_to_simulations
from tit.opt.flex.simulation_export import _build_export_montages


def _config(*, enable_mapping=True, run_final=True):
    return FlexConfig(
        subject_id="999",
        goal="focality",
        postproc="max_TI",
        current_mA=1.0,
        electrode=FlexConfig.ElectrodeConfig(),
        roi=FlexConfig.SubcorticalROI(
            atlas_path="/tmp/atlas.nii.gz",
            label=2,
            atlas_space="mni",
        ),
        non_roi_method="everything_else",
        enable_mapping=enable_mapping,
        eeg_net="GSN-HydroCel-256",
        run_final_electrode_simulation=run_final,
    )


def test_export_montages_only_includes_mapped_when_mapping_enabled(tmp_path):
    (tmp_path / "electrode_mapping.json").write_text(
        json.dumps(
            {
                "mapped_labels": ["E089", "E100", "E158", "E130"],
                "eeg_net": "GSN-HydroCel-256.csv",
            }
        )
    )

    montages = _build_export_montages(_config(), str(tmp_path), logging.getLogger())

    assert len(montages) == 1
    assert montages[0].mode.value == "flex_mapped"
    assert montages[0].electrode_pairs == [("E089", "E100"), ("E158", "E130")]
    assert montages[0].name.endswith("_mapped")


def test_export_montages_skips_when_mapping_disabled(tmp_path):
    (tmp_path / "electrode_mapping.json").write_text(
        json.dumps({"mapped_labels": ["E089", "E100", "E158", "E130"]})
    )

    montages = _build_export_montages(
        _config(enable_mapping=False, run_final=True),
        str(tmp_path),
        logging.getLogger(),
    )

    assert montages == []


def test_flex_export_hook_requires_mapping_and_final_simulation(monkeypatch, tmp_path):
    calls = []

    def fake_export(config, base_folder, logger):
        calls.append((config, base_folder))
        return [{"montage_name": "mapped"}]

    monkeypatch.setattr(
        "tit.opt.flex.simulation_export.export_flex_run_to_simulations",
        fake_export,
    )

    _export_to_simulations(
        _config(enable_mapping=True, run_final=False),
        str(tmp_path),
        logging.getLogger(),
    )
    assert calls == []

    _export_to_simulations(
        _config(enable_mapping=True, run_final=True),
        str(tmp_path),
        logging.getLogger(),
    )
    assert len(calls) == 1
