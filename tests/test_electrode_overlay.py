"""Tests for electrode placement NIfTI overlays."""

import json
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from tit.tools.electrode_overlay import (
    create_electrode_overlay_nifti,
    electrode_overlay_lut_path,
    simulation_config_has_xyz_electrodes,
)


class _FakeHeader:
    def __init__(self):
        self.dtype = None

    def copy(self):
        new = _FakeHeader()
        new.dtype = self.dtype
        return new

    def set_data_dtype(self, dtype):
        self.dtype = dtype


class _FakeImage:
    def __init__(self, data, affine, header=None):
        self._data = data
        self.affine = affine
        self.header = header or _FakeHeader()
        self.shape = data.shape

    def get_fdata(self):
        return self._data.astype(float)


def _install_fake_nibabel(monkeypatch, reference_img):
    saved = {}

    def load(path):
        return reference_img

    def save(img, path):
        saved["img"] = img
        saved["path"] = path

    fake_nib = SimpleNamespace(load=load, save=save, Nifti1Image=_FakeImage)
    monkeypatch.setitem(sys.modules, "nibabel", fake_nib)
    return saved


@pytest.mark.unit
def test_create_overlay_from_saved_simulation_config(tmp_path, monkeypatch):
    reference = _FakeImage(np.zeros((30, 30, 30)), np.eye(4))
    saved = _install_fake_nibabel(monkeypatch, reference)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "electrode_pairs": [
                    [[10.0, 10.0, 10.0], [20.0, 10.0, 10.0]],
                    [[10.0, 20.0, 10.0], [20.0, 20.0, 10.0]],
                ],
                "electrode_geometry": {
                    "shape": "ellipse",
                    "dimensions": [6.0, 6.0],
                    "gel_thickness": 2.0,
                    "rubber_thickness": 2.0,
                },
            }
        )
    )

    result = create_electrode_overlay_nifti(
        config_path, tmp_path / "reference.nii.gz", tmp_path / "overlay.nii.gz"
    )

    assert result == str(tmp_path / "overlay.nii.gz")
    assert saved["path"] == str(tmp_path / "overlay.nii.gz")
    data = saved["img"]._data
    assert set(np.unique(data)) == {0, 1, 2}
    assert data[10, 10, 10] == 1
    assert data[20, 20, 10] == 2
    lut = electrode_overlay_lut_path(tmp_path / "overlay.nii.gz")
    assert "1 Pair_1 128 0 128 0" in lut.read_text()
    assert "2 Pair_2 0 180 80 0" in lut.read_text()


@pytest.mark.unit
def test_create_overlay_from_multi_montage_input_config(tmp_path, monkeypatch):
    reference = _FakeImage(np.zeros((20, 20, 20)), np.eye(4))
    saved = _install_fake_nibabel(monkeypatch, reference)
    config_path = tmp_path / "input_config.json"
    config_path.write_text(
        json.dumps(
            {
                "electrode_dimensions": [4.0, 4.0],
                "gel_thickness": 1.0,
                "rubber_thickness": 1.0,
                "montages": [
                    {
                        "name": "labels",
                        "mode": "net",
                        "electrode_pairs": [["C3", "C4"], ["F3", "F4"]],
                    },
                    {
                        "name": "xyz",
                        "mode": "freehand",
                        "electrode_pairs": [
                            [[5.0, 5.0, 5.0], [10.0, 5.0, 5.0]],
                            [[5.0, 10.0, 5.0], [10.0, 10.0, 5.0]],
                        ],
                    },
                ],
            }
        )
    )

    create_electrode_overlay_nifti(
        config_path,
        tmp_path / "reference.nii.gz",
        tmp_path / "overlay.nii.gz",
        montage_name="xyz",
    )

    assert np.count_nonzero(saved["img"]._data == 2) > 0


@pytest.mark.unit
def test_label_only_montage_raises(tmp_path, monkeypatch):
    reference = _FakeImage(np.zeros((20, 20, 20)), np.eye(4))
    _install_fake_nibabel(monkeypatch, reference)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"electrode_pairs": [["C3", "C4"], ["F3", "F4"]]})
    )

    with pytest.raises(ValueError, match="Electrode label"):
        create_electrode_overlay_nifti(
            config_path, tmp_path / "reference.nii.gz", tmp_path / "overlay.nii.gz"
        )


@pytest.mark.unit
def test_simulation_config_has_xyz_electrodes(tmp_path):
    xyz_path = tmp_path / "xyz.json"
    xyz_path.write_text(
        json.dumps(
            {
                "electrode_pairs": [
                    [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
                    [[7.0, 8.0, 9.0], [10.0, 11.0, 12.0]],
                ]
            }
        )
    )
    label_path = tmp_path / "labels.json"
    label_path.write_text(json.dumps({"electrode_pairs": [["C3", "C4"]]}))

    assert simulation_config_has_xyz_electrodes(xyz_path)
    assert not simulation_config_has_xyz_electrodes(label_path)
    assert not simulation_config_has_xyz_electrodes(tmp_path / "missing.json")


@pytest.mark.unit
def test_simulation_config_has_xyz_electrodes_from_mapped_positions(tmp_path):
    config_path = tmp_path / "mapped.json"
    config_path.write_text(
        json.dumps(
            {
                "mapped_positions": [
                    [1.0, 2.0, 3.0],
                    [4.0, 5.0, 6.0],
                    [7.0, 8.0, 9.0],
                    [10.0, 11.0, 12.0],
                ]
            }
        )
    )

    assert simulation_config_has_xyz_electrodes(config_path)


@pytest.mark.unit
def test_label_montage_resolves_from_eeg_positions_csv(tmp_path, monkeypatch):
    reference = _FakeImage(np.zeros((20, 20, 20)), np.eye(4))
    saved = _install_fake_nibabel(monkeypatch, reference)
    eeg_dir = tmp_path / "eeg_positions"
    eeg_dir.mkdir()
    (eeg_dir / "cap.csv").write_text(
        "\n".join(
            [
                "Electrode,5.0,5.0,5.0,E001",
                "Electrode,10.0,5.0,5.0,E002",
                "Electrode,5.0,10.0,5.0,E003",
                "Electrode,10.0,10.0,5.0,E004",
            ]
        )
    )
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "eeg_net": "cap.csv",
                "electrode_pairs": [["E001", "E002"], ["E003", "E004"]],
            }
        )
    )

    assert simulation_config_has_xyz_electrodes(
        config_path, eeg_positions_dir=eeg_dir
    )
    create_electrode_overlay_nifti(
        config_path,
        tmp_path / "reference.nii.gz",
        tmp_path / "overlay.nii.gz",
        eeg_positions_dir=eeg_dir,
    )

    assert set(np.unique(saved["img"]._data)) == {0, 1, 2}
