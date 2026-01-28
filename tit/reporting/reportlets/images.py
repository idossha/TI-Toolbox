"""
Image-based reportlets for TI-Toolbox reports.

This module provides specialized reportlets for brain imaging visualizations,
including multi-slice brain views and electrode montage displays.
"""

import base64
import io
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from ..core.base import BaseReportlet, ImageReportlet
from ..core.protocols import ReportletType


class SliceSeriesReportlet(BaseReportlet):
    """
    Reportlet for displaying a series of brain slices.

    Displays multiple slices (typically 7) across axial, sagittal,
    or coronal views, commonly used for QC visualizations.
    """

    def __init__(
        self,
        title: Optional[str] = None,
        slices: Optional[List[Dict[str, Any]]] = None,
        orientation: str = "axial",
        caption: Optional[str] = None,
    ):
        """
        Initialize the slice series reportlet.

        Args:
            title: Title for the slice series
            slices: List of slice data dicts with 'base64' and optional 'label'
            orientation: View orientation (axial, sagittal, coronal)
            caption: Optional caption text
        """
        super().__init__(title)
        self.slices: List[Dict[str, Any]] = slices or []
        self.orientation = orientation
        self.caption = caption

    @property
    def reportlet_type(self) -> ReportletType:
        return ReportletType.IMAGE

    def add_slice(
        self,
        image_data: Union[str, bytes, Path, Any],
        label: Optional[str] = None,
        mime_type: str = "image/png",
    ) -> None:
        """
        Add a slice to the series.

        Args:
            image_data: Base64 string, bytes, path, or PIL Image
            label: Optional label for this slice
            mime_type: MIME type of the image
        """
        base64_data = self._process_image(image_data)
        self.slices.append(
            {
                "base64": base64_data,
                "label": label,
                "mime_type": mime_type,
            }
        )

    def _process_image(self, image_data: Union[str, bytes, Path, Any]) -> str:
        """Convert image data to base64 string."""
        if isinstance(image_data, str):
            # Assume already base64 encoded
            return image_data
        elif isinstance(image_data, bytes):
            return base64.b64encode(image_data).decode("utf-8")
        elif isinstance(image_data, Path):
            with open(image_data, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        else:
            # Assume PIL Image
            try:
                buffer = io.BytesIO()
                image_data.save(buffer, format="PNG")
                return base64.b64encode(buffer.getvalue()).decode("utf-8")
            except Exception:
                return ""

    def load_from_files(self, file_paths: List[Union[str, Path]]) -> None:
        """
        Load slices from a list of image files.

        Args:
            file_paths: List of paths to slice images
        """
        for i, path in enumerate(file_paths):
            path = Path(path)
            if path.exists():
                self.add_slice(path, label=f"Slice {i + 1}")

    def render_html(self) -> str:
        """Render the slice series as HTML."""
        if not self.slices:
            return f"""
            <div class="reportlet slice-series-reportlet" id="{self.reportlet_id}">
                <div class="image-placeholder">
                    <em>No slices available</em>
                </div>
            </div>
            """

        slice_images = []
        for slice_data in self.slices:
            mime_type = slice_data.get("mime_type", "image/png")
            label = slice_data.get("label", "")
            label_html = f'<span class="slice-label">{label}</span>' if label else ""

            slice_images.append(
                f"""
                <div class="slice-image">
                    <img src="data:{mime_type};base64,{slice_data["base64"]}"
                         alt="{label or 'Brain slice'}" />
                    {label_html}
                </div>
                """
            )

        title_html = f"<h3>{self._title}</h3>" if self._title else ""
        caption_html = (
            f'<p class="series-caption">{self.caption}</p>' if self.caption else ""
        )

        return f"""
        <div class="reportlet slice-series-reportlet {self.orientation}" id="{self.reportlet_id}">
            {title_html}
            <div class="slice-series">
                {"".join(slice_images)}
            </div>
            {caption_html}
        </div>
        """

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.reportlet_type.name,
            "id": self.reportlet_id,
            "title": self._title,
            "orientation": self.orientation,
            "caption": self.caption,
            "slice_count": len(self.slices),
        }


class MontageImageReportlet(BaseReportlet):
    """
    Reportlet for displaying electrode montage visualizations.

    Shows electrode placement with labeled pairs and optional
    intensity annotations.
    """

    def __init__(
        self,
        title: Optional[str] = None,
        image_source: Union[str, Path, bytes, Any, None] = None,
        electrode_pairs: Optional[List[Dict[str, Any]]] = None,
        montage_name: Optional[str] = None,
    ):
        """
        Initialize the montage image reportlet.

        Args:
            title: Title for the montage
            image_source: Montage image (path, bytes, or PIL Image)
            electrode_pairs: List of electrode pair configurations
            montage_name: Name of the montage
        """
        super().__init__(title)
        self._base64_data: Optional[str] = None
        self._mime_type: str = "image/png"
        self.electrode_pairs = electrode_pairs or []
        self.montage_name = montage_name

        if image_source is not None:
            self._load_image(image_source)

    @property
    def reportlet_type(self) -> ReportletType:
        return ReportletType.IMAGE

    def _load_image(self, source: Union[str, Path, bytes, Any]) -> None:
        """Load image from various sources and convert to base64."""
        if isinstance(source, (str, Path)):
            path = Path(source) if isinstance(source, str) else source
            if path.exists():
                suffix = path.suffix.lower()
                mime_types = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".gif": "image/gif",
                    ".svg": "image/svg+xml",
                }
                self._mime_type = mime_types.get(suffix, "image/png")
                with open(path, "rb") as f:
                    self._base64_data = base64.b64encode(f.read()).decode("utf-8")
        elif isinstance(source, bytes):
            self._base64_data = base64.b64encode(source).decode("utf-8")
        elif isinstance(source, str):
            # Assume already base64
            self._base64_data = source
        else:
            # Assume PIL Image
            try:
                buffer = io.BytesIO()
                source.save(buffer, format="PNG")
                self._base64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
            except Exception:
                pass

    def set_base64_data(self, data: str, mime_type: str = "image/png") -> None:
        """Directly set base64 encoded image data."""
        self._base64_data = data
        self._mime_type = mime_type

    def add_electrode_pair(
        self,
        name: str,
        electrode1: str,
        electrode2: str,
        intensity: Optional[float] = None,
    ) -> None:
        """
        Add an electrode pair to the montage info.

        Args:
            name: Name of the pair (e.g., "Pair 1")
            electrode1: First electrode position
            electrode2: Second electrode position
            intensity: Optional current intensity
        """
        self.electrode_pairs.append(
            {
                "name": name,
                "electrode1": electrode1,
                "electrode2": electrode2,
                "intensity": intensity,
            }
        )

    def render_html(self) -> str:
        """Render the montage image as HTML."""
        title_html = (
            f"<h3>{self._title or self.montage_name or 'Electrode Montage'}</h3>"
        )

        # Electrode pairs table
        pairs_html = ""
        if self.electrode_pairs:
            rows = []
            for pair in self.electrode_pairs:
                intensity_value = pair.get("intensity")
                if intensity_value is None or intensity_value == "":
                    intensity_str = "—"
                else:
                    try:
                        intensity_str = f"{float(intensity_value):.2f} mA"
                    except (TypeError, ValueError):
                        intensity_str = str(intensity_value)
                rows.append(
                    f"""
                    <tr>
                        <td>{pair.get("name", "")}</td>
                        <td>{pair.get("electrode1", "")}</td>
                        <td>{pair.get("electrode2", "")}</td>
                        <td>{intensity_str}</td>
                    </tr>
                    """
                )

            pairs_html = f"""
            <div class="electrode-pairs">
                <table class="data-table compact">
                    <thead>
                        <tr>
                            <th>Pair</th>
                            <th>Electrode 1</th>
                            <th>Electrode 2</th>
                            <th>Intensity</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(rows)}
                    </tbody>
                </table>
            </div>
            """

        # Image display
        image_html = ""
        if self._base64_data:
            image_html = f"""
            <figure class="montage-figure">
                <img src="data:{self._mime_type};base64,{self._base64_data}"
                     alt="{self.montage_name or 'Electrode montage'}"
                     class="report-image montage-image" />
            </figure>
            """
        else:
            image_html = """
            <div class="image-placeholder">
                <em>No montage image available</em>
            </div>
            """

        return f"""
        <div class="reportlet montage-reportlet" id="{self.reportlet_id}">
            {title_html}
            <div class="montage-content">
                {image_html}
                {pairs_html}
            </div>
        </div>
        """

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.reportlet_type.name,
            "id": self.reportlet_id,
            "title": self._title,
            "montage_name": self.montage_name,
            "electrode_pairs": self.electrode_pairs,
            "has_image": self._base64_data is not None,
        }


class MultiViewBrainReportlet(BaseReportlet):
    """
    Reportlet for displaying brain images in multiple views.

    Shows the same brain data in axial, sagittal, and coronal
    orientations side by side.
    """

    def __init__(
        self,
        title: Optional[str] = None,
        axial_image: Optional[Union[str, Path, bytes]] = None,
        sagittal_image: Optional[Union[str, Path, bytes]] = None,
        coronal_image: Optional[Union[str, Path, bytes]] = None,
        caption: Optional[str] = None,
    ):
        """
        Initialize the multi-view brain reportlet.

        Args:
            title: Title for the visualization
            axial_image: Axial view image
            sagittal_image: Sagittal view image
            coronal_image: Coronal view image
            caption: Optional caption
        """
        super().__init__(title)
        self.views: Dict[str, Optional[str]] = {
            "axial": None,
            "sagittal": None,
            "coronal": None,
        }
        self.caption = caption

        if axial_image:
            self.set_view("axial", axial_image)
        if sagittal_image:
            self.set_view("sagittal", sagittal_image)
        if coronal_image:
            self.set_view("coronal", coronal_image)

    @property
    def reportlet_type(self) -> ReportletType:
        return ReportletType.IMAGE

    def set_view(
        self, view_name: str, image_data: Union[str, Path, bytes, Any]
    ) -> None:
        """
        Set an image for a specific view.

        Args:
            view_name: One of 'axial', 'sagittal', 'coronal'
            image_data: Image data (path, bytes, base64, or PIL Image)
        """
        if view_name not in self.views:
            raise ValueError(f"Invalid view name: {view_name}")

        if isinstance(image_data, (str, Path)):
            path = Path(image_data)
            if path.exists():
                with open(path, "rb") as f:
                    self.views[view_name] = base64.b64encode(f.read()).decode("utf-8")
            else:
                # Assume already base64
                self.views[view_name] = str(image_data)
        elif isinstance(image_data, bytes):
            self.views[view_name] = base64.b64encode(image_data).decode("utf-8")
        else:
            # Assume PIL Image
            try:
                buffer = io.BytesIO()
                image_data.save(buffer, format="PNG")
                self.views[view_name] = base64.b64encode(buffer.getvalue()).decode(
                    "utf-8"
                )
            except Exception:
                pass

    def render_html(self) -> str:
        """Render the multi-view visualization as HTML."""
        title_html = f"<h3>{self._title}</h3>" if self._title else ""

        view_panels = []
        for view_name, base64_data in self.views.items():
            if base64_data:
                view_panels.append(
                    f"""
                    <div class="view-panel {view_name}">
                        <div class="view-label">{view_name.capitalize()}</div>
                        <img src="data:image/png;base64,{base64_data}"
                             alt="{view_name} view"
                             class="view-image" />
                    </div>
                    """
                )
            else:
                view_panels.append(
                    f"""
                    <div class="view-panel {view_name}">
                        <div class="view-label">{view_name.capitalize()}</div>
                        <div class="view-placeholder">Not available</div>
                    </div>
                    """
                )

        caption_html = (
            f'<p class="multiview-caption">{self.caption}</p>' if self.caption else ""
        )

        return f"""
        <div class="reportlet multiview-reportlet" id="{self.reportlet_id}">
            {title_html}
            <div class="multiview-grid">
                {"".join(view_panels)}
            </div>
            {caption_html}
        </div>
        """

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.reportlet_type.name,
            "id": self.reportlet_id,
            "title": self._title,
            "caption": self.caption,
            "available_views": [k for k, v in self.views.items() if v is not None],
        }
