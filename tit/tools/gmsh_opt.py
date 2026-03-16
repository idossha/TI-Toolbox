"""
Gmsh .opt file generation for TI-Toolbox.

Provides helpers for creating Gmsh visualization option files.
"""

__all__ = ["create_mesh_opt_file"]


def create_mesh_opt_file(mesh_path, field_info=None):
    """
    Create a .opt file for Gmsh visualization of mesh fields.

    Parameters
    ----------
    mesh_path : str
        Path to the .msh file (without .opt extension)
    field_info : dict, optional
        Dictionary with field information containing:
        - 'fields': list of field names to visualize
        - 'max_values': dict mapping field names to their max values (optional)
        - 'field_type': str, either 'node' or 'element' (default: 'node')
    """
    if field_info is None:
        field_info = {}

    fields = field_info.get("fields", [])
    max_values = field_info.get("max_values", {})

    opt_content = """// Gmsh visualization settings for mesh fields
Mesh.SurfaceFaces = 0;
Mesh.SurfaceEdges = 0;
Mesh.Points = 0;
Mesh.Lines = 0;

"""

    for i, field_name in enumerate(fields):
        view_index = i + 1
        max_value = max_values.get(field_name, 1.0)
        opt_content += f"""// View[{view_index}] ({field_name})
View[{view_index}].Visible = 1;
View[{view_index}].ColormapNumber = {i + 1};
View[{view_index}].RangeType = 2;
View[{view_index}].CustomMin = 0;
View[{view_index}].CustomMax = {max_value};
View[{view_index}].ShowScale = 1;
View[{view_index}].ColormapAlpha = 1;
View[{view_index}].ColormapAlphaPower = 0.08;

"""

    opt_content += "// Field information:\n"
    for i, field_name in enumerate(fields):
        max_value = max_values.get(field_name, 1.0)
        opt_content += f"// View[{i + 1}]: {field_name} (max: {max_value:.6f})\n"

    opt_path = f"{mesh_path}.opt"
    with open(opt_path, "w") as f:
        f.write(opt_content)

    return opt_path
