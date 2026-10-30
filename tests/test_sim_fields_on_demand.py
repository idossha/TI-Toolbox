"""A field the simulation did not save is produced, once, from its channel meshes (2026-10-30).

What this pins (``tit/volume_fields.py``; docs/dev/DECISIONS.md 2026-10-30, field meshes by default)
    * ``ensure_mesh_fields`` computes a missing volume field from the channel meshes kept in
      ``high_Frequency/mesh/`` (``<sid>_TDCS_1|2_<cond>.msh``; ``A..Z`` for mTI), cropped to brain
      tissue, adds it to ``<sim>/<TI|mTI>/mesh/<sim>_<TI|mTI>.msh`` (the header then lists it),
      re-cuts the grey/white copies and regenerates the central surface, and says so in one
      sentence; a second call finds it saved and reads nothing;
    * no fallback: a missing channel mesh, a missing run record, an envelope of a carrier-only run
      and an unsaved ``hf_power_density`` are a ``FieldUnavailableError`` naming what is missing,
      and the volume mesh is left as it was; a volume mesh from another run is refused;
    * a carrier-only run's carriers are produced coherently, as the simulator adds them;
    * ``ensure_niftis`` writes exactly the NIfTI a voxel step reads, under the simulator's own name
      (``<tissue_><sim>_<TI|mTI>_subject_<field>.nii.gz``; ``..._MNI_MNI_...`` in MNI space), from
      that tissue's field mesh; ``ensure_nifti_file`` does it for a resolved group-tool path and
      leaves any other name alone;
    * ``check_niftis_match_meshes``: the simulator's NIfTI set is its mesh field set, name for name.

Where the expected numbers come from
    Hand formulas on authored channel fields: for two channels ``hf_peak = max(|E1 + E2|,
    |E1 - E2|)`` and ``hf_sar = |E1|^2 + |E2|^2`` (Cassarà 2025), and the coherent carrier-only
    ``hf_sar = |E1 + E2|^2``. Meshes are real Gmsh 2.2 ASCII files (their headers are what is
    checked); SimNIBS is mocked on the host, so ``mesh_io`` here reads and writes those files.

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

import tit.sim.utils
from tit import volume_fields as fields
from tit.volume_fields import FieldUnavailableError
from tit.tools.msh_fields import msh_element_field, msh_field_names

SID, SIM = "001", "M"
# GM, WM, an electrode rubber (100, dropped by the brain crop), CSF, a GM triangle (1002)
TAGS = np.array([2, 1, 100, 3, 1002])
BRAIN = np.isin(TAGS, fields.BRAIN_TAGS)
E1 = np.array([[1.0, 0, 0], [0, 2, 0], [9, 9, 9], [3, 4, 0], [0, 0, 1]])
E2 = np.array([[0.0, 1, 0], [0, -1, 0], [9, 9, 9], [3, 4, 0], [0, 0, -2]])


def write_msh(path: Path, n: int, data: dict[str, np.ndarray]) -> None:
    """A Gmsh 2.2 ASCII mesh of *n* tetrahedra carrying *data* as element fields."""
    out = ["$MeshFormat", "2.2 0 8", "$EndMeshFormat", "$Nodes", "4"]
    out += [f"{i} {x} {y} {z}" for i, (x, y, z) in enumerate(np.eye(4)[:, :3], 1)]
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

    def __init__(self, tags, data):
        self.elm = SimpleNamespace(tag1=np.asarray(tags), nr=len(tags))
        self.elmdata = [
            SimpleNamespace(field_name=k, value=np.asarray(v)) for k, v in data.items()
        ]

    @property
    def field(self):
        return {d.field_name: d for d in self.elmdata}

    def add_element_field(self, value, name):
        self.elmdata.append(SimpleNamespace(field_name=name, value=np.asarray(value)))

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
        return FakeMesh(np.full(n, 2), {k: msh_element_field(path, k) for k in names})

    def write_msh(self, mesh, path):
        self.written[Path(path).name] = mesh
        write_msh(
            Path(path), mesh.elm.nr, {d.field_name: d.value for d in mesh.elmdata}
        )


def make_simulation(
    pm, *, mode="TI", channels=2, carrier_only=False, saved=("TI_max",)
):
    """A finished run on disk: run record, volume mesh with *saved*, kept channel meshes."""
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
            }
        )
    )
    n = int(BRAIN.sum())
    write_msh(
        sim_dir / mode / "mesh" / f"{SIM}_{mode}.msh", n, {f: np.ones(n) for f in saved}
    )
    hf = sim_dir / "high_Frequency" / "mesh"
    hf.mkdir(parents=True)
    labels = "ABCDEFGH"[:channels] if mode == "mTI" else "12"
    for label in labels:
        (hf / f"{SID}_TDCS_{label}_scalar.msh").write_text("kept by the run")
    return sim_dir


@pytest.fixture()
def producer(init_pm):
    """Mocked SimNIBS reading TI channel fields E1/E2; grey/white cut and msh2cortex recorded."""
    io = FakeMeshIO({f"{SID}_TDCS_1_scalar.msh": E1, f"{SID}_TDCS_2_scalar.msh": E2})
    calls = SimpleNamespace(extract=[], surface=[])
    with (
        patch.object(sys.modules["simnibs"], "mesh_io", io),
        patch.object(
            tit.sim.utils, "extract_fields", lambda *a: calls.extract.append(a)
        ),
        patch.object(
            tit.sim.utils,
            "generate_central_surface",
            lambda *a: calls.surface.append(a),
        ),
    ):
        yield SimpleNamespace(io=io, calls=calls, pm=init_pm)


def test_a_missing_field_is_computed_from_the_channel_meshes_and_saved(
    producer,
) -> None:
    sim_dir = make_simulation(producer.pm)
    volume = sim_dir / "TI" / "mesh" / f"{SIM}_TI.msh"

    notices = fields.ensure_mesh_fields(SID, SIM, ["TI_max", "hf_peak", "hf_sar"])

    assert notices == [
        "hf_peak and hf_sar were not saved for M; computing them from the channel "
        "fields and saving them to M_TI.msh."
    ]
    assert msh_field_names(volume) == {"TI_max", "hf_peak", "hf_sar"}
    e1, e2 = E1[BRAIN], E2[BRAIN]  # the brain crop drops the rubber element
    peak = np.maximum(np.linalg.norm(e1 + e2, axis=1), np.linalg.norm(e1 - e2, axis=1))
    sar = (e1**2).sum(axis=1) + (e2**2).sum(axis=1)
    np.testing.assert_allclose(msh_element_field(volume, "hf_peak"), peak)
    np.testing.assert_allclose(msh_element_field(volume, "hf_sar"), sar)
    np.testing.assert_allclose(
        msh_element_field(volume, "TI_max"), 1.0
    )  # kept as saved
    # The grey/white copies are re-cut from the volume mesh, the central surface regenerated.
    assert [a[:3] for a in producer.calls.extract] == [
        (str(volume), str(volume.parent), f"{SIM}_TI")
    ]
    assert [a[2] for a in producer.calls.surface] == [str(volume.parent / "surfaces")]


def test_saved_fields_produce_nothing(producer) -> None:
    make_simulation(producer.pm, saved=("TI_max", "hf_peak", "hf_sar"))
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
        fields.ensure_mesh_fields(SID, SIM, ["hf_sar"])


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
    fields.ensure_mesh_fields(SID, SIM, ["hf_sar"])
    e = E1[BRAIN] + E2[BRAIN]  # one sinusoid of amplitude E1 + E2
    np.testing.assert_allclose(
        msh_element_field(sim_dir / "TI" / "mesh" / f"{SIM}_TI.msh", "hf_sar"),
        (e**2).sum(axis=1),
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
        patch.object(tit.sim.utils, "extract_fields", lambda *a: None),
        patch.object(tit.sim.utils, "generate_central_surface", lambda *a: None),
    ):
        notices = fields.ensure_mesh_fields(SID, SIM, ["TI_max", "hf_sar"])
    assert notices == [
        "hf_sar was not saved for M; computing it from the channel fields and saving it "
        "to M_mTI.msh."
    ]
    assert io.reads[:4] == [f"{SID}_TDCS_{c}_scalar.msh" for c in "ABCD"]
    sar = sum((v[BRAIN] ** 2).sum(axis=1) for v in e)
    volume = Path(init_pm.simulation(SID, SIM)) / "mTI" / "mesh" / "M_mTI.msh"
    np.testing.assert_allclose(msh_element_field(volume, "hf_sar"), sar)


@pytest.fixture()
def converter(producer):
    """``mesh2nii`` writing ``<prefix>_<field>.nii.gz`` (subject) / ``<prefix>_MNI_<field>`` (MNI)."""
    import tit.tools.mesh2nii as mesh2nii

    calls = []

    def subject(mesh, m2m, prefix, fields=None):
        calls.append(("subject", Path(mesh).name, Path(prefix).name, list(fields)))
        for f in fields:
            Path(f"{prefix}_{f}.nii.gz").write_bytes(b"nii")

    def mni(mesh, m2m, prefix, fields=None):
        calls.append(("mni", Path(mesh).name, Path(prefix).name, list(fields)))
        for f in fields:
            Path(f"{prefix}_MNI_{f}.nii.gz").write_bytes(b"nii")

    with (
        patch.object(mesh2nii, "msh_to_nifti", subject),
        patch.object(mesh2nii, "msh_to_mni", mni),
    ):
        yield SimpleNamespace(calls=calls, producer=producer)


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
        ("subject", "grey_M_TI.msh", "grey_M_TI_subject", ["TI_max", "hf_peak"])
    ]
    assert notices == [
        "hf_peak was not saved for M; computing it from the channel fields and saving it "
        "to M_TI.msh.",
        "TI_max and hf_peak were not saved as NIfTIs for M; writing them from grey_M_TI.msh.",
    ]
    assert fields.ensure_niftis(SID, SIM, ["TI_max", "hf_peak"], tissue="grey")[1] == []


def test_an_mni_nifti_is_warped_from_the_tissue_mesh(converter) -> None:
    sim_dir = make_simulation(
        converter.producer.pm, saved=("TI_max", "hf_peak", "hf_sar")
    )
    paths, notices = fields.ensure_niftis(
        SID, SIM, ["TI_max"], tissue=None, space="mni"
    )
    assert paths == {"TI_max": sim_dir / "TI" / "niftis" / "M_TI_MNI_MNI_TI_max.nii.gz"}
    assert converter.calls == [("mni", "M_TI.msh", "M_TI_MNI", ["TI_max"])]
    assert notices == [
        "TI_max was not saved as an MNI-space NIfTI for M; writing it from M_TI.msh."
    ]


def test_a_group_tool_path_is_produced_and_any_other_name_left_alone(converter) -> None:
    sim_dir = make_simulation(
        converter.producer.pm, saved=("TI_max", "hf_peak", "hf_sar")
    )
    niftis = sim_dir / "TI" / "niftis"
    wanted = niftis / "white_M_TI_MNI_MNI_hf_sar.nii.gz"
    assert fields.ensure_nifti_file(SID, SIM, wanted) == [
        "hf_sar was not saved as an MNI-space NIfTI for M; writing it from white_M_TI.msh."
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
        converter.producer.pm, saved=("TI_max", "hf_peak", "hf_sar")
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
    for stem in ("M_TI", "grey_M_TI"):
        write_msh(mesh_dir / f"{stem}.msh", 1, {"TI_max": [1.0], "hf_peak": [2.0]})
    write_msh(
        mesh_dir / "M_normal.msh", 1, {"TI_normal": [1.0]}
    )  # surface-only: not converted
    for name in written:
        (nifti_dir / name).write_bytes(b"nii")
    return mesh_dir, nifti_dir


ALL_SUBJECT = [
    f"{stem}_subject_{f}.nii.gz"
    for stem in ("M_TI", "grey_M_TI")
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
            "M_TI.msh carries ['TI_max', 'hf_peak'] but its subject NIfTIs are ['hf_peak']",
        ),
        (ALL_SUBJECT + ["M_TI_subject_magnE.nii.gz"], "['TI_max', 'hf_peak', 'magnE']"),
    ],
)
def test_a_missing_or_extra_nifti_fails_the_run_naming_it(
    tmp_path, written, named
) -> None:
    with pytest.raises(RuntimeError, match="do not match the field meshes") as err:
        fields.check_niftis_match_meshes(
            *_meshes_and_niftis(tmp_path, written), mni=False
        )
    assert named in str(err.value)


def test_mni_niftis_are_checked_too(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="MNI_MNI NIfTIs are \\[\\]"):
        fields.check_niftis_match_meshes(
            *_meshes_and_niftis(tmp_path, ALL_SUBJECT), mni=True
        )
