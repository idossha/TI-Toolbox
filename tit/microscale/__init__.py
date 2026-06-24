"""Mesoscale coupling: drive NEURON neuron models with SimNIBS TI/mTI fields.

Takes the macroscale electric field that the simulator already computes
(per-element ``E`` vectors, plus the two high-frequency pair fields) and applies
it to multicompartment neuron models under the **quasi-static approximation**,
so researchers can see how neurons in an ROI respond to the exposure --
accounting for both field **intensity and orientation**, not just magnitude.

This is an *optional, research-grade* module.  It adds a heavy dependency
(NEURON) that is only imported lazily when a simulation is actually run; the
field-sampling and quasipotential math (:mod:`tit.microscale.field_sampler`) is
pure NumPy and usable without NEURON.

Pipeline::

    simnibs_python -m tit.microscale config.json

Physics
-------
Under the quasi-static approximation the FEM field is independent of the neuron
dynamics, so coupling is a four-step recipe (Aberra et al. 2020; Shirinpour et
al. 2021):

1. place a multicompartment neuron at a target location/orientation,
2. sample the E-field vector at each compartment,
3. integrate the field along the morphology into a quasipotential
   ``V_e = -∫ E·dl``,
4. inject ``V_e`` into NEURON's ``extracellular`` mechanism and run.

For temporal interference the cell is driven by the two kHz **carriers** (not a
precomputed envelope), so envelope demodulation emerges from the active
membrane biophysics (Mirzakhalili et al. 2020; Wang et al. 2022).

See Also
--------
tit.microscale.config : ``MicroscaleConfig`` and ``NeuronModelSpec``.
tit.microscale.field_sampler : NEURON-free field sampling and quasipotentials.
"""

from tit.microscale.config import MicroscaleConfig, NeuronModelSpec
from tit.microscale.field_sampler import (
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
from tit.microscale.viz import (
    animate_response,
    crop_surface_patch,
    plot_cell_in_cortex,
    plot_efield_vectors,
    plot_morphology,
    render_target,
    section_polylines,
)

__all__ = [
    "MicroscaleConfig",
    "NeuronModelSpec",
    "mm_to_um",
    "um_to_mm",
    "sample_at",
    "uniform_quasipotential",
    "path_quasipotential",
    "rotation_align",
    "place_morphology",
    "Cell",
    "build_cell",
    "build_from_spec",
    "load_swc_cell",
    "list_models",
    "register_model",
    "pyramidal_l5",
    "load_swc",
    "MorphologySpec",
    "SectionSpec",
    "build_extracellular_timeseries",
    "count_spikes",
    "per_pair_quasipotentials",
    "simulate_response",
    "polarization_map",
    "find_threshold",
    "plot_morphology",
    "plot_cell_in_cortex",
    "plot_efield_vectors",
    "animate_response",
    "render_target",
    "crop_surface_patch",
    "section_polylines",
]
