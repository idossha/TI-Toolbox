#!/usr/bin/env simnibs_python
"""
SimNIBS session builder for TI simulations.
"""

from simnibs import sim_struct

import os
from copy import deepcopy
from typing import List, Tuple, Union

from tit.sim.config import SimulationConfig, MontageConfig, SimulationMode, IntensityConfig
from tit.core import get_path_manager


class SessionBuilder:
    """Builder class for constructing SimNIBS SESSION objects."""

    def __init__(self, config: SimulationConfig):
        """
        Initialize session builder.

        Args:
            config: Simulation configuration
        """
        self.config = config
        self.pm = get_path_manager()

        # Setup paths
        self.m2m_dir = self.pm.get_m2m_dir(config.subject_id)
        self.mesh_file = os.path.join(self.m2m_dir, f"{config.subject_id}.msh")
        self.tensor_file = os.path.join(self.m2m_dir, "DTI_coregT1_tensor.nii.gz")

    def build_session(
        self,
        montage: MontageConfig,
        output_dir: str
    ) -> sim_struct.SESSION:
        """
        Build SimNIBS SESSION object for a montage.

        Args:
            montage: Montage configuration
            output_dir: Output directory for simulation results

        Returns:
            Configured SESSION object
        """
        # Create base session
        S = sim_struct.SESSION()
        S.subpath = self.m2m_dir
        S.fnamehead = self.mesh_file
        S.anisotropy_type = self.config.conductivity_type.value
        S.pathfem = output_dir

        # Set EEG cap if using electrode names (not XYZ)
        if not montage.is_xyz:
            eeg_net = montage.eeg_net or self.config.eeg_net
            S.eeg_cap = os.path.join(self.m2m_dir, "eeg_positions", eeg_net)

        # Mapping options
        S.map_to_surf = self.config.map_to_surf
        S.map_to_vol = self.config.map_to_vol
        S.map_to_mni = self.config.map_to_mni
        S.map_to_fsavg = self.config.map_to_fsavg
        S.open_in_gmsh = self.config.open_in_gmsh
        S.tissues_in_niftis = self.config.tissues_in_niftis

        # DTI tensor for anisotropic conductivity
        if os.path.exists(self.tensor_file):
            S.dti_nii = self.tensor_file

        # Add electrode pairs based on simulation mode
        if montage.simulation_mode == SimulationMode.TI:
            self._add_ti_pairs(S, montage)
        elif montage.simulation_mode == SimulationMode.MTI:
            self._add_mti_pairs(S, montage)

        return S

    def _add_ti_pairs(self, S: sim_struct.SESSION, montage: MontageConfig):
        """
        Add 2 electrode pairs for standard TI.

        Each pair gets equal and opposite currents from a single intensity value.
        For example: pair1=2.0mA means [+2.0mA, -2.0mA] for the two electrodes.

        Args:
            S: SESSION object to modify
            montage: Montage configuration
        """
        intensities = self.config.intensities

        # Convert mA to Amperes for SimNIBS (SimNIBS expects currents in Amperes)
        pair1_current_A = intensities.pair1 / 1000.0
        pair2_current_A = intensities.pair2 / 1000.0

        # First pair
        tdcs1 = S.add_tdcslist()
        tdcs1.anisotropy_type = self.config.conductivity_type.value
        tdcs1.currents = [pair1_current_A, -pair1_current_A]
        self._apply_tissue_conductivities(tdcs1)

        for idx, pos in enumerate(montage.electrode_pairs[0]):
            electrode = tdcs1.add_electrode()
            electrode.channelnr = idx + 1
            electrode.centre = pos
            self._configure_electrode(electrode)

        # Second pair (use deepcopy as shown in SimNIBS example)
        tdcs2 = S.add_tdcslist(deepcopy(tdcs1))
        tdcs2.currents = [pair2_current_A, -pair2_current_A]
        tdcs2.electrode[0].centre = montage.electrode_pairs[1][0]
        tdcs2.electrode[1].centre = montage.electrode_pairs[1][1]

    def _add_mti_pairs(self, S: sim_struct.SESSION, montage: MontageConfig):
        """
        Add 4 electrode pairs for multipolar TI.

        Each pair gets equal and opposite currents from a single intensity value.
        For example: pair1=2.0mA means [+2.0mA, -2.0mA] for the two electrodes.

        Args:
            S: SESSION object to modify
            montage: Montage configuration
        """
        intensities = self.config.intensities

        # Convert mA to Amperes for SimNIBS (SimNIBS expects currents in Amperes)
        pair_currents_A = [
            intensities.pair1 / 1000.0,
            intensities.pair2 / 1000.0,
            intensities.pair3 / 1000.0,
            intensities.pair4 / 1000.0
        ]

        # Add 4 pairs
        num_pairs = min(4, len(montage.electrode_pairs))
        for i in range(num_pairs):
            tdcs = S.add_tdcslist()
            tdcs.anisotropy_type = self.config.conductivity_type.value
            tdcs.currents = [pair_currents_A[i], -pair_currents_A[i]]
            self._apply_tissue_conductivities(tdcs)

            for idx, pos in enumerate(montage.electrode_pairs[i]):
                electrode = tdcs.add_electrode()
                electrode.channelnr = idx + 1
                electrode.centre = pos
                self._configure_electrode(electrode)

    def _configure_electrode(self, electrode):
        """
        Configure electrode properties.

        Args:
            electrode: Electrode object to configure
        """
        electrode.shape = self.config.electrode.shape
        electrode.dimensions = self.config.electrode.dimensions
        electrode.thickness = [
            self.config.electrode.thickness,
            self.config.electrode.sponge_thickness
        ]

    def _apply_tissue_conductivities(self, tdcs):
        """
        Apply tissue conductivities from environment variables if available.

        Args:
            tdcs: TDCS list object to modify
        """
        for i in range(len(tdcs.cond)):
            env_var = f"TISSUE_COND_{i+1}"
            if env_var in os.environ:
                try:
                    tdcs.cond[i].value = float(os.environ[env_var])
                except ValueError:
                    pass
