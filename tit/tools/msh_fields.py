"""Read the data fields of a Gmsh 2.2 ``.msh`` without SimNIBS and without loading the mesh.

A field ``.msh`` here is 24-420 MB, and the questions callers ask of it are small: which fields
does it carry (the analyzer's preflight, the catalog, the on-demand field producer), and what
range does one of them span (the Viewer's colour window when no NIfTI of it exists). Both are
answered by walking the section headers and seeking over every payload but the one asked for.

Public API
----------
msh_field_names
    Names of the node/element data fields in a mesh, or ``None`` when that cannot be told.
msh_element_field
    The values of one element data field, or ``None`` when the mesh does not carry it.
"""

from __future__ import annotations

import struct

#: Nodes per element for the Gmsh element types a SimNIBS mesh holds (line, triangle,
#: quadrangle, tetrahedron, hexahedron, prism, pyramid, point).
_GMSH_NODES_PER_ELEMENT = {1: 2, 2: 3, 3: 4, 4: 4, 5: 8, 6: 6, 7: 5, 15: 1}

_READ_ERRORS = (
    OSError,
    ValueError,
    IndexError,
    KeyError,
    struct.error,
    UnicodeDecodeError,
)


def _walk(path, want: str | None, *, tags: bool = False):
    """Every data field's name, the ``(rows, components)`` values of element field *want*, and
    with *tags* the first (physical) tag of each element of *want*'s rows, in row order.
    """
    import numpy as np  # only for the one block read; the catalog imports this module

    with open(path, "rb") as fh:
        if fh.readline().strip() != b"$MeshFormat":
            raise ValueError("not a Gmsh mesh")
        version, file_type, size = fh.readline().split()[:3]
        if not version.startswith(b"2"):
            raise ValueError("not Gmsh 2.x")
        binary, size = file_type == b"1", int(size)
        names: set[str] = set()
        values = None
        numbers = None  # element numbers of *want*'s rows
        elm_numbers: list = []  # with *tags*: element numbers and their physical tags
        elm_tags: list = []
        for line in iter(fh.readline, b""):
            tag = line.strip()
            if tag == b"$Nodes":
                count = int(fh.readline())
                if binary:
                    fh.seek(count * (4 + 3 * size), 1)
                else:
                    for _ in range(count):
                        fh.readline()
            elif tag == b"$Elements":
                count = int(fh.readline())
                while binary and count > 0:  # blocks of one element type each
                    etype, block, ntags = struct.unpack("<3i", fh.read(12))
                    nodes = _GMSH_NODES_PER_ELEMENT[etype]
                    if tags:
                        rows = np.frombuffer(
                            fh.read(block * 4 * (1 + ntags + nodes)), dtype="<i4"
                        ).reshape(block, 1 + ntags + nodes)
                        elm_numbers.append(rows[:, 0])
                        elm_tags.append(rows[:, 1])
                    else:
                        fh.seek(block * 4 * (1 + ntags + nodes), 1)
                    count -= block
                for _ in range(0 if binary else count):
                    line = fh.readline()
                    if tags:
                        parts = line.split()
                        elm_numbers.append([int(parts[0])])
                        elm_tags.append([int(parts[3])])
            elif tag in (b"$NodeData", b"$ElementData"):
                strings = [fh.readline() for _ in range(int(fh.readline()))]
                name = strings[0].strip().strip(b'"').decode() if strings else None
                if name is not None:
                    names.add(name)
                for _ in range(int(fh.readline())):  # real tags (time)
                    fh.readline()
                ints = [int(fh.readline()) for _ in range(int(fh.readline()))]
                components, count = ints[1], ints[2]
                read = tag == b"$ElementData" and name == want and values is None
                if binary:
                    if read:
                        row = np.dtype(
                            [("n", "<i4"), ("v", f"<f{size}", (components,))]
                        )
                        raw = fh.read(count * row.itemsize)
                        block = np.frombuffer(raw, dtype=row, count=count)
                        values, numbers = block["v"].copy(), block["n"].copy()
                    else:
                        fh.seek(count * (4 + components * size), 1)
                else:
                    rows = [fh.readline() for _ in range(count)]
                    if read:
                        values = np.array(
                            [r.split()[1 : 1 + components] for r in rows], dtype=float
                        ).reshape(count, components)
                        numbers = np.array([int(r.split()[0]) for r in rows])
        if tags and values is not None:
            known = np.concatenate(elm_numbers)
            lookup = np.zeros(int(known.max()) + 1, dtype=np.int64)
            lookup[known] = np.concatenate(elm_tags)
            return names, values, lookup[numbers]
        return names, values, None


def msh_field_names(path) -> set[str] | None:
    """Names of the node/element data fields in a Gmsh 2.2 ``.msh`` file, or ``None``.

    Walks the section headers and seeks over every payload (nodes, elements, field values),
    so a 40 MB central surface costs a few kilobytes of reading, not a mesh load, and
    nothing here needs SimNIBS. The field name is the first string tag of each
    ``$NodeData`` / ``$ElementData`` block. ``None`` means "could not tell" (not a Gmsh 2.2
    file, empty, truncated, an element type this table lacks) -- callers then skip the
    check rather than report a field as missing.
    """
    try:
        return _walk(path, None)[0]
    except _READ_ERRORS:
        return None


def msh_element_field(path, name: str, *, tags=None):
    """The values of element data field *name* in a Gmsh 2.2 ``.msh``: ``(N,)`` or ``(N, k)``.

    Only that block's payload is read (and, with *tags*, the element tags); everything else
    is seeked over as in :func:`msh_field_names`. With *tags*, only the values of elements
    whose physical tag is in *tags* (grey matter: ``[2]``). ``None`` when the mesh does not
    carry the field or cannot be read.
    """
    import numpy as np

    try:
        _, values, elm_tags = _walk(path, name, tags=tags is not None)
    except _READ_ERRORS:
        return None
    if values is None:
        return None
    if tags is not None:
        values = values[np.isin(elm_tags, list(tags))]
    return values[:, 0] if values.shape[1] == 1 else values
