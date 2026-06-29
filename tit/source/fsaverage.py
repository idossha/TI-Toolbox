#!/usr/bin/env simnibs_python
"""Project existing simulation field outputs onto an fsaverage template.

Complementary to :mod:`tit.source.forward`: where the forward pipeline lets a
researcher reconstruct EEG sources *onto* fsaverage, this pipeline puts the
*stimulation* fields on the same grid, so source activity and TI exposure can be
compared vertexwise.

For an already-completed TI simulation it reads the pipeline's own
central-surface overlays and morphs the requested scalar fields to fsaverage:

* ``TI_max``    -- orientation-maximized TI envelope |E| (central overlay)
* ``TI_normal`` -- directional TI envelope along the cortical normal
* ``magnitude`` -- coherent carrier exposure |E1 + E2| on the central surface
* ``hf_max``    -- peak instantaneous carrier exposure |E1| + |E2| (the upper
  bound the tissue sees; distinct from ``magnitude``)

Unlike SimNIBS's native ``map_to_fsavg`` (which only runs at simulation time and
only emits ``TI_max``), this works *post-hoc* on any finished simulation and on
the derived ``TI_normal`` / ``magnitude`` quantities.

Runs under ``simnibs_python`` (reads SimNIBS meshes)::

    simnibs_python -m tit.source fsavg_config.json

See Also
--------
tit.source.config.FsavgMapConfig : Parameter object.
tit.source.forward.prepare_forward : The companion forward pipeline.
"""

from __future__ import annotations

import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from tit.paths import get_path_manager
from tit.source.config import FsavgMapConfig

logger = logging.getLogger(__name__)

# fsaverage total node counts (both hemispheres) per subdivision factor.
_FSAVG_NODES = {5: 20484, 6: 81924, 7: 327684}


def _read_surface_scalar(path: Path, field_name: str) -> np.ndarray:
    """Read a node scalar field from a central-surface overlay mesh."""
    from simnibs.mesh_tools import mesh_io

    mesh = mesh_io.read_msh(str(path))
    if field_name not in mesh.field:
        raise ValueError(f"{path} has no field {field_name!r}")
    return np.asarray(mesh.field[field_name].value, dtype=float).reshape(-1)


def _read_surface_vector(path: Path, field_name: str = "E") -> np.ndarray:
    """Read a node vector field (n, 3) from a central-surface overlay mesh."""
    from simnibs.mesh_tools import mesh_io

    mesh = mesh_io.read_msh(str(path))
    if field_name not in mesh.field:
        raise ValueError(f"{path} has no field {field_name!r}")
    return np.asarray(mesh.field[field_name].value, dtype=float).reshape(-1, 3)


def _ti_max_overlay(pm, subject_id: str, sim: str) -> Path:
    path = Path(pm.ti_central_surface(subject_id, sim))
    if not path.exists():
        raise FileNotFoundError(f"TI central-surface overlay not found: {path}")
    return path


def _ti_normal_overlay(pm, subject_id: str, sim: str) -> Path:
    mesh_dir = Path(pm.ti_mesh_dir(subject_id, sim))
    candidates = sorted(
        p for p in mesh_dir.glob("*_normal.msh") if not p.name.startswith("._")
    )
    if not candidates:
        raise FileNotFoundError(f"No TI_normal overlay (*_normal.msh) in {mesh_dir}")
    return candidates[0]


def _carrier_overlays(pm, subject_id: str, sim: str) -> tuple[Path, Path]:
    """Locate the two per-pair central E-field overlays for a simulation."""
    sim_dir = Path(pm.simulation(subject_id, sim))

    # ponytail: match the overlays wherever they live -- SimNIBS writes them under
    # `subject_overlays/`, but the sim pipeline moves them to `surface_overlays/`.
    # The `_TDCS_{pair}_..._central` stem is specific enough to skip the TI overlay.
    def _find(pair: int) -> Path:
        matches = sorted(
            p
            for p in sim_dir.glob(f"**/*_TDCS_{pair}_*_central.msh")
            if not p.name.startswith("._")
        )
        if not matches:
            raise FileNotFoundError(
                f"No per-pair central overlay for TDCS_{pair} under {sim_dir}"
            )
        return matches[0]

    return _find(1), _find(2)


def _hemisphere_node_counts(subject_files) -> tuple[int, int]:
    """Return (n_lh, n_rh) central-surface node counts for splitting overlays."""
    from simnibs.mesh_tools import mesh_io

    central = mesh_io.load_subject_surfaces(subject_files, "central")
    return central["lh"].nodes.nr, central["rh"].nodes.nr


def _morph_split(
    values: np.ndarray, n_lh: int, n_rh: int, morph, hemispheres
) -> np.ndarray:
    """Split an [lh; rh] central-surface scalar and morph each hemi to fsaverage."""
    if values.shape[0] != n_lh + n_rh:
        raise ValueError(
            f"overlay has {values.shape[0]} nodes, expected {n_lh + n_rh} (lh+rh)"
        )
    split = {"lh": values[:n_lh], "rh": values[n_lh:]}
    return np.concatenate(
        [
            np.asarray(morph[hemi].resample(split[hemi]), dtype=float)
            for hemi in hemispheres
        ]
    )


def _compute_fields(
    pm, subject_id: str, sim: str, cfg: FsavgMapConfig
) -> dict[str, np.ndarray]:
    """Project the requested fields for one (subject, simulation) to fsaverage."""
    from simnibs.utils.file_finder import SubjectFiles
    from simnibs.utils.transformations import cross_subject_map

    m2m = Path(pm.m2m(subject_id))
    subject_files = SubjectFiles(subpath=str(m2m))
    morph = cross_subject_map(
        subject_files, "fsaverage", subsampling_to=cfg.fsaverage_spacing
    )
    n_lh, n_rh = _hemisphere_node_counts(subject_files)
    hemispheres = subject_files.hemispheres

    out: dict[str, np.ndarray] = {}
    if "TI_max" in cfg.fields:
        values = _read_surface_scalar(_ti_max_overlay(pm, subject_id, sim), "TI_max")
        out["TI_max"] = _morph_split(values, n_lh, n_rh, morph, hemispheres)
    if "TI_normal" in cfg.fields:
        values = _read_surface_scalar(
            _ti_normal_overlay(pm, subject_id, sim), "TI_normal"
        )
        out["TI_normal"] = _morph_split(values, n_lh, n_rh, morph, hemispheres)
    if "magnitude" in cfg.fields or "hf_max" in cfg.fields:
        pair1, pair2 = _carrier_overlays(pm, subject_id, sim)
        e1 = _read_surface_vector(pair1)
        e2 = _read_surface_vector(pair2)
        if "magnitude" in cfg.fields:
            values = np.linalg.norm(e1 + e2, axis=1)  # |E1 + E2| coherent sum
            out["magnitude"] = _morph_split(values, n_lh, n_rh, morph, hemispheres)
        if "hf_max" in cfg.fields:
            # |E1| + |E2|: peak instantaneous carrier exposure (both carriers at
            # crest), the upper bound -- not the cancellation-prone vector sum.
            values = np.linalg.norm(e1, axis=1) + np.linalg.norm(e2, axis=1)
            out["hf_max"] = _morph_split(values, n_lh, n_rh, morph, hemispheres)

    expected = _FSAVG_NODES[cfg.fsaverage_spacing]
    for name, arr in out.items():
        if arr.shape[0] != expected:
            raise ValueError(
                f"{name}: expected {expected} fsaverage{cfg.fsaverage_spacing} "
                f"nodes, got {arr.shape[0]}"
            )
    return out


def _output_path(pm, subject_id: str, sim: str, spacing: int) -> Path:
    out_dir = Path(pm.forward_fsaverage(subject_id))
    return out_dir / f"sub-{subject_id}_sim-{sim}_space-fsaverage{spacing}_fields.npz"


def project_subject(
    subject_id: str,
    sim: str,
    cfg: FsavgMapConfig,
) -> tuple[str, str, str]:
    """Project one (subject, simulation) and cache the result as ``.npz``.

    Returns ``(subject_id, status, message)`` where status is one of
    ``{"ok", "cached", "failed"}`` so batch runs can record and continue.
    """
    pm = get_path_manager()
    out_path = _output_path(pm, subject_id, sim, cfg.fsaverage_spacing)
    if out_path.exists() and not cfg.overwrite:
        return subject_id, "cached", out_path.name
    try:
        maps = _compute_fields(pm, subject_id, sim, cfg)
    except Exception as exc:  # noqa: BLE001 - record per-subject and continue
        return subject_id, "failed", repr(exc)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_path, subject_id=subject_id, simulation=sim, **maps)
    medians = ", ".join(f"{k} med={np.median(v):.3f}" for k, v in maps.items())
    return subject_id, "ok", f"{medians} -> {out_path.name}"


def project_fields_to_fsaverage(
    subjects: list[tuple[str, str]],
    cfg: FsavgMapConfig,
) -> list[tuple[str, str, str]]:
    """Project field outputs to fsaverage for many (subject, simulation) pairs.

    Parameters
    ----------
    subjects : list of (str, str)
        ``(subject_id, simulation_name)`` pairs to project.
    cfg : FsavgMapConfig
        Field selection, fsaverage spacing, worker count, overwrite flag.

    Returns
    -------
    list of (str, str, str)
        Per-pair ``(subject_id, status, message)`` results.
    """
    workers = max(1, min(cfg.workers, len(subjects))) if subjects else 1
    logger.info("Projecting %d simulation(s) with %d worker(s)", len(subjects), workers)

    results: list[tuple[str, str, str]] = []
    if workers == 1:
        for subject_id, sim in subjects:
            res = project_subject(subject_id, sim, cfg)
            _log_result(res)
            results.append(res)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(project_subject, sid, sim, cfg): (sid, sim)
                for sid, sim in subjects
            }
            for future in as_completed(futures):
                res = future.result()
                _log_result(res)
                results.append(res)
    return results


def _log_result(result: tuple[str, str, str]) -> None:
    subject_id, status, msg = result
    tag = {"ok": "✓", "cached": "CACHED", "failed": "✗ FAILED"}.get(status, status)
    print(f"[{tag}] {subject_id}: {msg}", flush=True)
