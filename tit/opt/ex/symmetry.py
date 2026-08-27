"""Left/right symmetric bucket enumeration shared by ex-search and m-ex-search.

Both optimizers accept ``symmetric_bucket`` / ``symmetry_eeg_csv`` /
``symmetry_pairing`` on their bucket-mode configs.  This module owns the
pieces they share:

* :func:`infer_symmetry_eeg_csv` -- guess the EEG-position CSV from the
  leadfield name (``{subject}_leadfield_{net}.hdf5``).
* :func:`build_symmetry_mirror_map` -- resolve the CSV and build the
  electrode mirror map (:func:`tit.opt.ex.buckets.build_electrode_mirror_map`).
* :func:`symmetric_pair_options` -- the ``(plus, mirror(plus))`` pairs a
  plus/minus bucket pair admits.
* :func:`format_mirror_map` -- compact ``F7->F8, ...`` rendering for
  diagnostics.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

from .buckets import build_electrode_mirror_map, canonical_template_coord_path

SYMMETRY_PAIRING_WITHIN_PAIRS = "within_pairs"
SYMMETRY_PAIRING_CROSS_PAIRS = "cross_pairs"
SYMMETRY_PAIRINGS = (
    SYMMETRY_PAIRING_WITHIN_PAIRS,
    SYMMETRY_PAIRING_CROSS_PAIRS,
)


def net_name_from_leadfield(leadfield_hdf: str | Path) -> str:
    """Return the EEG net name encoded in a leadfield filename.

    Leadfields are named ``{subject}_leadfield_{net}.hdf5``; a bare
    ``{net}_leadfield.hdf5`` and a plain stem are accepted as fallbacks.
    """
    stem = Path(leadfield_hdf).name.removesuffix(".hdf5")
    _, sep, net_name = stem.partition("_leadfield_")
    if not sep:
        net_name = stem.removesuffix("_leadfield")
    return net_name


def infer_symmetry_eeg_csv(
    leadfield_hdf: str | Path, eeg_positions_dir: str | Path | None
) -> Path | None:
    """Guess the EEG-position CSV for a leadfield.

    Known template nets (GSN) resolve to the bundled 2-D template
    coordinates; everything else looks for ``{net}.csv`` inside
    *eeg_positions_dir* (the subject's ``m2m_*/eeg_positions``).
    """
    net_name = net_name_from_leadfield(leadfield_hdf)
    if not net_name:
        return None
    canonical = canonical_template_coord_path(net_name)
    if canonical is not None:
        return canonical
    if eeg_positions_dir is None:
        return None
    candidate = Path(eeg_positions_dir) / f"{net_name}.csv"
    return candidate if candidate.is_file() else None


def resolve_eeg_positions_csv(config, pm) -> Path | None:
    """Return the EEG-position CSV for *config* (explicit or inferred), or None."""
    explicit = getattr(config, "symmetry_eeg_csv", None)
    if explicit:
        path = Path(explicit)
        if path.is_file():
            return path
    return infer_symmetry_eeg_csv(
        config.leadfield_hdf, pm.eeg_positions(config.subject_id)
    )


def build_symmetry_mirror_map(config, pm, logger) -> dict[str, str] | None:
    """Build the electrode mirror map for a symmetric bucket search.

    Returns ``None`` when ``config.symmetric_bucket`` is off.  Raises
    ``ValueError`` when no EEG-position CSV can be found.
    """
    if not config.symmetric_bucket:
        return None

    eeg_csv = resolve_eeg_positions_csv(config, pm)
    if eeg_csv is None:
        raise ValueError(
            "symmetric_bucket requires a valid symmetry_eeg_csv or an inferable "
            "EEG-position CSV from the selected leadfield."
        )

    logger.info("Symmetric bucket mode: using EEG mirror map from %s", eeg_csv)
    return build_electrode_mirror_map(eeg_csv)


def symmetric_pair_options(
    plus_bucket: Iterable[str],
    minus_bucket: Iterable[str],
    mirror_map: dict[str, str],
) -> Iterator[tuple[str, str]]:
    """Yield ``(plus, mirror(plus))`` for every plus electrode whose mirror is in the minus bucket."""
    minus_set = set(minus_bucket)
    seen = set()
    for plus in plus_bucket:
        minus = mirror_map.get(plus)
        pair = (plus, minus)
        if minus in minus_set and plus != minus and pair not in seen:
            seen.add(pair)
            yield pair


def format_mirror_map(
    electrodes: Iterable[str], mirror_map: dict[str, str], limit: int = 12
) -> str:
    """Render ``mirror_map`` restricted to *electrodes* as ``F7->F8, ...``."""
    items = []
    for label in dict.fromkeys(electrodes):
        items.append(f"{label}->{mirror_map.get(label, '?')}")
    shown = ", ".join(items[:limit])
    if len(items) > limit:
        shown += f", ... ({len(items) - limit} more)"
    return shown or "(empty)"
