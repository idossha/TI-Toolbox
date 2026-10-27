#!/usr/bin/env simnibs_python
"""Base simulation class with shared logic for TI and mTI simulations.

``BaseSimulation`` factors out the identical code shared by
``TISimulation`` and ``mTISimulation``:

* ``__init__`` -- config, montage, logger, path manager, m2m_dir
* ``_apply_tissue_conductivities`` -- env-var conductivity overrides
* ``run`` -- template method (setup dirs, viz, build session, post-process)
* ``_init_session`` -- common SESSION setup (subpath, tensor, eeg_cap, flags)
* ``_add_electrode_pair`` -- electrode creation on a TDCS list
* ``_cropped_carriers`` / ``_write_volume_mesh`` / ``_write_ti_normal`` -- the
  field outputs (:mod:`tit.calc` over all channel fields, any even count)

Subclasses implement the following abstract interface:

* ``_simulation_mode`` -- property returning ``SimulationMode.TI`` or ``.MTI``
* ``_montage_type_label`` -- property returning ``"TI"`` or ``"mTI"``
* ``_montage_imgs_key`` -- property returning dirs key for montage images
* ``_build_session`` -- electrode-pair-specific session construction
* ``_post_process`` -- field computation and file organization

See Also
--------
TISimulation : 2-pair TI implementation.
mTISimulation : N-pair mTI implementation.
SimulationConfig : Configuration consumed by simulations.
run_simulation : Top-level orchestration entry point.
"""

import os
import subprocess
from abc import ABC, abstractmethod
from copy import deepcopy

import numpy as np
from simnibs import mesh_io, run_simnibs, sim_struct

from tit import constants as const
from tit.calc import envelope, envelope_max, envelope_mean, hf_peak, hf_power
from tit.paths import get_path_manager
from tit.sim.config import Montage, SimulationConfig
from tit.sim.utils import (
    clear_previous_outputs,
    create_simulation_config_file,
    refuse_existing_result,
    run_montage_visualization,
    setup_montage_directories,
)

# Transient element field carrying the conductivity through the crop; never written.
_SIGMA = "_conductivity"

# Brain tissue crop mask: tissue volume elements and their surfaces
# (constants.BRAIN_TISSUE_TAG_RANGES); electrodes and gel are dropped.
_TAGS_KEEP = np.hstack([np.arange(lo, hi) for lo, hi in const.BRAIN_TISSUE_TAG_RANGES])


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


class BaseSimulation(ABC):
    """Abstract base class for TI/mTI simulations.

    Provides the template-method ``run`` pipeline that subclasses
    customise by implementing ``_build_session`` and ``_post_process``.

    Parameters
    ----------
    config : SimulationConfig
        Fully specified simulation configuration.
    montage : Montage
        The electrode montage to simulate.
    logger : logging.Logger
        Logger instance for status and diagnostic messages.

    Attributes
    ----------
    config : SimulationConfig
        Simulation configuration supplied at construction.
    montage : Montage
        Electrode montage supplied at construction.
    logger : logging.Logger
        Logger instance used throughout the pipeline.
    pm : tit.paths.PathManager
        Singleton path manager for BIDS path resolution.
    m2m_dir : str
        Absolute path to the subject's ``m2m_<subject>`` directory.

    See Also
    --------
    TISimulation : Concrete 2-pair TI subclass.
    mTISimulation : Concrete N-pair mTI subclass.
    run_simulation : Orchestrates ``BaseSimulation.run`` across montages.
    """

    def __init__(self, config: SimulationConfig, montage: Montage, logger):
        self.config = config
        self.montage = montage
        self.logger = logger
        self.pm = get_path_manager()
        self.m2m_dir = self.pm.m2m(config.subject_id)

    # ── Abstract interface ──────────────────────────────────────────────

    @property
    @abstractmethod
    def _simulation_mode(self):
        """Return the ``SimulationMode`` enum value (TI or MTI)."""

    @property
    @abstractmethod
    def _montage_type_label(self) -> str:
        """Return the human-readable montage type label (``'TI'`` or ``'mTI'``)."""

    @property
    @abstractmethod
    def _montage_imgs_key(self) -> str:
        """Return the dirs dict key for montage images."""

    @abstractmethod
    def _build_session(self, output_dir: str) -> sim_struct.SESSION:
        """Build the SimNIBS SESSION with electrode configuration."""

    @abstractmethod
    def _post_process(self, dirs: dict) -> str:
        """Run post-processing and return the path to the primary output mesh."""

    # ── Template method ─────────────────────────────────────────────────

    def run(self, simulation_dir: str, *, overwrite: bool = False) -> dict:
        """Execute the full simulation pipeline for one montage.

        This template method orchestrates directory setup, montage
        visualisation, SimNIBS FEM execution, and subclass-specific
        post-processing.

        Parameters
        ----------
        simulation_dir : str
            Root simulations directory for the subject.
        overwrite : bool
            Replace an earlier result of this montage.  The earlier run's
            derived outputs are removed first (see
            :func:`tit.sim.utils.clear_previous_outputs`), so the folder holds
            exactly what the new ``config.json`` says.

        Returns
        -------
        dict
            Result dictionary with keys ``montage_name``, ``montage_type``,
            ``status``, and ``output_mesh``.

        Raises
        ------
        FileExistsError
            If *overwrite* is ``False`` and the montage folder already holds a
            result mesh.  Nothing is written, ``config.json`` included.

        See Also
        --------
        run_simulation : Calls ``run`` for each montage in a config.
        """
        montage_dir = self.pm.simulation(
            self.config.subject_id,
            self.montage.name,
        )
        # SimNIBS's own guard looks for its session record in pathfem, which
        # _organize_files moves into documentation/, so after a completed run it
        # never fires: the result mesh is the toolbox's own marker of a result.
        if overwrite:
            clear_previous_outputs(montage_dir)
        else:
            refuse_existing_result(montage_dir, self.montage.name)
        dirs = setup_montage_directories(montage_dir, self._simulation_mode)
        create_simulation_config_file(
            self.config, self.montage, dirs["documentation"], self.logger
        )

        viz_pairs = None if self.montage.is_xyz else self.montage.electrode_pairs

        run_montage_visualization(
            montage_name=self.montage.name,
            simulation_mode=self._simulation_mode,
            eeg_net=self.montage.eeg_net,
            output_dir=dirs[self._montage_imgs_key],
            logger=self.logger,
            electrode_pairs=viz_pairs,
        )

        self.logger.info("SimNIBS simulation: Started")
        session = self._build_session(dirs["hf_dir"])
        self._session = session  # its conductivity settings feed hf_power_density
        if overwrite:
            # run_simnibs does not expose this supported SESSION option. Keep the
            # native existence guard for ordinary runs; never delete marker files.
            session.run(allow_multiple_runs=True)
        else:
            run_simnibs(session)
        self.logger.info("SimNIBS simulation: \u2713 Complete")

        output_mesh = self._post_process(dirs)
        self._write_report()
        self.logger.info(f"\u2713 {self.montage.name} complete")

        return {
            "montage_name": self.montage.name,
            "montage_type": self._montage_type_label,
            "status": "completed",
            "output_mesh": output_mesh,
            "output_dir": montage_dir,
        }

    # ── Shared helpers ──────────────────────────────────────────────────

    def _write_report(self) -> None:
        """Write the simulator report; a report that cannot be written never fails the run."""
        from tit.reporting.generators.simulation import create_simulation_report

        try:
            path = create_simulation_report(
                self.pm.project_dir, self.config.subject_id, self.montage.name
            )
            self.logger.info(f"Simulation report: {path}")
        except Exception as exc:  # the simulation stands without its report
            self.logger.warning(f"Simulation report could not be written: {exc}")

    def _init_session(self, output_dir: str) -> sim_struct.SESSION:
        """Create and configure a SimNIBS SESSION with common settings.

        Sets up the subject path, head mesh, output directory, tensor
        file (if available), and EEG cap file (for net-based montages).

        Parameters
        ----------
        output_dir : str
            Directory where SimNIBS writes its FEM output.

        Returns
        -------
        sim_struct.SESSION
            A SESSION ready for electrode pair configuration.
        """
        cfg = self.config
        S = sim_struct.SESSION()
        S.subpath = self.m2m_dir
        S.fnamehead = os.path.join(self.m2m_dir, f"{cfg.subject_id}.msh")
        S.pathfem = output_dir
        S.map_to_surf = cfg.map_to_surf
        S.map_to_vol = False
        S.map_to_MNI = False
        S.open_in_gmsh = cfg.open_in_gmsh

        if not self.montage.is_xyz:
            eeg_net = self.montage.eeg_net
            S.eeg_cap = os.path.join(self.pm.eeg_positions(cfg.subject_id), eeg_net)

        tensor = os.path.join(self.m2m_dir, "DTI_coregT1_tensor.nii.gz")
        if os.path.exists(tensor):
            S.fname_tensor = tensor

        return S

    def _add_electrode_pair(
        self,
        session: sim_struct.SESSION,
        pair_positions,
        current_mA: float,
        pair_index: int = 0,
    ):
        """Add one electrode pair as a TDCS list on *session*.

        Parameters
        ----------
        session : sim_struct.SESSION
            The SimNIBS session to add the pair to.
        pair_positions : sequence
            Two-element sequence of electrode positions (labels or XYZ).
        current_mA : float
            Current intensity in mA (converted to A internally).

        Returns
        -------
        sim_struct.TDCSLIST
            The configured TDCS list, for further customization if needed.
        """
        cfg = self.config
        current_A = current_mA / 1000.0
        tdcs = session.add_tdcslist()
        tdcs.anisotropy_type = cfg.conductivity
        tdcs.aniso_maxratio = cfg.aniso_maxratio
        tdcs.aniso_maxcond = cfg.aniso_maxcond
        tdcs.currents = [current_A, -current_A]
        self._apply_tissue_conductivities(tdcs)

        for idx, pos in enumerate(pair_positions):
            el = tdcs.add_electrode()
            el.channelnr = idx + 1
            el.centre = pos
            if self.montage.electrode_poses is not None:
                pose = self.montage.electrode_poses[pair_index * 2 + idx]
                el.pos_ydir = [pose[i][3] + 20 * pose[i][1] for i in range(3)]
            el.shape = cfg.electrode_shape
            el.dimensions = cfg.electrode_dimensions
            el.thickness = [cfg.gel_thickness, cfg.rubber_thickness]

        return tdcs

    def _element_conductivity(self, mesh) -> np.ndarray:
        """Per-element conductivity of this run's FEM solve, on its output *mesh*.

        SimNIBS rebuilds it from the session's own settings -- tissue values
        with any overrides, the anisotropy model and the DTI tensor file --
        exactly as the solve did (``TDCSLIST.cond2elmdata``), on the same
        mesh, and triangles take their tetrahedron's value as they do for
        ``E``.  Returns ``(N,)`` S/m for ``"scalar"``, ``(N, 9)`` row-major
        tensors for ``"dir"``/``"vn"``/``"mc"``.
        """
        cond = self._session.poslists[0].cond2elmdata(mesh, logger_level=10)
        cond.assign_triangle_values()
        return cond.value

    def _cropped_carriers(self, hf_dir: str, n_channels: int) -> list:
        """The channels' FEM output meshes ``TDCS_1..N``, cropped to brain tissue.

        With ``hf_power_density`` selected, channel 1 carries the solve's
        conductivity through the crop (:data:`_SIGMA`): added on the whole
        mesh, so it is the conductivity SimNIBS used, and cropped with it.
        """
        sid = self.config.subject_id
        cond = self.config.conductivity
        meshes = []
        for i in range(1, n_channels + 1):
            m = mesh_io.read_msh(os.path.join(hf_dir, f"{sid}_TDCS_{i}_{cond}.msh"))
            if i == 1 and const.FIELD_HF_POWER_DENSITY in self.config.output_fields:
                m.add_element_field(self._element_conductivity(m), _SIGMA)
            meshes.append(m.crop_mesh(tags=_TAGS_KEEP))
        return meshes

    def _write_volume_mesh(self, meshes: list, max_name: str, path: str) -> None:
        """Write the selected volume fields of the channels' ``E`` to *path*.

        Every field runs over all channel fields jointly, paired positionally
        (each two consecutive channels beat on one carrier pair).  The
        envelope maximum is written as *max_name* (``TI_max``; ``mTI_max``
        for mTI); carrier-only runs add the carriers coherently.
        """
        selected = set(self.config.output_fields)
        coherent = self.config.carrier_only
        fields = [m.field["E"].value for m in meshes]

        mout = deepcopy(meshes[0])
        mout.elmdata = []
        if const.FIELD_TI_MAX in selected:
            mout.add_element_field(envelope_max(fields), max_name)
        if const.FIELD_TI_AVG in selected:
            mout.add_element_field(envelope_mean(fields), const.FIELD_TI_AVG)
        if const.FIELD_HF_PEAK in selected:
            # Peak carrier field (Cassarà 2025 Part I, Eq. 3); one channel field is one carrier.
            mout.add_element_field(
                hf_peak(fields, coherent=coherent), const.FIELD_HF_PEAK
            )
        if const.FIELD_HF_SAR in selected:
            # hf_sar keeps sum|E_c|^2 = 2*hf_power on disk until its pending rename to hf_power.
            mout.add_element_field(
                2.0 * hf_power(fields, coherent=coherent), const.FIELD_HF_SAR
            )
        if const.FIELD_HF_POWER_DENSITY in selected:
            mout.add_element_field(
                hf_power_density(
                    fields, meshes[0].field[_SIGMA].value, coherent=coherent
                ),
                const.FIELD_HF_POWER_DENSITY,
            )

        view_field = (
            max_name if const.FIELD_TI_MAX in selected else next(iter(selected))
        )
        mesh_io.write_msh(mout, path)
        mout.view(visible_tags=[1002, 1006], visible_fields=view_field).write_opt(path)
        self.logger.info(f"{self._montage_type_label} mesh saved: {path}")

    def _write_ti_normal(self, hf_dir: str, n_channels: int, path: str) -> None:
        """Write ``TI_normal`` on the cortical surface to *path*.

        The envelope of all channel fields along the node normals of the
        SimNIBS central-surface overlays (:func:`tit.calc.envelope`).  An
        overlay holding only ``E_normal`` gives the field ``E_normal * n``.
        """
        sid = self.config.subject_id
        cond = self.config.conductivity
        overlays = os.path.join(hf_dir, "subject_overlays")
        cms = [
            mesh_io.read_msh(
                os.path.join(overlays, f"{sid}_TDCS_{i}_{cond}_central.msh")
            )
            for i in range(1, n_channels + 1)
        ]

        normals = cms[0].nodes_normals().value
        if "E" in cms[0].field:
            fields = [cm.field["E"].value for cm in cms]
        else:
            fields = [cm.field["E_normal"].value.reshape(-1, 1) * normals for cm in cms]

        mout = deepcopy(cms[0])
        mout.nodedata = []
        mout.add_node_field(envelope(fields, normals), const.FIELD_TI_NORMAL)
        mesh_io.write_msh(mout, path)
        mout.view(visible_fields=[const.FIELD_TI_NORMAL]).write_opt(path)
        self.logger.debug(f"TI_normal saved: {path}")

    def _generate_central_surface(self, mesh_path: str, surfaces_dir: str) -> None:
        """Generate the central cortical surface mesh via ``msh2cortex``.

        Parameters
        ----------
        mesh_path : str
            Path to the input TI/mTI mesh file.
        surfaces_dir : str
            Output directory for the generated surface mesh.
        """
        self.logger.info("Central surface generation: Started")
        subprocess.run(
            ["msh2cortex", "-i", mesh_path, "-m", self.m2m_dir, "-o", surfaces_dir],
            check=True,
            capture_output=True,
        )
        self.logger.info("Central surface generation: Complete")

    def _apply_tissue_conductivities(self, tdcs) -> None:
        """Override tissue conductivities from environment variables if set."""
        for i in range(len(tdcs.cond)):
            env_var = f"TISSUE_COND_{i + 1}"
            if env_var in os.environ:
                tdcs.cond[i].value = float(os.environ[env_var])
