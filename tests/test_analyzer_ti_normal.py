"""Mesh analysis of ``TI_normal`` reads the central surface; a field the surface lacks is refused.

What this pins (2026-10-22; layout of 2026-10-30)
    The run's central surface ``<sim>_TI_central.msh`` carries every volume field and
    ``TI_normal`` (``tit.volume_fields.central_surface``), so ``field="TI_normal"`` in mesh space
    is read from it, as the ``normal_*`` statistics of every other analysis are. A field it does
    not carry (``hf_peak`` of an older simulation) is a ``ValueError`` naming the field and the
    fields the surface does carry, and the submit-time preflight reports it before a job starts.
    The header reader also reads one tissue's element values from a binary mesh (``tags``).

Where the expectations come from
    Hand arithmetic on authored node values and areas (comments at each assertion), and an
    independent second path through the code: a ``TI_max`` analysis of the same ROI reports
    ``normal_mean``/``normal_max`` from ``_get_normal_stats``, which must equal the ``TI_normal``
    analysis's ``roi_mean``/``roi_max``. The ``.msh`` files for the header reader are written
    here by hand from the Gmsh 2.2 file-format specification (ASCII and binary), not by the
    reader under test.

Run: .venv/bin/python -m pytest tests/test_analyzer_ti_normal.py -q -p no:cacheprovider
Real SimNIBS meshes and Dataset 000: tests/numerical/test_analyzer_p06_real.py.
"""

from __future__ import annotations

import struct
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from tests.field_mesh import DEFAULT_FIELDS, write_central_surface, write_field_mesh
from tit.paths import get_path_manager

SID = "101"
SIM = "M1"

# Six nodes on the x axis, 10 mm apart, areas 1..6 mm^2.
COORDS = np.array([[10.0 * i, 0.0, 0.0] for i in range(6)])
AREAS = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
TI_MAX = np.array([1.0, 0.9, 0.8, 0.7, 0.6, 0.5])
TI_NORMAL = np.array([0.4, -0.1, 0.6, 0.2, 0.05, 0.3])
# A sphere at x = 10 mm, r = 10.5 mm holds nodes 0, 1, 2.
CENTER, RADIUS = (10.0, 0.0, 0.0), 10.5


def _mesh(fields: dict[str, np.ndarray], n: int = 6):
    return SimpleNamespace(
        nodes=SimpleNamespace(node_coord=COORDS[:n]),
        field={k: SimpleNamespace(value=v) for k, v in fields.items()},
        nodes_areas=lambda: AREAS[:n],
    )


def _touch(path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    pm = get_path_manager(str(tmp_path))
    _touch(Path(pm.m2m(SID)) / f"{SID}.msh")
    write_field_mesh(pm.ti_mesh(SID, SIM))
    write_central_surface(pm.ti_central_surface(SID, SIM), DEFAULT_FIELDS)
    return tmp_path


def _read_msh(project: Path, surface):
    pm = get_path_manager(str(project))
    by_path = {str(Path(pm.ti_central_surface(SID, SIM))): surface}
    return lambda path: by_path[str(path)]


def _analyzer(field):
    from tit.analyzer.analyzer import Analyzer

    with patch("tit.analyzer.analyzer.add_file_handler"):
        return Analyzer(SID, SIM, space="mesh", field=field)


def test_ti_normal_mesh_analysis_reads_the_central_surface(project: Path) -> None:
    surface = _mesh({"TI_max": TI_MAX, "TI_normal": TI_NORMAL})
    with patch("simnibs.read_msh", _read_msh(project, surface)):
        normal_run = _analyzer("TI_normal").analyze_sphere(CENTER, RADIUS)
        max_run = _analyzer(None).analyze_sphere(CENTER, RADIUS)

    # ROI TI_normal = [0.4, -0.1, 0.6] on areas [1, 2, 3]; positive: 0.4 (1), 0.6 (3).
    assert normal_run.field_name == "TI_normal"
    assert normal_run.roi_mean == pytest.approx((0.4 * 1 + 0.6 * 3) / 4)  # 0.55
    assert normal_run.roi_max == pytest.approx(0.6)
    assert normal_run.roi_min == pytest.approx(0.4)
    assert normal_run.n_elements == 2
    # Whole surface, positive: [0.4, 0.6, 0.2, 0.05, 0.3] on areas [1, 3, 4, 5, 6].
    gm = (0.4 * 1 + 0.6 * 3 + 0.2 * 4 + 0.05 * 5 + 0.3 * 6) / 19
    assert normal_run.gm_mean == pytest.approx(gm)
    # The TI_max run of the same ROI: [1.0, 0.9, 0.8] on [1, 2, 3].
    assert max_run.roi_mean == pytest.approx((1.0 + 1.8 + 2.4) / 6)
    # Independent path (_get_normal_stats) agrees with the TI_normal analysis.
    assert max_run.normal_mean == pytest.approx(normal_run.roi_mean)
    assert max_run.normal_max == pytest.approx(normal_run.roi_max)
    assert normal_run.roi_max <= max_run.roi_max


def test_field_absent_from_the_surface_names_it_and_the_fields_present(
    project: Path,
) -> None:
    surface = _mesh({"TI_max": TI_MAX, "TI_normal": TI_NORMAL})
    with patch("simnibs.read_msh", _read_msh(project, surface)):
        with pytest.raises(ValueError) as err:
            _analyzer("hf_peak").analyze_sphere(CENTER, RADIUS)
    message = str(err.value)
    assert "'hf_peak'" in message and "carries: TI_max" in message
    assert "KeyError" not in message


# -- the .msh header reader and the preflight that uses it -------------------------------------


def _ascii_msh(fields: list[tuple[str, str]]) -> bytes:
    """A Gmsh 2.2 ASCII mesh: 3 nodes, 1 triangle, one data block per (section, name)."""
    out = [
        "$MeshFormat",
        "2.2 0 8",
        "$EndMeshFormat",
        "$Nodes",
        "3",
        "1 0 0 0",
        "2 1 0 0",
        "3 0 1 0",
        "$EndNodes",
        "$Elements",
        "1",
        "1 2 2 1002 1 1 2 3",
        "$EndElements",
    ]
    for section, name in fields:
        count = 3 if section == "NodeData" else 1
        out += [f"${section}", "1", f'"{name}"', "1", "0.0", "3", "0", "1", str(count)]
        out += [f"{i + 1} {0.5 + i}" for i in range(count)]
        out += [f"$End{section}"]
    return ("\n".join(out) + "\n").encode()


TRIANGLE = (2, [[1, 1002, 1, 1, 2, 3]])  # Gmsh type 2: two tags, three nodes
# 24 bytes a byte-scanning reader would take for a field header; a header walker seeks
# over them, because they are one node's three coordinates.
POISON = b'\n$NodeData\n1\n"FAKE"\n1\n00'


def _binary_msh(
    fields: list[tuple[str, str]], blocks=(TRIANGLE,), poison: bool = False
) -> bytes:
    """The same mesh in Gmsh 2.2 binary: int 1 marker, packed nodes/elements/data."""
    out = b"$MeshFormat\n2.2 1 8\n" + struct.pack("<i", 1) + b"\n$EndMeshFormat\n"
    out += b"$Nodes\n4\n"
    for i, xyz in enumerate([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)], start=1):
        if poison and i == 2:
            out += struct.pack("<i", i) + POISON
        else:
            out += struct.pack("<i3d", i, *xyz)
    count = sum(len(rows) for _, rows in blocks)
    out += f"\n$EndNodes\n$Elements\n{count}\n".encode()
    for etype, rows in blocks:
        out += struct.pack("<3i", etype, len(rows), 2)
        for row in rows:
            out += struct.pack(f"<{len(row)}i", *row)
    out += b"\n$EndElements\n"
    for section, name in fields:
        count = 4 if section == "NodeData" else 1
        out += f'${section}\n1\n"{name}"\n1\n0.0\n3\n0\n1\n{count}\n'.encode()
        for i in range(count):
            out += struct.pack("<id", i + 1, 0.5 + i)
        out += f"\n$End{section}\n".encode()
    return out


def test_msh_field_names_seeks_over_payloads_and_element_blocks(tmp_path: Path) -> None:
    from tit.tools.msh_fields import msh_field_names

    assert len(POISON) == 24
    path = tmp_path / "volume.msh"
    tetra = (4, [[2, 2, 2, 1, 2, 3, 4], [3, 2, 2, 4, 3, 2, 1]])
    path.write_bytes(
        _binary_msh([("ElementData", "TI_max")], blocks=(TRIANGLE, tetra), poison=True)
    )
    assert msh_field_names(path) == {"TI_max"}  # not "FAKE"
    path.write_bytes(_binary_msh([("NodeData", "x")], blocks=((99, [[1, 0, 0]]),)))
    assert msh_field_names(path) is None  # an element type it cannot size


def _tail_poisoned_msh(rows: int = 6) -> bytes:
    """Binary Gmsh 2.2 whose last node, last element row and last data row are POISON.

    Each payload row is 4 bytes longer than a stride that forgets the leading int (node
    number, element number, data-row node number), so such a stride stops 4 x 6 = 24 bytes
    early -- exactly at the planted bytes, inside a fake "$NodeData" header. Too-long strides
    are pinned by the other fixtures.
    """
    assert rows * 4 >= len(POISON)
    out = b"$MeshFormat\n2.2 1 8\n" + struct.pack("<i", 1) + b"\n$EndMeshFormat\n"
    out += f"$Nodes\n{rows}\n".encode()
    for i in range(1, rows + 1):  # int number + three doubles (24 bytes)
        out += struct.pack("<i", i)
        out += POISON if i == rows else struct.pack("<3d", i, 0.0, 0.0)
    out += f"\n$EndNodes\n$Elements\n{rows}\n".encode()
    out += struct.pack("<3i", 2, rows, 2)  # one block: `rows` triangles, two tags each
    for i in range(1, rows + 1):  # number, 2 tags, 3 nodes: six ints (24 bytes)
        out += POISON if i == rows else struct.pack("<6i", i, 1002, 1, 1, 2, 3)
    out += b"\n$EndElements\n"
    # A 3-component node field (int number + three doubles per row), then a scalar one.
    out += f'$NodeData\n1\n"E"\n1\n0.0\n3\n0\n3\n{rows}\n'.encode()
    for i in range(1, rows + 1):
        out += struct.pack("<i", i)
        out += POISON if i == rows else struct.pack("<3d", 0.1, 0.2, 0.3)
    out += b'\n$EndNodeData\n$ElementData\n1\n"TI_max"\n1\n0.0\n3\n0\n1\n1\n'
    out += struct.pack("<id", 1, 0.5) + b"\n$EndElementData\n"
    return out


def test_msh_field_names_seeks_the_full_row_of_every_payload(tmp_path: Path) -> None:
    from tit.tools.msh_fields import msh_field_names

    path = tmp_path / "tails.msh"
    data = _tail_poisoned_msh()
    assert data.count(POISON) == 3  # last node, last element row, last data row
    path.write_bytes(data)
    assert msh_field_names(path) == {"E", "TI_max"}  # never "FAKE", never None


@pytest.mark.parametrize("writer", [_ascii_msh, _binary_msh])
def test_msh_field_names_reads_every_data_block(tmp_path: Path, writer) -> None:
    from tit.tools.msh_fields import msh_field_names

    path = tmp_path / "surface.msh"
    path.write_bytes(
        writer([("NodeData", "TI_max"), ("ElementData", "hf_peak"), ("NodeData", "x")])
    )
    assert msh_field_names(path) == {"TI_max", "hf_peak", "x"}
    path.write_bytes(writer([]))
    assert msh_field_names(path) == set()


def test_msh_field_names_cannot_tell_for_a_non_mesh(tmp_path: Path) -> None:
    from tit.tools.msh_fields import msh_field_names

    empty = _touch(tmp_path / "empty.msh")
    other = tmp_path / "other.msh"
    other.write_text('not a mesh\n$NodeData\n1\n"TI_max"\n')
    assert msh_field_names(empty) is None
    assert msh_field_names(other) is None
    assert msh_field_names(tmp_path / "missing.msh") is None


def _preflight(project: Path, **config):
    from tit.jobs.preflight import preflight

    base = {
        "mode": "single",
        "subject_id": SID,
        "simulation": SIM,
        "space": "mesh",
        "analysis_type": "spherical",
        "center": list(CENTER),
        "radius": RADIUS,
    }
    return preflight("analyzer", {**base, **config}, str(project))


def test_preflight_reports_an_unsaved_field_only_when_it_cannot_be_produced(
    project: Path,
) -> None:
    import json

    pm = get_path_manager(str(project))
    sim_dir = Path(pm.simulation(SID, SIM))
    volume = Path(pm.ti_mesh(SID, SIM))
    volume.write_bytes(_binary_msh([("ElementData", "TI_max")]))
    (sim_dir / "documentation").mkdir()
    (sim_dir / "documentation" / "config.json").write_text(
        json.dumps(
            {
                "subject_id": SID,
                "conductivity": "scalar",
                "electrode_pairs": [["a", "b"], ["c", "d"]],
            }
        )
    )
    hf = sim_dir / "high_Frequency" / "mesh"

    # hf_peak was not saved and the channel meshes it is computed from are missing.
    found = _preflight(project, field="hf_peak")
    assert [m.expected_path for m in found] == [str(volume)]
    assert "hf_peak" in found[0].what
    assert str(hf / f"{SID}_TDCS_1_scalar.msh") in found[0].how_to_fix
    # TI_normal is read from the normal mesh; carriers it cannot get only empty its carrier
    # metrics (carrier_note says why), so they are not a missing input.
    assert _preflight(project, field="TI_normal") == []
    assert _preflight(project) == []  # TI_max is saved
    # With the channel meshes kept, the analysis produces hf_peak (and TI_max's carriers).
    for label in ("1", "2"):
        _touch(hf / f"{SID}_TDCS_{label}_scalar.msh")
    assert _preflight(project, field="hf_peak") == []
    assert _preflight(project) == []


def test_msh_element_field_reads_one_tissue_of_a_binary_mesh(tmp_path: Path) -> None:
    """``tags`` keeps the values of the elements with that physical tag, in element order."""
    from tit.tools.msh_fields import msh_element_field

    tetra = (4, [[2, 2, 2, 1, 2, 3, 4], [3, 5, 5, 4, 3, 2, 1], [4, 2, 2, 1, 3, 2, 4]])
    out = b"$MeshFormat\n2.2 1 8\n" + struct.pack("<i", 1) + b"\n$EndMeshFormat\n"
    out += b"$Nodes\n4\n"
    for i, xyz in enumerate([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)], start=1):
        out += struct.pack("<i3d", i, *xyz)
    out += b"\n$EndNodes\n$Elements\n4\n"
    for etype, rows in (
        TRIANGLE,
        tetra,
    ):  # element 1: tag 1002; 2, 4: GM (2); 3: scalp (5)
        out += struct.pack("<3i", etype, len(rows), 2)
        for row in rows:
            out += struct.pack(f"<{len(row)}i", *row)
    out += b'\n$EndElements\n$ElementData\n1\n"TI_max"\n1\n0.0\n3\n0\n1\n4\n'
    for number, value in ((1, 10.0), (2, 20.0), (3, 30.0), (4, 40.0)):
        out += struct.pack("<id", number, value)
    out += b"\n$EndElementData\n"
    path = tmp_path / "volume.msh"
    path.write_bytes(out)
    assert list(msh_element_field(path, "TI_max")) == [10.0, 20.0, 30.0, 40.0]
    assert list(msh_element_field(path, "TI_max", tags=[2])) == [20.0, 40.0]
    assert list(msh_element_field(path, "TI_max", tags=[2, 1002])) == [10.0, 20.0, 40.0]
