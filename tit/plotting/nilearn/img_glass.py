"""Glass-brain PDF of a group-averaged field (Nilearn Visuals).

Called by :mod:`tit.plotting.nilearn.__main__`, the runner behind the desktop panel.
"""

from .cutoffs import format_vm, resolve_cutoffs


def create_glass_brain_entry_point_group(
    averaged_img,
    base_filename: str,
    output_dir: str,
    min_cutoff: float | None = None,
    max_cutoff: float | None = None,
    cmap: str = "hot",
    output_callback=None,
):
    """
    Entry point for glass brain visualization creation with pre-averaged nifti data.

    Args:
        averaged_img: Pre-averaged nibabel Nifti1Image
        base_filename: Base filename for output (without extension)
        output_dir: Output directory path
        min_cutoff: Minimum cutoff for visualization (V/m)
        max_cutoff: Maximum cutoff for visualization (V/m), if None uses 99.9th percentile
        cmap: Colormap name for visualization
        output_callback: Optional callback function for output (for GUI integration)
    """
    # Redirect stdout if callback provided (for GUI integration)
    import sys
    from contextlib import redirect_stdout
    import io
    import os
    import numpy as np
    import matplotlib.pyplot as plt
    from nilearn import plotting

    if output_callback:
        # Capture stdout and send to callback
        captured_output = io.StringIO()
        with redirect_stdout(captured_output):
            # Load and analyze data
            data = averaged_img.get_fdata()
            data_nonzero = data[data > 0]
            if len(data_nonzero) == 0:
                print("Warning: No non-zero field values found")
                return None

            max_value = np.max(data)
            percentile_999 = np.percentile(data_nonzero, 99.9)
            min_value = np.min(data_nonzero)

            min_cutoff, max_cutoff = resolve_cutoffs(
                data_nonzero, min_cutoff, max_cutoff
            )

            print(f"Electric field statistics (averaged data):")
            print(f"  Absolute maximum: {format_vm(max_value)} V/m")
            print(f"  99.9th percentile: {format_vm(percentile_999)} V/m")
            print(f"  Minimum (non-zero): {format_vm(min_value)} V/m")
            print(
                f"  Visualization range: {format_vm(min_cutoff)} - {format_vm(max_cutoff)} V/m"
            )

            # Create output filename
            pdf_filename = f"{base_filename}_glass_brain.pdf"
            pdf_filepath = os.path.join(output_dir, pdf_filename)

            # Create glass brain visualization
            plotting.plot_glass_brain(
                stat_map_img=averaged_img,
                threshold=min_cutoff,
                vmax=max_cutoff,
                cmap=cmap,
                colorbar=True,
                plot_abs=False,
                symmetric_cbar=False,
                display_mode="lyrz",
                title=f"Electric Field - Group Average\n{format_vm(min_cutoff)}-{format_vm(max_cutoff)} V/m",
                output_file=pdf_filepath,
            )

            print(f"✓ Saved glass brain visualization: {pdf_filepath}")
            result = pdf_filepath

        # Send captured output to callback line by line
        output_text = captured_output.getvalue()
        for line in output_text.split("\n"):
            if line.strip():
                output_callback(line)

        if result:
            output_callback(f"✓ Glass brain visualization completed: {result}")
            return result
        else:
            output_callback("✗ Glass brain visualization failed")
            return None
    else:
        # Normal operation - print to stdout
        # Load and analyze data
        data = averaged_img.get_fdata()
        data_nonzero = data[data > 0]
        if len(data_nonzero) == 0:
            print("Warning: No non-zero field values found")
            return None

        max_value = np.max(data)
        percentile_999 = np.percentile(data_nonzero, 99.9)
        min_value = np.min(data_nonzero)

        min_cutoff, max_cutoff = resolve_cutoffs(data_nonzero, min_cutoff, max_cutoff)

        print(f"Electric field statistics (averaged data):")
        print(f"  Absolute maximum: {format_vm(max_value)} V/m")
        print(f"  99.9th percentile: {format_vm(percentile_999)} V/m")
        print(f"  Minimum (non-zero): {format_vm(min_value)} V/m")
        print(
            f"  Visualization range: {format_vm(min_cutoff)} - {format_vm(max_cutoff)} V/m"
        )

        # Create output filename
        pdf_filename = f"{base_filename}_glass_brain.pdf"
        pdf_filepath = os.path.join(output_dir, pdf_filename)

        # Create glass brain visualization
        plotting.plot_glass_brain(
            stat_map_img=averaged_img,
            threshold=min_cutoff,
            vmax=max_cutoff,
            cmap=cmap,
            colorbar=True,
            plot_abs=False,
            symmetric_cbar=False,
            display_mode="lyrz",
            title=f"Electric Field - Group Average\n{format_vm(min_cutoff)}-{format_vm(max_cutoff)} V/m",
            output_file=pdf_filepath,
        )

        print(f"✓ Saved glass brain visualization: {pdf_filepath}")
        result = pdf_filepath

        if result:
            print(f"\n✓ Glass brain visualization completed: {result}")
            return result
        else:
            print("\n✗ Glass brain visualization failed")
            return None
