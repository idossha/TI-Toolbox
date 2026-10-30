"""A simulation's volume fields: computed by the simulator, produced again on demand.

:func:`compute_volume_fields` is the one per-field computation. The simulator writes its output
into the montage's volume mesh (:meth:`tit.sim.base.BaseSimulation._write_volume_mesh`), and the
on-demand path below produces a field the simulation did not save from the same inputs: the
channel meshes every run keeps in ``high_Frequency/mesh/`` (``<sid>_TDCS_<k>_<cond>.msh``, ``k``
= 1, 2 for TI and A..Z for mTI), cropped to brain tissue as the simulator crops them.

What persists, so the next step finds the field saved:

* :func:`ensure_mesh_fields` adds the field to the volume mesh
  ``<sim>/<TI|mTI>/mesh/<sim>_<TI|mTI>.msh``, re-cuts its ``grey_``/``white_`` copies from it and
  regenerates its central surface (``msh2cortex``), which is what a mesh analysis reads;
* :func:`ensure_niftis` / :func:`ensure_nifti_file` also write the NIfTI a voxel step reads,
  under the simulator's own name (``<tissue_><sim>_<TI|mTI>_subject_<field>.nii.gz``, or
  ``..._MNI_MNI_<field>.nii.gz`` in MNI space) in ``<sim>/<TI|mTI>/niftis/``.

NIfTIs and the mesh stay consistent. A run that wrote NIfTIs (``map_to_vol`` in its run record)
has one per mesh field, so a field added to its mesh gets its NIfTIs too -- every converted
mesh, subject space and, with ``map_to_mni``, MNI space -- and the set still equals the mesh field
set. A run with NIfTIs off has no such set: its ``niftis/`` holds only what voxel steps asked for,
each a NIfTI of a field its mesh carries, never one the mesh lacks.

Each says one plain sentence per production before doing it ("hf_peak and hf_sar were not saved
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
import string
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from tit import constants as const
from tit.calc import envelope_max, envelope_mean, hf_peak, hf_power
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
    const.FIELD_HF_SAR,
    const.FIELD_HF_POWER_DENSITY,
)
_ENVELOPE_FIELDS = (const.FIELD_TI_MAX, const.FIELD_TI_AVG)


class FieldUnavailableError(FileNotFoundError):
    """A field a step needs was not saved and cannot be produced from what the simulation kept."""


def hf_power_density(fields, sigma, *, coherent: bool = False) -> np.ndarray:
    """Time-averaged carrier power absorbed per volume, W/m^3.

    ``(1/2) sum_c E_c^T sigma E_c`` for zero-to-peak carrier fields ``E_c``
    (V/m) at distinct frequencies: ``sigma * hf_power`` for isotropic
    ``sigma`` ``(N,)`` S/m, the full tensor form for ``(N, 9)`` anisotropic
    conductivities (``J . E`` averaged over time).  ``SAR = this / rho``
    (IEEE C95.1-2019, p. 35).  *coherent* is the carrier-only control: one
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
        elif name == const.FIELD_HF_SAR:
            # hf_sar keeps sum|E_c|^2 = 2*hf_power on disk until its pending rename to hf_power.
            out.append((name, 2.0 * hf_power(e_fields, coherent=coherent)))
        else:
            out.append((name, hf_power_density(e_fields, sigma, coherent=coherent)))
    return out


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
    """Logical *names* the volume mesh does not carry (none when its header cannot be read)."""
    if not sim.volume_mesh.is_file():
        raise FieldUnavailableError(
            f"{sim.name} has no field mesh at {sim.volume_mesh}; run the simulation first."
        )
    carried = msh_field_names(sim.volume_mesh)
    if carried is None:  # not a mesh whose headers this can read: the reader will say
        return []
    return [n for n in names if _on_disk(sim, n) not in carried]


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
    """``hf_peak``, ``hf_peak and hf_sar``, ``TI_max, hf_peak and hf_sar``."""
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def _was(names: list[str]) -> tuple[str, str]:
    return ("was", "it") if len(names) == 1 else ("were", "them")


def _quiet(notice: str) -> None:
    """The default ``say``: the notice is still returned to the caller."""


@contextmanager
def _producing(sim: _Simulation):
    """One producer per simulation at a time: two analyses may need the same field at once."""
    with open(sim.dir / ".on-demand.lock", "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def ensure_mesh_fields(
    subject_id: str, simulation: str, fields, *, say: Callable[[str], None] = _quiet
) -> list[str]:
    """Make the simulation's volume mesh carry every field of *fields*; the sentences said.

    A missing field is computed with :func:`compute_volume_fields` from the channel meshes,
    added to the volume mesh (written whole, then moved into place), and the mesh's
    ``grey_``/``white_`` copies and central surface are regenerated from it. Returns one
    sentence per production (empty when everything was saved), each handed to *say* before
    the work it announces starts.

    Args:
        subject_id: Subject identifier (no ``sub-``).
        simulation: Simulation (montage) folder name.
        fields: Logical or on-disk volume field names (``TI_max`` and ``mTI_max`` alike).
        say: Called with each sentence first (a caller's ``logger.info``).

    Raises:
        FieldUnavailableError: a missing field cannot be produced (see the module docstring).
        ValueError: a name is not a volume field (``TI_normal`` is a surface field).
    """
    sim = _simulation(subject_id, simulation)
    names = _validated(fields)
    if not _missing(sim, names):
        return []
    with _producing(sim):
        missing = _missing(sim, names)  # another producer may have finished meanwhile
        if not missing:
            return []
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
        _produce_mesh_fields(sim, config, missing)
        # A run that writes NIfTIs keeps one per mesh field (check_niftis_match_meshes).
        for space in spaces:
            for tissue in (None, "grey", "white"):
                base = f"{tissue + '_' if tissue else ''}{sim.name}_{sim.mode}"
                _write_niftis(sim, sim.mesh_dir / f"{base}.msh", base, space, names)
    return [notice]


def _recorded_nifti_spaces(config: dict) -> tuple[str, ...]:
    """The NIfTI spaces the run itself writes: none, subject, or subject and MNI."""
    options = config.get("mapping_options") or {}
    if options.get("map_to_vol") is not True:
        return ()
    return ("subject", "mni") if options.get("map_to_mni") is True else ("subject",)


def _produce_mesh_fields(sim: _Simulation, config: dict, missing: list[str]) -> None:
    from simnibs import mesh_io

    from tit.paths import get_path_manager
    from tit.sim.utils import extract_fields, generate_central_surface

    channels = [
        mesh_io.read_msh(str(p)).crop_mesh(tags=BRAIN_TAGS)
        for p in _channel_meshes(sim, config)
    ]
    volume = mesh_io.read_msh(str(sim.volume_mesh))
    if volume.elm.nr != channels[0].elm.nr:
        raise RuntimeError(
            f"{sim.volume_mesh} has {volume.elm.nr} elements but its brain-cropped channel "
            f"meshes have {channels[0].elm.nr}: they are not from the same run. Re-run the "
            "simulation."
        )
    for name, values in compute_volume_fields(
        [m.field["E"].value for m in channels],
        missing,
        max_name=sim.max_name,
        coherent=config.get("carrier_only") is True,
    ):
        volume.add_element_field(values, name)
    partial = sim.volume_mesh.with_name(sim.volume_mesh.name + ".partial")
    mesh_io.write_msh(volume, str(partial))
    os.replace(partial, sim.volume_mesh)

    m2m = get_path_manager().m2m(sim.subject_id)
    stem = sim.volume_mesh.stem
    extract_fields(
        str(sim.volume_mesh), str(sim.mesh_dir), stem, m2m, sim.subject_id, logger
    )
    generate_central_surface(str(sim.volume_mesh), m2m, str(sim.mesh_dir / "surfaces"))


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
        tissue: ``"grey"``, ``"white"`` or ``None`` (the whole brain-tissue mesh).
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
    notices = ensure_mesh_fields(subject_id, simulation, names, say=say)
    with _producing(sim):
        absent = [f for f, p in paths.items() if not _saved(p)]
        if absent:
            mesh = sim.mesh_dir / f"{base}.msh"
            was, it = _was(absent)
            kind = "an MNI-space NIfTI" if space == "mni" else "a NIfTI"
            if len(absent) > 1:
                kind = "MNI-space NIfTIs" if space == "mni" else "NIfTIs"
            notice = (
                f"{_listed(absent)} {was} not saved as {kind} for {sim.name}; writing "
                f"{it} from {mesh.name}."
            )
            say(notice)
            notices.append(notice)
            _write_niftis(sim, mesh, base, space, absent)
            unwritten = [str(paths[f]) for f in absent if not _saved(paths[f])]
            if unwritten:
                raise RuntimeError(
                    f"The NIfTI conversion of {mesh} did not write {', '.join(unwritten)}."
                )
    return {f: _saved(p) or p for f, p in paths.items()}, notices


def _write_niftis(sim: _Simulation, mesh: Path, base: str, space: str, fields) -> None:
    from tit.paths import get_path_manager
    from tit.tools.mesh2nii import msh_to_mni, msh_to_nifti

    sim.niftis_dir.mkdir(parents=True, exist_ok=True)
    m2m = get_path_manager().m2m(sim.subject_id)
    if space == "mni":
        msh_to_mni(str(mesh), m2m, str(sim.niftis_dir / f"{base}_MNI"), fields=fields)
    else:
        msh_to_nifti(
            str(mesh), m2m, str(sim.niftis_dir / f"{base}_subject"), fields=fields
        )


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
    missing = _missing(sim, [field])
    if missing:
        _check_producible(sim, missing)
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
    return ensure_niftis(
        subject_id, simulation, [field], tissue=tissue, space=space, say=say
    )[1]


def check_niftis_match_meshes(mesh_dir, niftis_dir, *, mni: bool) -> None:
    """Raise unless every volume mesh in *mesh_dir* has exactly one NIfTI per field, per space.

    The simulator's NIfTI set is its mesh field set, name for name: ``<mesh>_subject_<field>``
    (and ``<mesh>_MNI_MNI_<field>`` with *mni*) for each field of each converted mesh, and
    nothing else under that mesh's name. The surface-only ``*_normal.msh`` is not converted.

    Raises:
        RuntimeError: a mesh's fields cannot be read, or its NIfTIs differ from them.
    """
    mesh_dir, niftis_dir = Path(mesh_dir), Path(niftis_dir)
    written = [p.name for p in niftis_dir.glob("*.nii*")]
    problems = []
    for mesh in sorted(mesh_dir.glob("*.msh")):
        if mesh.name.startswith("._") or mesh.stem.endswith("_normal"):
            continue
        carried = msh_field_names(mesh)
        if carried is None:
            raise RuntimeError(f"Cannot read the fields of {mesh} to check its NIfTIs.")
        for token in ("subject", "MNI_MNI") if mni else ("subject",):
            prefix = f"{mesh.stem}_{token}_"
            have = {
                n[len(prefix) :].split(".nii")[0]
                for n in written
                if n.startswith(prefix)
            }
            if have != carried:
                problems.append(
                    f"{mesh.name} carries {sorted(carried)} but its {token} NIfTIs are "
                    f"{sorted(have)}"
                )
    if problems:
        raise RuntimeError(
            "The NIfTIs do not match the field meshes: " + "; ".join(problems) + "."
        )
