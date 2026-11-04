"""TI on white-matter networks defined by tractography.

Stages (each a public function; ``simnibs_python -m tit.tract config.json`` runs them in
order from a :class:`TractConfig`):

* :func:`run_track` -- DIPY whole-brain tractogram in m2m T1 world (``tractography/``);
* :func:`run_network` -- endpoint -> atlas region labels and the region connectome;
* :func:`run_assess` -- TI fields on the streamlines of each simulation
  (``Simulations/<sim>/tract/``);
* :func:`run_target` -- a tract-density ROI mask for the optimizers and a
  direction-aware montage ranking.

Heavy libraries (DIPY, SimNIBS, nibabel, scipy) are imported inside the functions, so
importing this package costs only numpy.
"""

from tit.tract.config import (
    AssessConfig,
    NetworkConfig,
    Selection,
    TargetConfig,
    TrackConfig,
    TractConfig,
)
from tit.tract.fields import run_assess, sample_carriers
from tit.tract.network import assign_endpoints, region_points, run_network, select
from tit.tract.target import density_mask, rank_montages, roi_specs, run_target
from tit.tract.tracking import run_track

__all__ = [
    "AssessConfig",
    "NetworkConfig",
    "Selection",
    "TargetConfig",
    "TrackConfig",
    "TractConfig",
    "assign_endpoints",
    "density_mask",
    "rank_montages",
    "region_points",
    "roi_specs",
    "run_assess",
    "run_network",
    "run_target",
    "run_track",
    "sample_carriers",
    "select",
]
