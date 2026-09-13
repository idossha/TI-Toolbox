"""EEG source-forward preparation and fsaverage field mapping.

Two pipelines that put EEG source reconstruction and TI stimulation fields on a
common cortical grid:

* :func:`prepare_forward` -- build an MNE-compatible EEG forward solution
  (leadfield + source space + fsaverage morph) from a SimNIBS head model.
* :func:`project_fields_to_fsaverage` -- project existing simulation field
  outputs (TI_max, TI_normal, hf_peak, hf_sar) onto an fsaverage template.

Both run under the SimNIBS interpreter::

    simnibs_python -m tit.source config.json

See Also
--------
tit.source.config : ``ForwardConfig`` and ``FsavgMapConfig`` dataclasses.
"""

from tit.source.config import ForwardConfig, FsavgMapConfig


def __getattr__(name: str):
    # Loading inverse/array utilities must not import the SimNIBS forward stack.
    if name == "prepare_forward":
        from tit.source.forward import prepare_forward

        return prepare_forward
    if name in {
        "project_fields_to_fsaverage",
        "project_subject",
        "project_carrier_fields",
        "project_scalar_field",
    }:
        from tit.source import fsaverage

        return getattr(fsaverage, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ForwardConfig",
    "FsavgMapConfig",
    "prepare_forward",
    "project_fields_to_fsaverage",
    "project_subject",
    "project_carrier_fields",
    "project_scalar_field",
]
