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
        self._qc: dict = {}

    def _get_default_title(self) -> str:
        return f"DTI Quality Control - Subject {self.subject_id}"

    def _get_report_prefix(self) -> str:
        return "dti_qc"

    def generate(self, tensor_file: str, t1_file: str, qc: dict | None = None) -> Path:
        """Generate the DTI QC report.

        Parameters
        ----------
        tensor_file : str
            Path to the 6-component tensor NIfTI.
        t1_file : str
            Path to the T1-weighted anatomical NIfTI.
        qc : dict or None
            The ``DTI_coregT1_qc.json`` record (registration NCC, chain-vs-NCC
            displacement, positive-definite fraction, out-of-brain count ...).

        Returns
        -------
        Path
            Path to the saved HTML report.
        """
        from tit.plotting.dti_qc import compute_dti_qc_metrics, generate_color_fa_image
        from tit.plotting.static_overlay import generate_static_overlay_images

        self._tensor_file = tensor_file
        self._t1_file = t1_file
        self._qc = qc or {}

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

        from tit.plotting.dti_qc import fa_volume
        from tit.plotting.static_overlay import generate_static_overlay_images

        img, fa_vol = fa_volume(tensor_file)

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
                "on world (scanner RAS) axes (red=left-right, "
                "green=anterior-posterior, blue=superior-inferior). "
                "Corpus callosum should be red, "
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
        if self._qc:
            gate = {
                key: self._qc[key]
                for key in (
                    "passed",
                    "failures",
                    "ncc_chain",
                    "chain_vs_ncc_mm",
                    "pct_pd",
                    "pct_wmgm_zero",
                    "n_out_of_brain",
                    "wm_md_median",
                    "wm_fa_median",
                    "pct_wm_covered",
                    "pct_gm_covered",
                )
                if key in self._qc
            }
            section.add_reportlet(
                MetadataReportlet(
                    data=gate,
                    title="QC gate (DTI_coregT1_qc.json)",
                    display_mode="table",
                )
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
    qc: dict | None = None,
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
    qc : dict or None
        The ``DTI_coregT1_qc.json`` record, shown as the QC gate table.

    Returns
    -------
    Path
        Path to the saved HTML report.
    """
    gen = DTIQCReportGenerator(project_dir=project_dir, subject_id=subject_id)
    return gen.generate(tensor_file=tensor_file, t1_file=t1_file, qc=qc)
