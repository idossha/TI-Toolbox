"""Refuse a job whose required inputs are not on disk, at submission instead of minutes later.

Background: an analyzer job in voxel space with a cortical ``DK40`` target was accepted,
queued, started, and only then died with ``FileNotFoundError: Atlas 'DK40' not found in
.../fastsurfer/sub-101/mri, ...`` because that subject had no FastSurfer/recon-all volume
parcellation. Nothing about that needed a running job to find out.

:func:`preflight` runs one small checker per job kind. Every check is a filesystem existence
or name-correctness test built on :class:`tit.paths.PathManager` and the *same* resolution
rules the runner uses (the analyzer's own :func:`~tit.analyzer.field_selector.select_field_file`
and :attr:`~tit.analyzer.analyzer.Analyzer._SURFACE_ATLAS_VOLUMES`, ``tit.opt.flex.utils.
eeg_net_csv_path``, ...), so the check and the runner cannot disagree about where an input
lives. No SimNIBS import, no mesh or volume is loaded; a config the checker cannot read
(missing keys, wrong shapes) yields nothing here -- that is :mod:`tit.jobs.config_check`'s job.

Each finding is a :class:`MissingInput`: what is missing, the named path it was expected at,
and how to produce it ("run FastSurfer for sub-101", "run the L_Insula simulation first",
"analyze in mesh space instead"). ``POST /api/jobs`` and ``POST /api/jobs/groups`` answer 422
with the list and create no job record.
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from tit.paths import PathManager, get_path_manager


@dataclass(frozen=True)
class MissingInput:
    """One input a job needs that is not on disk."""

    what: str
    expected_path: str | None
    how_to_fix: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


Checker = Callable[[PathManager, dict[str, Any]], list[MissingInput]]


def preflight(
    kind: str, config: dict[str, Any], project_dir: str
) -> list[MissingInput]:
    """Every input a *kind* job with *config* needs that is not on disk under *project_dir*.

    An empty list means the sweep found nothing missing (not that the job will succeed).
    Unknown kinds and kinds with nothing to check return ``[]``.
    """
    checker = _CHECKERS.get(kind)
    if checker is None or not isinstance(config, dict):
        return []
    pm = get_path_manager(project_dir)
    return checker(pm, config)


# -- shared pieces ----------------------------------------------------------------------------


def _preprocess_fix(sid: str) -> str:
    return f"Run preprocessing (SimNIBS charm) for sub-{sid} to build its head model."


def _head_model(pm: PathManager, sid: str) -> list[MissingInput]:
    """The subject's m2m directory and its head mesh -- what every per-subject kind reads."""
    m2m = Path(pm.m2m(sid))
    if not m2m.is_dir():
        return [
            MissingInput(
                what=f"head model (m2m directory) for sub-{sid}",
                expected_path=str(m2m),
                how_to_fix=_preprocess_fix(sid),
            )
        ]
    head = m2m / f"{sid}.msh"
    if not head.is_file():
        return [
            MissingInput(
                what=f"SimNIBS head mesh for sub-{sid}",
                expected_path=str(head),
                how_to_fix=(
                    f"The m2m folder exists but has no {sid}.msh; re-run charm for "
                    f"sub-{sid} (or delete the incomplete folder first)."
                ),
            )
        ]
    return []


def _eeg_net_missing(
    pm: PathManager, sid: str, csv_path: Path, what: str
) -> MissingInput:
    return MissingInput(
        what=what,
        expected_path=str(csv_path),
        how_to_fix=(
            f"Choose an EEG net that exists in {pm.eeg_positions(sid)} "
            "(the net names are the CSV file names)."
        ),
    )


def _collapsed_net(sid: str, csv_path: Path, then: str = "") -> list[MissingInput]:
    """A net whose electrodes collapsed onto each other, as one finding (or none).

    Nets warped before the 3.1.1 frame fix put dozens of electrodes on one scalp
    point; a simulation, mapping or leadfield on such a net runs and is wrong.
    :func:`tit.caps.net_file_collapsed` is the caps panel's own check, with the
    10-20 alias pairs (T3/T7, ...) of a correct SPM12 cap not counted.
    """
    from tit import caps

    pairs = caps.net_file_collapsed(csv_path)
    if not pairs:
        return []
    return [
        MissingInput(
            what=caps.collapsed_summary(csv_path.name, sid, pairs),
            expected_path=str(csv_path),
            how_to_fix=caps.REAPPLY_FIX.format(sid=sid, net=csv_path.name) + then,
        )
    ]


def _eeg_labels(csv_path: Path) -> set[str]:
    """Electrode labels of a SimNIBS net CSV (``Electrode,x,y,z,label`` rows), or empty."""
    labels: set[str] = set()
    try:
        with open(csv_path, newline="") as handle:
            for row in csv.reader(handle):
                if len(row) >= 5 and row[0].strip().lower() == "electrode":
                    labels.add(row[4].strip())
    except OSError:
        return set()
    return labels


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _atlas_files(paths: Any, what: str, how_to_fix: str) -> list[MissingInput]:
    """Every distinct path in *paths* (scalar or list) that is not a file."""
    missing = []
    for path in dict.fromkeys(p for p in _as_list(paths) if isinstance(p, str) and p):
        if not Path(path).is_file():
            missing.append(MissingInput(what, path, how_to_fix))
    return missing


def _not_own(pm: PathManager, sid: str, path: str | Path) -> bool:
    """Whether *path* lies outside sub-<sid>'s own derivatives (SimNIBS, FastSurfer, FreeSurfer).

    The folder is resolved, the file is not: a mask or leadfield symlinked into the subject's
    folder from shared storage is that subject's own file.
    """
    head, name = os.path.split(os.path.abspath(path))
    real = os.path.join(os.path.realpath(head), name)
    roots = (pm.sub(sid), pm.fastsurfer_subject(sid), pm.freesurfer_subject(sid))
    return not any(real.startswith(os.path.realpath(root) + os.sep) for root in roots)


def _subject_atlas_files(
    pm: PathManager, sid: str, roi: dict[str, Any], what: str
) -> list[MissingInput]:
    """:func:`_atlas_files` for an ROI's ``atlas_path``; a subject-space one (every space but
    ``mni``) must also be sub-<sid>'s own file, never another subject's.
    """
    fix = (
        f"Pick an atlas or mask file that exists for sub-{sid} (a subject atlas "
        "needs FastSurfer/recon-all; a custom mask must be imported first)."
    )
    paths = [p for p in _as_list(roi.get("atlas_path")) if isinstance(p, str) and p]
    if roi.get("atlas_space") == "mni":
        return _atlas_files(paths, what, fix)
    foreign = [p for p in dict.fromkeys(paths) if _not_own(pm, sid, p)]
    return [
        MissingInput(
            f"sub-{sid}'s own {what} (this one is not in sub-{sid}'s derivatives)",
            p,
            f"Pick sub-{sid}'s own atlas or mask; a subject-space file belongs to "
            "one subject's anatomy.",
        )
        for p in foreign
    ] + _atlas_files([p for p in paths if p not in foreign], what, fix)


def _subject_ids(config: dict[str, Any]) -> list[str]:
    sid = config.get("subject_id")
    if isinstance(sid, str) and sid:
        return [sid]
    return [s for s in config.get("subject_ids") or [] if isinstance(s, str) and s]


def _simulation_fix(sid: str, sim: str) -> str:
    return f"Run the {sim} simulation for sub-{sid} first (Simulator page)."


def _sim_nifti(pm: PathManager, sid: str, sim: str, pattern: str) -> list[MissingInput]:
    """The NIfTI *pattern* names in the simulation -- the file the group tools read.

    Resolved as the tools resolve it (``TI/niftis/``, or ``mTI/niftis/`` with mTI names).
    """
    from tit.analyzer.field_selector import simulation_nifti_path
    from tit.volume_fields import FieldUnavailableError, check_nifti_producible

    path = simulation_nifti_path(sid, sim, pattern)
    if path.is_file():
        return []
    what = (
        f"{'MNI field' if '_MNI' in path.name else 'field'} NIfTI for sub-{sid} / {sim}"
    )
    if not Path(pm.simulation(sid, sim)).is_dir():
        return [MissingInput(what, str(path), _simulation_fix(sid, sim))]
    # A simulator NIfTI the run did not save is written by the job, from the field mesh.
    try:
        if check_nifti_producible(sid, sim, path):
            return []
    except FieldUnavailableError as exc:
        return [MissingInput(what, str(path), str(exc))]
    fix = (
        f"{path.name} is not a NIfTI the {sim} simulation for sub-{sid} writes; check the "
        f"NIfTI file pattern against the simulator's names in {path.parent}."
    )
    return [MissingInput(what, str(path), fix)]


# -- sim -------------------------------------------------------------------------------------


def _check_sim(pm: PathManager, config: dict[str, Any]) -> list[MissingInput]:
    sid = config.get("subject_id")
    if not isinstance(sid, str) or not sid:
        return []
    missing = _head_model(pm, sid)
    if missing:
        return missing  # everything else lives under the head model
    checked_nets: set[Path] = set()  # one collapse finding per net, not per montage
    for montage in config.get("montages") or []:
        if not isinstance(montage, dict):
            continue
        # NET / FLEX_MAPPED montages are label-based and resolved against the cap CSV
        # (tit.sim.base: S.eeg_cap = eeg_positions/<eeg_net>); XYZ modes need no net.
        if montage.get("mode") not in ("net", "flex_mapped"):
            continue
        name = montage.get("name") or "?"
        net = montage.get("eeg_net")
        if not isinstance(net, str) or not net:
            missing.append(
                MissingInput(
                    what=f"EEG net for montage {name!r}",
                    expected_path=pm.eeg_positions(sid),
                    how_to_fix="Select an EEG net for this montage.",
                )
            )
            continue
        csv_path = Path(pm.eeg_positions(sid)) / net
        if not csv_path.is_file():
            missing.append(
                _eeg_net_missing(
                    pm, sid, csv_path, f"EEG net {net!r} for montage {name!r}"
                )
            )
            continue
        if csv_path not in checked_nets:
            checked_nets.add(csv_path)
            missing.extend(_collapsed_net(sid, csv_path))
        labels = _eeg_labels(csv_path)
        wanted = [
            e
            for pair in montage.get("electrode_pairs") or []
            for e in (pair if isinstance(pair, (list, tuple)) else [])
            if isinstance(e, str)
        ]
        unknown = [e for e in dict.fromkeys(wanted) if e not in labels]
        if unknown and labels:
            missing.append(
                MissingInput(
                    what=(
                        f"electrode(s) {', '.join(unknown)} of montage {name!r} "
                        f"in EEG net {net!r}"
                    ),
                    expected_path=str(csv_path),
                    how_to_fix=(
                        "Use electrode labels that exist in this net, or pick the net "
                        "the montage was defined on."
                    ),
                )
            )
    return missing


# -- flex ------------------------------------------------------------------------------------


def _check_flex(pm: PathManager, config: dict[str, Any]) -> list[MissingInput]:
    sid = config.get("subject_id")
    if not isinstance(sid, str) or not sid:
        return []
    missing = _head_model(pm, sid)
    if missing:
        return missing  # everything else lives under the head model
    # Both nets are names in the subject's eeg_positions, resolved by
    # tit.opt.flex.utils.eeg_net_csv_path's rule (not imported: tit.opt pulls SimNIBS in
    # at import time): the base name, with ".csv" appended when absent.
    nets = [("skin visualization EEG net", config.get("skin_visualization_net"))]
    if config.get("enable_mapping"):
        nets.insert(0, ("mapped EEG net", config.get("eeg_net")))
    for what, net in nets:
        if not isinstance(net, str) or not Path(net).name:
            continue
        filename = Path(net).name
        if Path(filename).suffix.lower() != ".csv":
            filename = f"{filename}.csv"
        csv_path = Path(pm.eeg_positions(sid)) / filename
        if not csv_path.is_file():
            missing.append(_eeg_net_missing(pm, sid, csv_path, f"{what} {net!r}"))
        elif what == "mapped EEG net":
            # The run's result is mapped onto this net's labels; the skin picture
            # net only draws, so a collapsed one is not worth refusing the run for.
            missing.extend(_collapsed_net(sid, csv_path))
    if (
        config.get("avoid_landmark_regions", True)
        and (config.get("skin_region_margin_mm") or 0) > 0
    ):
        fiducials = Path(pm.eeg_positions(sid)) / "Fiducials.csv"
        if not fiducials.is_file():
            missing.append(
                MissingInput(
                    f"SimNIBS fiducials for sub-{sid}",
                    str(fiducials),
                    "Set skin_region_margin_mm to 0, or re-run charm so eeg_positions/"
                    "Fiducials.csv is written.",
                )
            )
    for label, key in (("ROI", "roi"), ("non-ROI", "non_roi")):
        roi = config.get(key)
        if isinstance(roi, dict):
            missing.extend(
                _subject_atlas_files(pm, sid, roi, f"{label} atlas/mask file")
            )
    return missing


# -- ex / mex --------------------------------------------------------------------------------


def _leadfield_labels(csv_path: Path) -> set[str]:
    """The electrode names a leadfield built on the net CSV *csv_path* holds, or empty.

    SimNIBS's TDCSLEADFIELD stores every ``Electrode`` row and the ``ReferenceElectrode``
    row (Dataset 000: the 75 electrodes of EEG10-10_UI_Jurak_2007 plus ``Cz``), and
    ``TI_utils.load_leadfield`` maps the reference too (as the zero-potential pole), so
    both are usable Ex/mEx labels; a ``Fiducial`` row is not an electrode.
    """
    labels: set[str] = set()
    try:
        with open(csv_path, newline="") as handle:
            for row in csv.reader(handle):
                kind = row[0].strip().lower() if row else ""
                if len(row) >= 5 and kind in ("electrode", "referenceelectrode"):
                    labels.add(row[4].strip())
    except OSError:
        return set()
    return labels


def _ex_labels_off_net(electrodes: Any, net: str, net_csv: Path) -> list[MissingInput]:
    """Every bucket/pool label of an Ex/mEx ``electrodes`` dict the leadfield lacks, as one finding.

    The runner would load the whole leadfield and only then fail on the first unknown
    label inside SimNIBS's index lookup (``tit.opt.ex.engine``, ``TI.get_field``).
    """
    if not isinstance(electrodes, dict):
        return []
    wanted = [
        label
        for value in electrodes.values()
        if isinstance(value, (list, tuple))  # skips the "_type" discriminator
        for label in value
        if isinstance(label, str)
    ]
    known = _leadfield_labels(net_csv)
    unknown = [label for label in dict.fromkeys(wanted) if label not in known]
    if not unknown or not known:
        return []
    return [
        MissingInput(
            what=(
                f"electrode(s) {', '.join(unknown)} in EEG net {net!r}, "
                "the leadfield's net"
            ),
            expected_path=str(net_csv),
            how_to_fix=(
                f"Pick electrodes from {net}, or the leadfield of the net these "
                "came from."
            ),
        )
    ]


def _check_ex(pm: PathManager, config: dict[str, Any]) -> list[MissingInput]:
    sid = config.get("subject_id")
    if not isinstance(sid, str) or not sid:
        return []
    missing = _head_model(pm, sid)
    if missing:
        return missing  # everything else lives under the head model
    hdf = config.get("leadfield_hdf")
    path = Path(pm.leadfields(sid)) / hdf if isinstance(hdf, str) and hdf else None
    if path is not None and _not_own(pm, sid, path):
        # An absolute (or climbing) path wins the join: another subject's leadfield would run.
        missing.append(
            MissingInput(
                f"sub-{sid}'s own leadfield ({hdf!r} is not in sub-{sid}'s derivatives)",
                hdf,
                f"Use sub-{sid}'s leadfield from {pm.leadfields(sid)}; a leadfield is "
                "computed on one subject's head model.",
            )
        )
    elif path is not None:
        if not path.is_file():
            missing.append(
                MissingInput(
                    f"leadfield {hdf!r} for sub-{sid}",
                    str(path),
                    f"Generate the leadfield for sub-{sid} and this EEG net first "
                    "(Optimizer page, Leadfield).",
                )
            )
        # The leadfield's net, by tit.opt.ex.symmetry.net_name_from_leadfield's rule
        # (not imported: tit.opt pulls SimNIBS in): "<sid>_leadfield_<net>.hdf5".
        stem = Path(hdf).name.removesuffix(".hdf5")
        _, sep, net = stem.partition("_leadfield_")
        net = net if sep else stem.removesuffix("_leadfield")
        net_csv = Path(pm.eeg_positions(sid)) / f"{net}.csv"
        if net and net_csv.is_file():
            missing.extend(
                _collapsed_net(
                    sid,
                    net_csv,
                    " Then regenerate this leadfield: one built on the collapsed net "
                    "is wrong too.",
                )
            )
            missing.extend(_ex_labels_off_net(config.get("electrodes"), net, net_csv))
    # ExConfig/MExConfig.__post_init__ append ".csv"; roi_names=None means [roi_name].
    names = config.get("roi_names")
    if names is None:
        names = [config.get("roi_name")]
    for name in names or []:
        if not isinstance(name, str) or not name:
            continue
        if not name.endswith(".csv"):
            name += ".csv"
        path = Path(pm.rois(sid)) / name
        if not path.is_file():
            missing.append(
                MissingInput(
                    f"ROI {name!r} for sub-{sid}",
                    str(path),
                    f"Save this ROI for sub-{sid} first (Optimizer page, ROI list); "
                    f"ROI CSVs live in {pm.rois(sid)}.",
                )
            )
    for i, entry in enumerate(config.get("roi_atlas") or []):
        if isinstance(entry, dict):
            missing.extend(
                _subject_atlas_files(pm, sid, entry, f"roi_atlas[{i}] atlas/mask file")
            )
    sym = config.get("symmetry_eeg_csv")
    if isinstance(sym, str) and sym and not Path(sym).is_file():
        missing.append(
            MissingInput(
                "symmetry EEG net CSV",
                sym,
                "Point symmetry_eeg_csv at an existing net CSV, or unset it so the "
                "leadfield's own net is used.",
            )
        )
    return missing


# -- leadfield -------------------------------------------------------------------------------


def _check_leadfield(pm: PathManager, config: dict[str, Any]) -> list[MissingInput]:
    sid = config.get("subject_id")
    if not isinstance(sid, str) or not sid:
        return []
    missing = _head_model(pm, sid)
    if missing:
        return missing  # everything else lives under the head model
    net = config.get("eeg_net", "GSN-HydroCel-185")
    if isinstance(net, str) and net:
        # tit.opt.leadfield.LeadfieldGenerator: eeg_positions/<cap>.csv (name without .csv).
        csv_path = Path(pm.eeg_positions(sid)) / f"{net}.csv"
        if not csv_path.is_file():
            missing.append(_eeg_net_missing(pm, sid, csv_path, f"EEG net {net!r}"))
        else:
            missing.extend(_collapsed_net(sid, csv_path))
    return missing


# -- analyzer --------------------------------------------------------------------------------


def _check_analyzer(pm: PathManager, config: dict[str, Any]) -> list[MissingInput]:
    sim = config.get("simulation")
    if not isinstance(sim, str) or not sim:
        return []
    space = config.get("space", "mesh")
    analysis_type = config.get("analysis_type", "spherical")
    missing: list[MissingInput] = []
    for sid in _subject_ids(config):
        head = _head_model(pm, sid)
        if head:
            missing.extend(head)
            continue
        missing.extend(_analyzer_field(pm, sid, sim, space, config))
        if analysis_type == "cortical":
            missing.extend(_analyzer_atlas(pm, sid, space, config))
        elif analysis_type == "subcortical" and not _mni_atlas_space(config):
            missing.extend(_analyzer_subject_volume_atlas(pm, sid, config))
    if analysis_type == "subcortical" and _mni_atlas_space(config):
        missing.extend(_analyzer_mni_atlas(config))
    if analysis_type == "mask":
        mask = config.get("mask_path")
        if isinstance(mask, str) and mask and not Path(mask).is_file():
            missing.append(
                MissingInput(
                    "mask NIfTI",
                    mask,
                    "Import the mask through the NIfTI mask picker, or use a path that "
                    "exists inside the container.",
                )
            )
    return missing


def _analyzer_field(
    pm: PathManager, sid: str, sim: str, space: str, config: dict[str, Any]
) -> list[MissingInput]:
    """The field file the analyzer would open, resolved by the analyzer's own selector.

    The analysed field (or, in voxel space, a NIfTI the selector finds -- an older or renamed
    one included) the simulation did not save is not missing when the job can produce it from
    the channel meshes (:func:`tit.volume_fields.check_producible`); when it cannot, that is
    the finding. Carrier fields are not checked: an analysis without them still runs, with
    the reason in ``carrier_note``.
    """
    from tit import constants as const
    from tit.analyzer.analyzer import Analyzer
    from tit.analyzer.field_selector import (
        default_field,
        is_mti_simulation,
        select_field_file,
    )
    from tit.volume_fields import (
        FieldUnavailableError,
        check_producible,
        check_surface_producible,
    )

    sim_dir = Path(pm.simulation(sid, sim))
    if not sim_dir.is_dir():
        return [
            MissingInput(
                f"simulation {sim!r} for sub-{sid}",
                str(sim_dir),
                _simulation_fix(sid, sim),
            )
        ]
    is_mti = is_mti_simulation(sid, sim)
    volume_mesh = (
        pm.ti_mesh(sid, sim)
        if not is_mti
        else str(Path(pm.mti_mesh_dir(sid, sim)) / f"{sim}_mTI.msh")
    )
    field = config.get("field") or default_field(sid, sim)
    if space == "voxel":
        # The selector first: a NIfTI it finds is analysed as it is (an older or renamed one
        # too). Carriers that cannot be produced only empty the carrier metrics.
        try:
            select_field_file(
                sid,
                sim,
                "voxel",
                tissue_type=config.get("tissue_type") or "GM",
                field=config.get("field"),  # None keeps an older run's unsuffixed NIfTI
            )
            return []
        except FileNotFoundError:
            pass
        except (ValueError, KeyError):
            return []  # an invalid field/space is a config error, not a missing input
    analysed = Analyzer.volume_fields_read(space, field)[:1]
    if field == const.FIELD_TI_NORMAL:
        analysed = []
    if analysed:
        try:
            check_producible(sid, sim, analysed)
        except FieldUnavailableError as exc:
            return [
                MissingInput(
                    f"field {analysed[0]} for sub-{sid} / {sim}", volume_mesh, str(exc)
                )
            ]
        except ValueError:
            return []  # an invalid field is a config error, not a missing input
        if space == "voxel":
            return []  # its NIfTI is written from the field mesh
    if space == "mesh":
        # Mesh analyses are measured on the central surface; the analysis writes it (or an old
        # run's TI_normal) from the field mesh when it is missing or incomplete.
        try:
            check_surface_producible(sid, sim)
        except FieldUnavailableError as exc:
            surface = (
                pm.mti_central_surface(sid, sim)
                if is_mti
                else pm.ti_central_surface(sid, sim)
            )
            return [
                MissingInput(
                    f"central (grey-matter) surface for sub-{sid} / {sim}",
                    surface,
                    str(exc),
                )
            ]
        return []
    try:
        select_field_file(
            sid,
            sim,
            space,
            tissue_type=config.get("tissue_type") or "GM",
            field=field,
        )
    except FileNotFoundError as exc:
        return [
            MissingInput(
                f"field mesh for sub-{sid} / {sim}",
                volume_mesh,
                f"{exc} Re-run the {sim} simulation for sub-{sid}.",
            )
        ]
    except (ValueError, KeyError):
        return []  # an invalid field/space is a config error, not a missing input
    return []


def _analyzer_atlas(
    pm: PathManager, sid: str, space: str, config: dict[str, Any]
) -> list[MissingInput]:
    atlas = config.get("atlas")
    if not isinstance(atlas, str) or not atlas:
        return []
    if Path(atlas).is_file():
        return []
    if space == "voxel":
        # Same search as Analyzer._resolve_voxel_atlas (imported, not restated).
        from tit.analyzer.analyzer import Analyzer

        fs_mri = Path(pm.fastsurfer_mri(sid))
        legacy_mri = Path(pm.freesurfer_mri(sid))
        seg_dir = Path(pm.segmentation(sid))
        found = next(
            (p for p in Analyzer.voxel_atlas_candidates(pm, sid, atlas) if p.exists()),
            None,
        )
        if found is not None:
            return [
                MissingInput(
                    f"region {name!r} in the {found.name} volume of atlas {atlas!r}",
                    str(found),
                    f"{atlas}'s DKT volume parcellation has no {name!r} (the DKT protocol "
                    "dropped it); analyze this region in mesh space, or pick another.",
                )
                for name in Analyzer.surface_regions_without_volume(
                    atlas, _as_list(config.get("region"))
                )
            ]
        volumes = Analyzer._SURFACE_ATLAS_VOLUMES.get(atlas)
        if volumes is not None:
            return [
                MissingInput(
                    f"volume parcellation for atlas {atlas!r} of sub-{sid}",
                    str(fs_mri / volumes[0]),
                    f"Run FastSurfer (or recon-all) for sub-{sid} (Preprocess page), "
                    "or analyze in mesh space instead -- the surface atlas needs no "
                    "volume parcellation.",
                )
            ]
        return [
            MissingInput(
                f"voxel atlas {atlas!r} for sub-{sid}",
                str(fs_mri / atlas),
                f"Run FastSurfer/recon-all for sub-{sid}, place {atlas} in one of "
                f"{fs_mri}, {legacy_mri}, {seg_dir}, or pass the atlas as a full path.",
            )
        ]
    # mesh: the SimNIBS built-ins come from the m2m itself; anything else is an .annot pair.
    from tit.atlas.constants import BUILTIN_ATLASES
    from tit.atlas.mesh import MeshAtlasManager

    if atlas in BUILTIN_ATLASES:
        return []
    manager = MeshAtlasManager(pm.segmentation(sid))
    if any(manager.find_atlas_file(atlas, hemi) for hemi in ("lh", "rh")):
        return []
    return [
        MissingInput(
            f"surface atlas {atlas!r} (.annot) for sub-{sid}",
            os.path.join(pm.segmentation(sid), f"lh.{atlas}.annot"),
            f"Use one of the built-in atlases ({', '.join(BUILTIN_ATLASES)}) or place "
            f"lh./rh.<name>.annot files in {pm.segmentation(sid)}.",
        )
    ]


def _mni_atlas_space(config: dict[str, Any]) -> bool:
    return str(config.get("coordinate_space") or "subject").lower() == "mni"


def _region_names(config: dict[str, Any]) -> list[str]:
    """The named (non-numeric) regions of the target; label numbers need the volume itself."""
    return [
        r.strip()
        for r in _as_list(config.get("region"))
        if isinstance(r, str) and r.strip() and not r.strip().isdigit()
    ]


def _unknown_regions(
    atlas_path: Path, atlas: str, regions: list[str]
) -> list[MissingInput]:
    """Regions no name in the atlas's lookup table matches (the runner's own matching rule)."""
    from tit.analyzer.analyzer import Analyzer
    from tit.atlas.segstats import resolve_lut_for_atlas

    lut = resolve_lut_for_atlas(str(atlas_path)) if regions else {}
    if not lut:
        return []  # no table to check against: the runner reads the volume itself
    labels = sorted(lut.items())
    return [
        MissingInput(
            f"region {name!r} in atlas {atlas!r}",
            str(atlas_path),
            f"No label of {atlas} is named {name!r}; pick a region from the atlas's own "
            "list (the target picker), or give its label number.",
        )
        for name in regions
        if Analyzer.match_region_label(name, labels) is None
    ]


def _analyzer_subject_volume_atlas(
    pm: PathManager, sid: str, config: dict[str, Any]
) -> list[MissingInput]:
    """A subject-space subcortical atlas, found where Analyzer._resolve_voxel_atlas looks."""
    from tit.analyzer.analyzer import Analyzer

    atlas = config.get("atlas")
    if not isinstance(atlas, str) or not atlas:
        return []
    if Path(atlas).is_file():
        return _unknown_regions(Path(atlas), atlas, _region_names(config))
    candidates = Analyzer.voxel_atlas_candidates(pm, sid, atlas)
    found = next((p for p in candidates if p.exists()), None)
    if found is not None:
        return _unknown_regions(found, atlas, _region_names(config))
    if atlas == Path(pm.tissue_labeling(sid)).name:
        # charm's own segmentation output, not a FreeSurfer volume
        return [
            MissingInput(
                f"atlas {atlas!r} (charm segmentation) for sub-{sid}",
                pm.tissue_labeling(sid),
                f"Re-run preprocessing (SimNIBS charm) for sub-{sid}: its segmentation "
                f"writes {atlas}. Or pick a FreeSurfer/FastSurfer volume atlas, or an "
                "MNI atlas.",
            )
        ]
    return [
        MissingInput(
            f"volume atlas {atlas!r} for sub-{sid}",
            str(candidates[0]),
            f"Run FastSurfer (or recon-all) for sub-{sid} (Preprocess page), place "
            f"{atlas} in {candidates[0].parent} or {pm.segmentation(sid)}, or pass the "
            "atlas as a full path.",
        )
    ]


def _analyzer_mni_atlas(config: dict[str, Any]) -> list[MissingInput]:
    """A shipped MNI atlas id (or MNI atlas file), resolved by Analyzer._resolve_mni_atlas."""
    from tit.analyzer.analyzer import Analyzer

    atlas = config.get("atlas")
    if not isinstance(atlas, str) or not atlas:
        return []
    try:
        path = Analyzer._resolve_mni_atlas(atlas)
    except (FileNotFoundError, ValueError) as exc:
        return [
            MissingInput(
                f"MNI atlas {atlas!r}",
                atlas,
                f"{exc}. Pick one of the MNI atlases the target picker lists, or a file "
                "path inside the project.",
            )
        ]
    return _unknown_regions(path, atlas, _region_names(config))


# -- source ----------------------------------------------------------------------------------


def _check_source(pm: PathManager, config: dict[str, Any]) -> list[MissingInput]:
    from tit.volume_fields import FieldUnavailableError, check_surface_producible

    missing: list[MissingInput] = []
    if config.get("mode", "forward") == "forward":
        forward = config.get("forward") or {}
        net = (
            forward.get("eeg_net", "GSN-HydroCel-185")
            if isinstance(forward, dict)
            else None
        )
        for sid in _subject_ids(config):
            head = _head_model(pm, sid)
            missing.extend(head)
            if not head and isinstance(net, str) and net:
                # tit.source.forward._read_simnibs_montage: m2m/eeg_positions/<net>.csv
                csv_path = Path(pm.eeg_positions(sid)) / f"{net}.csv"
                if not csv_path.is_file():
                    missing.append(
                        _eeg_net_missing(pm, sid, csv_path, f"EEG net {net!r}")
                    )
        return missing
    for pair in config.get("pairs") or []:
        if not isinstance(pair, dict):
            continue
        sid, sim = pair.get("subject_id"), pair.get("simulation")
        if not (isinstance(sid, str) and isinstance(sim, str) and sid and sim):
            continue
        head = _head_model(pm, sid)
        if head:
            missing.extend(head)
            continue
        if not Path(pm.simulation(sid, sim)).is_dir():
            missing.append(
                MissingInput(
                    f"central surface for sub-{sid} / {sim}",
                    pm.ti_central_surface(sid, sim),
                    _simulation_fix(sid, sim),
                )
            )
            continue
        try:  # the projection writes an incomplete surface (an old run's) from the field mesh
            check_surface_producible(sid, sim)
        except FieldUnavailableError as exc:
            missing.append(
                MissingInput(
                    f"central surface for sub-{sid} / {sim}",
                    pm.ti_central_surface(sid, sim),
                    str(exc),
                )
            )
    return missing


# -- pre -------------------------------------------------------------------------------------


def _check_pre(pm: PathManager, config: dict[str, Any]) -> list[MissingInput]:
    from tit.pre.preflight import find_missing_preprocessing_inputs

    problems = find_missing_preprocessing_inputs(
        pm.project_dir,
        _subject_ids(config),
        convert_dicom=bool(config.get("convert_dicom", False)),
        create_m2m=bool(config.get("create_m2m", False)),
        run_fastsurfer=bool(config.get("run_fastsurfer", False)),
        run_freesurfer=bool(config.get("run_freesurfer", False)),
        freesurfer_recon_all=bool(config.get("freesurfer_recon_all", True)),
        freesurfer_subregions=config.get("freesurfer_subregions") or [],
        run_tissue_analysis=bool(config.get("run_tissue_analysis", False)),
        run_qsiprep=bool(config.get("run_qsiprep", False)),
        run_qsirecon=bool(config.get("run_qsirecon", False)),
        extract_dti=bool(config.get("extract_dti", False)),
        skip_existing_outputs=bool(config.get("skip_existing_outputs", False)),
        qsiprep_config=config.get("qsiprep_config"),
        qsi_recon_config=config.get("qsi_recon_config"),
    )
    return [
        MissingInput(
            what=(
                f"{p.label} input for sub-{p.subject_id}"
                if p.subject_id and p.label != "FreeSurfer license"
                else p.label
            ),
            expected_path=str(p.path),
            how_to_fix=p.message,
        )
        for p in problems
    ]


# -- group tools: stats / nifti_average / nilearn --------------------------------------------


def _check_stats(pm: PathManager, config: dict[str, Any]) -> list[MissingInput]:
    from tit.stats.config import _nifti_pattern_for_tissue, _TissueType

    missing: list[MissingInput] = []
    if config.get("space", "mni") == "fsaverage":
        spacing = config.get("fsaverage_spacing", 5)
        for entry in config.get("subjects") or []:
            if not isinstance(entry, dict):
                continue
            sid, sim = entry.get("subject_id"), entry.get("simulation_name")
            if not (isinstance(sid, str) and isinstance(sim, str)):
                continue
            msh = Path(pm.sim_fsaverage_fields(sid, sim, spacing))
            if not msh.is_file():
                missing.append(
                    MissingInput(
                        f"fsaverage projection for sub-{sid} / {sim}",
                        str(msh),
                        f"Re-run the fsaverage projection for sub-{sid} / {sim}: "
                        "simulate it again with the Simulator's 'Map fields to "
                        "fsaverage' on, or map its existing outputs with "
                        "tit.source.fsaverage.project_fields_to_fsaverage.",
                    )
                )
        return missing
    pattern = config.get("nifti_file_pattern")
    if not isinstance(pattern, str) or not pattern:
        try:
            pattern = _nifti_pattern_for_tissue(
                _TissueType(config.get("tissue_type", "grey"))
            )
        except ValueError:
            return []
    return _check_nifti_subjects(pm, config.get("subjects"), pattern)


def _check_nifti_subjects(
    pm: PathManager, subjects: Any, pattern: str
) -> list[MissingInput]:
    missing: list[MissingInput] = []
    for entry in subjects or []:
        if not isinstance(entry, dict):
            continue
        sid, sim = entry.get("subject_id"), entry.get("simulation_name")
        if not (isinstance(sid, str) and isinstance(sim, str) and sid and sim):
            continue
        try:
            missing.extend(_sim_nifti(pm, sid, sim, pattern))
        except (KeyError, IndexError, ValueError):
            return []
    return missing


def _check_nifti_average(pm: PathManager, config: dict[str, Any]) -> list[MissingInput]:
    from tit.stats.nifti_average_config import _DEFAULT_PATTERNS, NiftiAverageSpace

    pattern = config.get("nifti_file_pattern")
    if not isinstance(pattern, str) or not pattern:
        try:
            pattern = _DEFAULT_PATTERNS[NiftiAverageSpace(config.get("space", "mni"))]
        except (ValueError, KeyError):
            return []
    return _check_nifti_subjects(pm, config.get("subjects"), pattern)


def _check_nilearn(pm: PathManager, config: dict[str, Any]) -> list[MissingInput]:
    from tit.plotting.nilearn.__main__ import _NIFTI_FILE_PATTERN

    return _check_nifti_subjects(
        pm, config.get("subject_simulation_pairs"), _NIFTI_FILE_PATTERN
    )


# -- blender ---------------------------------------------------------------------------------


def _check_blender(pm: PathManager, config: dict[str, Any]) -> list[MissingInput]:
    """The files the ``_type``'s exporter opens, resolved by the exporters' own helpers.

    :mod:`tit.blender.config`'s ``central_surface_path`` / ``carrier_mesh_paths`` are what
    the region, vector and montage runners read (an mTI run's own surface and lettered
    carriers), so this check and the runner name the same file.
    """
    sid = config.get("subject_id")
    if not isinstance(sid, str) or not sid:
        return []
    missing = _head_model(pm, sid)
    if missing:
        return missing  # everything else lives under the head model
    mode = config.get(
        "_type"
    )  # tit.blender.__main__ dispatches on it; None runs nothing
    sim = config.get("simulation_name")
    sim = sim.strip() if isinstance(sim, str) else ""
    if sim and not Path(pm.simulation(sid, sim)).is_dir():
        return [
            MissingInput(
                f"simulation {sim!r} for sub-{sid}",
                pm.simulation(sid, sim),
                _simulation_fix(sid, sim),
            )
        ]
    nifti = config.get("nifti_path")
    nifti = nifti.strip() if isinstance(nifti, str) else ""
    if mode == "SubcorticalConfig" and not nifti:
        # run_subcortical's default volume.
        nifti = os.path.join(pm.m2m(sid), "segmentation", "labeling.nii.gz")
        if not Path(nifti).is_file():
            missing.append(
                MissingInput("subcortical NIfTI", nifti, _preprocess_fix(sid))
            )
    elif nifti and not Path(nifti).is_file():
        missing.append(
            MissingInput(
                "subcortical NIfTI", nifti, "Point nifti_path at an existing file."
            )
        )
    if sim and mode in ("RegionConfig", "VectorConfig", "MontageConfig"):
        missing.extend(_blender_simulation_inputs(pm, sid, sim, mode))
    if sim and mode == "SubcorticalConfig":
        missing.extend(_blender_field_nifti(sid, sim, config.get("field_name")))
    return missing


def _blender_field_nifti(sid: str, sim: str, field: Any) -> list[MissingInput]:
    """The whole-head field NIfTI that colours a sub-cortical PLY: saved, or producible."""
    from tit.blender.subcortical_exporter import field_nifti_path
    from tit.volume_fields import FieldUnavailableError, check_nifti_producible

    path = field_nifti_path(
        sid, sim, field if isinstance(field, str) and field else "TI_max"
    )
    if Path(path).is_file():
        return []
    try:
        check_nifti_producible(sid, sim, path)
    except FieldUnavailableError as exc:
        return [MissingInput(f"field NIfTI for sub-{sid} / {sim}", path, str(exc))]
    return []


def _blender_simulation_inputs(
    pm: PathManager, sid: str, sim: str, mode: str
) -> list[MissingInput]:
    """What a region / vector / montage export reads from the simulation itself."""
    from tit.blender.config import (
        carrier_mesh_paths,
        central_surface_path,
        scalp_source_mesh,
    )

    found: list[MissingInput] = []
    rerun = _simulation_fix(sid, sim)
    record_path = Path(pm.simulation(sid, sim)) / "documentation" / "config.json"
    record: dict[str, Any] | None = None
    if mode in ("VectorConfig", "MontageConfig"):
        try:
            record = json.loads(record_path.read_text())
        except (OSError, ValueError):
            found.append(
                MissingInput(
                    f"simulation record (config.json) of {sim!r}",
                    str(record_path),
                    rerun,
                )
            )
    if mode == "MontageConfig" and isinstance(record, dict):
        net = record.get("eeg_net")
        if not isinstance(net, str) or not net.strip():
            found.append(
                MissingInput(
                    "This simulation has no recorded EEG net. Its electrodes were "
                    "placed by coordinates, and the montage scene places a net's "
                    "electrodes",
                    str(record_path),
                    "Export this simulation as cortical regions or field vectors, or "
                    "visualise a simulation run on an EEG net.",
                )
            )
        else:
            csv_path = Path(pm.eeg_positions(sid)) / net
            if not csv_path.is_file():
                found.append(_eeg_net_missing(pm, sid, csv_path, f"EEG net {net!r}"))
            else:
                found.extend(_collapsed_net(sid, csv_path))
    if mode == "MontageConfig":
        ti_mesh = pm.ti_mesh(sid, sim)
        if scalp_source_mesh(ti_mesh, pm.simulation(sid, sim)) is None:
            found.append(
                MissingInput(
                    f"volume mesh of {sim!r} to cut the montage's scalp from (its TI "
                    "mesh, or any high_Frequency/mesh/*.msh)",
                    ti_mesh,
                    rerun,
                )
            )
    if mode == "VectorConfig" and isinstance(record, dict):
        cond = record.get("conductivity")
        if not isinstance(cond, str) or not cond:
            found.append(
                MissingInput(
                    f"conductivity recorded in {sim!r}'s config.json",
                    str(record_path),
                    rerun,
                )
            )
        else:
            for path in carrier_mesh_paths(sid, sim, cond):
                if not Path(path).is_file():
                    found.append(
                        MissingInput(f"carrier field mesh of {sim!r}", path, rerun)
                    )
    surface = central_surface_path(sid, sim)
    if not Path(surface).is_file():
        found.append(
            MissingInput(f"central cortical surface of {sim!r}", surface, rerun)
        )
    return found


_CHECKERS: dict[str, Checker] = {
    "sim": _check_sim,
    "flex": _check_flex,
    "flex_adaptive": _check_flex,
    "flex_pareto": _check_flex,
    "ex": _check_ex,
    "mex": _check_ex,
    "leadfield": _check_leadfield,
    "analyzer": _check_analyzer,
    "source": _check_source,
    "pre": _check_pre,
    "stats": _check_stats,
    "nifti_average": _check_nifti_average,
    "nilearn": _check_nilearn,
    "blender": _check_blender,
    # project_init creates the tree; tools' arguments are
    # already jailed to the project by tit.jobs.kinds.check_tool_args.
}
