"""QSIPrep defaults chosen from the subject's BIDS data (tit.pre.qsi.utils).

Pins: distortion-correction mode and the fieldmap sidecar repair (IntendedFor /
TotalReadoutTime written only when missing, only into the fieldmap's own JSON),
unusable fieldmaps reported instead of guessed, the rpg/mrdegibbs choice from
PartialFourier, the native output resolution, the arm64 host refusal, and the
QSIPrep command flags those choices produce. Headers are hand-packed NIfTI-1 bytes
(nibabel is mocked here); the expected values are the header fields written.
"""

import gzip
import json
import struct
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tit.pre.qsi.config import QSIPrepConfig
from tit.pre.qsi.docker_builder import DockerCommandBuilder
from tit.pre.qsi.utils import (
    choose_unringing_method,
    native_dwi_resolution,
    plan_distortion_correction,
    read_nifti_zooms,
    validate_dood_environment,
)


def _header(dims, zooms=(0.0, 0.0, 0.0)) -> bytes:
    header = bytearray(352)
    struct.pack_into("<i", header, 0, 348)
    struct.pack_into("<8h", header, 40, len(dims), *dims, *([1] * (7 - len(dims))))
    struct.pack_into("<8f", header, 76, 1.0, *zooms, 0, 0, 0, 0)
    header[344:348] = b"n+1\x00"
    return bytes(header)


def _nifti(path: Path, dims, zooms=(2.0, 2.0, 2.0)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb") as handle:
        handle.write(_header(dims, zooms))
    return path


def _json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def subject(tmp_path, write_dwi):
    """sub-001 with a j- DWI (64x64x40, TotalReadoutTime 0.05)."""
    write_dwi(tmp_path / "sub-001" / "dwi")
    return tmp_path


def _fmap(root: Path, name: str, sidecar: dict | None, dims=(64, 64, 40, 2)) -> Path:
    image = _nifti(root / "sub-001" / "fmap" / f"{name}.nii.gz", dims)
    if sidecar is not None:
        _json(image.with_name(f"{name}.json"), sidecar)
    return image.with_name(f"{name}.json")


def _plan(root, **kwargs):
    return plan_distortion_correction(str(root), "001", logger=MagicMock(), **kwargs)


class TestDistortionCorrectionPlan:
    def test_no_fieldmap_means_syn(self, subject):
        plan = _plan(subject)
        assert plan.mode == "syn" and plan.use_syn
        assert plan.blocking_error is None
        assert "SyN" in plan.describe()

    def test_reverse_pe_fieldmap_gets_intended_for(self, subject):
        sidecar = _fmap(
            subject,
            "sub-001_acq-dwi_dir-PA_epi",
            {"PhaseEncodingDirection": "j", "TotalReadoutTime": 0.05},
        )
        plan = _plan(subject)
        assert plan.mode == "fieldmap" and not plan.use_syn
        assert json.loads(sidecar.read_text())["IntendedFor"] == [
            "dwi/sub-001_dwi.nii.gz"
        ]

    def test_fieldmap_without_acq_matched_by_matrix(self, subject):
        _fmap(
            subject,
            "sub-001_dir-PA_epi",
            {"PhaseEncodingDirection": "j", "TotalReadoutTime": 0.05},
        )
        assert _plan(subject).mode == "fieldmap"

    def test_existing_intended_for_is_not_rewritten(self, subject):
        meta = {
            "PhaseEncodingDirection": "j",
            "TotalReadoutTime": 0.05,
            "IntendedFor": "bids::sub-001/dwi/sub-001_dwi.nii.gz",
        }
        sidecar = _fmap(subject, "sub-001_acq-dwi_dir-PA_epi", meta)
        before = sidecar.read_text()
        assert _plan(subject).mode == "fieldmap"
        assert sidecar.read_text() == before

    def test_missing_readout_time_is_derived_and_written(self, subject):
        sidecar = _fmap(
            subject,
            "sub-001_acq-dwi_dir-PA_epi",
            {
                "PhaseEncodingDirection": "j",
                "EffectiveEchoSpacing": 0.0005,
                "ReconMatrixPE": 101,
            },
        )
        assert _plan(subject).mode == "fieldmap"
        assert json.loads(sidecar.read_text())["TotalReadoutTime"] == pytest.approx(
            0.05
        )

    def test_preflight_mode_does_not_write(self, subject):
        sidecar = _fmap(
            subject,
            "sub-001_acq-dwi_dir-PA_epi",
            {"PhaseEncodingDirection": "j", "TotalReadoutTime": 0.05},
        )
        before = sidecar.read_text()
        assert _plan(subject, repair=False).mode == "fieldmap"
        assert sidecar.read_text() == before

    def test_bold_fieldmap_is_not_used_for_dwi(self, subject):
        sidecar = _fmap(
            subject,
            "sub-001_acq-bold_dir-PA_epi",
            {"PhaseEncodingDirection": "j", "TotalReadoutTime": 0.03},
            dims=(90, 90, 60, 3),
        )
        before = sidecar.read_text()
        plan = _plan(subject)
        assert plan.mode == "syn" and plan.problems == ()
        assert sidecar.read_text() == before

    def test_same_pe_fieldmap_blocks(self, subject):
        _fmap(
            subject,
            "sub-001_acq-dwi_dir-AP_epi",
            {"PhaseEncodingDirection": "j-", "TotalReadoutTime": 0.05},
        )
        plan = _plan(subject)
        assert plan.mode == "syn"
        assert "same PhaseEncodingDirection" in plan.blocking_error

    def test_missing_sidecar_blocks(self, subject):
        _fmap(subject, "sub-001_acq-dwi_dir-PA_epi", None)
        assert "no sub-001_acq-dwi_dir-PA_epi.json" in _plan(subject).blocking_error

    def test_unusable_fieldmap_beside_a_usable_one_is_only_reported(self, subject):
        """CHN's layout: dir-AP has a sidecar (PE j), dir-PA has none."""
        _fmap(
            subject,
            "sub-001_acq-dwi_dir-AP_epi",
            {"PhaseEncodingDirection": "j", "TotalReadoutTime": 0.06},
        )
        _fmap(subject, "sub-001_acq-dwi_dir-PA_epi", None)
        plan = _plan(subject)
        assert plan.mode == "fieldmap" and plan.blocking_error is None
        assert len(plan.problems) == 1

    def test_reverse_pe_dwi_series(self, tmp_path, write_dwi):
        write_dwi(tmp_path / "sub-001" / "dwi", "sub-001_dir-AP_dwi")
        write_dwi(
            tmp_path / "sub-001" / "dwi",
            "sub-001_dir-PA_dwi",
            sidecar={"PhaseEncodingDirection": "j", "TotalReadoutTime": 0.05},
        )
        assert _plan(tmp_path).mode == "reverse-pe-dwi"


class TestUnringingAndResolution:
    def test_partial_fourier_selects_rpg(self, tmp_path, write_dwi):
        write_dwi(
            tmp_path / "sub-001" / "dwi",
            sidecar={"PhaseEncodingDirection": "j-", "PartialFourier": 0.75},
        )
        method, reason = choose_unringing_method(str(tmp_path), "001")
        assert method == "rpg" and "0.75" in reason

    @pytest.mark.parametrize("extra", [{}, {"PartialFourier": 1}])
    def test_full_kspace_selects_mrdegibbs(self, tmp_path, write_dwi, extra):
        write_dwi(
            tmp_path / "sub-001" / "dwi",
            sidecar={"PhaseEncodingDirection": "j-", **extra},
        )
        assert choose_unringing_method(str(tmp_path), "001")[0] == "mrdegibbs"

    def test_native_resolution_is_the_finest_axis_rounded(self, tmp_path):
        _nifti(
            tmp_path / "sub-001" / "dwi" / "sub-001_dwi.nii.gz",
            (116, 116, 74, 30),
            zooms=(1.71875, 1.71875, 2.5),
        )
        assert native_dwi_resolution(str(tmp_path), "001") == pytest.approx(1.7)

    def test_zooms_read_from_header(self, tmp_path):
        path = _nifti(tmp_path / "x.nii.gz", (10, 10, 10), zooms=(2.0, 2.5, 3.0))
        assert read_nifti_zooms(path) == pytest.approx((2.0, 2.5, 3.0))

    def test_no_readable_header(self, tmp_path):
        (tmp_path / "sub-001" / "dwi").mkdir(parents=True)
        (tmp_path / "sub-001" / "dwi" / "sub-001_dwi.nii.gz").write_bytes(b"x")
        assert native_dwi_resolution(str(tmp_path), "001") is None


class TestArm64HostRefused:
    def _run(self, tmp_path, arch):
        info = MagicMock(
            returncode=0, stdout=f" OSType: linux\n Architecture: {arch}\n", stderr=""
        )
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch.dict("os.environ", {"LOCAL_PROJECT_DIR": str(tmp_path)}),
            patch("subprocess.run", return_value=info),
        ):
            return validate_dood_environment(str(tmp_path), require_x86_64=True)

    def test_aarch64_refused_with_reason(self, tmp_path):
        ok, message = self._run(tmp_path, "aarch64")
        assert ok is False
        assert "x86-64" in message and "AVX" in message

    def test_x86_64_accepted(self, tmp_path):
        assert self._run(tmp_path, "x86_64") == (True, None)


class TestQsiprepFlags:
    @pytest.fixture
    def builder(self, tmp_path):
        with (
            patch.dict("os.environ", {"LOCAL_PROJECT_DIR": str(tmp_path)}),
            patch(
                "tit.pre.qsi.docker_builder.resolve_fs_license_path", return_value=None
            ),
        ):
            yield DockerCommandBuilder(str(tmp_path))

    def _cmd(self, builder, **kwargs):
        with patch(
            "tit.pre.qsi.docker_builder.get_inherited_dood_resources",
            return_value=(8, 16),
        ):
            return builder.build_qsiprep_cmd(QSIPrepConfig(subject_id="001", **kwargs))

    @staticmethod
    def _value(cmd, flag):
        return cmd[cmd.index(flag) + 1]

    def test_explicit_defaults(self, builder):
        cmd = self._cmd(builder)
        assert self._value(cmd, "--hmc-model") == "eddy"
        assert self._value(cmd, "--pepolar-method") == "TOPUP"
        assert self._value(cmd, "--b0-threshold") == "100"
        assert self._value(cmd, "--denoise-method") == "dwidenoise"
        assert "--skip-anat-based-spatial-normalization" in cmd
        assert "--use-syn-sdc" not in cmd

    def test_syn_sdc_keeps_mni_normalization(self, builder):
        cmd = self._cmd(builder, use_syn_sdc=True)
        assert self._value(cmd, "--use-syn-sdc") == "warn"
        assert "--skip-anat-based-spatial-normalization" not in cmd

    def test_mni_normalization_opt_in(self, builder):
        cmd = self._cmd(builder, mni_normalization=True)
        assert "--skip-anat-based-spatial-normalization" not in cmd

    def test_resolved_resolution_and_unringing(self, builder):
        cmd = self._cmd(builder, output_resolution=1.7, unringing_method="rpg")
        assert self._value(cmd, "--output-resolution") == "1.7"
        assert self._value(cmd, "--unringing-method") == "rpg"
