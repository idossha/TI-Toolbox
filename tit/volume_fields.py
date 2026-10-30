"""A simulation's volume fields: computed by the simulator, produced again on demand.

:func:`compute_volume_fields` is the one per-field computation. The simulator writes its output
into the montage's volume mesh (:meth:`tit.sim.base.BaseSimulation._write_volume_mesh`), and the
on-demand path below produces a field the simulation did not save from the same inputs: the
channel meshes every run keeps in ``high_Frequency/mesh/`` (``<sid>_TDCS_<k>_<cond>.msh``, ``k``
= 1, 2 for TI and A..Z for mTI), cropped to brain tissue as the simulator crops them.

What persists, so the next step finds the field saved:

* :func:`ensure_mesh_fields` adds the field to the volume mesh
  ``<sim>/<TI|mTI>/mesh/<sim>_<TI|mTI>.msh`` and rewrites its central surface
  ``<sim>/<TI|mTI>/mesh/surfaces/<sim>_<TI|mTI>_central.msh`` (:func:`central_surface`: every
  volume field and ``TI_normal`` as node data), which is what a mesh analysis reads. It also
  builds that surface for a run that lacks it or whose surface lacks a field -- a run made before
  the surface carried ``TI_normal`` -- taking ``TI_normal`` from the run's old
  ``<sim>_normal.msh`` (``<sim>_mTI_normal.msh``) when it has one, else from the channel meshes.
  It never deletes an old run's files; nothing reads them;
* :func:`ensure_niftis` / :func:`ensure_nifti_file` also write the NIfTI a voxel step reads,
  under the simulator's own name (``<tissue_><sim>_<TI|mTI>_subject_<field>.nii.gz``, or
  ``..._MNI_MNI_<field>.nii.gz`` in MNI space) in ``<sim>/<TI|mTI>/niftis/``; a ``grey_`` or
  ``white_`` NIfTI is converted from the volume mesh cropped to that tissue
  (:data:`tit.tools.mesh2nii.TISSUE_TAGS`).

NIfTIs and the mesh stay consistent. A run that wrote NIfTIs (``map_to_vol`` in its run record)
has one per mesh field, so a field added to its mesh gets its NIfTIs too -- every converted
mesh, subject space and, with ``map_to_mni``, MNI space -- and the set still equals the mesh field
set. A run with NIfTIs off has no such set: its ``niftis/`` holds only what voxel steps asked for,
each a NIfTI of a field its mesh carries, never one the mesh lacks.

Writes are crash-safe: everything is staged in a hidden folder and moved into place with atomic
renames, derived files first and the volume mesh last (:func:`_produce_mesh_fields`).

Each says one plain sentence per production before doing it ("hf_peak and hf_rms were not saved
for L_Insula; computing them from the channel fields and saving them to L_Insula_TI.msh."),
through the caller's ``say`` (its own ``logger.info``, so it reaches that job's output), and
returns the sentences so the caller can show them wherever its results are read.
Nothing is guessed: a field that cannot be produced (no channel meshes, no recorded config, an
envelope of a carrier-only run, ``hf_power_density`` whose conductivity is not kept) raises
:class:`FieldUnavailableError` naming what is missing.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import shutil
import string
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from tit import constants as const
from tit.calc import envelope, envelope_max, envelope_mean, hf_peak, hf_power
from tit.tools.msh_fields import msh_field_names

logger = logging.getLogger(__name__)

#: Brain tissue crop mask: tissue volume elements and their surfaces
#: (constants.BRAIN_TISSUE_TAG_RANGES); electrodes and gel are dropped.
BRAIN_TAGS = np.hstack([np.arange(lo, hi) for lo, hi in const.BRAIN_TISSUE_TAG_RANGES])

#: The order fields are written in (the registry's): the volume mesh and its NIfTIs list them so.
_FIELD_ORDER = (
    const.FIELD_TI_MAX,
    const.FIELD_TI_AVG,
    const.FIELD_HF_PEAK,
    const.FIELD_HF_RMS,
    const.FIELD_HF_POWER_DENSITY,
)
_ENVELOPE_FIELDS = (const.FIELD_TI_MAX, const.FIELD_TI_AVG)


class FieldUnavailableError(FileNotFoundError):
    """A field a step needs was not saved and cannot be produced from what the simulation kept."""


def hf_power_density(fields, sigma, *, coherent: bool = False) -> np.ndarray:
    """Absorbed (Joule) power density of the carriers, time-averaged, W/m^3.

    ``(1/2) sum_c E_c^T sigma E_c`` for zero-to-peak carrier fields ``E_c``
    (V/m) at distinct frequencies: ``sigma * hf_power`` for isotropic
    ``sigma`` ``(N,)`` S/m, the full tensor form for ``(N, 9)`` anisotropic
    conductivities (``J . E`` averaged over time).  Not SAR (that is this over the
    tissue density, IEEE C95.1-2019 p. 35, and no SAR limit applies below 100 kHz).  *coherent* is the carrier-only control: one
    sinusoid of amplitude ``sum_c E_c``.
    """
    sigma = np.asarray(sigma, dtype=np.float64)
    if sigma.ndim == 1:
        return sigma * hf_power(fields, coherent=coherent)
    E = np.stack([np.asarray(f, dtype=np.float64) for f in fields])
    if coherent:
        E = E.sum(axis=0, keepdims=True)
    return 0.5 * np.einsum("fni,nij,fnj->n", E, sigma.reshape(-1, 3, 3), E)


def compute_volume_fields(
    e_fields: list,
    names,
    *,
    max_name: str,
    coherent: bool,
    sigma=None,
) -> list[tuple[str, np.ndarray]]:
    """``(on-disk name, values)`` of each selected volume field, over all channel fields jointly.

    Args:
        e_fields: The channels' ``E`` on the brain-cropped mesh, in channel order (channels
            2k-1 and 2k form beating pair k).
        names: Logical field names (:data:`tit.constants.SELECTABLE_OUTPUT_FIELDS`); written
            in registry order whatever order they come in.
        max_name: The envelope maximum's on-disk name (``TI_max``; ``mTI_max`` for mTI).
        coherent: Carrier-only control: the channel fields add coherently.
        sigma: Per-element conductivity of the solve, for ``hf_power_density`` only.
    """
    selected = set(names)
    out = []
    for name in _FIELD_ORDER:
        if name not in selected:
            continue
        if name == const.FIELD_TI_MAX:
            out.append((max_name, envelope_max(e_fields)))
        elif name == const.FIELD_TI_AVG:
            out.append((name, envelope_mean(e_fields)))
        elif name == const.FIELD_HF_PEAK:
            # Peak carrier field (Cassarà 2025 Part I, Eq. 3); each channel field enters on its own.
            out.append((name, hf_peak(e_fields, coherent=coherent)))
        elif name == const.FIELD_HF_RMS:
            # RMS carrier field over time: power adds across carriers (Cassarà 2025).
            out.append((name, np.sqrt(hf_power(e_fields, coherent=coherent))))
        else:
            out.append((name, hf_power_density(e_fields, sigma, coherent=coherent)))
    return out


def central_surface(volume, m2m_dir, *, e_fields=None):
    """The subject's central cortical surface (lh then rh) carrying *volume*'s fields as node data.

    What SimNIBS's ``msh2cortex`` does, in process: the brain-tissue *volume* mesh is cropped to
    white matter, grey matter and CSF, and its fields are interpolated onto the m2m central
    surfaces inside the grey-matter tetrahedra (``ElementData.interpolate_to_surface``), all of
    them in one stacked call per hemisphere; the hemispheres are joined as ``msh2cortex`` joins
    them (tags ``LH_/RH_CENTRAL_SURFACE``). With *e_fields* -- the channels' ``E`` on
    *volume*'s elements, in channel order -- their interpolated vectors give ``TI_normal``, the
    envelope along the node normals (:func:`tit.calc.envelope`), as the old surface overlays'
    ``E_normal`` gave it (tests/numerical/test_central_surface_real.py: both to 3e-14 V/m).

    Raises:
        ValueError: *volume* carries a field that is not a scalar.
    """
    from simnibs import mesh_io
    from simnibs.mesh_tools.mesh_io import ElementTags
    from simnibs.utils.file_finder import SubjectFiles

    names = [d.field_name for d in volume.elmdata]
    columns = []
    for data in volume.elmdata:
        if data.nr_comp != 1:
            raise ValueError(
                f"the field mesh carries {data.field_name!r} with {data.nr_comp} components; "
                "a volume field is a scalar"
            )
        columns.append(np.asarray(data.value, dtype=np.float64).reshape(-1, 1))
    columns += [np.asarray(e, dtype=np.float64).reshape(-1, 3) for e in e_fields or ()]
    values = np.hstack(columns)
    stacked = mesh_io.Msh(volume.nodes, volume.elm)
    # SimNIBS interpolates an (N, 1) block wrongly; one column goes in as the scalar it is.
    stacked.add_element_field(
        values[:, 0] if values.shape[1] == 1 else values, "stacked"
    )
    stacked = stacked.crop_mesh(tags=[ElementTags.WM, ElementTags.GM, ElementTags.CSF])
    gm = stacked.elm.get_tags(ElementTags.GM, return_element_numbers=True)

    subject = SubjectFiles(subpath=str(m2m_dir))
    surfaces = mesh_io.load_subject_surfaces(subject, "central")
    values = np.vstack(
        [
            np.asarray(
                stacked.field["stacked"]
                .interpolate_to_surface(surfaces[hemi], th_indices=gm)
                .value
            ).reshape(surfaces[hemi].nodes.nr, -1)
            for hemi in ("lh", "rh")
        ]
    )
    for hemi, tag in (
        ("lh", ElementTags.LH_CENTRAL_SURFACE),
        ("rh", ElementTags.RH_CENTRAL_SURFACE),
    ):
        surfaces[hemi].elm.tag1 = tag * np.ones(surfaces[hemi].elm.nr, dtype=int)
        surfaces[hemi].elm.tag2 = tag * np.ones(surfaces[hemi].elm.nr, dtype=int)
    surface = surfaces["lh"].join_mesh(surfaces["rh"])
    surface.nodedata, surface.elmdata = [], []
    for i, name in enumerate(names):
        surface.add_node_field(values[:, i], name)
    if e_fields:
        k = len(names)
        vectors = [values[:, k + 3 * c : k + 3 * c + 3] for c in range(len(e_fields))]
        normals = surface.nodes_normals().value
        surface.add_node_field(envelope(vectors, normals), const.FIELD_TI_NORMAL)
    return surface


# ── where a simulation keeps what ────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Simulation:
    subject_id: str
    name: str
    dir: Path
    mode: str  # "TI" or "mTI"

    @property
    def mesh_dir(self) -> Path:
        return self.dir / self.mode / "mesh"

    @property
    def volume_mesh(self) -> Path:
        return self.mesh_dir / f"{self.name}_{self.mode}.msh"

    @property
    def niftis_dir(self) -> Path:
        return self.dir / self.mode / "niftis"

    @property
    def central(self) -> Path:
        return self.mesh_dir / "surfaces" / f"{self.name}_{self.mode}_central.msh"

    @property
    def legacy_normal(self) -> Path:
        """The ``TI_normal`` mesh runs wrote before the central surface carried it (read-only)."""
        suffix = "_mTI_normal" if self.mode == "mTI" else "_normal"
        return self.mesh_dir / f"{self.name}{suffix}.msh"

    @property
    def max_name(self) -> str:
        return const.FIELD_MTI_MAX if self.mode == "mTI" else const.FIELD_TI_MAX


def _simulation(subject_id: str, simulation: str) -> _Simulation:
    from tit.paths import get_path_manager

    sim_dir = Path(get_path_manager().simulation(subject_id, simulation))
    mode = "mTI" if (sim_dir / "mTI" / "mesh").is_dir() else "TI"
    return _Simulation(subject_id, simulation, sim_dir, mode)


def _logical(name: str) -> str:
    """``TI_max`` for ``mTI_max`` (one quantity, two spellings); every other name as given."""
    return const.FIELD_TI_MAX if name == const.FIELD_MTI_MAX else name


def _on_disk(sim: _Simulation, name: str) -> str:
    return sim.max_name if _logical(name) == const.FIELD_TI_MAX else name


def _recorded_config(sim: _Simulation) -> dict:
    path = sim.dir / "documentation" / "config.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise FieldUnavailableError(
            f"{sim.name} has no readable run record at {path} ({exc}); it names the channel "
            "meshes and the carrier mode a field is computed from. Re-run the simulation."
        ) from exc


def _channel_meshes(sim: _Simulation, config: dict) -> list[Path]:
    """``high_Frequency/mesh/<sid>_TDCS_<k>_<cond>.msh``, ``k`` = 1, 2 (TI) or A..Z (mTI).

    The simulator renames mTI channels to letters when it organises its files; the count and
    conductivity come from the run's own ``documentation/config.json``.
    """
    n = len(config.get("electrode_pairs") or [])
    labels = (
        list(string.ascii_uppercase[:n])
        if sim.mode == "mTI"
        else [str(i) for i in range(1, n + 1)]
    )
    sid = config.get("subject_id") or sim.subject_id
    cond = config.get("conductivity") or "scalar"
    hf_mesh = sim.dir / "high_Frequency" / "mesh"
    return [hf_mesh / f"{sid}_TDCS_{label}_{cond}.msh" for label in labels]


def _validated(names) -> list[str]:
    out = []
    for name in names:
        logical = _logical(name)
        if logical not in const.SELECTABLE_OUTPUT_FIELDS:
            raise ValueError(
                f"{name!r} is not a volume field; on-demand fields are "
                f"{', '.join(const.SELECTABLE_OUTPUT_FIELDS)}."
            )
        if logical not in out:
            out.append(logical)
    return out


def _missing(sim: _Simulation, names: list[str]) -> list[str]:
    """Logical *names* the volume mesh does not carry.

    Raises:
        FieldUnavailableError: there is no volume mesh, or its field list cannot be read.
    """
    if not sim.volume_mesh.is_file():
        raise FieldUnavailableError(
            f"{sim.name} has no field mesh at {sim.volume_mesh}; run the simulation first."
        )
    carried = msh_field_names(sim.volume_mesh)
    if carried is None:
        raise FieldUnavailableError(
            f"Cannot read the field list of {sim.volume_mesh} (not a Gmsh 2.2 mesh, or "
            "truncated), so which fields the simulation saved is unknown. Re-run the "
            "simulation."
        )
    return [n for n in names if _on_disk(sim, n) not in carried]


def _surface_lacks(sim: _Simulation) -> list[str] | None:
    """What the central surface lacks of the volume mesh's fields and ``TI_normal``.

    ``None`` when the surface file is missing; empty when it is complete. A carrier-only run
    has no envelope, so no ``TI_normal``: the run record is read only when the surface has none.
    """
    if not sim.central.is_file():
        return None
    carried = msh_field_names(sim.central) or set()
    lacks = [
        n for n in sorted(msh_field_names(sim.volume_mesh) or ()) if n not in carried
    ]
    if const.FIELD_TI_NORMAL not in carried and (
        _recorded_config(sim).get("carrier_only") is not True
    ):
        lacks.append(const.FIELD_TI_NORMAL)
    return lacks


def _check_surface_producible(sim: _Simulation, config: dict) -> None:
    """Raise unless the central surface can be built: m2m surfaces, and a ``TI_normal`` source."""
    from tit.paths import get_path_manager

    m2m = Path(get_path_manager().m2m(sim.subject_id))
    absent = [
        p
        for p in (m2m / "surfaces" / f"{h}.central.gii" for h in ("lh", "rh"))
        if not p.is_file()
    ]
    if absent:
        raise FieldUnavailableError(
            f"The central surface of {sim.name} cannot be built: the head model has no "
            f"central surfaces ({', '.join(str(p) for p in absent)}). Re-run charm."
        )
    if config.get("carrier_only") is True or sim.legacy_normal.is_file():
        return
    channels = [p for p in _channel_meshes(sim, config) if not p.is_file()]
    if channels or not config.get("electrode_pairs"):
        raise FieldUnavailableError(
            f"The central surface of {sim.name} cannot be built: TI_normal is computed from "
            "the channel meshes, and they are missing: "
            + (
                ", ".join(str(p) for p in channels)
                or "the run record names no channels"
            )
            + ". Re-run the simulation."
        )


def check_surface_producible(subject_id: str, simulation: str) -> None:
    """Raise :class:`FieldUnavailableError` if the central surface is incomplete and cannot be built.

    Filesystem checks only (headers and file existence), for a job's preflight.
    """
    sim = _simulation(subject_id, simulation)
    _missing(sim, [])  # the volume mesh must be there and readable
    if _surface_lacks(sim) != []:
        _check_surface_producible(sim, _recorded_config(sim))


def _check_producible(sim: _Simulation, missing: list[str]) -> dict:
    """The run record, once every *missing* field is known to be producible; raises otherwise."""
    config = _recorded_config(sim)
    if config.get("carrier_only") is True:
        envelope = [_on_disk(sim, n) for n in missing if n in _ENVELOPE_FIELDS]
        if envelope:
            raise FieldUnavailableError(
                f"{sim.name} is a carrier-only control (ΔF = 0): it has no envelope, so "
                f"{_listed(envelope)} {'is' if len(envelope) == 1 else 'are'} undefined "
                "for it."
            )
    if const.FIELD_HF_POWER_DENSITY in missing:
        raise FieldUnavailableError(
            f"hf_power_density was not saved for {sim.name}, and it cannot be computed "
            "afterwards: it needs the conductivity of the original solve, which is not kept. "
            "Re-run the simulation with hf_power_density among its output fields."
        )
    absent = [p for p in _channel_meshes(sim, config) if not p.is_file()]
    if absent or not config.get("electrode_pairs"):
        names = [_on_disk(sim, n) for n in missing]
        was, it = _was(names)
        raise FieldUnavailableError(
            f"{_listed(names)} {was} not saved for {sim.name}, and the channel meshes "
            f"{'it is' if it == 'it' else 'they are'} computed from are missing: "
            + (", ".join(str(p) for p in absent) or "the run record names no channels")
            + ". Re-run the simulation."
        )
    return config


def check_producible(subject_id: str, simulation: str, fields) -> None:
    """Raise :class:`FieldUnavailableError` if a field of *fields* is neither saved nor producible.

    Filesystem checks only (no mesh is loaded), for a job's preflight.
    """
    sim = _simulation(subject_id, simulation)
    missing = _missing(sim, _validated(fields))
    if missing:
        _check_producible(sim, missing)


def _listed(names: list[str]) -> str:
    """``hf_peak``, ``hf_peak and hf_rms``, ``TI_max, hf_peak and hf_rms``."""
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def _was(names: list[str]) -> tuple[str, str]:
    return ("was", "it") if len(names) == 1 else ("were", "them")


def _quiet(notice: str) -> None:
    """The default ``say``: the notice is still returned to the caller."""


_STAGE_PREFIX = ".on-demand-"


@contextmanager
def _producing(sim: _Simulation):
    """One producer per simulation at a time: two analyses may need the same field at once.

    Holding the lock, any staging folder left in ``<sim>/<mode>/`` is from a producer that was
    killed, so it is removed first: nothing in it was ever moved into place.
    """
    with open(sim.dir / ".on-demand.lock", "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            for stale in (sim.dir / sim.mode).glob(_STAGE_PREFIX + "*"):
                shutil.rmtree(stale, ignore_errors=True)
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


@contextmanager
def _staging(sim: _Simulation):
    """A hidden folder in ``<sim>/<mode>/`` (the outputs' filesystem), removed on exit.

    Everything a production writes goes here first and is moved into place with
    :func:`os.replace` only once complete, so a reader never sees a partial file.
    """
    parent = sim.dir / sim.mode
    parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=_STAGE_PREFIX, dir=parent))
    try:
        yield stage
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def _move_all(src: Path, dst: Path) -> None:
    """Move every file of *src* into *dst*, each with one atomic rename."""
    if not src.is_dir():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.iterdir()):
        os.replace(path, dst / path.name)


def ensure_mesh_fields(
    subject_id: str,
    simulation: str,
    fields,
    *,
    say: Callable[[str], None] = _quiet,
    surface: bool = True,
) -> list[str]:
    """Make the volume mesh carry every field of *fields*, and its central surface all of them.

    A missing field is computed with :func:`compute_volume_fields` from the channel meshes and
    added to the volume mesh, and the central surface is rewritten from it with every field.
    A central surface that is missing or lacks a field of the volume mesh or ``TI_normal`` is
    rebuilt even when *fields* is empty (an old run, :func:`_produce_surface`). Returns one
    sentence per production (empty when nothing was needed), each handed to *say* before the
    work it announces starts.

    Args:
        subject_id: Subject identifier (no ``sub-``).
        simulation: Simulation (montage) folder name.
        fields: Logical or on-disk volume field names (``TI_max`` and ``mTI_max`` alike); may be
            empty, to make sure of the central surface only.
        say: Called with each sentence first (a caller's ``logger.info``).
        surface: Also rebuild an incomplete central surface when no field is missing.
            ``False`` for a step that reads only NIfTIs (:func:`ensure_niftis`).

    Raises:
        FieldUnavailableError: a missing field or the surface cannot be produced.
        ValueError: a name is not a volume field (``TI_normal`` is a surface field).
        RuntimeError: the head model's central surface is not the one the run used.
    """
    sim = _simulation(subject_id, simulation)
    names = _validated(fields)
    if not _missing(sim, names) and (not surface or _surface_lacks(sim) == []):
        return []
    with _producing(sim):
        missing = _missing(sim, names)  # another producer may have finished meanwhile
        if missing:
            config = _check_producible(sim, missing)
            names = [_on_disk(sim, n) for n in missing]
            was, it = _was(names)
            spaces = _recorded_nifti_spaces(config)
            also = ""
            if spaces:
                kind = "subject and MNI-space NIfTIs" if "mni" in spaces else "NIfTIs"
                also = f", with the {kind} this run writes for every field"
            notice = (
                f"{_listed(names)} {was} not saved for {sim.name}; computing {it} from the "
                f"channel fields and saving {it} to {sim.volume_mesh.name}{also}."
            )
            say(notice)
            _produce_mesh_fields(sim, config, missing, names, spaces)
            return [notice]
        if not surface:
            return []
        lacks = _surface_lacks(sim)
        if lacks == []:
            return []
        config = _recorded_config(sim)
        _check_surface_producible(sim, config)
        what = (
            "has no central surface"
            if lacks is None
            else (f"has a central surface without {_listed(lacks)}")
        )
        notice = f"{sim.name} {what}; writing {sim.central.name} from its field mesh."
        say(notice)
        _produce_surface(sim, config)
    return [notice]


def _recorded_nifti_spaces(config: dict) -> tuple[str, ...]:
    """The NIfTI spaces the run itself writes: none, subject, or subject and MNI."""
    options = config.get("mapping_options") or {}
    if options.get("map_to_vol") is not True:
        return ()
    return ("subject", "mni") if options.get("map_to_mni") is True else ("subject",)


def _read_channels(sim: _Simulation, config: dict, volume) -> list:
    """The channel meshes cropped to brain tissue as the simulator crops them, checked against
    *volume*'s elements."""
    from simnibs import mesh_io

    channels = [
        mesh_io.read_msh(str(p)).crop_mesh(tags=BRAIN_TAGS)
        for p in _channel_meshes(sim, config)
    ]
    if volume.elm.nr != channels[0].elm.nr:
        raise RuntimeError(
            f"{sim.volume_mesh} has {volume.elm.nr} elements but its brain-cropped channel "
            f"meshes have {channels[0].elm.nr}: they are not from the same run. Re-run the "
            "simulation."
        )
    return channels


def _surface(sim: _Simulation, config: dict, volume, channels=None):
    """The central surface of *volume*'s fields, ``TI_normal`` included unless carrier-only.

    ``TI_normal`` comes from *channels* when given, else from the run's old
    ``<sim>_normal.msh`` (the same nodes: ``msh2cortex`` and the overlays used the m2m central
    surfaces too), else from the channel meshes read here.

    Raises:
        RuntimeError: the m2m central surface has another node count than this run's own
            surface (or its old ``TI_normal`` mesh): the subject was re-segmented since.
    """
    from simnibs import mesh_io

    from tit.paths import get_path_manager

    m2m = get_path_manager().m2m(sim.subject_id)
    if config.get("carrier_only") is True:
        surface = central_surface(volume, m2m)
    elif channels is None and sim.legacy_normal.is_file():
        surface = central_surface(volume, m2m)
        old = mesh_io.read_msh(str(sim.legacy_normal))
        _same_nodes(sim, surface, old, sim.legacy_normal)
        surface.add_node_field(
            np.asarray(old.field[const.FIELD_TI_NORMAL].value), const.FIELD_TI_NORMAL
        )
    else:
        if channels is None:
            channels = _read_channels(sim, config, volume)
        surface = central_surface(
            volume, m2m, e_fields=[m.field["E"].value for m in channels]
        )
    if sim.central.is_file():
        _same_nodes(sim, surface, mesh_io.read_msh(str(sim.central)), sim.central)
    return surface


def _same_nodes(sim: _Simulation, surface, reference, path: Path) -> None:
    if surface.nodes.nr != reference.nodes.nr:
        raise RuntimeError(
            f"The head model's central surface has {surface.nodes.nr} nodes but {path} has "
            f"{reference.nodes.nr}: sub-{sim.subject_id} was segmented again after "
            f"{sim.name} ran. Re-run the simulation."
        )


def _produce_surface(sim: _Simulation, config: dict) -> None:
    """Write the central surface of the volume mesh as it is (staged, then moved into place)."""
    from simnibs import mesh_io

    surface = _surface(sim, config, mesh_io.read_msh(str(sim.volume_mesh)))
    with _staging(sim) as stage:
        staged = stage / sim.central.name
        mesh_io.write_msh(surface, str(staged))
        sim.central.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged, sim.central)


def _produce_mesh_fields(
    sim: _Simulation, config: dict, missing: list[str], names: list[str], spaces
) -> None:
    """Compute *missing*, then write every output it changes, the volume mesh last.

    All of it -- the volume mesh, its central surface and, for a run that writes NIfTIs, the
    new fields' NIfTIs in its *spaces* (whole, grey and white matter) -- is written into a
    staging folder and moved into place once complete: the derived files first, the volume
    mesh last. So "the volume mesh carries the field" (what :func:`_missing` reads) implies
    every derived file is complete; a production killed earlier leaves the volume mesh without
    the field and the next one redoes all of it.
    """
    from simnibs import mesh_io

    from tit.paths import get_path_manager

    volume = mesh_io.read_msh(str(sim.volume_mesh))
    channels = _read_channels(sim, config, volume)
    for name, values in compute_volume_fields(
        [m.field["E"].value for m in channels],
        missing,
        max_name=sim.max_name,
        coherent=config.get("carrier_only") is True,
    ):
        volume.add_element_field(values, name)
    surface = _surface(sim, config, volume, channels)

    m2m = get_path_manager().m2m(sim.subject_id)
    stem = sim.volume_mesh.stem
    with _staging(sim) as stage:
        staged = stage / sim.volume_mesh.name
        mesh_io.write_msh(volume, str(staged))
        mesh_io.write_msh(surface, str(stage / sim.central.name))
        # A run that writes NIfTIs keeps one per mesh field (check_niftis_match_meshes).
        for space in spaces:
            for tissue in (None, "grey", "white"):
                base = f"{tissue + '_' if tissue else ''}{stem}"
                _convert(staged, m2m, stage / "niftis", base, space, names, tissue)
        sim.central.parent.mkdir(parents=True, exist_ok=True)
        os.replace(stage / sim.central.name, sim.central)
        _move_all(stage / "niftis", sim.niftis_dir)
        os.replace(staged, sim.volume_mesh)


def _nifti_name(base: str, space: str, field: str) -> str:
    token = "MNI_MNI" if space == "mni" else "subject"
    return f"{base}_{token}_{field}.nii.gz"


def _saved(path: Path) -> Path | None:
    """*path* (``.nii.gz``) or its uncompressed ``.nii`` twin, whichever is on disk."""
    for candidate in (path, path.with_name(path.name[: -len(".gz")])):
        if candidate.is_file():
            return candidate
    return None


def ensure_niftis(
    subject_id: str,
    simulation: str,
    fields,
    *,
    tissue: str | None,
    space: str = "subject",
    say: Callable[[str], None] = _quiet,
) -> tuple[dict[str, Path], list[str]]:
    """The NIfTI of each field of *fields* for one tissue and space, produced if not saved.

    Args:
        subject_id: Subject identifier (no ``sub-``).
        simulation: Simulation (montage) folder name.
        fields: Volume field names, as for :func:`ensure_mesh_fields`.
        tissue: ``"grey"``, ``"white"`` or ``None`` (the whole brain-tissue mesh); a tissue's
            NIfTI is converted from the volume mesh cropped to it.
        space: ``"subject"`` or ``"mni"``.
        say: As for :func:`ensure_mesh_fields`.

    Returns:
        ``{on-disk field name: path}`` and the sentences said while producing them.

    Raises:
        FieldUnavailableError: a missing field cannot be produced.
        RuntimeError: the conversion ran but did not write a requested file.
    """
    if tissue not in ("grey", "white", None) or space not in ("subject", "mni"):
        raise ValueError(
            f"tissue {tissue!r} / space {space!r} is not one a simulation writes"
        )
    sim = _simulation(subject_id, simulation)
    names = _validated(fields)
    base = f"{tissue + '_' if tissue else ''}{sim.name}_{sim.mode}"
    paths = {
        _on_disk(sim, n): sim.niftis_dir / _nifti_name(base, space, _on_disk(sim, n))
        for n in names
    }
    if all(_saved(p) for p in paths.values()):
        return {f: _saved(p) for f, p in paths.items()}, []
    notices = ensure_mesh_fields(subject_id, simulation, names, say=say, surface=False)
    with _producing(sim):
        absent = [f for f, p in paths.items() if not _saved(p)]
        if absent:
            mesh = sim.volume_mesh
            was, it = _was(absent)
            kind = "an MNI-space NIfTI" if space == "mni" else "a NIfTI"
            if len(absent) > 1:
                kind = "MNI-space NIfTIs" if space == "mni" else "NIfTIs"
            notice = (
                f"{_listed(absent)} {was} not saved as {kind} for {sim.name}; writing "
                f"{it} from {mesh.name}{f' ({tissue} matter)' if tissue else ''}."
            )
            say(notice)
            notices.append(notice)
            from tit.paths import get_path_manager

            m2m = get_path_manager().m2m(sim.subject_id)
            with _staging(sim) as stage:
                _convert(mesh, m2m, stage, base, space, absent, tissue)
                _move_all(stage, sim.niftis_dir)
    return {f: _saved(p) or p for f, p in paths.items()}, notices


def _convert(
    mesh: Path,
    m2m,
    out_dir: Path,
    base: str,
    space: str,
    fields,
    tissue: str | None = None,
) -> list[Path]:
    """The NIfTI of each of *fields* of *mesh* (cropped to *tissue*) in *space*, into *out_dir*.

    The simulator's own conversion (:mod:`tit.tools.mesh2nii`) and names
    (``<base>_subject_<field>.nii.gz`` / ``<base>_MNI_MNI_<field>.nii.gz``).

    Raises:
        RuntimeError: the conversion did not write a requested file.
    """
    from tit.tools.mesh2nii import TISSUE_TAGS, msh_to_mni, msh_to_nifti

    out_dir.mkdir(parents=True, exist_ok=True)
    convert = msh_to_mni if space == "mni" else msh_to_nifti
    token = "MNI" if space == "mni" else "subject"
    convert(
        str(mesh),
        str(m2m),
        str(out_dir / f"{base}_{token}"),
        fields=list(fields),
        tags=TISSUE_TAGS[tissue] if tissue else None,
    )
    written = [out_dir / _nifti_name(base, space, f) for f in fields]
    unwritten = [str(p) for p in written if not p.is_file()]
    if unwritten:
        raise RuntimeError(
            f"The NIfTI conversion of {mesh} did not write {', '.join(unwritten)}."
        )
    return written


def voxelise(mesh, m2m, out_dir, fields, *, tissue=None) -> dict[str, Path]:
    """Subject-space NIfTIs of *fields* of the field mesh *mesh* (cropped to *tissue*).

    Written into *out_dir* as ``<tissue_><mesh stem>_subject_<field>.nii.gz``.

    The conversion the on-demand path uses, for a caller that keeps the volumes elsewhere
    (the simulation report voxelises its envelope into a scratch folder). Keyed by field.

    Raises:
        FieldUnavailableError: *mesh* is missing, or does not carry one of *fields*.
        RuntimeError: the conversion did not write a requested file.
    """
    mesh = Path(mesh)
    carried = msh_field_names(mesh) if mesh.is_file() else None
    absent = [f for f in fields if carried is None or f not in carried]
    if absent:
        raise FieldUnavailableError(
            f"{mesh} is missing or does not carry {_listed(absent)}, so it cannot be "
            "voxelised."
        )
    base = f"{tissue + '_' if tissue else ''}{mesh.stem}"
    written = _convert(mesh, m2m, Path(out_dir), base, "subject", fields, tissue)
    return dict(zip(fields, written))


def _parse_nifti(sim: _Simulation, filename: str) -> tuple[str | None, str, str] | None:
    """``(tissue, space, on-disk field)`` of a simulator NIfTI name of *sim*, else ``None``."""
    for tissue in ("grey", "white", None):
        base = f"{tissue + '_' if tissue else ''}{sim.name}_{sim.mode}"
        for space in ("subject", "mni"):
            for name in _FIELD_ORDER:
                field = _on_disk(sim, name)
                name = _nifti_name(base, space, field)
                if filename in (name, name[: -len(".gz")]):
                    return tissue, space, field
    return None


def _nifti_at(subject_id: str, simulation: str, path: Path):
    """The simulation and ``(tissue, space, field)`` a simulator NIfTI path names, else ``None``.

    Read from the path itself (``<sim>/<TI|mTI>/niftis/<name>``), so it is the simulation the
    caller resolved, whatever folder that is.
    """
    niftis, mode_dir = path.parent, path.parent.parent
    if niftis.name != "niftis" or mode_dir.name not in ("TI", "mTI"):
        return None
    if mode_dir.parent.name != simulation:
        return None
    sim = _Simulation(subject_id, simulation, mode_dir.parent, mode_dir.name)
    parsed = _parse_nifti(sim, path.name)
    return None if parsed is None else (sim, parsed)


def check_nifti_producible(subject_id: str, simulation: str, path) -> bool:
    """Whether *path* is a NIfTI this simulation writes and could produce now (raises if not).

    ``False`` when the name is not one the simulator writes (the caller's own missing-file
    message applies); raises :class:`FieldUnavailableError` when it is, but its field cannot
    be produced (no field mesh, no channel meshes, ...).
    """
    found = _nifti_at(subject_id, simulation, Path(path))
    if found is None:
        return False
    sim, (_, _, field) = found
    try:
        missing = _missing(sim, [field])
        if missing:
            _check_producible(sim, missing)
    except FieldUnavailableError as exc:
        raise FieldUnavailableError(
            f"{path} was not saved and cannot be written: {exc}"
        )
    return True


def ensure_nifti_file(
    subject_id: str, simulation: str, path, *, say: Callable[[str], None] = _quiet
) -> list[str]:
    """Produce the simulation NIfTI *path* if it is missing; the sentences said.

    *path* is a name the simulator writes (``simulation_nifti_path`` resolves the group tools'
    patterns to one) of a simulation that has its field mesh. Any other missing file -- another
    name, a simulation that is not there -- is left to the caller to report as missing.

    Raises:
        FieldUnavailableError: the field mesh is there, but the field cannot be produced.
    """
    path = Path(path)
    if path.is_file():
        return []
    found = _nifti_at(subject_id, simulation, path)
    if found is None or not found[0].volume_mesh.is_file():
        return []
    tissue, space, field = found[1]
    try:
        return ensure_niftis(
            subject_id, simulation, [field], tissue=tissue, space=space, say=say
        )[1]
    except FieldUnavailableError as exc:
        raise FieldUnavailableError(
            f"{path} was not saved and cannot be written: {exc}"
        )


def check_niftis_match_meshes(volume_mesh, niftis_dir, *, mni: bool) -> None:
    """Raise unless *volume_mesh* has exactly one NIfTI per field, per tissue and space.

    The simulator's NIfTI set is its mesh field set, name for name: ``<base>_subject_<field>``
    (and ``<base>_MNI_MNI_<field>`` with *mni*) for each field, where ``<base>`` is the volume
    mesh's stem and its ``grey_`` / ``white_`` crops, and nothing else under those names.

    Raises:
        RuntimeError: the mesh's fields cannot be read, or the NIfTIs differ from them.
    """
    volume_mesh, niftis_dir = Path(volume_mesh), Path(niftis_dir)
    carried = msh_field_names(volume_mesh)
    if carried is None:
        raise RuntimeError(
            f"Cannot read the fields of {volume_mesh} to check its NIfTIs."
        )
    written = [p.name for p in niftis_dir.glob("*.nii*")]
    problems = []
    for base in (f"{t}{volume_mesh.stem}" for t in ("", "grey_", "white_")):
        for token in ("subject", "MNI_MNI") if mni else ("subject",):
            prefix = f"{base}_{token}_"
            have = {
                n[len(prefix) :].split(".nii")[0]
                for n in written
                if n.startswith(prefix)
            }
            if have != carried:
                problems.append(
                    f"{base} carries {sorted(carried)} but its {token} NIfTIs are "
                    f"{sorted(have)}"
                )
    if problems:
        raise RuntimeError(
            "The NIfTIs do not match the field mesh: " + "; ".join(problems) + "."
        )
