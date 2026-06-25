#!/usr/bin/env simnibs_python
"""Run the unconnected-population meso-scale model (NEURON distribution pass).

Drives tit.microscale.population.run_population for each subject: places an
unconnected population of L5 pyramidal clones x azimuthal rotations on the TI
central surface, sampled over the cluster, and solves the steady-state somatic
ΔVm under the subject's two-carrier TI field (quasi-uniform coupling
ψ = −E·s; Aberra 2018/2020; Radman 2009).

This is the *distribution* tier of the two-tier population estimate. The cheap
analytic central estimate (ΔVm = 0.27·E_normal over OUR fsaverage5 significant
cluster, related to per-subject response) is computed host-side in
sleepTI/src/microscale/run_cluster_polarization.py. This NEURON pass quantifies
how morphology / dendritic poles / orientation spread distribute polarization
around that central value, and validates the sub-mV priming magnitude.

INPUT REQUIREMENT
-----------------
run_population expects the toolbox's current simulation mesh layout:
    <ti_mesh_dir>/surfaces/*_TI_central.msh   (central surface + node normals)
    <ti_mesh_dir>/*_normal.msh                (TI_normal node field)
Older sims (e.g. OG1 with surface_overlays/lh.central) lack the central .msh and
must be re-run with the current toolbox simulation, or adapted. Verify with:
    ls <project>/derivatives/SimNIBS/sub-<id>/Simulations/<SIM>/TI/mesh/surfaces/

CLUSTER NOTE
------------
The population module defines its cluster by thresholding the subject's TI_normal
on the SUBJECT central surface (cluster_threshold), i.e. a field-defined cluster
in subject space -- a reasonable proxy for the insula field focus, but NOT a
1:1 map of our fsaverage5 functional significant cluster. Use this pass for the
magnitude/distribution check; keep the per-subject response correlation on the
host analytic script over the functional cluster. (Restricting the NEURON pass
to the exact functional cluster would require morphing the fsaverage5 mask into
each subject's central surface -- a follow-up extension.)

Run inside the ti-toolbox Docker container (from /ti-toolbox):
    simnibs_python scripts/run_population.py
"""

from __future__ import annotations

import sys

from tit.paths import get_path_manager
from tit.microscale.config import PopulationConfig
from tit.microscale.population import run_population

# --- Edit these ------------------------------------------------------------
SUBJECTS = ["101", "108", "112"]  # a few active subjects for the magnitude check
SIM_NAME = "OG1"                  # completed simulation folder name
CLUSTER_THRESHOLD = None          # V/m on TI_normal; None = whole surface, then
                                  # NEURON subsamples it. Set e.g. 0.15 to focus.
N_SUBSAMPLE = 30                  # cluster vertices solved with NEURON
N_CLONES = 5                      # morphological clones per site (Aberra std)
N_AZIMUTH = 6                     # rotations about the cortical normal
COUPLING = 0.27                   # mV/(V/m), L5 pyramidal soma (Radman 2009)


def main() -> int:
    pm = get_path_manager()
    if not pm.project_dir:
        print("ERROR: set PROJECT_DIR (export PROJECT_DIR=/mnt/<project>).", flush=True)
        return 1

    cfg = PopulationConfig(
        sim_name=SIM_NAME,
        model="l5_pyramidal",
        cluster_normal_field="TI_normal",
        cluster_threshold=CLUSTER_THRESHOLD,
        n_subsample=N_SUBSAMPLE,
        n_clones=N_CLONES,
        n_azimuth=N_AZIMUTH,
        polarization_coupling=COUPLING,
    )
    print(f"Population: sim={SIM_NAME} subjects={SUBJECTS} "
          f"subsample={N_SUBSAMPLE} clones={N_CLONES} azimuth={N_AZIMUTH}", flush=True)

    failed = []
    for sid in SUBJECTS:
        try:
            run_population(sid, cfg)
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ sub-{sid} FAILED: {exc}", flush=True)
            failed.append(sid)
    if failed:
        print(f"Failed: {', '.join(failed)}", flush=True)
        return 1
    print("✓ population complete; per-subject *_population.npz/_summary.csv written.",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
