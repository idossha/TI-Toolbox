"""
DTI quality control report generator for TI-Toolbox.

Produces an HTML report with FA-on-T1 registration overlays,
color-coded principal diffusion direction maps, and tensor statistics.
"""

import tempfile
from pathlib import Path

from ..core.base import MetadataReportlet
from ..reportlets.images import SliceSeriesReportlet
from .base_generator import BaseReportGenerator


class DTIQCReportGenerator(BaseReportGenerator):
    """Report generator for DTI tensor quality control."""

    def __init__(
        self,
        project_dir: str | Path,
        subject_id: str,
    ):
        super().__init__(
            project_dir=project_dir,
            subject_id=subject_id,
            report_type="dti_qc",
        )
        self._tensor_file: str = ""
        self._t1_file: str = ""
        self._metrics: dict = {}
        self._color_fa_images: dict = {}
        self._fa_overlay_images: dict = {}

    def _get_default_title(self) -> str:
        return f"DTI Quality Control - Subject {self.subject_id}"

    def _get_report_prefix(self) -> str:
        return "dti_qc"

    def generate(self, tensor_file: str, t1_file: str) -> Path:
        """Generate the DTI QC report.

        Parameters
        ----------
        tensor_file : str
            Path to the 6-component tensor NIfTI.
        t1_file : str
            Path to the T1-weighted anatomical NIfTI.

        Returns
        -------
        Path
            Path to the saved HTML report.
        """
        from tit.plotting.dti_qc import compute_dti_qc_metrics, generate_color_fa_image
        from tit.plotting.static_overlay import generate_static_overlay_images

        self._tensor_file = tensor_file
        self._t1_file = t1_file

        # 1. Compute metrics
        self._metrics = compute_dti_qc_metrics(tensor_file)

        # 2. Generate color FA images
        self._color_fa_images = generate_color_fa_image(tensor_file, t1_file)

        # 3. Compute FA volume and generate FA-on-T1 overlay
        self._fa_overlay_images = self._generate_fa_overlay(tensor_file, t1_file)

        # 4. Build and save report (calls _build_report via super)
        return super().generate()

    def _generate_fa_overlay(self, tensor_file: str, t1_file: str) -> dict:
        """Compute FA volume as temp NIfTI and overlay on T1."""
        import nibabel as nib
        import numpy as np

        from tit.plotting.static_overlay import generate_static_overlay_images

        img = nib.load(tensor_file)
        data = img.get_fdata(dtype=np.float32)
        spatial = data.shape[:3]

        nonzero_mask = np.any(data != 0, axis=-1)
        voxels = data[nonzero_mask]

        N = voxels.shape[0]
        tensors = np.zeros((N, 3, 3), dtype=np.float32)
        tensors[:, 0, 0] = voxels[:, 0]
        tensors[:, 0, 1] = voxels[:, 1]
        tensors[:, 0, 2] = voxels[:, 2]
        tensors[:, 1, 0] = voxels[:, 1]
        tensors[:, 1, 1] = voxels[:, 3]
        tensors[:, 1, 2] = voxels[:, 4]
        tensors[:, 2, 0] = voxels[:, 2]
        tensors[:, 2, 1] = voxels[:, 4]
        tensors[:, 2, 2] = voxels[:, 5]

        eigenvalues = np.linalg.eigvalsh(tensors)
        lam_mean = eigenvalues.mean(axis=-1, keepdims=True)
        lam_sq_sum = np.sum(eigenvalues**2, axis=-1)
        lam_diff_sq_sum = np.sum((eigenvalues - lam_mean) ** 2, axis=-1)
        denom = lam_sq_sum.copy()
        denom[denom == 0] = 1.0
        fa = np.sqrt(1.5) * np.sqrt(lam_diff_sq_sum) / np.sqrt(denom)
        fa = np.clip(fa, 0.0, 1.0)

        fa_vol = np.zeros(spatial, dtype=np.float32)
        fa_vol[nonzero_mask] = fa

        # Write to temp file and call static overlay
        with tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False) as tmp:
            fa_img = nib.Nifti1Image(fa_vol, img.affine, img.header)
            nib.save(fa_img, tmp.name)
            return generate_static_overlay_images(
                t1_file=t1_file,
                overlay_file=tmp.name,
            )

    def _build_report(self) -> None:
        """Build the three report sections."""
        self._build_registration_section()
        self._build_orientation_section()
        self._build_statistics_section()

    # ------------------------------------------------------------------
    def _build_registration_section(self) -> None:
        section = self.assembler.add_section(
            section_id="registration",
            title="Registration Quality",
            description=(
                "FA map overlaid on T1w anatomical image. White matter "
                "regions in the FA map should align with white matter "
                "visible in the T1."
            ),
            order=0,
        )

        for orientation in ("axial", "coronal"):
            slices = self._fa_overlay_images.get(orientation, [])
            if not slices:
                continue
            series = SliceSeriesReportlet(
                title=f"FA on T1 - {orientation.title()}",
                orientation=orientation,
            )
            for s in slices:
                series.add_slice(s["base64"], label=f"Slice {s['slice_num']}")
            section.add_reportlet(series)

    def _build_orientation_section(self) -> None:
        section = self.assembler.add_section(
            section_id="orientation",
            title="Tensor Orientation",
            description=(
                "Color-coded principal diffusion direction map "
                "(red=left-right, green=anterior-posterior, "
                "blue=superior-inferior). Corpus callosum should be red, "
                "corticospinal tract blue, superior longitudinal "
                "fasciculus green."
            ),
            order=1,
        )

        for orientation in ("axial", "coronal"):
            slices = self._color_fa_images.get(orientation, [])
            if not slices:
                continue
            series = SliceSeriesReportlet(
                title=f"Color FA - {orientation.title()}",
                orientation=orientation,
            )
            for s in slices:
                series.add_slice(s["base64"], label=f"Slice {s['slice_num']}")
            section.add_reportlet(series)

    def _build_statistics_section(self) -> None:
        section = self.assembler.add_section(
            section_id="statistics",
            title="Tensor Statistics",
            order=2,
        )
        meta = MetadataReportlet(
            data=self._metrics,
            title="DTI Metrics",
            display_mode="table",
        )
        section.add_reportlet(meta)


def create_dti_qc_report(
    project_dir: str | Path,
    subject_id: str,
    tensor_file: str,
    t1_file: str,
) -> Path:
    """Convenience wrapper to generate a DTI QC report.

    Parameters
    ----------
    project_dir : str or Path
        BIDS project root.
    subject_id : str
        Subject identifier (without ``sub-`` prefix).
    tensor_file : str
        Path to the 6-component tensor NIfTI.
    t1_file : str
        Path to the T1-weighted NIfTI.

    Returns
    -------
    Path
        Path to the saved HTML report.
    """
    gen = DTIQCReportGenerator(project_dir=project_dir, subject_id=subject_id)
    return gen.generate(tensor_file=tensor_file, t1_file=t1_file)
