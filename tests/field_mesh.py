"""A stand-in field mesh: a Gmsh 2.2 file with no elements whose header lists the saved fields.

The on-demand path reads which fields a simulation saved from its volume mesh's section
headers (``tit.tools.msh_fields.msh_field_names``) and refuses a mesh it cannot read, so a
fixture's ``<sim>_TI.msh`` must be a readable mesh, not an empty file. Importable by any test
(``from tests.field_mesh import write_field_mesh``).
"""

from __future__ import annotations

from pathlib import Path

#: What a default simulation saves.
DEFAULT_FIELDS = ("TI_max", "hf_peak", "hf_sar")


def write_field_mesh(path, fields=DEFAULT_FIELDS) -> Path:
    """Write a header-only Gmsh 2.2 ASCII mesh carrying *fields* (element data) at *path*."""
    lines = ["$MeshFormat", "2.2 0 8", "$EndMeshFormat", "$Nodes", "1", "1 0 0 0"]
    lines += ["$EndNodes", "$Elements", "0", "$EndElements"]
    for name in fields:
        lines += ["$ElementData", "1", f'"{name}"', "1", "0.0", "3", "0", "1", "0"]
        lines += ["$EndElementData"]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path
