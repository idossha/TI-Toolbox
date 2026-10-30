#!/usr/bin/env simnibs_python
"""Two-channel Temporal Interference (TI) simulation.

Implements :class:`TISimulation`, the concrete ``BaseSimulation`` subclass
for standard two-channel TI stimulation.  The session structure mirrors the
official SimNIBS TI example:

* SESSION with two TDCS lists (one per channel)
* ``deepcopy`` pattern for the second channel
* ``TI_max`` computed with :func:`tit.calc.envelope_max` on cropped meshes
* ``TI_normal`` computed with :func:`tit.calc.envelope` along the normals of
  the cortical surface overlays

Output mesh includes the selected ``TI_max``, ``TI_avg``, ``hf_peak``,
``hf_rms`` and ``hf_power_density``.
Per-channel E-field magnitudes are not retained on it; those live on the
``high_Frequency/`` carrier meshes.

See Also
--------
BaseSimulation : Abstract base class providing the ``run`` template.
mTISimulation : N-channel multi-channel TI variant.
SimulationConfig : Configuration consumed by the simulation.
run_simulation : Top-level orchestration that dispatches to this class.
"""

import glob
import os
from copy import deepcopy

from simnibs import sim_struct

from tit import constants as const
from tit.sim.base import BaseSimulation
from tit.sim.config import SimulationMode
from tit.sim.utils import (
    extract_fields,
    safe_move,
)


class TISimulation(BaseSimulation):
    """Run a single two-channel TI simulation.

    Pipeline
    --------
    1. Set up BIDS output directory structure.
    2. Visualize electrode placement.
    3. Build SimNIBS SESSION, run FEM.
    4. Compute ``TI_max``/``TI_avg``/``hf_peak``/``hf_rms``/
       ``hf_power_density`` (volume) and
       ``TI_normal`` (surface).
    5. Extract GM/WM meshes and organize outputs; with ``map_to_vol``, write
       one NIfTI per field.

    See Also
    --------
    BaseSimulation : Parent class with shared setup and template ``run``.
    mTISimulation : Multi-channel variant for 4 or more channels.
    """

    @property
    def _simulation_mode(self):
        """Return ``SimulationMode.TI``."""
        return SimulationMode.TI

    @property
    def _montage_type_label(self) -> str:
        """Return ``'TI'``."""
        return "TI"

    @property
    def _montage_imgs_key(self) -> str:
        """Return ``'ti_montage_imgs'``."""
        return "ti_montage_imgs"

    # ── Session building ────────────────────────────────────────────────────────────────

    def _build_session(self, output_dir: str) -> sim_struct.SESSION:
        """Build SimNIBS SESSION for two-channel TI.

        Parameters
        ----------
        output_dir : str
            Directory where SimNIBS writes FEM output.

        Returns
        -------
        sim_struct.SESSION
            Configured session with two TDCS lists.
        """
        S = self._init_session(output_dir)

        # Pair 1
        tdcs1 = self._add_electrode_pair(
            S, self.montage.electrode_pairs[0], self.config.intensities[0]
        )

        # Pair 2 — deepcopy from pair 1, update centres and current
        p2_A = self.config.intensities[1] / 1000.0
        tdcs2 = S.add_tdcslist(deepcopy(tdcs1))
        tdcs2.currents = [p2_A, -p2_A]
        tdcs2.electrode[0].centre = self.montage.electrode_pairs[1][0]
        tdcs2.electrode[1].centre = self.montage.electrode_pairs[1][1]
        if self.montage.electrode_poses is not None:
            for electrode, pose in zip(
                tdcs2.electrode, self.montage.electrode_poses[2:]
            ):
                electrode.pos_ydir = [pose[i][3] + 20 * pose[i][1] for i in range(3)]

        return S

    # ── Post-processing ────────────────────────────────────────────────────────────────

    def _post_process(self, dirs: dict) -> str:
        """Compute TI fields and extract meshes; NIfTIs only with ``map_to_vol``.

        Parameters
        ----------
        dirs : dict
            Directory mapping returned by ``setup_montage_directories``.

        Returns
        -------
        str
            Path to the output TI mesh file.
        """
        sid = self.config.subject_id
        name = self.montage.name

        meshes = self._cropped_carriers(dirs["hf_dir"], 2)
        ti_path = os.path.join(dirs["ti_mesh"], f"{name}_TI.msh")
        self._write_volume_mesh(meshes, const.FIELD_TI_MAX, ti_path)

        if not self.config.carrier_only:  # ΔF = 0: no envelope to project
            self._write_ti_normal(
                dirs["hf_dir"], 2, os.path.join(dirs["ti_mesh"], f"{name}_normal.msh")
            )

        self.logger.info("Field extraction: Started")
        extract_fields(
            ti_path, dirs["ti_mesh"], f"{name}_TI", self.m2m_dir, sid, self.logger
        )
        self.logger.info("Field extraction: \u2713 Complete")

        # Organize files before NIfTI conversion so meshes are in their
        # final directories (hf_mesh/, ti_surface_overlays/, etc.)
        self._organize_files(dirs)

        self._generate_central_surface(ti_path, dirs["ti_surfaces"])

        if self.config.map_to_vol:
            self._write_niftis(dirs, "ti_mesh", "ti_niftis")

        return ti_path

    def _organize_files(self, dirs: dict) -> None:
        """Move SimNIBS output files into the BIDS directory structure."""
        hf = dirs["hf_dir"]

        # Move HF mesh files (.msh, .geo, .opt) into hf_mesh/
        cond = self.config.conductivity
        for pattern in ("TDCS_1", "TDCS_2"):
            for ext in (".geo", f"{cond}.msh", f"{cond}.msh.opt"):
                for f in glob.glob(os.path.join(hf, f"*{pattern}*{ext}")):
                    safe_move(
                        f,
                        os.path.join(dirs["hf_mesh"], os.path.basename(f)),
                    )

        # Move surface overlays (needed for TI_normal)
        overlays = os.path.join(hf, "subject_overlays")
        if os.path.isdir(overlays):
            for fname in os.listdir(overlays):
                safe_move(
                    os.path.join(overlays, fname),
                    os.path.join(dirs["ti_surface_overlays"], fname),
                )
            os.rmdir(overlays)

        safe_move(
            os.path.join(hf, "fields_summary.txt"),
            os.path.join(dirs["hf_analysis"], "fields_summary.txt"),
        )

        for pattern in ("simnibs_simulation_*.log", "simnibs_simulation_*.mat"):
            for f in glob.glob(os.path.join(hf, pattern)):
                safe_move(
                    f,
                    os.path.join(dirs["documentation"], os.path.basename(f)),
                )
