#!/usr/bin/env simnibs_python
"""
2-pair Temporal Interference (TI) simulation.

Session structure mirrors the official SimNIBS TI example:
  - SESSION with two TDCS lists (one per electrode pair)
  - deepcopy pattern for the second pair
  - TI_max computed with TI.get_maxTI on cropped meshes
  - TI_normal computed on cortical surface overlays

Output mesh includes per-pair E-field magnitudes and TI_max,
matching the reference visualisation layout.
"""

import glob
import os
from copy import deepcopy

import numpy as np
from simnibs import mesh_io, run_simnibs, sim_struct
from simnibs.utils import TI_utils as TI

from tit.paths import get_path_manager
from tit.sim.config import SimulationConfig, MontageConfig, SimulationMode
from tit.sim.utils import (
    convert_t1_to_mni,
    create_simulation_config_file,
    extract_fields,
    run_montage_visualization,
    safe_move,
    safe_rmdir,
    setup_montage_directories,
    transform_to_nifti,
)

# Brain tissue crop mask — keeps tissue volume elements (1-99) and tissue
# surface elements (1001-1099). Hardcoded ranges match the proven approach
# from the previous TI-toolbox release; using ElementTags constants produced
# a wider range that caught electrode-adjacent elements whose counts differ
# between the two placements, causing TI.get_maxTI's shape assertion to fail.
_TAGS_KEEP = np.hstack((np.arange(1, 100), np.arange(1001, 1100)))


class TISimulation:
    """
    Runs a single 2-pair TI simulation.

    Pipeline:
      1. Set up BIDS output directory structure
      2. Visualize electrode placement
      3. Build SimNIBS SESSION, run FEM
      4. Compute TI_max (volume) and TI_normal (surface)
      5. Extract GM/WM meshes, convert to NIfTI, organize outputs
    """

    def __init__(self, config: SimulationConfig, montage: MontageConfig, logger):
        self.config  = config
        self.montage = montage
        self.logger  = logger
        self.pm      = get_path_manager()
        self.m2m_dir = self.pm.path("m2m", subject_id=config.subject_id)

    def run(self, simulation_dir: str) -> dict:
        """Execute the full pipeline. Returns a result dict."""
        montage_dir = self.pm.path(
            "simulation",
            subject_id=self.config.subject_id,
            simulation_name=self.montage.name,
        )
        dirs = setup_montage_directories(montage_dir, SimulationMode.TI)
        create_simulation_config_file(self.config, self.montage, dirs["documentation"], self.logger)

        viz_pairs = None if self.montage.is_xyz else self.montage.electrode_pairs

        run_montage_visualization(
            montage_name=self.montage.name,
            simulation_mode=SimulationMode.TI,
            eeg_net=self.montage.eeg_net,
            output_dir=dirs["ti_montage_imgs"],
            project_dir=self.config.project_dir,
            logger=self.logger,
            electrode_pairs=viz_pairs,
        )

        self.logger.info("SimNIBS simulation: Started")
        run_simnibs(self._build_session(dirs["hf_dir"]))
        self.logger.info("SimNIBS simulation: ✓ Complete")

        output_mesh = self._post_process(dirs)
        self.logger.info(f"✓ {self.montage.name} complete")

        return {
            "montage_name": self.montage.name,
            "montage_type": "TI",
            "status":       "completed",
            "output_mesh":  output_mesh,
        }

    # ------------------------------------------------------------------
    # Session building
    # ------------------------------------------------------------------

    def _build_session(self, output_dir: str) -> sim_struct.SESSION:
        """Build SimNIBS SESSION for 2-pair TI."""
        cfg = self.config
        S = sim_struct.SESSION()
        S.subpath  = self.m2m_dir
        S.fnamehead = os.path.join(self.m2m_dir, f"{cfg.subject_id}.msh")
        S.anisotropy_type = cfg.conductivity_type.value
        S.pathfem  = output_dir
        S.map_to_surf   = cfg.map_to_surf
        S.map_to_vol    = cfg.map_to_vol
        S.map_to_mni    = cfg.map_to_mni
        S.map_to_fsavg  = cfg.map_to_fsavg
        S.open_in_gmsh  = cfg.open_in_gmsh
        S.tissues_in_niftis = cfg.tissues_in_niftis

        if not self.montage.is_xyz:
            eeg_net = self.montage.eeg_net
            S.eeg_cap = os.path.join(
                self.pm.path("eeg_positions", subject_id=cfg.subject_id), eeg_net
            )

        tensor = os.path.join(self.m2m_dir, "DTI_coregT1_tensor.nii.gz")
        if os.path.exists(tensor):
            S.dti_nii = tensor

        # Pair 1
        p1_A = cfg.intensities.pair1 / 1000.0
        tdcs1 = S.add_tdcslist()
        tdcs1.anisotropy_type = cfg.conductivity_type.value
        tdcs1.currents = [p1_A, -p1_A]
        self._apply_tissue_conductivities(tdcs1)
        for idx, pos in enumerate(self.montage.electrode_pairs[0]):
            el = tdcs1.add_electrode()
            el.channelnr = idx + 1
            el.centre    = pos
            self._configure_electrode(el)

        # Pair 2 — deepcopy from pair 1, update centres and current
        p2_A = cfg.intensities.pair2 / 1000.0
        tdcs2 = S.add_tdcslist(deepcopy(tdcs1))
        tdcs2.currents = [p2_A, -p2_A]
        tdcs2.electrode[0].centre = self.montage.electrode_pairs[1][0]
        tdcs2.electrode[1].centre = self.montage.electrode_pairs[1][1]

        return S

    def _configure_electrode(self, electrode) -> None:
        el_cfg = self.config.electrode
        electrode.shape      = el_cfg.shape
        electrode.dimensions = el_cfg.dimensions
        electrode.thickness  = [el_cfg.thickness, el_cfg.sponge_thickness]

    def _apply_tissue_conductivities(self, tdcs) -> None:
        for i in range(len(tdcs.cond)):
            env_var = f"TISSUE_COND_{i + 1}"
            if env_var in os.environ:
                tdcs.cond[i].value = float(os.environ[env_var])

    # ------------------------------------------------------------------
    # Post-processing
    # ------------------------------------------------------------------

    def _post_process(self, dirs: dict) -> str:
        sid  = self.config.subject_id
        cond = self.config.conductivity_type.value
        name = self.montage.name

        # Load and crop HF meshes
        m1 = mesh_io.read_msh(os.path.join(dirs["hf_dir"], f"{sid}_TDCS_1_{cond}.msh"))
        m2 = mesh_io.read_msh(os.path.join(dirs["hf_dir"], f"{sid}_TDCS_2_{cond}.msh"))
        m1 = m1.crop_mesh(tags=_TAGS_KEEP)
        m2 = m2.crop_mesh(tags=_TAGS_KEEP)

        ef1 = m1.field["E"]
        ef2 = m2.field["E"]
        TImax = TI.get_maxTI(ef1.value, ef2.value)

        mout = deepcopy(m1)
        mout.elmdata = []
        mout.add_element_field(TImax, "TI_max")

        ti_path = os.path.join(dirs["ti_mesh"], f"{name}_TI.msh")
        mesh_io.write_msh(mout, ti_path)
        mout.view(visible_tags=[1002, 1006], visible_fields="TI_max").write_opt(ti_path)
        self.logger.info(f"TI_max saved: {ti_path}")

        self._calculate_ti_normal(dirs["hf_dir"], dirs["ti_mesh"], name)

        self.logger.info("Field extraction: Started")
        extract_fields(ti_path, dirs["ti_mesh"], f"{name}_TI", self.m2m_dir, sid, self.logger)
        self.logger.info("Field extraction: ✓ Complete")

        self.logger.info("NIfTI transformation: Started")
        transform_to_nifti(dirs["ti_mesh"], dirs["ti_niftis"], sid, self.m2m_dir, self.logger)
        self.logger.info("NIfTI transformation: ✓ Complete")

        self._organize_files(dirs)
        convert_t1_to_mni(self.m2m_dir, sid, self.logger)

        return ti_path

    def _calculate_ti_normal(self, hf_dir: str, output_dir: str, montage_name: str) -> None:
        """Compute TI_normal on the cortical surface (requires surface overlays from SimNIBS)."""
        sid  = self.config.subject_id
        cond = self.config.conductivity_type.value
        overlays = os.path.join(hf_dir, "subject_overlays")
        c1 = os.path.join(overlays, f"{sid}_TDCS_1_{cond}_central.msh")
        c2 = os.path.join(overlays, f"{sid}_TDCS_2_{cond}_central.msh")

        cm1 = mesh_io.read_msh(c1)
        cm2 = mesh_io.read_msh(c2)

        if "E" in cm1.field:
            ef1_v = cm1.field["E"].value
            ef2_v = cm2.field["E"].value
        else:
            normals = cm1.nodes_normals().value
            ef1_v = cm1.field["E_normal"].value.reshape(-1, 1) * normals
            ef2_v = cm2.field["E_normal"].value.reshape(-1, 1) * normals

        TI_normal = TI.get_dirTI(ef1_v, ef2_v, cm1.nodes_normals().value)

        mout = deepcopy(cm1)
        mout.nodedata = []
        mout.add_node_field(TI_normal, "TI_normal")

        normal_path = os.path.join(output_dir, f"{montage_name}_normal.msh")
        mesh_io.write_msh(mout, normal_path)
        mout.view(visible_fields=["TI_normal"]).write_opt(normal_path)
        self.logger.debug(f"TI_normal saved: {normal_path}")

    def _organize_files(self, dirs: dict) -> None:
        """Move SimNIBS output files into the BIDS directory structure."""
        hf = dirs["hf_dir"]

        for pattern in ("TDCS_1", "TDCS_2"):
            for ext in (".geo", "scalar.msh", "scalar.msh.opt"):
                for f in glob.glob(os.path.join(hf, f"*{pattern}*{ext}")):
                    safe_move(f, os.path.join(dirs["hf_mesh"], os.path.basename(f)), self.logger)

        vols = os.path.join(hf, "subject_volumes")
        for fname in os.listdir(vols):
            safe_move(os.path.join(vols, fname), os.path.join(dirs["hf_niftis"], fname), self.logger)
        safe_rmdir(vols, self.logger)

        overlays = os.path.join(hf, "subject_overlays")
        for fname in os.listdir(overlays):
            safe_move(os.path.join(overlays, fname),
                      os.path.join(dirs["ti_surface_overlays"], fname), self.logger)
        safe_rmdir(overlays, self.logger)

        safe_move(os.path.join(hf, "fields_summary.txt"),
                  os.path.join(dirs["hf_analysis"], "fields_summary.txt"), self.logger)

        for pattern in ("simnibs_simulation_*.log", "simnibs_simulation_*.mat"):
            for f in glob.glob(os.path.join(hf, pattern)):
                safe_move(f, os.path.join(dirs["documentation"], os.path.basename(f)), self.logger)
