"""Microscale coupling: map a TI/mTI field to cortical neuron polarization.

Takes the macroscale electric field the simulator already computes (the two
high-frequency pair fields) and, under the **quasi-static approximation**,
estimates how strongly -- and in what sign -- it polarizes cortical neurons
across a region, accounting for field **intensity and orientation**.

The headline product is a **subthreshold cortical polarization map**: the
per-vertex somatic ΔVm an unconnected population of L5 pyramidal neurons would
experience.  This is the literature-grounded, robust quantity for realistic
(scalp-deliverable) TI, where fields are far below the threshold for direct
firing (Wang et al. 2022; Rampersad et al. 2019).

This is an *optional, research-grade* module.  The heavy dependency (NEURON) is
imported lazily and only needed for the population's NEURON-subsample refinement;
the field-sampling and quasipotential math (:mod:`tit.microscale.field_sampler`)
and the analytic polarization map are pure NumPy and run without NEURON.

Pipeline::

    simnibs_python -m tit.microscale config.json   # mode: "polarization"

Physics
-------
Under the quasi-static approximation the FEM field is independent of the neuron
dynamics, so coupling is (Aberra et al. 2018/2020; Wang et al. 2022):

1. sample the E-field vector at the soma (locally near-uniform at cell scale),
2. integrate it over the morphology into a quasipotential ``V_e = -E·l_c``,
3. for the central estimate, take the first-order somatic polarization
   ``ΔVm = coupling · E_normal`` (Radman et al. 2009), linear in the field.

NEURON refines this on a subsample to characterize the morphology- and
orientation-dependent spread; it does not move the analytic estimate.

See Also
--------
tit.microscale.population : ``run_population`` -- the polarization-map pipeline.
tit.microscale.field_sampler : NEURON-free field sampling and quasipotentials.
"""

from tit.microscale.config import (
    DEFAULT_COUPLING_MV_PER_VM,
    KHZ_TIS_THRESHOLD_VM,
    LFS_THRESHOLD_VM,
    MicroscaleConfig,
    NeuronModelSpec,
    PopulationConfig,
    RegionSpec,
)
from tit.microscale.field_sampler import (
    load_field,
    mm_to_um,
    path_quasipotential,
    place_morphology,
    rotation_align,
    sample_at,
    uniform_quasipotential,
    um_to_mm,
)
from tit.microscale.coupling import (
    build_extracellular_timeseries,
    count_spikes,
    find_threshold,
    per_pair_quasipotentials,
    polarization_map,
    simulate_response,
)
from tit.microscale.models import (
    Cell,
    build_cell,
    build_from_spec,
    list_models,
    load_swc_cell,
    register_model,
)
from tit.microscale.morphology import (
    MorphologySpec,
    SectionSpec,
    load_swc,
    pyramidal_l5,
)
from tit.microscale.population import (
    analytic_polarization_map,
    azimuths,
    load_cluster_surface,
    place_spec_world,
    run_population,
    select_cluster,
    select_region,
)
from tit.microscale.metrics import (
    region_summary,
    write_polarization_gifti,
    write_polarization_msh,
    write_population_npz,
    write_region_summary_csv,
)
from tit.microscale.viz import (
    animate_polarization,
    instantaneous_field,
    plot_morphology,
    plot_polarization_histogram,
    plot_polarization_map,
    plot_population_3d,
    render_polarization_summary,
    render_population_figure,
    render_population_region,
)

__all__ = [
    # --- configs ---
    "PopulationConfig",
    "RegionSpec",
    "NeuronModelSpec",
    "MicroscaleConfig",  # experimental single-cell demonstrator
    "DEFAULT_COUPLING_MV_PER_VM",
    "LFS_THRESHOLD_VM",
    "KHZ_TIS_THRESHOLD_VM",
    # --- the polarization-map pipeline (headline) ---
    "run_population",
    "analytic_polarization_map",
    "select_region",
    "select_cluster",
    "load_cluster_surface",
    "place_spec_world",
    "azimuths",
    "region_summary",
    # --- quasi-static coupling math (NEURON-free foundation) ---
    "mm_to_um",
    "um_to_mm",
    "sample_at",
    "load_field",
    "uniform_quasipotential",
    "path_quasipotential",
    "rotation_align",
    "place_morphology",
    "per_pair_quasipotentials",
    "build_extracellular_timeseries",
    "count_spikes",
    "polarization_map",
    # --- cells ---
    "Cell",
    "build_cell",
    "build_from_spec",
    "load_swc_cell",
    "register_model",
    "list_models",
    "pyramidal_l5",
    "load_swc",
    "MorphologySpec",
    "SectionSpec",
    # --- figures ---
    "render_polarization_summary",
    "plot_polarization_map",
    "plot_polarization_histogram",
    "plot_morphology",
    "render_population_figure",
    "render_population_region",
    "plot_population_3d",
    "animate_polarization",
    "instantaneous_field",
    # --- output writers ---
    "write_population_npz",
    "write_region_summary_csv",
    "write_polarization_msh",
    "write_polarization_gifti",
    # --- experimental single-cell demonstrator (not quantitatively faithful) ---
    "simulate_response",
    "find_threshold",
]
