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

``TI_max`` / ``TI_normal`` are read from the pipeline's central-surface overlays;
``magnitude`` / ``hf_max`` are interpolated from the carrier **volume** meshes
(the surface overlays only reliably carry ``E_normal`` on some SimNIBS builds).

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

from tit.constants import FSAVG_NODES as _FSAVG_NODES
from tit.paths import get_path_manager
from tit.source.config import FsavgMapConfig

logger = logging.getLogger(__name__)


def _read_surface_scalar(path: Path, field_name: str) -> np.ndarray:
    """Read a node scalar field from a central-surface overlay mesh."""
    from simnibs.mesh_tools import mesh_io

    mesh = mesh_io.read_msh(str(path))
    if field_name not in mesh.field:
        raise ValueError(f"{path} has no field {field_name!r}")
    return np.asarray(mesh.field[field_name].value, dtype=float).reshape(-1)


def _carrier_volume_meshes(pm, subject_id: str, sim: str) -> tuple[Path, Path]:
    """Locate the two per-pair carrier VOLUME meshes for a simulation.

    Unlike the central-surface overlays -- which some SimNIBS builds fill with
    only ``E_normal`` -- the high-frequency volume meshes always carry the full
    vector ``E``, so ``magnitude`` / ``hf_max`` can be derived reliably from them.
    """
    sim_dir = Path(pm.simulation(subject_id, sim))

    def _find(pair: int) -> Path:
        # The carrier volume mesh always lives under high_Frequency/ (directly
        # before file organization, in mesh/ after); restrict to that subtree so
        # no surface overlay elsewhere under the sim dir can be picked instead.
        matches = sorted(
            p
            for p in sim_dir.glob(f"high_Frequency/**/*_TDCS_{pair}_*.msh")
            if not p.name.startswith("._") and not p.name.endswith("_central.msh")
        )
        if not matches:
            raise FileNotFoundError(
                f"No carrier volume mesh for TDCS_{pair} under {sim_dir}"
            )
        return matches[0]

    return _find(1), _find(2)


def _load_carrier_mesh(vol_path: Path):
    """Read a carrier volume mesh cropped to brain tissue, with its GM elements."""
    from simnibs.mesh_tools import mesh_io
    from simnibs.mesh_tools.mesh_io import ElementTags

    mesh = mesh_io.read_msh(str(vol_path)).crop_mesh(
        tags=[ElementTags.WM, ElementTags.GM, ElementTags.CSF]
    )
    gm_th = mesh.elm.get_tags(ElementTags.GM, return_element_numbers=True)
    return mesh, gm_th


def _interp_to_central(mesh, gm_th, field_name, central, hemispheres) -> np.ndarray:
    """Interpolate a named GM field onto the ``[lh; rh]`` central surface.

    Mirrors the pipeline's (and sleepTI's) volume->central interpolation for
    ``TI_max``.  Returns ``(n_lh + n_rh,)`` for a scalar field (e.g. ``magnE``)
    or ``(n_lh + n_rh, 3)`` for a vector field (e.g. ``E``).
    """
    field = mesh.field[field_name]
    return np.concatenate(
        [
            np.asarray(
                field.interpolate_to_surface(central[hemi], th_indices=gm_th).value,
                dtype=float,
            )
            for hemi in hemispheres
        ]
    )


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


def _morph_split(
    values: np.ndarray, n_lh: int, n_rh: int, morph, hemispheres
) -> np.ndarray:
    """Split a per-hemisphere central-surface scalar and morph each to fsaverage.

    The values are concatenated in ``hemispheres`` order, so we split in that
    same order (rather than assuming lh first) -- keeping the split aligned with
    however :func:`_interp_to_central` / the central overlay were concatenated.
    """
    if values.shape[0] != n_lh + n_rh:
        raise ValueError(
            f"overlay has {values.shape[0]} nodes, expected {n_lh + n_rh} (lh+rh)"
        )
    counts = {"lh": n_lh, "rh": n_rh}
    out: list[np.ndarray] = []
    offset = 0
    for hemi in hemispheres:
        n = counts[hemi]
        out.append(np.asarray(morph[hemi].resample(values[offset : offset + n]), float))
        offset += n
    return np.concatenate(out)


def _compute_fields(
    pm, subject_id: str, sim: str, cfg: FsavgMapConfig
) -> dict[str, np.ndarray]:
    """Project the requested fields for one (subject, simulation) to fsaverage."""
    from simnibs.mesh_tools import mesh_io
    from simnibs.utils.file_finder import SubjectFiles
    from simnibs.utils.transformations import cross_subject_map

    m2m = Path(pm.m2m(subject_id))
    subject_files = SubjectFiles(subpath=str(m2m))
    morph = cross_subject_map(
        subject_files, "fsaverage", subsampling_to=cfg.fsaverage_spacing
    )
    central = mesh_io.load_subject_surfaces(subject_files, "central")
    hemispheres = subject_files.hemispheres
    n_lh, n_rh = central["lh"].nodes.nr, central["rh"].nodes.nr

    # Each field is projected independently so one bad input (e.g. a missing
    # carrier overlay) drops only that field, not the others.
    out: dict[str, np.ndarray] = {}
    errors: list[str] = []
    expected = _FSAVG_NODES[cfg.fsaverage_spacing]

    def _project(name: str, compute) -> None:
        if name not in cfg.fields:
            return
        try:
            arr = _morph_split(compute(), n_lh, n_rh, morph, hemispheres)
            if arr.shape[0] != expected:
                raise ValueError(
                    f"expected {expected} fsaverage{cfg.fsaverage_spacing} nodes, "
                    f"got {arr.shape[0]}"
                )
            out[name] = arr
        except Exception as exc:  # noqa: BLE001 - per-field, keep the rest
            errors.append(f"{name}: {exc!r}")

    _project(
        "TI_max",
        lambda: _read_surface_scalar(_ti_max_overlay(pm, subject_id, sim), "TI_max"),
    )
    _project(
        "TI_normal",
        lambda: _read_surface_scalar(
            _ti_normal_overlay(pm, subject_id, sim), "TI_normal"
        ),
    )
    if "magnitude" in cfg.fields or "hf_max" in cfg.fields:
        try:
            vol1, vol2 = _carrier_volume_meshes(pm, subject_id, sim)
            m1, gm1 = _load_carrier_mesh(vol1)
            m2, gm2 = _load_carrier_mesh(vol2)
            # The full vector E is always present on the FEM volume mesh (unlike
            # the surface overlays, which some builds fill with only E_normal), so
            # both carrier fields derive from it -- interpolate it once per carrier.
            e1 = _interp_to_central(m1, gm1, "E", central, hemispheres).reshape(-1, 3)
            e2 = _interp_to_central(m2, gm2, "E", central, hemispheres).reshape(-1, 3)
        except Exception as exc:  # noqa: BLE001 - shared carrier read; skip both
            errors.append(f"carriers: {exc!r}")
        else:
            # hf_max = |E1| + |E2| peak instantaneous exposure (the upper bound);
            # magnitude = |E1 + E2| coherent vector sum. Both the full field.
            _project(
                "hf_max",
                lambda: np.linalg.norm(e1, axis=1) + np.linalg.norm(e2, axis=1),
            )
            _project("magnitude", lambda: np.linalg.norm(e1 + e2, axis=1))

    if not out:
        raise ValueError(
            f"no fields projected for {subject_id}/{sim}: " + "; ".join(errors)
        )
    if errors:
        logger.warning(
            "partial fsaverage projection for %s/%s: %s",
            subject_id,
            sim,
            "; ".join(errors),
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
