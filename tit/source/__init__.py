"""EEG source-forward preparation and fsaverage field mapping.

Two pipelines that put EEG source reconstruction and TI stimulation fields on a
common cortical grid:

* :func:`prepare_forward` -- build an MNE-compatible EEG forward solution
  (leadfield + source space + fsaverage morph) from a SimNIBS head model.
* :func:`project_fields_to_fsaverage` -- project existing simulation field
  outputs (TI_max, TI_normal, |E|) onto an fsaverage template.

Both run under the SimNIBS interpreter::

    simnibs_python -m tit.source config.json

See Also
--------
tit.source.config : ``ForwardConfig`` and ``FsavgMapConfig`` dataclasses.
"""

from tit.source.config import ForwardConfig, FsavgMapConfig
from tit.source.fsaverage import project_fields_to_fsaverage, project_subject
from tit.source.forward import prepare_forward

__all__ = [
    "ForwardConfig",
    "FsavgMapConfig",
    "prepare_forward",
    "project_fields_to_fsaverage",
    "project_subject",
]
