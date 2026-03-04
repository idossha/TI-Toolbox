#!/usr/bin/env simnibs_python
"""
4-pair Multi-channel Temporal Interference (mTI) simulation.

Extends the TI pattern to 4 electrode pairs (A/B/C/D):
  - Pair AB  → TI_AB  (intermediate field)
  - Pair CD  → TI_CD  (intermediate field)
  - mTI_max  = TI.get_maxTI(TI_AB_vectors, TI_CD_vectors)

Intermediate TI vector fields are saved for inspection alongside
the final mTI_max mesh.
"""

import glob
import os
import shutil
from copy import deepcopy

import numpy as np
from simnibs import mesh_io, run_simnibs, sim_struct
from simnibs.utils import TI_utils as TI

from tit.core.calc import get_TI_vectors
from tit.paths import get_path_manager
from tit.sim.config import SimulationConfig, MontageConfig, SimulationMode
from tit.sim.utils import (
    convert_t1_to_mni,
    create_simulation_config_file,
    extract_fields,
    run_montage_visualization,
    safe_move,
    setup_montage_directories,
    transform_to_nifti,
)

_TAGS_KEEP = np.hstack((np.arange(1, 100), np.arange(1001, 1100)))


class mTISimulation:
    """
    Runs a single 4-pair mTI simulation.

    Pipeline:
      1. Set up BIDS output directory structure
      2. Visualize electrode placement
      3. Build SimNIBS SESSION (4 TDCS lists), run FEM
      4. Compute TI_AB and TI_CD vector fields
      5. Compute mTI_max = max-TI of the two intermediate fields
      6. Extract GM/WM, convert to NIfTI, organize outputs
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
        dirs = setup_montage_directories(montage_dir, SimulationMode.MTI)
        create_simulation_config_file(self.config, self.montage, dirs["documentation"], self.logger)

        viz_pairs = None if self.montage.is_xyz else self.montage.electrode_pairs

        run_montage_visualization(
            montage_name=self.montage.name,
            simulation_mode=SimulationMode.MTI,
            eeg_net=self.montage.eeg_net,
            output_dir=dirs["mti_montage_imgs"],
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
            "montage_type": "mTI",
            "status":       "completed",
            "output_mesh":  output_mesh,
        }

    # ------------------------------------------------------------------
    # Session building
    # ------------------------------------------------------------------

    def _build_session(self, output_dir: str) -> sim_struct.SESSION:
        """Build SimNIBS SESSION for 4-pair mTI."""
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

        pair_currents_A = [
            cfg.intensities.pair1 / 1000.0,
            cfg.intensities.pair2 / 1000.0,
            cfg.intensities.pair3 / 1000.0,
            cfg.intensities.pair4 / 1000.0,
        ]
        for i in range(4):
            current = pair_currents_A[i]
            tdcs = S.add_tdcslist()
            tdcs.anisotropy_type = cfg.conductivity_type.value
            tdcs.currents = [current, -current]
            self._apply_tissue_conductivities(tdcs)
            for idx, pos in enumerate(self.montage.electrode_pairs[i]):
                el = tdcs.add_electrode()
                el.channelnr = idx + 1
                el.centre    = pos
                self._configure_electrode(el)

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

        # Load and crop all 4 HF meshes
        meshes = []
        for i in range(1, 5):
            m = mesh_io.read_msh(os.path.join(dirs["hf_dir"], f"{sid}_TDCS_{i}_{cond}.msh"))
            meshes.append(m.crop_mesh(tags=_TAGS_KEEP))

        # Intermediate TI vector fields for each pair of pairs
        ti_ab = get_TI_vectors(meshes[0].field["E"].value, meshes[1].field["E"].value)
        ti_cd = get_TI_vectors(meshes[2].field["E"].value, meshes[3].field["E"].value)

        # Save intermediate meshes (for inspection)
        self._save_ti_vectors(meshes[0], ti_ab, dirs["ti_mesh"], f"{name}_TI_AB.msh")
        self._save_ti_vectors(meshes[0], ti_cd, dirs["ti_mesh"], f"{name}_TI_CD.msh")

        # Final mTI_max
        mti_field = TI.get_maxTI(ti_ab, ti_cd)
        mout = deepcopy(meshes[0])
        mout.elmdata = []
        mout.add_element_field(mti_field, "TI_Max")

        mti_path = os.path.join(dirs["mti_mesh"], f"{name}_mTI.msh")
        mesh_io.write_msh(mout, mti_path)
        mout.view(visible_tags=[1002, 1006], visible_fields="TI_Max").write_opt(mti_path)
        self.logger.info(f"mTI_max saved: {mti_path}")

        # Field extraction — mTI mesh and both intermediate TI meshes
        self.logger.info("Field extraction: Started")
        extract_fields(mti_path, dirs["mti_mesh"], f"{name}_mTI", self.m2m_dir, sid, self.logger)
        for suffix in ("TI_AB", "TI_CD"):
            extract_fields(os.path.join(dirs["ti_mesh"], f"{name}_{suffix}.msh"),
                           dirs["ti_mesh"], f"{name}_{suffix}", self.m2m_dir, sid, self.logger)
        self.logger.info("Field extraction: ✓ Complete")

        self.logger.info("NIfTI transformation: Started")
        transform_to_nifti(dirs["mti_mesh"], dirs["mti_niftis"], sid, self.m2m_dir, self.logger)
        self.logger.info("NIfTI transformation: ✓ Complete")

        self._organize_files(dirs)
        convert_t1_to_mni(self.m2m_dir, sid, self.logger)

        return mti_path

    def _save_ti_vectors(self, base_mesh, ti_vectors, output_dir: str, filename: str) -> None:
        """Save an intermediate TI vector field mesh."""
        mout = deepcopy(base_mesh)
        mout.elmdata = []
        mout.add_element_field(ti_vectors, "TI_vectors")
        path = os.path.join(output_dir, filename)
        mesh_io.write_msh(mout, path)
        mout.view(visible_tags=[1002, 1006], visible_fields="TI_vectors").write_opt(path)
        self.logger.debug(f"Saved: {path}")

    def _organize_files(self, dirs: dict) -> None:
        """Move HF files, renaming pairs 1-4 → A-D for mTI convention."""
        hf = dirs["hf_dir"]
        letter = {1: "A", 2: "B", 3: "C", 4: "D"}

        for i, ltr in letter.items():
            for ext in (".geo", "scalar.msh", "scalar.msh.opt"):
                for f in glob.glob(os.path.join(hf, f"*TDCS_{i}*{ext}")):
                    new_name = os.path.basename(f).replace(f"TDCS_{i}", f"TDCS_{ltr}")
                    safe_move(f, os.path.join(dirs["hf_mesh"], new_name), self.logger)

        # subject_volumes not needed for mTI
        shutil.rmtree(os.path.join(hf, "subject_volumes"))

        safe_move(os.path.join(hf, "fields_summary.txt"),
                  os.path.join(dirs["hf_analysis"], "fields_summary.txt"), self.logger)

        for pattern in ("simnibs_simulation_*.log", "simnibs_simulation_*.mat"):
            for f in glob.glob(os.path.join(hf, pattern)):
                safe_move(f, os.path.join(dirs["documentation"], os.path.basename(f)), self.logger)
