#!/usr/bin/env python3
"""Convert a NIfTI segmentation/mask to a surface mesh (.stl or .msh)."""

import argparse
import sys
import nibabel as nib
import numpy as np
from pathlib import Path
from skimage import measure
from scipy import ndimage


def remove_small_components(mask, threshold=0.1):
    """
    Remove connected components smaller than threshold * largest component.

    Parameters
    ----------
    mask : ndarray
        Binary mask array
    threshold : float
        Minimum size threshold as fraction of largest component (0-1)

    Returns
    -------
    ndarray
        Cleaned binary mask
    """
    labeled, num_features = ndimage.label(mask)
    if num_features <= 1:
        return mask

    # Get size of each component
    component_sizes = ndimage.sum(mask, labeled, range(1, num_features + 1))
    max_size = component_sizes.max()
    min_size = max_size * threshold

    # Keep only components above threshold
    keep_labels = np.where(component_sizes >= min_size)[0] + 1
    cleaned = np.isin(labeled, keep_labels)

    return cleaned, num_features - len(keep_labels)


def nifti_to_mesh(input_file, output_file=None, clean_components=False, clean_threshold=0.1):
    """
    Convert a NIfTI segmentation/mask to a surface mesh.

    Parameters
    ----------
    input_file : str or Path
        Path to input NIfTI file
    output_file : str or Path, optional
        Path to output mesh file (.stl or .msh). If None, defaults to input_file with .stl extension
    clean_components : bool
        Whether to remove small disconnected components
    clean_threshold : float
        Minimum size threshold for component removal (as fraction of largest component)

    Returns
    -------
    dict
        Dictionary with mesh statistics: {'vertices': int, 'faces': int, 'output_file': str}
    """
    input_path = Path(input_file)

    if output_file is None:
        output_file = input_path.parent / f"{input_path.stem}.stl"

    output_path = Path(output_file)

    # Validate output format
    if output_path.suffix.lower() not in ['.stl', '.msh']:
        raise ValueError("Output file must have .stl or .msh extension")

    # Load NIfTI
    img = nib.load(str(input_path))
    data = img.get_fdata()
    affine = img.affine

    # Create binary mask (any non-zero value)
    mask = data > 0

    # Remove small disconnected components if requested
    removed_components = 0
    if clean_components:
        mask, removed_components = remove_small_components(mask, threshold=clean_threshold)

    # Run marching cubes
    verts, faces, normals, _ = measure.marching_cubes(mask, level=0.5)

    # Transform vertices to world coordinates (RAS)
    verts_world = nib.affines.apply_affine(affine, verts)

    # Save based on extension
    if output_path.suffix.lower() == '.stl':
        save_stl(verts_world, faces, str(output_path))
    else:  # .msh
        save_gmsh(verts_world, faces, str(output_path))

    return {
        'vertices': len(verts_world),
        'faces': len(faces),
        'output_file': str(output_path),
        'removed_components': removed_components
    }


def save_stl(verts, faces, filename):
    """Save mesh as binary STL format."""
    try:
        from stl import mesh as stl_mesh
    except ImportError:
        raise ImportError("stl package required for STL output. Install with: pip install numpy-stl")

    # Create the mesh
    surface = stl_mesh.Mesh(np.zeros(faces.shape[0], dtype=stl_mesh.Mesh.dtype))
    for i, f in enumerate(faces):
        for j in range(3):
            surface.vectors[i][j] = verts[f[j], :]

    surface.save(filename)


def save_gmsh(verts, faces, filename):
    """Save mesh as Gmsh .msh format (v2.2 ASCII)."""
    with open(filename, 'w') as f:
        # Header
        f.write("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n")

        # Nodes
        f.write("$Nodes\n")
        f.write(f"{len(verts)}\n")
        for i, v in enumerate(verts, 1):
            f.write(f"{i} {v[0]} {v[1]} {v[2]}\n")
        f.write("$EndNodes\n")

        # Elements (triangles = type 2)
        f.write("$Elements\n")
        f.write(f"{len(faces)}\n")
        for i, face in enumerate(faces, 1):
            # elem_id, elem_type(2=tri), num_tags, tag1, tag2, node1, node2, node3
            f.write(f"{i} 2 2 1 1 {face[0]+1} {face[1]+1} {face[2]+1}\n")
        f.write("$EndElements\n")


def main():
    """Command-line interface for converting NIfTI files to meshes."""
    parser = argparse.ArgumentParser(
        description="Convert NIfTI segmentation to surface mesh using marching cubes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s segmentation.nii.gz -o thalamus.stl
  %(prog)s mask.nii.gz --clean --output mesh.msh
  %(prog)s brain.nii.gz  # outputs brain.stl

Supported output formats: .stl (binary STL), .msh (Gmsh ASCII)
        """
    )
    parser.add_argument("input", help="Input NIfTI segmentation file")
    parser.add_argument("-o", "--output", help="Output mesh file (.stl or .msh)")
    parser.add_argument("--clean", action="store_true",
                        help="Remove small disconnected components (<10%% of largest)")
    parser.add_argument("--clean-threshold", type=float, default=0.1,
                        help="Minimum size threshold for component removal (0-1, default: 0.1)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print verbose output")

    args = parser.parse_args()

    # Validate clean threshold
    if not 0 <= args.clean_threshold <= 1:
        parser.error("Clean threshold must be between 0 and 1")

    try:
        # Convert to mesh
        result = nifti_to_mesh(
            args.input,
            args.output,
            clean_components=args.clean,
            clean_threshold=args.clean_threshold
        )

        if args.verbose:
            print(f"Input file: {args.input}")
            print(f"Output file: {result['output_file']}")
            print(f"Mesh statistics:")
            print(f"  Vertices: {result['vertices']}")
            print(f"  Faces: {result['faces']}")
            if result['removed_components'] > 0:
                print(f"  Removed components: {result['removed_components']}")
        else:
            print(f"Created mesh: {result['output_file']}")
            print(f"  Vertices: {result['vertices']}, Faces: {result['faces']}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
