"""Multi-slice PDF of a group-averaged field with atlas outlines (Nilearn Visuals).

Called by :mod:`tit.plotting.nilearn.__main__`, the runner behind the desktop panel.
"""

from .visualizer import NilearnVisualizer


def create_pdf_entry_point_group(
    averaged_img,
    base_filename: str,
    output_dir: str,
    min_cutoff: float | None = None,
    max_cutoff: float | None = None,
    atlas_name: str = "harvard_oxford_sub",
    selected_regions: list = None,
    output_callback=None,
):
    """
    Entry point for PDF visualization creation with pre-averaged nifti data.

    Args:
        averaged_img: Pre-averaged nibabel Nifti1Image
        base_filename: Base filename for output (without extension)
        output_dir: Output directory path
        min_cutoff: Minimum cutoff for visualization (V/m)
        max_cutoff: Maximum cutoff for visualization (V/m), if None uses 99.9th percentile
        atlas_name: Atlas name for contours
        selected_regions: List of region indices to include (0-indexed), if None includes all
        output_callback: Optional callback function for output (for GUI integration)
    """
    # Redirect stdout if callback provided (for GUI integration)
    import sys
    from contextlib import redirect_stdout
    import io

    if output_callback:
        # Capture stdout and send to callback
        captured_output = io.StringIO()
        with redirect_stdout(captured_output):
            visualizer = NilearnVisualizer()
            result = visualizer.create_pdf_visualization_group(
                averaged_img,
                base_filename,
                output_dir,
                min_cutoff,
                max_cutoff,
                atlas_name,
                selected_regions,
            )

        # Send captured output to callback line by line
        output_text = captured_output.getvalue()
        for line in output_text.split("\n"):
            if line.strip():
                output_callback(line)

        if result:
            output_callback(f"✓ PDF visualization completed: {result}")
            return result
        else:
            output_callback("✗ PDF visualization failed")
            return None
    else:
        # Normal operation - print to stdout
        visualizer = NilearnVisualizer()
        result = visualizer.create_pdf_visualization_group(
            averaged_img,
            base_filename,
            output_dir,
            min_cutoff,
            max_cutoff,
            atlas_name,
            selected_regions,
        )
        if result:
            print(f"\n✓ PDF visualization completed: {result}")
            return result
        else:
            print("\n✗ PDF visualization failed")
            return None
