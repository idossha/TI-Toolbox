"""Naming contract: the files a TI/mTI post-process writes are the files every reader opens.

What this pins (2026-10-22, package p04 "output-naming-contract")
    A simulation writes its outputs under names built in three places -- ``tit/sim/TI.py`` /
    ``tit/sim/mTI.py`` (mesh names, the fields they add), ``tit/sim/utils.extract_fields``
    (``grey_``/``white_`` copies) and ``tit/tools/mesh2nii._collect_tasks`` (the
    ``<base>_subject`` / ``<base>_MNI`` output prefixes, to which SimNIBS appends
    ``_<field>`` and ``_MNI_<field>``). Every reader then rebuilds one of those names on its
    own: the simulation report, the analyzer's field selector, the group tools'
    ``simulation_nifti_path``, the fsaverage projection and the job preflight. This file
    builds the *writer's* file set in a temporary project -- no FEM, the files are touched --
    and checks that each reader resolves the file it is meant to and nothing else; then it
    deletes each file in turn and checks that exactly the readers that need it notice.

Where the expected names come from
    The writer code paths named above (read, not imported: nothing here calls the code
    under test to learn a name), and the SimNIBS suffix rule observed on disk in Dataset 000
    (``L_Insula_TI_subject_TI_max.nii.gz``, ``grey_L_Insula_TI_MNI_MNI_hf_peak.nii.gz``,
    ``101_TDCS_1_scalar_MNI_MNI_magnE.nii.gz``, ``ernie_TDCS_1_vn_subject_magnE.nii.gz``).
    :func:`test_writer_model_matches_dataset_000` re-checks that rule against the real
    listing when ``TIT_DATASET_000`` is set.

Reproduce
    .venv/bin/python -m pytest tests/test_sim_output_naming_contract.py -q -p no:cacheprovider
    TIT_DATASET_000=/path/to/000 .venv/bin/python -m pytest tests/test_sim_output_naming_contract.py -q

Deliberately elsewhere
    What the catalog and the viewer list: ``tests/test_catalog_sim_fields.py`` and
    ``tests/test_nifti_space_classifier.py`` (they import the writer model below).
"""

from __future__ import annotations

import json
import os
import string
from pathlib import Path

import pytest

from tests.field_mesh import write_field_mesh
from tit.paths import get_path_manager

# ── the writer model ─────────────────────────────────────────────────────────

#: Element fields the post-process adds to the ``<name>_<mode>.msh`` volume mesh
#: (``TI.py`` ``_post_process`` / ``mTI.py`` ``_post_process``, ``add_element_field``).
#: mTI spells the envelope ``mTI_max``; ``TI_avg``, ``hf_peak`` and ``hf_sar`` keep
#: their names in both modes.
VOLUME_FIELDS = {
    "TI": ("TI_max", "TI_avg", "hf_peak", "hf_sar"),
    "mTI": ("mTI_max", "TI_avg", "hf_peak", "hf_sar"),
}
#: ``extract_fields`` writes ``grey_<base>.msh`` and ``white_<base>.msh`` beside ``<base>.msh``.
TISSUE_PREFIX = {None: "", "grey": "grey_", "white": "white_"}
#: The conductivity token SimNIBS puts in a carrier's file name (``SimulationConfig.conductivity``).
CONDUCTIVITIES = ("scalar", "vn", "dir", "mc")


def nifti_name(base: str, space: str, field: str) -> str:
    """The NIfTI mesh2nii makes of mesh ``<base>.msh`` for *field* in *space*.

    ``_collect_tasks`` hands SimNIBS the prefixes ``<base>_subject`` and ``<base>_MNI``;
    ``interpolate_to_volume`` appends ``_<field>``, ``warp_volume`` appends ``_MNI_<field>``
    (observed: ``L_Insula_TI_MNI_MNI_TI_max.nii.gz`` in Dataset 000).
    """
    if space == "subject":
        return f"{base}_subject_{field}.nii.gz"
    if space == "mni":
        return f"{base}_MNI_MNI_{field}.nii.gz"
    raise ValueError(space)


def envelope_base(sim: str, mode: str, tissue: str | None) -> str:
    """``<tissue_>?<sim>_<TI|mTI>``: the volume mesh and its tissue copies."""
    return f"{TISSUE_PREFIX[tissue]}{sim}_{mode}"


def carrier_labels(mode: str, n_pairs: int) -> list[str]:
    """SimNIBS numbers carriers ``1..N``; ``mTI._organize_files`` renames them ``A..Z``."""
    if mode == "TI":
        return [str(i) for i in range(1, n_pairs + 1)]
    return list(string.ascii_uppercase[:n_pairs])


def carrier_base(sid: str, label: str, cond: str) -> str:
    """``<sid>_TDCS_<i>_<cond>``: one carrier's SimNIBS output mesh."""
    return f"{sid}_TDCS_{label}_{cond}"


def write_simulation(
    project: Path,
    sid: str,
    sim: str,
    mode: str = "TI",
    *,
    fields: tuple[str, ...] | None = None,
    map_to_mni: bool = True,
    cond: str = "scalar",
    n_pairs: int | None = None,
) -> dict:
    """Touch every file a finished TI/mTI run leaves, named as the writer names them.

    Returns ``{"sim_dir", "envelope": {(tissue, space, field): path}, "hf": {(label, space):
    path}, "mesh": path, "normal": path, "central": path}``. *fields* is the subset of
    :data:`VOLUME_FIELDS` written (``SimulationConfig.output_fields``, in the mode's
    spelling); ``None`` writes all of them.
    """
    pm = get_path_manager(str(project))
    m2m = Path(pm.m2m(sid))
    m2m.mkdir(parents=True, exist_ok=True)
    (m2m / "T1.nii.gz").write_bytes(b"t1")
    n_pairs = n_pairs or (2 if mode == "TI" else 4)
    fields = VOLUME_FIELDS[mode] if fields is None else fields
    sim_dir = Path(pm.simulation(sid, sim))
    # setup_montage_directories creates the TI tree for every run, mTI adds its own.
    for sub in (
        "documentation",
        "high_Frequency/mesh",
        "high_Frequency/niftis",
        "TI/mesh/surfaces",
        "TI/niftis",
    ):
        (sim_dir / sub).mkdir(parents=True, exist_ok=True)
    if mode == "mTI":
        for sub in ("mTI/mesh/surfaces", "mTI/niftis"):
            (sim_dir / sub).mkdir(parents=True, exist_ok=True)
    (sim_dir / "documentation" / "config.json").write_text(
        json.dumps(
            {
                "subject_id": sid,
                "simulation_name": sim,
                "simulation_mode": mode,
                "conductivity": cond,
                "mapping_options": {"map_to_mni": map_to_mni},
            }
        )
    )

    mesh_dir = sim_dir / mode / "mesh"
    mesh = mesh_dir / f"{envelope_base(sim, mode, None)}.msh"
    # TI.py writes <name>_normal.msh, mTI.py <name>_mTI_normal.msh, beside the volume mesh.
    normal = mesh_dir / (
        f"{sim}_normal.msh" if mode == "TI" else f"{sim}_mTI_normal.msh"
    )
    # msh2cortex -o surfaces/ names its output <mesh stem>_central.msh.
    central = mesh_dir / "surfaces" / f"{sim}_{mode}_central.msh"
    for tissue in TISSUE_PREFIX:
        write_field_mesh(mesh_dir / f"{envelope_base(sim, mode, tissue)}.msh", fields)
    normal.write_bytes(b"msh")
    central.write_bytes(b"msh")
    if mode == "mTI":
        # The intermediate pairwise TI vector meshes land in TI/mesh, never converted.
        for i in range(0, n_pairs, 2):
            pair = (
                f"{sim}_TI_{string.ascii_uppercase[i]}{string.ascii_uppercase[i + 1]}"
            )
            (sim_dir / "TI" / "mesh" / f"{pair}.msh").write_bytes(b"msh")

    spaces = ("subject", "mni") if map_to_mni else ("subject",)
    envelope = {}
    for tissue in TISSUE_PREFIX:
        for space in spaces:
            for field in fields:
                path = (
                    sim_dir
                    / mode
                    / "niftis"
                    / nifti_name(envelope_base(sim, mode, tissue), space, field)
                )
                path.write_bytes(b"nii")
                envelope[(tissue, space, field)] = path

    hf = {}
    for label in carrier_labels(mode, n_pairs):
        base = carrier_base(sid, label, cond)
        (sim_dir / "high_Frequency" / "mesh" / f"{base}.msh").write_bytes(b"msh")
        for space in spaces:
            path = (
                sim_dir / "high_Frequency" / "niftis" / nifti_name(base, space, "magnE")
            )
            path.write_bytes(b"nii")
            hf[(label, space)] = path
    return {
        "sim_dir": sim_dir,
        "envelope": envelope,
        "hf": hf,
        "mesh": mesh,
        "normal": normal,
        "central": central,
    }


# ── the readers, each asked for the one file it is meant to open ─────────────


def _envelope_field(mode: str) -> str:
    return "TI_max" if mode == "TI" else "mTI_max"


def _readers(sid: str, sim: str, mode: str) -> dict:
    """``{reader id: (callable returning the resolved path, the path it must resolve)}``.

    A reader that cannot find its file raises ``FileNotFoundError`` or returns a
    ``MissingInput`` list; both count as "reports it missing" below.
    """
    from tit.analyzer.field_selector import select_field_file, simulation_nifti_path
    from tit.jobs import preflight
    from tit.reporting.generators.simulation import _envelope_niftis
    from tit.source.fsaverage import _ti_max_overlay, _ti_normal_overlay

    pm = get_path_manager()
    sim_dir = Path(pm.simulation(sid, sim))
    env = _envelope_field(mode)

    def voxel(tissue, field):
        return lambda: select_field_file(
            sid, sim, "voxel", tissue_type=tissue, field=field
        )[0]

    def report(tissue):
        def read():
            hits = _envelope_niftis(sim_dir, sim, mode)
            if tissue not in hits:
                raise FileNotFoundError(tissue)
            return hits[tissue]

        return read

    def group(pattern):
        def read():
            path = simulation_nifti_path(sid, sim, pattern)
            missing = preflight._sim_nifti(pm, sid, sim, pattern)
            if missing:
                raise FileNotFoundError(path)
            return path

        return read

    niftis = sim_dir / mode / "niftis"
    mesh_dir = sim_dir / mode / "mesh"

    def nii(tissue, space, field):
        return niftis / nifti_name(envelope_base(sim, mode, tissue), space, field)

    return {
        "report grey envelope": (report("grey"), nii("grey", "subject", env)),
        "report white envelope": (report("white"), nii("white", "subject", env)),
        "voxel GM default": (voxel("GM", None), nii("grey", "subject", env)),
        "voxel WM default": (voxel("WM", None), nii("white", "subject", env)),
        "voxel both default": (voxel("both", None), nii(None, "subject", env)),
        "voxel GM TI_max alias": (voxel("GM", "TI_max"), nii("grey", "subject", env)),
        "voxel GM TI_avg": (voxel("GM", "TI_avg"), nii("grey", "subject", "TI_avg")),
        "voxel GM hf_peak": (voxel("GM", "hf_peak"), nii("grey", "subject", "hf_peak")),
        "voxel WM hf_sar": (voxel("WM", "hf_sar"), nii("white", "subject", "hf_sar")),
        "mesh default": (
            lambda: select_field_file(sid, sim, "mesh")[0],
            mesh_dir / f"{sim}_{mode}.msh",
        ),
        "mesh TI_normal": (
            lambda: select_field_file(sid, sim, "mesh", field="TI_normal")[0],
            mesh_dir
            / (f"{sim}_normal.msh" if mode == "TI" else f"{sim}_mTI_normal.msh"),
        ),
        # Group tools take a 2-pair spelling and resolve it for mTI themselves.
        "group grey MNI TI_max": (
            group("grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"),
            nii("grey", "mni", env),
        ),
        "group grey subject TI_max": (
            group("grey_{simulation_name}_TI_subject_TI_max.nii.gz"),
            nii("grey", "subject", env),
        ),
        "group grey MNI TI_avg": (
            group("grey_{simulation_name}_TI_MNI_MNI_TI_avg.nii.gz"),
            nii("grey", "mni", "TI_avg"),
        ),
        "group MNI hf_peak": (
            group("{simulation_name}_TI_MNI_MNI_hf_peak.nii.gz"),
            nii(None, "mni", "hf_peak"),
        ),
        "fsaverage TI_max overlay": (
            lambda: _ti_max_overlay(pm, sid, sim)[0],
            mesh_dir / "surfaces" / f"{sim}_{mode}_central.msh",
        ),
        "fsaverage TI_normal overlay": (
            lambda: _ti_normal_overlay(pm, sid, sim),
            mesh_dir
            / (f"{sim}_normal.msh" if mode == "TI" else f"{sim}_mTI_normal.msh"),
        ),
    }


#: Readers that also need a second file the preflight checks (the central surface).
def _preflight_readers(sid: str, sim: str, mode: str) -> dict:
    from tit.jobs import preflight

    pm = get_path_manager()

    def check(space, tissue, field):
        def read():
            missing = preflight._analyzer_field(
                pm, sid, sim, space, {"tissue_type": tissue, "field": field}
            )
            return [m.expected_path for m in missing]

        return read

    return {
        "preflight voxel GM default": check("voxel", "GM", None),
        "preflight voxel WM hf_peak": check("voxel", "WM", "hf_peak"),
        "preflight mesh default": check("mesh", "GM", None),
    }


def _resolve(read):
    try:
        return Path(read())
    except FileNotFoundError:
        return None


# Adversarial but legal names (tit.paths.NAME_RE): each contains a token a reader once
# matched by substring -- MNI, TI, TDCS, subject, normal, grey_/white_.
TRICKY_NAMES = (
    "L_Insula",
    "MNI_target",
    "hippo_MNI",
    "TDCS_vs_TI",
    "subject_A",
    "TI",
    "grey_matter",
    "abnormal",
)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    get_path_manager(str(tmp_path))
    return tmp_path


@pytest.mark.parametrize("mode", ["TI", "mTI"])
@pytest.mark.parametrize("sim", TRICKY_NAMES)
def test_every_reader_opens_the_file_the_writer_wrote(project, sim, mode):
    write_simulation(project, "101", sim, mode)
    readers = _readers("101", sim, mode)
    assert len(readers) == 17  # the table above; a reader dropped from it is a hole
    for reader_id, (read, expected) in readers.items():
        assert (
            expected.is_file()
        ), f"{reader_id}: the writer model did not write {expected}"
        assert _resolve(read) == expected, reader_id
    for reader_id, read in _preflight_readers("101", sim, mode).items():
        assert read() == [], reader_id


@pytest.mark.parametrize("mode", ["TI", "mTI"])
@pytest.mark.parametrize("sim", ["L_Insula", "MNI_target", "grey_matter"])
def test_deleting_a_file_breaks_exactly_the_readers_that_need_it(project, sim, mode):
    written = write_simulation(project, "101", sim, mode)
    readers = _readers("101", sim, mode)
    needed = {expected for _, expected in readers.values()}
    # Every file some reader needs, plus files no reader should depend on.
    victims = sorted(needed) + [
        written["hf"][(carrier_labels(mode, 4 if mode == "mTI" else 2)[0], "subject")]
    ]
    for victim in victims:
        data = victim.read_bytes()
        victim.unlink()
        try:
            for reader_id, (read, expected) in readers.items():
                got = _resolve(read)
                # A group tool's NIfTI that is gone is written again from the field mesh,
                # which is still there (tests/test_sim_fields_on_demand.py): nothing breaks.
                if expected == victim and reader_id.startswith("group "):
                    assert got == expected, f"{reader_id}: {victim.name} is producible"
                elif expected == victim:
                    assert (
                        got is None
                    ), f"{reader_id} still resolved {got} without {victim.name}"
                else:
                    assert got == expected, f"{reader_id} broke when {victim.name} went"
        finally:
            victim.write_bytes(data)


@pytest.mark.parametrize("mode", ["TI", "mTI"])
def test_preflight_names_the_missing_central_surface_only_for_mesh(project, mode):
    written = write_simulation(project, "101", "L_Insula", mode)
    written["central"].unlink()
    checks = _preflight_readers("101", "L_Insula", mode)
    assert checks["preflight mesh default"]() == [str(written["central"])]
    assert checks["preflight voxel GM default"]() == []


@pytest.mark.parametrize("mode", ["TI", "mTI"])
def test_without_mni_export_the_mni_readers_find_them_producible(project, mode):
    # The group tools write an MNI NIfTI the run did not save from its field mesh.
    write_simulation(project, "101", "L_Insula", mode, map_to_mni=False)
    for reader_id, (read, expected) in _readers("101", "L_Insula", mode).items():
        assert _resolve(read) == expected, reader_id


def test_default_voxel_field_never_falls_back_to_another_field(project):
    """No TI_max NIfTI but hf_peak/TI_avg present: the default must not analyse those as TI_max."""
    from tit.analyzer.field_selector import select_field_file

    write_simulation(project, "101", "L_Insula", "TI", fields=("TI_avg", "hf_peak"))
    with pytest.raises(FileNotFoundError):
        select_field_file("101", "L_Insula", "voxel", tissue_type="GM")


def _renamed_simulation(project: Path, mode: str) -> Path:
    """A ``L_Insula`` run without its envelope, whose folder was renamed to ``L_Insula_copy``.

    Its files keep the old name, so the writer's exact name for ``L_Insula_copy`` matches
    none of them and the selector falls through to its scan of the folder: the case where
    only the field suffix still tells ``TI_avg`` and ``hf_peak`` apart from the envelope.
    """
    written = write_simulation(
        project, "101", "L_Insula", mode, fields=("TI_avg", "hf_peak")
    )
    copy = written["sim_dir"].with_name("L_Insula_copy")
    written["sim_dir"].rename(copy)
    return copy / mode / "niftis"


@pytest.mark.parametrize("mode", ["TI", "mTI"])
@pytest.mark.parametrize("tissue_type", ["GM", "WM", "both"])
def test_a_renamed_simulation_never_analyses_another_field_as_the_envelope(
    project, mode, tissue_type
):
    """The scan of a renamed folder refuses ``*_TI_avg`` / ``*_hf_peak`` for the default field."""
    from tit.analyzer.field_selector import select_field_file

    niftis = _renamed_simulation(project, mode)
    names = sorted(p.name for p in niftis.iterdir())
    # The folder still holds this tissue's TI_avg and hf_peak volumes, just no envelope.
    prefix = {"GM": "grey_", "WM": "white_", "both": ""}[tissue_type]
    for field in ("TI_avg", "hf_peak"):
        assert f"{prefix}L_Insula_{mode}_subject_{field}.nii.gz" in names
    with pytest.raises(FileNotFoundError):
        select_field_file("101", "L_Insula_copy", "voxel", tissue_type=tissue_type)
    # Asked for by name, the field the folder does hold is still found.
    path, field = select_field_file(
        "101", "L_Insula_copy", "voxel", tissue_type=tissue_type, field="TI_avg"
    )
    assert (path.name, field) == (
        f"{prefix}L_Insula_{mode}_subject_TI_avg.nii.gz",
        "TI_avg",
    )


@pytest.mark.parametrize("mode", ["TI", "mTI"])
def test_a_suffix_less_legacy_volume_is_still_the_default(project, mode):
    """An older release wrote one grey-matter volume without a field suffix: the default reads it.

    ``grey_montage.nii.gz`` sorts after ``grey_L_Insula_*`` (``m`` > ``L``), so a scan that
    took the first grey-matter file without checking its suffix would answer ``TI_avg``.
    """
    from tit.analyzer.field_selector import select_field_file

    niftis = _renamed_simulation(project, mode)
    legacy = niftis / "grey_montage.nii.gz"
    legacy.write_bytes(b"nii")
    envelope = "TI_max" if mode == "TI" else "mTI_max"
    assert sorted(p.name for p in niftis.glob("grey_*"))[-1] == legacy.name
    assert select_field_file("101", "L_Insula_copy", "voxel", tissue_type="GM") == (
        legacy,
        envelope,
    )


# ── the writer model against the real thing ─────────────────────────────────

_DATASET = os.environ.get("TIT_DATASET_000")


@pytest.mark.skipif(
    not _DATASET or not os.path.isdir(_DATASET),
    reason="skipping: TIT_DATASET_000 is unset or not a directory (Dataset 000 copy)",
)
def test_writer_model_matches_dataset_000():
    """Every NIfTI the real simulator left in Dataset 000 is a name this model produces."""
    root = Path(_DATASET) / "derivatives" / "SimNIBS"
    sims = sorted(root.glob("sub-*/Simulations/*/documentation/config.json"))
    assert sims, "Dataset 000 has no simulation to check"
    before = {p: p.stat().st_mtime_ns for p in root.glob("sub-*/Simulations/*/**/*")}
    checked = 0
    for config_path in sims:
        sim_dir = config_path.parent.parent
        config = json.loads(config_path.read_text())
        sid = sim_dir.parent.parent.name.removeprefix("sub-")
        sim = sim_dir.name
        mode = "mTI" if str(config.get("simulation_mode")).upper() == "MTI" else "TI"
        cond = config.get("conductivity", "scalar")
        model = {
            nifti_name(envelope_base(sim, mode, tissue), space, field)
            for tissue in TISSUE_PREFIX
            for space in ("subject", "mni")
            for field in VOLUME_FIELDS[mode]
        } | {
            nifti_name(carrier_base(sid, label, cond), space, "magnE")
            for label in carrier_labels(mode, 26 if mode == "mTI" else 2)
            for space in ("subject", "mni")
        }
        on_disk = {
            p.name
            for d in (sim_dir / mode / "niftis", sim_dir / "high_Frequency" / "niftis")
            if d.is_dir()
            for p in d.iterdir()
            if p.name.endswith(".nii.gz") and not p.name.startswith("._")
        }
        assert on_disk, f"{sim_dir} has no NIfTIs"
        assert on_disk <= model, f"{sim_dir}: {sorted(on_disk - model)}"
        # The grey subject envelope every reader starts from is always there.
        assert (
            nifti_name(
                envelope_base(sim, mode, "grey"), "subject", _envelope_field(mode)
            )
            in on_disk
        )
        checked += 1
    assert checked >= 5
    after = {p: p.stat().st_mtime_ns for p in root.glob("sub-*/Simulations/*/**/*")}
    assert after == before
