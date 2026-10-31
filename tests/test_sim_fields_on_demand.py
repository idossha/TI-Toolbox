"""A field the simulation did not save is produced, once, from its channel meshes (2026-10-30).

What this pins (``tit/volume_fields.py``; docs/dev/DECISIONS.md 2026-10-30, field meshes by default)
    * ``ensure_mesh_fields`` computes a missing volume field from the channel meshes kept in
      ``high_Frequency/mesh/`` (``<sid>_TDCS_1|2_<cond>.msh``; ``A..Z`` for mTI), cropped to brain
      tissue, adds it to ``<sim>/<TI|mTI>/mesh/<sim>_<TI|mTI>.msh`` (the header then lists it),
      rewrites the central surface with every field and ``TI_normal``, and says so in one
      sentence; a second call finds it saved and reads nothing;
    * an old run's central surface (no ``TI_normal``) is rebuilt from its volume mesh, with
      ``TI_normal`` copied from its ``<sim>_normal.msh`` or else computed from the channel
      meshes; a head model whose central surface has another node count is refused;
    * no fallback: a missing channel mesh, a missing run record, an envelope of a carrier-only run
      and an unsaved ``hf_power_density`` are a ``FieldUnavailableError`` naming what is missing,
      and the volume mesh is left as it was; a volume mesh from another run is refused;
    * a carrier-only run's carriers are produced coherently, as the simulator adds them;
    * ``ensure_niftis`` writes exactly the NIfTI a voxel step reads, under the simulator's own name
      (``<tissue_><sim>_<TI|mTI>_subject_<field>.nii.gz``; ``..._MNI_MNI_...`` in MNI space), from
      the volume mesh cropped to that tissue; ``ensure_nifti_file`` does it for a resolved
      group-tool path and leaves any other name alone;
    * ``check_niftis_match_meshes``: the simulator's NIfTI set is its mesh field set, name for name.

Where the expected numbers come from
    Hand formulas on authored channel fields: for two channels ``hf_peak = max(|E1 + E2|,
    |E1 - E2|)`` and ``hf_rms = sqrt((|E1|^2 + |E2|^2) / 2)`` (Cassarà 2025), and the coherent carrier-only
    ``hf_rms = |E1 + E2| / sqrt(2)``. Meshes are real Gmsh 2.2 ASCII files (their headers are what is
    checked); SimNIBS is mocked on the host, so ``mesh_io`` here reads and writes those files,
    and :func:`tit.volume_fields.central_surface` is replaced by a recorder (its numbers are
    tests/numerical/test_central_surface_real.py's).

Reproduce: ``.venv/bin/python -m pytest tests/test_sim_fields_on_demand.py -q -p no:cacheprovider``
The same path on real SimNIBS meshes is tests/numerical/test_sim_fields_on_demand_real.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from tit import volume_fields as fields
from tit.volume_fields import FieldUnavailableError
from tit.tools.msh_fields import msh_element_field, msh_field_names

SID, SIM = "001", "M"
# GM, WM, an electrode rubber (100, dropped by the brain crop), CSF, a GM triangle (1002)
TAGS = np.array([2, 1, 100, 3, 1002])
BRAIN = np.isin(TAGS, fields.BRAIN_TAGS)
E1 = np.array([[1.0, 0, 0], [0, 2, 0], [9, 9, 9], [3, 4, 0], [0, 0, 1]])
E2 = np.array([[0.0, 1, 0], [0, -1, 0], [9, 9, 9], [3, 4, 0], [0, 0, -2]])


def write_msh(path: Path, n: int, data: dict[str, np.ndarray], nodes: int = 4) -> None:
    """A Gmsh 2.2 ASCII mesh of *n* tetrahedra carrying *data* as element fields."""
    out = ["$MeshFormat", "2.2 0 8", "$EndMeshFormat", "$Nodes", str(nodes)]
    out += [f"{i} {i} 0 0" for i in range(1, nodes + 1)]
    out += ["$EndNodes", "$Elements", str(n)]
    out += [f"{i} 4 2 2 2 1 2 3 4" for i in range(1, n + 1)]
    out += ["$EndElements"]
    for name, values in data.items():
        values = np.asarray(values, dtype=float).reshape(n, -1)
        out += [
            "$ElementData",
            "1",
            f'"{name}"',
            "1",
            "0.0",
            "3",
            "0",
            str(values.shape[1]),
            str(n),
        ]
        out += [
            f"{i} " + " ".join(f"{v:.17g}" for v in row)
            for i, row in enumerate(values, 1)
        ]
        out += ["$EndElementData"]
    path.write_text("\n".join(out) + "\n")


class FakeMesh:
    """The slice of ``simnibs.mesh_io.Msh`` the producer touches."""

    def __init__(self, tags, data, nodes=4):
        self.elm = SimpleNamespace(tag1=np.asarray(tags), nr=len(tags))
        self.nodes = SimpleNamespace(nr=nodes)
        self.elmdata = [
            SimpleNamespace(field_name=k, value=np.asarray(v)) for k, v in data.items()
        ]

    @property
    def field(self):
        return {d.field_name: d for d in self.elmdata}

    def add_element_field(self, value, name):
        self.elmdata.append(SimpleNamespace(field_name=name, value=np.asarray(value)))

    add_node_field = add_element_field  # the fake keeps every field per element

    def crop_mesh(self, tags):
        keep = np.isin(self.elm.tag1, tags)
        return FakeMesh(
            self.elm.tag1[keep], {d.field_name: d.value[keep] for d in self.elmdata}
        )


class FakeMeshIO:
    """Channel meshes are authored in memory; every other path is a real ASCII file."""

    def __init__(self, channels: dict[str, np.ndarray]):
        self.channels = channels
        self.reads: list[str] = []
        self.written: dict[str, FakeMesh] = {}

    def read_msh(self, path):
        self.reads.append(Path(path).name)
        for name, e in self.channels.items():
            if Path(path).name == name:
                return FakeMesh(TAGS, {"E": e})
        names = sorted(msh_field_names(path))
        n = len(msh_element_field(path, names[0])) if names else int(BRAIN.sum())
        lines = Path(path).read_text().splitlines()
        nodes = int(lines[lines.index("$Nodes") + 1])
        return FakeMesh(
            np.full(n, 2), {k: msh_element_field(path, k) for k in names}, nodes
        )

    def write_msh(self, mesh, path):
        self.written[Path(path).name] = mesh
        write_msh(
            Path(path),
            mesh.elm.nr,
            {d.field_name: d.value for d in mesh.elmdata},
            mesh.nodes.nr,
        )


def make_simulation(
    pm,
    *,
    mode="TI",
    channels=2,
    carrier_only=False,
    saved=("TI_max",),
    niftis=(),
    surface=True,
    legacy_normal=None,
):
    """A finished run on disk: run record, volume mesh with *saved*, its central surface, kept
    channel meshes, and the head model's central surfaces.

    *niftis* (``"subject"``, ``"mni"``) is a run that wrote NIfTIs: its record says so, and the
    volume mesh and its grey/white crops have one NIfTI per saved field in those spaces.
    *surface* ``"old"`` is a central surface written before it carried ``TI_normal``, ``False``
    none; *legacy_normal* (values) adds the old ``<sim>_normal.msh``.
    """
    sim_dir = Path(pm.simulation(SID, SIM))
    (sim_dir / mode / "mesh" / "surfaces").mkdir(parents=True)
    (sim_dir / "documentation").mkdir()
    (sim_dir / "documentation" / "config.json").write_text(
        json.dumps(
            {
                "subject_id": SID,
                "conductivity": "scalar",
                "electrode_pairs": [["a", "b"]] * channels,
                "carrier_only": carrier_only,
                "mapping_options": {
                    "map_to_vol": bool(niftis),
                    "map_to_mni": "mni" in niftis,
                },
            }
        )
    )
    n = int(BRAIN.sum())
    write_msh(
        sim_dir / mode / "mesh" / f"{SIM}_{mode}.msh", n, {f: np.ones(n) for f in saved}
    )
    if surface:
        on_surface = {f: np.ones(n) for f in saved}
        if surface != "old" and not carrier_only:
            on_surface["TI_normal"] = np.ones(n)
        write_msh(
            sim_dir / mode / "mesh" / "surfaces" / f"{SIM}_{mode}_central.msh",
            n,
            on_surface,
        )
    if legacy_normal is not None:
        suffix = "_mTI_normal" if mode == "mTI" else "_normal"
        write_msh(
            sim_dir / mode / "mesh" / f"{SIM}{suffix}.msh",
            len(legacy_normal),
            {"TI_normal": np.asarray(legacy_normal, dtype=float)},
            nodes=4 if len(legacy_normal) == n else 5,
        )
    m2m_surfaces = Path(pm.m2m(SID)) / "surfaces"
    m2m_surfaces.mkdir(parents=True, exist_ok=True)
    for hemi in ("lh", "rh"):
        (m2m_surfaces / f"{hemi}.central.gii").write_text("gifti")
    for space in niftis:
        token = "MNI_MNI" if space == "mni" else "subject"
        for stem in (f"{SIM}_{mode}", f"grey_{SIM}_{mode}", f"white_{SIM}_{mode}"):
            for f in saved:
                path = sim_dir / mode / "niftis" / f"{stem}_{token}_{f}.nii.gz"
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(b"nii")
    hf = sim_dir / "high_Frequency" / "mesh"
    hf.mkdir(parents=True)
    labels = "ABCDEFGH"[:channels] if mode == "mTI" else "12"
    for label in labels:
        (hf / f"{SID}_TDCS_{label}_scalar.msh").write_text("kept by the run")
    return sim_dir


def fake_central(calls: list, fail: list | None = None):
    """``central_surface``: the volume's fields per element, ``TI_normal`` (= 7) with channels.

    Records ``(volume field names, e_fields given)``; raises while *fail* is set.
    """

    def central(volume, m2m, *, e_fields=None):
        calls.append(([d.field_name for d in volume.elmdata], e_fields is not None))
        if fail:
            raise RuntimeError(fail.pop())
        data = {d.field_name: d.value for d in volume.elmdata}
        if e_fields is not None:
            data["TI_normal"] = np.full(volume.elm.nr, 7.0)
        return FakeMesh(np.full(volume.elm.nr, 1002), data)

    return central


@pytest.fixture()
def producer(init_pm):
    """Mocked SimNIBS reading TI channel fields E1/E2; the central surface recorded."""
    io = FakeMeshIO({f"{SID}_TDCS_1_scalar.msh": E1, f"{SID}_TDCS_2_scalar.msh": E2})
    calls = SimpleNamespace(surface=[])
    with (
        patch.object(sys.modules["simnibs"], "mesh_io", io),
        patch.object(fields, "central_surface", fake_central(calls.surface)),
    ):
        yield SimpleNamespace(io=io, calls=calls, pm=init_pm)


def test_a_missing_field_is_computed_from_the_channel_meshes_and_saved(
    producer,
) -> None:
    sim_dir = make_simulation(producer.pm)
    volume = sim_dir / "TI" / "mesh" / f"{SIM}_TI.msh"

    notices = fields.ensure_mesh_fields(SID, SIM, ["TI_max", "hf_peak", "hf_rms"])

    assert notices == [
        "hf_peak and hf_rms were not saved for M; computing them from the channel "
        "fields and saving them to M_TI.msh."
    ]
    assert msh_field_names(volume) == {"TI_max", "hf_peak", "hf_rms"}
    e1, e2 = E1[BRAIN], E2[BRAIN]  # the brain crop drops the rubber element
    peak = np.maximum(np.linalg.norm(e1 + e2, axis=1), np.linalg.norm(e1 - e2, axis=1))
    rms = np.sqrt(((e1**2).sum(axis=1) + (e2**2).sum(axis=1)) / 2)
    np.testing.assert_allclose(msh_element_field(volume, "hf_peak"), peak)
    np.testing.assert_allclose(msh_element_field(volume, "hf_rms"), rms)
    np.testing.assert_allclose(
        msh_element_field(volume, "TI_max"), 1.0
    )  # kept as saved
    # The central surface is rewritten from the new mesh with the channel fields (TI_normal),
    # in a staging folder, and moved into place; no grey/white mesh and no stage is left.
    assert producer.calls.surface == [(["TI_max", "hf_peak", "hf_rms"], True)]
    assert msh_field_names(volume.parent / "surfaces" / "M_TI_central.msh") == {
        "TI_max",
        "hf_peak",
        "hf_rms",
        "TI_normal",
    }
    assert sorted(p.name for p in volume.parent.iterdir()) == ["M_TI.msh", "surfaces"]
    assert not list((volume.parents[1]).glob(".on-demand-*"))


def test_a_production_killed_midway_leaves_nothing_half_written_and_a_rerun_completes(
    producer,
) -> None:
    sim_dir = make_simulation(producer.pm)
    volume = sim_dir / "TI" / "mesh" / f"{SIM}_TI.msh"
    central = sim_dir / "TI" / "mesh" / "surfaces" / "M_TI_central.msh"
    before, surface_before = volume.read_bytes(), central.read_bytes()
    fail = ["interpolation died"]
    with patch.object(fields, "central_surface", fake_central([], fail)):
        with pytest.raises(RuntimeError, match="interpolation died"):
            fields.ensure_mesh_fields(SID, SIM, ["hf_peak"])
        # Nothing moved: the volume mesh and its surface are as they were, and the staging
        # folder is gone, so the field still reads as not saved.
        assert volume.read_bytes() == before and central.read_bytes() == surface_before
        assert not list((sim_dir / "TI").glob(".on-demand-*"))
        # A stage left by a producer that was killed outright is cleared by the next one.
        (sim_dir / "TI" / ".on-demand-killed").mkdir()
        assert fields.ensure_mesh_fields(SID, SIM, ["hf_peak"])
    assert msh_field_names(volume) == {"TI_max", "hf_peak"}
    assert msh_field_names(central) == {"TI_max", "hf_peak", "TI_normal"}
    assert not list((sim_dir / "TI").glob(".on-demand-*"))


def test_saved_fields_produce_nothing(producer) -> None:
    make_simulation(producer.pm, saved=("TI_max", "hf_peak", "hf_rms"))
    assert fields.ensure_mesh_fields(SID, SIM, ["mTI_max", "hf_peak"]) == []
    assert producer.io.reads == [] and producer.calls.surface == []


def test_a_produced_field_is_saved_for_the_next_step(producer) -> None:
    make_simulation(producer.pm)
    assert fields.ensure_mesh_fields(SID, SIM, ["hf_peak"])
    producer.io.reads.clear()
    assert fields.ensure_mesh_fields(SID, SIM, ["hf_peak"]) == []
    assert producer.io.reads == []


def test_a_missing_channel_mesh_fails_naming_it_and_changes_nothing(producer) -> None:
    sim_dir = make_simulation(producer.pm)
    gone = sim_dir / "high_Frequency" / "mesh" / f"{SID}_TDCS_2_scalar.msh"
    gone.unlink()
    volume = sim_dir / "TI" / "mesh" / f"{SIM}_TI.msh"
    before = volume.read_bytes()
    with pytest.raises(
        FieldUnavailableError,
        match="hf_peak was not saved for M, and the channel meshes it is computed from",
    ) as err:
        fields.ensure_mesh_fields(SID, SIM, ["hf_peak"])
    assert str(gone) in str(err.value)
    assert volume.read_bytes() == before and producer.io.written == {}


def test_a_run_without_its_record_cannot_name_its_channels(producer) -> None:
    sim_dir = make_simulation(producer.pm)
    (sim_dir / "documentation" / "config.json").unlink()
    with pytest.raises(FieldUnavailableError, match="config.json"):
        fields.ensure_mesh_fields(SID, SIM, ["hf_rms"])


def test_no_field_mesh_is_run_the_simulation_first(producer) -> None:
    sim_dir = make_simulation(producer.pm)
    (sim_dir / "TI" / "mesh" / f"{SIM}_TI.msh").unlink()
    with pytest.raises(FieldUnavailableError, match="run the simulation first"):
        fields.ensure_mesh_fields(SID, SIM, ["TI_max"])


def test_a_carrier_only_run_has_no_envelope_and_adds_its_carriers_coherently(
    producer,
) -> None:
    sim_dir = make_simulation(producer.pm, carrier_only=True, saved=("hf_peak",))
    with pytest.raises(FieldUnavailableError, match="carrier-only control"):
        fields.ensure_mesh_fields(SID, SIM, ["TI_max"])
    fields.ensure_mesh_fields(SID, SIM, ["hf_rms"])
    e = E1[BRAIN] + E2[BRAIN]  # one sinusoid of amplitude E1 + E2
    np.testing.assert_allclose(
        msh_element_field(sim_dir / "TI" / "mesh" / f"{SIM}_TI.msh", "hf_rms"),
        np.sqrt((e**2).sum(axis=1) / 2),
    )


def test_hf_power_density_cannot_be_computed_afterwards(producer) -> None:
    make_simulation(producer.pm)
    with pytest.raises(
        FieldUnavailableError, match="conductivity of the original solve"
    ):
        fields.ensure_mesh_fields(SID, SIM, ["hf_power_density"])


def test_a_volume_mesh_from_another_run_is_refused(producer) -> None:
    sim_dir = make_simulation(producer.pm)
    write_msh(sim_dir / "TI" / "mesh" / f"{SIM}_TI.msh", 3, {"TI_max": np.ones(3)})
    with pytest.raises(RuntimeError, match="not from the same run"):
        fields.ensure_mesh_fields(SID, SIM, ["hf_peak"])


def test_surface_and_unknown_fields_are_not_volume_fields(producer) -> None:
    make_simulation(producer.pm)
    for name in ("TI_normal", "magnE"):
        with pytest.raises(ValueError, match="not a volume field"):
            fields.ensure_mesh_fields(SID, SIM, [name])


def test_an_mti_run_reads_its_lettered_channels_in_order(init_pm) -> None:
    e = [np.eye(5, 3, k) for k in range(4)]
    io = FakeMeshIO({f"{SID}_TDCS_{c}_scalar.msh": v for c, v in zip("ABCD", e)})
    make_simulation(init_pm, mode="mTI", channels=4, saved=("mTI_max",))
    with (
        patch.object(sys.modules["simnibs"], "mesh_io", io),
        patch.object(fields, "central_surface", fake_central([])),
    ):
        notices = fields.ensure_mesh_fields(SID, SIM, ["TI_max", "hf_rms"])
    assert notices == [
        "hf_rms was not saved for M; computing it from the channel fields and saving it "
        "to M_mTI.msh."
    ]
    assert io.reads[1:5] == [
        f"{SID}_TDCS_{c}_scalar.msh" for c in "ABCD"
    ]  # after the volume
    rms = np.sqrt(sum((v[BRAIN] ** 2).sum(axis=1) for v in e) / 2)
    volume = Path(init_pm.simulation(SID, SIM)) / "mTI" / "mesh" / "M_mTI.msh"
    np.testing.assert_allclose(msh_element_field(volume, "hf_rms"), rms)


@pytest.fixture()
def converter(producer):
    """``mesh2nii`` writing ``<prefix>_<field>.nii.gz`` (subject) / ``<prefix>_MNI_<field>`` (MNI)."""
    import tit.tools.mesh2nii as mesh2nii

    calls = []

    def subject(mesh, m2m, prefix, fields=None, tags=None):
        calls.append(
            ("subject", Path(mesh).name, Path(prefix).name, list(fields), tags)
        )
        for f in fields:
            Path(f"{prefix}_{f}.nii.gz").write_bytes(b"nii")

    def mni(mesh, m2m, prefix, fields=None, tags=None):
        calls.append(("mni", Path(mesh).name, Path(prefix).name, list(fields), tags))
        for f in fields:
            Path(f"{prefix}_MNI_{f}.nii.gz").write_bytes(b"nii")

    with (
        patch.object(mesh2nii, "msh_to_nifti", subject),
        patch.object(mesh2nii, "msh_to_mni", mni),
    ):
        yield SimpleNamespace(calls=calls, producer=producer)


@pytest.mark.parametrize("spaces", [("subject",), ("subject", "mni")])
def test_a_run_that_writes_niftis_still_has_one_per_mesh_field_after_on_demand(
    converter, spaces
) -> None:
    sim_dir = make_simulation(converter.producer.pm, niftis=spaces)
    mesh_dir = sim_dir / "TI" / "mesh"
    notices = fields.ensure_mesh_fields(SID, SIM, ["hf_peak"])

    kind = "subject and MNI-space NIfTIs" if "mni" in spaces else "NIfTIs"
    assert notices == [
        "hf_peak was not saved for M; computing it from the channel fields and saving it "
        f"to M_TI.msh, with the {kind} this run writes for every field."
    ]
    assert sorted(c[0] for c in converter.calls) == sorted(
        ["subject"] * 3 + ["mni"] * 3 * ("mni" in spaces)
    )
    assert all(c[3] == ["hf_peak"] for c in converter.calls)
    # Whole brain tissue and its grey/white crops, all converted from the volume mesh.
    assert sorted(str(c[4]) for c in converter.calls if c[0] == "subject") == [
        "None",
        "[1]",
        "[2]",
    ]
    # The simulator's own invariant, checked the way the simulator checks it.
    fields.check_niftis_match_meshes(
        mesh_dir / "M_TI.msh", sim_dir / "TI" / "niftis", mni="mni" in spaces
    )


def test_a_run_without_niftis_gets_none_from_a_mesh_analysis(converter) -> None:
    sim_dir = make_simulation(converter.producer.pm)
    assert fields.ensure_mesh_fields(SID, SIM, ["hf_peak"])
    assert converter.calls == [] and not (sim_dir / "TI" / "niftis").exists()


def test_a_voxel_step_writes_the_tissue_niftis_it_reads(converter) -> None:
    sim_dir = make_simulation(converter.producer.pm)
    paths, notices = fields.ensure_niftis(
        SID, SIM, ["TI_max", "hf_peak"], tissue="grey"
    )
    niftis = sim_dir / "TI" / "niftis"
    assert paths == {
        "TI_max": niftis / "grey_M_TI_subject_TI_max.nii.gz",
        "hf_peak": niftis / "grey_M_TI_subject_hf_peak.nii.gz",
    }
    assert all(p.is_file() for p in paths.values())
    assert converter.calls == [
        ("subject", "M_TI.msh", "grey_M_TI_subject", ["TI_max", "hf_peak"], [2])
    ]
    assert notices == [
        "hf_peak was not saved for M; computing it from the channel fields and saving it "
        "to M_TI.msh.",
        "TI_max and hf_peak were not saved as NIfTIs for M; writing them from M_TI.msh "
        "(grey matter).",
    ]
    assert fields.ensure_niftis(SID, SIM, ["TI_max", "hf_peak"], tissue="grey")[1] == []


def test_an_mni_nifti_is_warped_from_the_tissue_mesh(converter) -> None:
    sim_dir = make_simulation(
        converter.producer.pm, saved=("TI_max", "hf_peak", "hf_rms")
    )
    paths, notices = fields.ensure_niftis(
        SID, SIM, ["TI_max"], tissue=None, space="mni"
    )
    assert paths == {"TI_max": sim_dir / "TI" / "niftis" / "M_TI_MNI_MNI_TI_max.nii.gz"}
    assert converter.calls == [("mni", "M_TI.msh", "M_TI_MNI", ["TI_max"], None)]
    assert notices == [
        "TI_max was not saved as an MNI-space NIfTI for M; writing it from M_TI.msh."
    ]


def test_a_group_tool_path_is_produced_and_any_other_name_left_alone(converter) -> None:
    sim_dir = make_simulation(
        converter.producer.pm, saved=("TI_max", "hf_peak", "hf_rms")
    )
    niftis = sim_dir / "TI" / "niftis"
    wanted = niftis / "white_M_TI_MNI_MNI_hf_rms.nii.gz"
    assert fields.ensure_nifti_file(SID, SIM, wanted) == [
        "hf_rms was not saved as an MNI-space NIfTI for M; writing it from M_TI.msh "
        "(white matter)."
    ]
    assert wanted.is_file()
    assert fields.ensure_nifti_file(SID, SIM, niftis / "my_own_average.nii.gz") == []
    assert (
        fields.check_nifti_producible(SID, SIM, niftis / "my_own_average.nii.gz")
        is False
    )
    assert fields.check_nifti_producible(
        SID, SIM, niftis / "grey_M_TI_subject_TI_avg.nii.gz"
    )


def test_an_unproducible_nifti_is_refused_before_any_conversion(converter) -> None:
    sim_dir = make_simulation(converter.producer.pm)
    for p in (sim_dir / "high_Frequency" / "mesh").iterdir():
        p.unlink()
    target = sim_dir / "TI" / "niftis" / "grey_M_TI_MNI_MNI_hf_peak.nii.gz"
    with pytest.raises(
        FieldUnavailableError, match="channel meshes it is computed from"
    ):
        fields.check_nifti_producible(SID, SIM, target)
    with pytest.raises(FieldUnavailableError):
        fields.ensure_nifti_file(SID, SIM, target)
    assert converter.calls == []


def test_an_uncompressed_nifti_counts_as_saved(converter) -> None:
    sim_dir = make_simulation(
        converter.producer.pm, saved=("TI_max", "hf_peak", "hf_rms")
    )
    niftis = sim_dir / "TI" / "niftis"
    niftis.mkdir()
    (niftis / "grey_M_TI_subject_TI_max.nii").write_bytes(b"nii")
    paths, notices = fields.ensure_niftis(SID, SIM, ["TI_max"], tissue="grey")
    assert paths == {"TI_max": niftis / "grey_M_TI_subject_TI_max.nii"}
    assert notices == [] and converter.calls == []


# ── the simulator's NIfTI set is its mesh field set ─────────────────────────────────


def _meshes_and_niftis(tmp_path: Path, written: list[str]) -> tuple[Path, Path]:
    mesh_dir, nifti_dir = tmp_path / "mesh", tmp_path / "niftis"
    mesh_dir.mkdir(parents=True)
    nifti_dir.mkdir(parents=True)
    write_msh(mesh_dir / "M_TI.msh", 1, {"TI_max": [1.0], "hf_peak": [2.0]})
    for name in written:
        (nifti_dir / name).write_bytes(b"nii")
    return mesh_dir / "M_TI.msh", nifti_dir


ALL_SUBJECT = [
    f"{stem}_subject_{f}.nii.gz"
    for stem in ("M_TI", "grey_M_TI", "white_M_TI")
    for f in ("TI_max", "hf_peak")
]


def test_one_nifti_per_mesh_field_passes(tmp_path: Path) -> None:
    fields.check_niftis_match_meshes(
        *_meshes_and_niftis(tmp_path, ALL_SUBJECT), mni=False
    )
    mni = [n.replace("_subject_", "_MNI_MNI_") for n in ALL_SUBJECT]
    fields.check_niftis_match_meshes(
        *_meshes_and_niftis(tmp_path / "mni", ALL_SUBJECT + mni), mni=True
    )


@pytest.mark.parametrize(
    "written, named",
    [
        (
            ALL_SUBJECT[1:],
            "M_TI carries ['TI_max', 'hf_peak'] but its subject NIfTIs are ['hf_peak']",
        ),
        (ALL_SUBJECT + ["M_TI_subject_magnE.nii.gz"], "['TI_max', 'hf_peak', 'magnE']"),
        (
            [n for n in ALL_SUBJECT if not n.startswith("white_")],
            "white_M_TI carries ['TI_max', 'hf_peak'] but its subject NIfTIs are []",
        ),
    ],
)
def test_a_missing_or_extra_nifti_fails_the_run_naming_it(
    tmp_path, written, named
) -> None:
    with pytest.raises(RuntimeError, match="do not match the field mesh") as err:
        fields.check_niftis_match_meshes(
            *_meshes_and_niftis(tmp_path, written), mni=False
        )
    assert named in str(err.value)


def test_mni_niftis_are_checked_too(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="MNI_MNI NIfTIs are \\[\\]"):
        fields.check_niftis_match_meshes(
            *_meshes_and_niftis(tmp_path, ALL_SUBJECT), mni=True
        )


# ── an old run's central surface ─────────────────────────────────────────────────────


def test_an_old_surface_gains_ti_normal_from_its_old_normal_mesh(producer) -> None:
    sim_dir = make_simulation(
        producer.pm,
        saved=("TI_max", "hf_peak", "hf_rms"),
        surface="old",
        legacy_normal=[5.0, 6.0, 7.0, 8.0],
    )
    central = sim_dir / "TI" / "mesh" / "surfaces" / "M_TI_central.msh"
    notices = fields.ensure_mesh_fields(SID, SIM, [])
    assert notices == [
        "M has a central surface without TI_normal; writing M_TI_central.msh from its "
        "field mesh."
    ]
    # The volume fields are interpolated again (no channel fields), TI_normal is the old one.
    assert producer.calls.surface == [(["TI_max", "hf_peak", "hf_rms"], False)]
    assert msh_field_names(central) == {"TI_max", "hf_peak", "hf_rms", "TI_normal"}
    np.testing.assert_array_equal(
        msh_element_field(central, "TI_normal"), [5.0, 6.0, 7.0, 8.0]
    )
    assert not any("TDCS" in r for r in producer.io.reads)  # channel meshes not needed
    assert (sim_dir / "TI" / "mesh" / "M_normal.msh").is_file()  # never deleted
    assert fields.ensure_mesh_fields(SID, SIM, []) == []


def test_without_an_old_normal_mesh_ti_normal_is_computed_from_the_channels(
    producer,
) -> None:
    sim_dir = make_simulation(producer.pm, surface=False)
    notices = fields.ensure_mesh_fields(SID, SIM, ["TI_max"])
    assert notices == [
        "M has no central surface; writing M_TI_central.msh from its field mesh."
    ]
    assert producer.calls.surface == [(["TI_max"], True)]
    central = sim_dir / "TI" / "mesh" / "surfaces" / "M_TI_central.msh"
    np.testing.assert_array_equal(msh_element_field(central, "TI_normal"), 7.0)


def test_a_re_segmented_head_model_is_refused(producer) -> None:
    make_simulation(producer.pm, surface="old", legacy_normal=[1.0] * 5)
    with pytest.raises(RuntimeError, match="segmented again"):
        fields.ensure_mesh_fields(SID, SIM, [])


def test_a_carrier_only_surface_needs_no_ti_normal(producer) -> None:
    make_simulation(producer.pm, carrier_only=True, saved=("hf_peak", "hf_rms"))
    assert fields.ensure_mesh_fields(SID, SIM, []) == []
    fields.check_surface_producible(SID, SIM)


def test_a_surface_that_cannot_be_built_is_refused_before_anything_runs(
    producer,
) -> None:
    sim_dir = make_simulation(producer.pm, surface="old")
    fields.check_surface_producible(SID, SIM)  # the channel meshes are kept
    for p in (sim_dir / "high_Frequency" / "mesh").iterdir():
        p.unlink()
    with pytest.raises(FieldUnavailableError, match="TI_normal is computed from"):
        fields.check_surface_producible(SID, SIM)
    with pytest.raises(FieldUnavailableError, match="TI_normal is computed from"):
        fields.ensure_mesh_fields(SID, SIM, [])
    assert producer.calls.surface == []


def test_a_voxel_step_never_needs_the_surface(converter) -> None:
    # An old run whose surface lacks TI_normal and cannot be rebuilt (no channel meshes):
    # a NIfTI of a saved field is still written from the volume mesh.
    sim_dir = make_simulation(converter.producer.pm, surface="old")
    for p in (sim_dir / "high_Frequency" / "mesh").iterdir():
        p.unlink()
    paths, _ = fields.ensure_niftis(SID, SIM, ["TI_max"], tissue="grey")
    assert paths["TI_max"].is_file()
    assert converter.producer.calls.surface == []


def test_a_retired_field_on_an_old_mesh_needs_no_nifti_and_no_surface(
    producer, tmp_path
):
    # A field outside the registry (an old run's retired name): no NIfTI is expected for it...
    mesh_dir, nifti_dir = tmp_path / "mesh", tmp_path / "niftis"
    mesh_dir.mkdir()
    nifti_dir.mkdir()
    write_msh(mesh_dir / "M_TI.msh", 1, {"TI_max": [1.0], "retired_field": [2.0]})
    for stem in ("M_TI", "grey_M_TI", "white_M_TI"):
        (nifti_dir / f"{stem}_subject_TI_max.nii.gz").write_bytes(b"nii")
    fields.check_niftis_match_meshes(mesh_dir / "M_TI.msh", nifti_dir, mni=False)
    # ...and a surface without it is complete, so nothing is rebuilt.
    sim_dir = make_simulation(producer.pm, saved=("TI_max", "retired_field"))
    central = sim_dir / "TI" / "mesh" / "surfaces" / "M_TI_central.msh"
    write_msh(
        central,
        int(BRAIN.sum()),
        {"TI_max": np.ones(int(BRAIN.sum())), "TI_normal": np.ones(int(BRAIN.sum()))},
    )
    assert fields.ensure_mesh_fields(SID, SIM, []) == []
    assert producer.calls.surface == []
