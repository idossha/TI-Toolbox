#!/usr/bin/env simnibs_python
"""
Base simulation class with shared logic for TI and mTI simulations.

BaseSimulation factors out the identical code shared by TISimulation and
mTISimulation:
  - __init__ (config, montage, logger, path manager, m2m_dir)
  - _apply_tissue_conductivities (env-var overrides)
  - run() template method (setup dirs, viz, build session, post-process)
  - _init_session() (common SESSION setup: subpath, tensor, eeg_cap, flags)
  - _add_electrode_pair() (electrode creation on a TDCS list)

Subclasses implement:
  - _simulation_mode      (property returning SimulationMode.TI or .MTI)
  - _montage_type_label   (property returning "TI" or "mTI")
  - _montage_imgs_key     (property returning dirs key for montage images)
  - _build_session()      (electrode-pair-specific session construction)
  - _post_process()       (field computation and file organization)
"""


import os
from abc import ABC, abstractmethod

from simnibs import run_simnibs, sim_struct

from tit.paths import get_path_manager
from tit.sim.config import SimulationConfig, Montage
from tit.sim.utils import (
    create_simulation_config_file,
    run_montage_visualization,
    setup_montage_directories,
)


class BaseSimulation(ABC):
    """Abstract base class for TI/mTI simulations.

    Subclasses must implement :pyattr:`_simulation_mode`,
    :pyattr:`_montage_type_label`, :pyattr:`_montage_imgs_key`,
    :meth:`_build_session`, and :meth:`_post_process`.
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
        """Return the SimulationMode enum value (TI or MTI)."""

    @property
    @abstractmethod
    def _montage_type_label(self) -> str:
        """Return the human-readable montage type label ('TI' or 'mTI')."""

    @property
    @abstractmethod
    def _montage_imgs_key(self) -> str:
        """Return the dirs dict key for montage images."""

    @abstractmethod
    def _build_session(self, output_dir: str) -> sim_struct.SESSION:
        """Build the SimNIBS SESSION with electrode configuration."""

    @abstractmethod
    def _post_process(self, dirs: dict) -> str:
        """Run post-processing. Return the path to the primary output mesh."""

    # ── Template method ─────────────────────────────────────────────────

    def run(self, simulation_dir: str) -> dict:
        """Execute the full simulation pipeline. Returns a result dict."""
        montage_dir = self.pm.simulation(
            self.config.subject_id,
            self.montage.name,
        )
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
            project_dir=self.config.project_dir,
            logger=self.logger,
            electrode_pairs=viz_pairs,
        )

        self.logger.info("SimNIBS simulation: Started")
        run_simnibs(self._build_session(dirs["hf_dir"]))
        self.logger.info("SimNIBS simulation: \u2713 Complete")

        output_mesh = self._post_process(dirs)
        self.logger.info(f"\u2713 {self.montage.name} complete")

        return {
            "montage_name": self.montage.name,
            "montage_type": self._montage_type_label,
            "status": "completed",
            "output_mesh": output_mesh,
        }

    # ── Shared helpers ──────────────────────────────────────────────────

    def _init_session(self, output_dir: str) -> sim_struct.SESSION:
        """Create and configure a SimNIBS SESSION with common settings.

        Returns a SESSION ready for electrode pair configuration.
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
        self, session: sim_struct.SESSION, pair_positions, current_mA: float
    ):
        """Add one electrode pair as a TDCS list and return it.

        Parameters
        ----------
        session : sim_struct.SESSION
            The SimNIBS session to add the pair to.
        pair_positions : sequence
            Two-element sequence of electrode positions (labels or XYZ).
        current_mA : float
            Current intensity in mA (will be converted to A).

        Returns
        -------
        tdcs : sim_struct.TDCSLIST
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
            el.shape = cfg.electrode_shape
            el.dimensions = cfg.electrode_dimensions
            el.thickness = [cfg.gel_thickness, cfg.rubber_thickness]

        return tdcs

    def _apply_tissue_conductivities(self, tdcs) -> None:
        """Override tissue conductivities from environment variables if set."""
        for i in range(len(tdcs.cond)):
            env_var = f"TISSUE_COND_{i + 1}"
            if env_var in os.environ:
                tdcs.cond[i].value = float(os.environ[env_var])
