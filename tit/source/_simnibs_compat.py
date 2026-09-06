"""Make SimNIBS 4.6's EEG-to-MNE bridge run against the libraries it ships with.

The failure this prevents
------------------------
``simnibs.eeg.utils_mne`` -- the module that turns a SimNIBS point-electrode
leadfield into an ``mne.Forward`` plus an fsaverage ``mne.SourceMorph`` -- was
written against older versions of two of its own dependencies and was never
updated.  On the container's stack (SimNIBS 4.6, mne 1.12.1) it raises about
ten minutes into a forward run, right after the FEM leadfield has been paid
for (job ``674801945bee46aa``, 2026-09-03).  Two independent breakages, in the
order a run hits them:

1. **mne** (>= 1.6) assembles its namespace with ``lazy_loader``.
   ``mne.source_space`` became a *subpackage* exposing public names only, and a
   private submodule is not bound onto its parent until something imports it.
   Three of SimNIBS's lookups therefore raise
   ``AttributeError: No mne.<x> attribute <y>``::

       mne.source_space._complete_source_space_info   # utils_mne:235 _add_surface_info
       mne.morph._get_src_data / ._hemi_morph         # utils_mne:283,344 source_morph
       mne.forward._make_forward._prepare_for_forward / ._to_forward_dict
                                                      # utils_mne:439,482 make_forward

   Every one of those callables still exists in mne 1.12 with an unchanged
   signature -- only the path to reach it moved -- so they are re-attached
   where SimNIBS looks, rather than pinning mne back to 1.5.

2. **cortech**: SimNIBS 4.6 rewrote ``simnibs.utils.transformations.cross_subject_map``
   on top of ``cortech.surface.Sphere`` (its return annotation says
   ``dict[str, cortech.Sphere]``), but ``utils_mne.setup_source_space`` still reads
   the pre-cortech attribute::

       mmaps = {h: v.morph_mat for h, v in morphs.items()}   # utils_mne:103

   ``AttributeError: 'Sphere' object has no attribute 'morph_mat'``.  The matrix
   is still there under cortech's own name, ``Sphere._mapping_matrix``: a
   ``(target.n_vertices, self.n_vertices)`` sparse map filled in by
   ``Sphere.project`` -- for ``cross_subject_map(subject, "fsaverage")`` that is
   ``(n_fsaverage, n_subject)``, exactly the orientation
   ``mne.morph._hemi_morph`` wants for ``maps``.  So ``morph_mat`` is restored
   as a read-only alias.

Where this has to run
---------------------
In the same interpreter as ``simnibs.eeg.utils_mne``.  SimNIBS's own
``prepare_eeg_forward`` console script runs ``python -E``, which ignores
``PYTHONPATH`` and every other ``PYTHON*`` variable, so it cannot be shimmed
from the environment -- :mod:`tit.source._prepare_forward` calls the same
SimNIBS entry point directly with :func:`ensure_simnibs_eeg_compat` applied
first.
"""

from __future__ import annotations

import importlib
import logging
from types import ModuleType

logger = logging.getLogger(__name__)

#: ``(parent module, attribute, submodule to import)`` -- private submodules that
#: lazy_loader leaves unbound until something imports them.
_PRIVATE_SUBMODULES: tuple[tuple[str, str, str], ...] = (
    ("mne", "morph", "mne.morph"),
    ("mne.forward", "_make_forward", "mne.forward._make_forward"),
)

#: ``(parent module, attribute, modules that may define it)`` -- callables that
#: moved when their parent module became a package.
_MOVED_CALLABLES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "mne.source_space",
        "_complete_source_space_info",
        # mne >= 1.6 (the package's implementation module), then mne 1.5, where
        # ``mne.source_space`` is itself the module that defines it.
        ("mne.source_space._source_space", "mne.source_space"),
    ),
)

#: ``(module, class, old attribute, cortech's name for it)``.
_RENAMED_ATTRIBUTES: tuple[tuple[str, str, str, str], ...] = (
    ("cortech.surface", "Sphere", "morph_mat", "_mapping_matrix"),
)


def _find(module_names: tuple[str, ...], attr: str) -> object | None:
    for name in module_names:
        try:
            module: ModuleType = importlib.import_module(name)
        except ImportError:
            continue
        found = getattr(module, attr, None)
        if found is not None:
            return found
    return None


def _alias_property(old: str, new: str) -> property:
    """A read-only ``old`` that reads ``new``, with a message naming both.

    ``new`` is an *instance* attribute (cortech sets ``_mapping_matrix`` in
    ``__init__``/``project``), so it cannot be checked on the class up front;
    the failure surfaces here instead, saying which of the two possible causes
    a reader should look at.
    """

    def _get(self):
        value = getattr(self, new, None)
        if value is None:
            raise AttributeError(
                f"{type(self).__name__}.{old} is empty: either .project(target) "
                f"was never called, or this cortech release no longer fills in "
                f"{new!r} (see tit/source/_simnibs_compat.py)."
            )
        return value

    _get.__name__ = old
    return property(
        _get,
        doc=f"Compatibility alias for :attr:`{new}` (see tit.source._simnibs_compat).",
    )


def ensure_simnibs_eeg_compat() -> list[str]:
    """Repair SimNIBS 4.6's stale lookups into mne and cortech.

    Idempotent: a second call finds everything already bound and returns ``[]``.

    Returns
    -------
    list of str
        Dotted names this call had to (re-)attach, for the log.

    Raises
    ------
    RuntimeError
        If something SimNIBS needs cannot be found in the installed library --
        a readable message naming the version, rather than an ``AttributeError``
        from deep inside ``simnibs.eeg.utils_mne`` ten minutes into a run.
    """
    import mne

    applied: list[str] = []

    for parent_name, attr, submodule_name in _PRIVATE_SUBMODULES:
        parent = importlib.import_module(parent_name)
        if getattr(parent, attr, None) is not None:
            continue
        try:
            submodule = importlib.import_module(submodule_name)
        except ImportError as exc:  # pragma: no cover - a gutted mne install
            raise RuntimeError(
                f"mne {mne.__version__} has no module {submodule_name!r}, which "
                "simnibs.eeg.utils_mne needs to build an EEG forward solution "
                f"({exc})."
            ) from exc
        # Importing normally binds the child onto its parent; a lazy_loader
        # parent that shadows __getattr__ may not, so bind it explicitly.
        setattr(parent, attr, submodule)
        applied.append(f"{parent_name}.{attr}")

    for parent_name, attr, candidates in _MOVED_CALLABLES:
        parent = importlib.import_module(parent_name)
        if getattr(parent, attr, None) is not None:
            continue
        found = _find(candidates, attr)
        if found is None:
            raise RuntimeError(
                f"mne {mne.__version__} does not define {attr!r} in any of "
                f"{list(candidates)}; simnibs.eeg.utils_mne needs it to build an "
                "EEG forward solution. Install a supported mne (>=1.5,<2) or "
                "update tit/source/_simnibs_compat.py for this release."
            )
        setattr(parent, attr, found)
        applied.append(f"{parent_name}.{attr}")

    for module_name, class_name, old, new in _RENAMED_ATTRIBUTES:
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        if hasattr(cls, old):
            continue
        setattr(cls, old, _alias_property(old, new))
        applied.append(f"{module_name}.{class_name}.{old}")

    if applied:
        logger.info(
            "Applied SimNIBS/mne %s EEG-bridge compatibility shims: %s",
            mne.__version__,
            ", ".join(applied),
        )
    return applied
