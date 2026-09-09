"""Mask request validation and CLI dispatch; numerical sampling is tested separately.

2026-09-09; .venv/bin/python -m pytest tests/test_analyzer_mask_config.py -q.
"""

from unittest.mock import MagicMock

import pytest

from tit.analyzer.config import AnalyzerConfig
from tit.analyzer.__main__ import _build_config, _run_single


def test_legacy_mask_request_roundtrips_without_atlas():
    config = _build_config(
        dict(
            subject_id="s",
            analysis_type="mask",
            mask_path="/data/roi.nii.gz",
            coordinate_space="mni",
        )
    )
    assert config.mask_path == "/data/roi.nii.gz"
    assert config.atlas is None


@pytest.mark.parametrize("path", [None, "", "/data/roi.txt"])
def test_mask_requires_nifti_path(path):
    with pytest.raises(ValueError, match="mask_path"):
        AnalyzerConfig(subject_id="s", analysis_type="mask", mask_path=path)


def test_group_rejects_subject_mask():
    with pytest.raises(ValueError, match="MNI-space"):
        AnalyzerConfig(
            mode="group",
            subject_ids=["a", "b"],
            analysis_type="mask",
            mask_path="/mask.nii",
        )


def test_invalid_mask_stops_before_analyzer_construction(monkeypatch):
    ctor = MagicMock()
    monkeypatch.setattr("tit.analyzer.Analyzer", ctor)

    def reject(path):
        raise ValueError("invalid image")

    monkeypatch.setattr("tit.opt.masks.validate_mask", reject)
    with pytest.raises(ValueError, match="invalid image"):
        _run_single(
            AnalyzerConfig(subject_id="s", analysis_type="mask", mask_path="/mask.nii")
        )
    ctor.assert_not_called()
