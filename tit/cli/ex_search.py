#!/usr/bin/env simnibs_python
"""
TI-Toolbox Ex-Search CLI.

Thin wrapper around `tit.opt.ex.main.main()` which is env-driven.

- Interactive default (no args)
- Direct mode via flags
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from tit.cli.base import ArgumentDefinition, BaseCLI
from tit.cli import utils
from tit.core import get_path_manager

_ELECTRODE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")


def _parse_electrode_list(raw: Any) -> List[str]:
    """
    Accept either:
    - a comma-separated string: "C3,C4,Fz,Cz"
    - a list of tokens: ["C3", "C4", "Fz", "Cz"]
    - a mixed list: ["C3,C4", "Fz", "Cz"]
    """
    tokens: List[str] = []
    if raw is None:
        tokens = []
    elif isinstance(raw, (list, tuple)):
        for t in raw:
            tokens.extend([x.strip() for x in str(t).split(",") if x.strip()])
    else:
        tokens = [x.strip() for x in str(raw).split(",") if x.strip()]
    return list(dict.fromkeys(tokens))  # stable-unique


def _derive_eeg_net_stem_from_leadfield(leadfield_hdf: str) -> Optional[str]:
    """
    Derive EEG net stem from leadfield filename.

    Expected pattern:
      {subject}_leadfield_{net}.hdf5 -> {net}
    """
    name = Path(leadfield_hdf).name
    for ext in (".hdf5", ".h5"):
        if name.endswith(ext):
            name = name[: -len(ext)]
            break
    if "_leadfield_" not in name:
        return None
    _, _, net = name.partition("_leadfield_")
    net = net.strip()
    return net or None


def _resolve_leadfield_path(subject_id: str, leadfield_arg: str) -> Path:
    """
    Resolve a leadfield passed via --lf.

    Accepts:
    - an absolute/relative path to an existing file
    - a filename (with or without extension) that lives under the subject leadfields directory
    """
    if not leadfield_arg:
        raise RuntimeError("Missing leadfield. Use --lf <path-or-stem>.")

    p = Path(str(leadfield_arg))
    if p.is_file():
        return p

    # If user passed a bare name or a non-existent relative path, try subject leadfields dir.
    pm = get_path_manager()
    lf_dir = Path(pm.path("leadfields", subject_id=subject_id))
    if not lf_dir.is_dir():
        raise RuntimeError(
            f"Leadfields directory not found for subject {subject_id}: {lf_dir}"
        )

    name = Path(str(leadfield_arg)).name
    stem = Path(name).stem if name else ""

    candidates: List[Path] = []
    for cand in (lf_dir / name, lf_dir / f"{name}.hdf5", lf_dir / f"{name}.h5"):
        if cand.name and cand.is_file():
            candidates.append(cand)

    if stem:
        for cand in (lf_dir / f"{stem}.hdf5", lf_dir / f"{stem}.h5"):
            if cand.is_file():
                candidates.append(cand)

        # Fuzzy fallback: prefix match (handles users omitting subject prefix etc.)
        for ext in ("*.hdf5", "*.h5"):
            for f in lf_dir.glob(ext):
                if f.stem.lower() == stem.lower() or f.name.lower() == name.lower():
                    candidates.append(f)

    # De-dupe while preserving order
    uniq: List[Path] = []
    seen = set()
    for c in candidates:
        s = str(c)
        if s not in seen:
            seen.add(s)
            uniq.append(c)

    if len(uniq) == 1:
        return uniq[0]
    if len(uniq) > 1:
        opts = ", ".join(sorted({u.name for u in uniq}))
        raise RuntimeError(f"Ambiguous leadfield '{leadfield_arg}'. Matches: {opts}")

    available = sorted(
        [f.name for f in lf_dir.glob("*.hdf5")] + [f.name for f in lf_dir.glob("*.h5")]
    )
    hint = (
        f" Available leadfields: {', '.join(available)}"
        if available
        else " No leadfields found in that folder."
    )
    raise RuntimeError(
        f"Leadfield file not found: {leadfield_arg} (searched in {lf_dir}).{hint}"
    )


def _find_eeg_net_csv(
    subject_id: str, *, leadfield_hdf: str
) -> Tuple[Optional[str], Optional[Path]]:
    """
    The rule is simple:
    - EEG cap CSV files live under: m2m_<subject>/eeg_positions/*.csv
    - EEG cap name is derived from the leadfield filename

    Returns (net_stem, csv_path). If not found, csv_path=None.
    """
    net_stem = _derive_eeg_net_stem_from_leadfield(leadfield_hdf)
    if not net_stem:
        return None, None

    pm = get_path_manager()
    eeg_pos_dir_p = Path(pm.path("eeg_positions", subject_id=subject_id))
    if not eeg_pos_dir_p.is_dir():
        return net_stem, None

    direct = eeg_pos_dir_p / f"{net_stem}.csv"
    if direct.is_file():
        return net_stem, direct

    # Case-insensitive fallback
    target = f"{net_stem}.csv".lower()
    for p in eeg_pos_dir_p.glob("*.csv"):
        if p.name.lower() == target or p.stem.lower() == net_stem.lower():
            return net_stem, p

    return net_stem, None


def _load_eeg_labels(csv_path: Path) -> List[str]:
    """
    Load electrode labels from an EEG cap CSV.
    Prefer SimNIBS reader when available; fall back to our CSV loader.
    """
    if not csv_path.is_file():
        return []

    try:
        from simnibs.utils.csv_reader import read_csv_positions as simnibs_read_csv  # type: ignore[import-not-found]

        type_, _coords, _extra, name, _extra_cols, _header = simnibs_read_csv(
            str(csv_path)
        )
        labels: List[str] = []
        for t, n in zip(type_, name):
            if t in ["Electrode", "ReferenceElectrode"] and n:
                labels.append(str(n).strip())
        labels = [x for x in labels if x]
        return list(dict.fromkeys(labels))
    except Exception:
        return utils.load_eeg_cap_labels(csv_path)


def _validate_electrode_names(
    *, specified: Iterable[str], available: List[str]
) -> None:
    bad_format = sorted({e for e in specified if not _ELECTRODE_RE.match(e)})
    if bad_format:
        raise ValueError(f"Invalid electrode names (format): {', '.join(bad_format)}")

    if not available:
        return

    available_set = set(available)
    invalid = sorted(set(specified) - available_set)
    if invalid:
        raise ValueError(f"Electrodes not found in EEG net: {', '.join(invalid)}")


class ExSearchCLI(BaseCLI):
    def __init__(self) -> None:
        super().__init__("Run exhaustive search optimization (env-driven core).")

        self.add_argument(
            ArgumentDefinition(
                name="subject", type=str, help="Subject ID", required=True
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="leadfield_hdf",
                type=str,
                help="Leadfield file (path or stem under subject leadfields; .hdf5/.h5)",
                required=True,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="roi_name",
                type=str,
                help="ROI name (with or without .csv)",
                required=True,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="roi_radius", type=float, help="ROI radius (mm)", default=3.0
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="optimization_mode",
                type=str,
                help="Optimization mode: 'buckets' or 'pool'",
                choices=["buckets", "pool"],
                required=False,
                default=None,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="pool",
                type=bool,
                help="Shorthand for --optimization-mode pool",
                default=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="buckets",
                type=bool,
                help="Shorthand for --optimization-mode buckets",
                default=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="e1_plus",
                type=str,
                nargs="+",
                help="E1+ electrodes (comma-separated or space-separated)",
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="e1_minus",
                type=str,
                nargs="+",
                help="E1- electrodes (comma-separated or space-separated)",
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="e2_plus",
                type=str,
                nargs="+",
                help="E2+ electrodes (comma-separated or space-separated)",
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="e2_minus",
                type=str,
                nargs="+",
                help="E2- electrodes (comma-separated or space-separated)",
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="pool_electrodes",
                type=str,
                nargs="+",
                help="All electrodes (comma-separated or space-separated, min 4)",
                required=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="total_current", type=float, help="Total current (mA)", default=1.0
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="current_step", type=float, help="Current step (mA)", default=0.1
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="channel_limit",
                type=float,
                help="Optional per-channel limit (mA)",
                required=False,
            )
        )

    def run_interactive(self) -> int:
        pm = get_path_manager()
        if not pm.project_dir:
            raise RuntimeError(
                "Project directory not resolved. In Docker set PROJECT_DIR_NAME so /mnt/<name> exists."
            )

        utils.echo_header("Ex-Search (interactive)")

        # Select subject
        subject_id = self.select_one(
            prompt_text="Select subject",
            options=pm.list_subjects(),
            help_text="Choose from available subjects in your project",
        )

        # Select leadfield (no EEG cap selection)
        lf_dir = pm.path("leadfields", subject_id=subject_id)
        lf_files: List[str] = []
        if lf_dir and Path(lf_dir).is_dir():
            lf_files = sorted([p.name for p in Path(lf_dir).glob("*.hdf5")])
        if not lf_files:
            utils.echo_error("No leadfield files found for this subject")
            return 1
        leadfield_hdf = str(
            Path(lf_dir)
            / self.select_one(
                prompt_text="Select leadfield",
                options=lf_files,
                help_text="Available leadfield files",
            )
        )

        # Select or create ROI
        roi_name = self._select_or_create_roi(subject_id)

        # Select optimization mode
        optimization_mode = self.select_one(
            prompt_text="Select optimization mode",
            options=["buckets", "pool"],
            help_text="'buckets': separate electrode groups for each position\n'pool': all electrodes available for any position",
        )

        # Get electrodes based on mode (validate against EEG net CSV if available)
        electrode_args = self._prompt_electrodes(
            subject_id, leadfield_hdf, optimization_mode
        )

        # Get ROI radius
        roi_radius = utils.ask_float("ROI radius (mm)", default="3.0")

        # Get current parameters
        total_current = utils.ask_float("Total current (mA)", default="1.0")
        current_step = utils.ask_float("Current step (mA)", default="0.1")
        channel_limit_raw = utils.ask("Channel limit (mA) (empty for none)", default="")
        channel_limit = float(channel_limit_raw) if channel_limit_raw else None

        net_stem, csv_path = _find_eeg_net_csv(subject_id, leadfield_hdf=leadfield_hdf)
        review_items = [
            ("Subject", subject_id),
            ("Leadfield", Path(leadfield_hdf).name),
            ("ROI", roi_name),
            ("ROI radius (mm)", str(roi_radius)),
            ("Optimization mode", optimization_mode),
            ("EEG net (derived)", net_stem or "-"),
            ("EEG net CSV", str(csv_path) if csv_path else "-"),
            ("Total current (mA)", str(total_current)),
            ("Current step (mA)", str(current_step)),
            (
                "Channel limit (mA)",
                str(channel_limit) if channel_limit is not None else "-",
            ),
        ]
        if optimization_mode == "pool":
            review_items.insert(
                5, ("Electrode pool", electrode_args["pool_electrodes"])
            )
        else:
            review_items.insert(
                5,
                (
                    "E1+/E1-/E2+/E2-",
                    f"{electrode_args['e1_plus']} | {electrode_args['e1_minus']} | {electrode_args['e2_plus']} | {electrode_args['e2_minus']}",
                ),
            )

        if not utils.review_and_confirm(
            "Review (ex-search)", items=review_items, default_yes=True
        ):
            utils.echo_warning("Cancelled.")
            return 0

        args: Dict[str, Any] = dict(
            subject=subject_id,
            leadfield_hdf=leadfield_hdf,
            roi_name=roi_name,
            roi_radius=roi_radius,
            optimization_mode=optimization_mode,
            total_current=total_current,
            current_step=current_step,
            channel_limit=channel_limit,
            **electrode_args,
        )
        return self.execute(args)

    def _select_or_create_roi(self, subject_id: str) -> str:
        """Select an existing ROI or create a new one."""
        # Lazy import: ex-search backend pulls SimNIBS; keep CLI import-light so `--help` works everywhere.
        from tit.opt.ex import get_available_rois

        while True:
            existing = get_available_rois(subject_id)
            roi_stems = (
                sorted([x.replace(".csv", "") for x in existing]) if existing else []
            )
            options = roi_stems + ["[Create new ROI...]"]
            choice = self.select_one(
                prompt_text="ROI",
                options=options,
                help_text="Choose an existing ROI or create a new ROI.",
            )
            if choice == "[Create new ROI...]":
                self._create_roi_from_coordinates(subject_id)
                continue
            return f"{choice}.csv"

    def _create_roi_from_coordinates(self, subject_id: str) -> Optional[str]:
        """Create an ROI from custom coordinates."""
        # Lazy import: ex-search backend pulls SimNIBS; keep CLI import-light so `--help` works everywhere.
        from tit.opt.ex import create_roi_from_coordinates

        roi_name = utils.ask_required("ROI name (without .csv extension)")

        utils.echo_info("Enter coordinates in subject space (RAS coordinates in mm)")
        x = utils.ask_float("X coordinate")
        y = utils.ask_float("Y coordinate")
        z = utils.ask_float("Z coordinate")

        success, message = create_roi_from_coordinates(subject_id, roi_name, x, y, z)
        if success:
            utils.echo_success(message)
            return roi_name
        else:
            utils.echo_error(message)
            return None

    def _prompt_electrodes(
        self, subject_id: str, leadfield_hdf: str, mode: str
    ) -> Dict[str, Any]:
        net_stem, csv_path = _find_eeg_net_csv(subject_id, leadfield_hdf=leadfield_hdf)
        available_labels: List[str] = _load_eeg_labels(csv_path) if csv_path else []
        if net_stem and not csv_path:
            eeg_dir = get_path_manager().path("eeg_positions", subject_id=subject_id)
            utils.echo_warning(
                f"EEG net CSV not found: {net_stem}.csv (expected under {eeg_dir}) - electrode validation skipped"
            )

        if mode == "pool":
            utils.echo_info("Pool mode: all electrodes available for any position")
            while True:
                raw = utils.ask_required("All electrodes (comma-separated, minimum 4)")
                pool = _parse_electrode_list(raw)
                if len(pool) < 4:
                    utils.echo_error("At least 4 electrodes are required for pool mode")
                    continue
                try:
                    _validate_electrode_names(
                        specified=pool, available=available_labels
                    )
                except ValueError as e:
                    utils.echo_error(str(e))
                    if available_labels:
                        utils.echo_info(
                            f"Available electrodes: {', '.join(sorted(available_labels))}"
                        )
                    continue
                return dict(pool_electrodes=", ".join(pool))

        utils.echo_info("Buckets mode: separate electrode groups for each position")
        while True:
            e1p = _parse_electrode_list(
                utils.ask_required("E1_PLUS electrodes (comma-separated)")
            )
            e1m = _parse_electrode_list(
                utils.ask_required("E1_MINUS electrodes (comma-separated)")
            )
            e2p = _parse_electrode_list(
                utils.ask_required("E2_PLUS electrodes (comma-separated)")
            )
            e2m = _parse_electrode_list(
                utils.ask_required("E2_MINUS electrodes (comma-separated)")
            )
            if not (len(e1p) == len(e1m) == len(e2p) == len(e2m)):
                utils.echo_error(
                    "All electrode categories must have the same number of electrodes"
                )
                continue
            specified = list(dict.fromkeys([*e1p, *e1m, *e2p, *e2m]))
            try:
                _validate_electrode_names(
                    specified=specified, available=available_labels
                )
            except ValueError as e:
                utils.echo_error(str(e))
                if available_labels:
                    utils.echo_info(
                        f"Available electrodes: {', '.join(sorted(available_labels))}"
                    )
                continue
            return dict(
                e1_plus=", ".join(e1p),
                e1_minus=", ".join(e1m),
                e2_plus=", ".join(e2p),
                e2_minus=", ".join(e2m),
            )

    def execute(self, args: Dict[str, Any]) -> int:
        pm = get_path_manager()
        if not pm.project_dir:
            raise RuntimeError(
                "Project directory not resolved. In Docker set PROJECT_DIR_NAME so /mnt/<name> exists."
            )

        subject_id = str(args["subject"])
        leadfield_hdf = str(
            _resolve_leadfield_path(subject_id, str(args["leadfield_hdf"]))
        )

        net_stem, csv_path = _find_eeg_net_csv(subject_id, leadfield_hdf=leadfield_hdf)
        if not net_stem:
            utils.echo_warning(
                "Could not derive EEG net name from leadfield filename - electrode validation skipped"
            )
        elif not csv_path:
            eeg_dir = pm.path("eeg_positions", subject_id=subject_id)
            utils.echo_warning(
                f"EEG net CSV not found: {net_stem}.csv (expected under {eeg_dir}) - electrode validation skipped"
            )

        available_labels: List[str] = _load_eeg_labels(csv_path) if csv_path else []

        # Resolve optimization mode with ergonomic flags
        if args.get("pool") and args.get("buckets"):
            raise ValueError("Choose only one of --pool or --buckets")
        mode = args.get("optimization_mode")
        if not mode:
            if args.get("pool"):
                mode = "pool"
            elif args.get("buckets"):
                mode = "buckets"
        if mode not in ("pool", "buckets"):
            raise ValueError(
                "Missing optimization mode. Use --optimization-mode {pool,buckets} or the shorthand --pool/--buckets."
            )
        if mode == "pool":
            pool = _parse_electrode_list(args.get("pool_electrodes"))
            if len(pool) < 4:
                raise ValueError(
                    "Pool mode requires --pool-electrodes with at least 4 electrodes"
                )
            _validate_electrode_names(specified=pool, available=available_labels)
            pool_raw = ", ".join(pool)
        else:
            e1p = _parse_electrode_list(args.get("e1_plus"))
            e1m = _parse_electrode_list(args.get("e1_minus"))
            e2p = _parse_electrode_list(args.get("e2_plus"))
            e2m = _parse_electrode_list(args.get("e2_minus"))
            if not (e1p and e1m and e2p and e2m):
                raise ValueError(
                    "Buckets mode requires --e1-plus/--e1-minus/--e2-plus/--e2-minus"
                )
            if not (len(e1p) == len(e1m) == len(e2p) == len(e2m)):
                raise ValueError(
                    "Buckets mode requires all electrode lists to have the same length"
                )
            specified = list(dict.fromkeys([*e1p, *e1m, *e2p, *e2m]))
            _validate_electrode_names(specified=specified, available=available_labels)

        # Set env vars expected by tit.opt.ex.config + tit.opt.ex.main
        os.environ["PROJECT_DIR"] = pm.project_dir
        os.environ["SUBJECT_NAME"] = subject_id
        os.environ["SELECTED_EEG_NET"] = net_stem or "unknown_net"
        os.environ["ROI_NAME"] = str(args["roi_name"])
        os.environ["ROI_RADIUS"] = str(args.get("roi_radius", 3.0))
        os.environ["LEADFIELD_HDF"] = leadfield_hdf

        if mode == "pool":
            os.environ["E1_PLUS"] = pool_raw
            os.environ["E1_MINUS"] = pool_raw
            os.environ["E2_PLUS"] = pool_raw
            os.environ["E2_MINUS"] = pool_raw
            os.environ["ALL_COMBINATIONS"] = "true"
        else:
            os.environ.pop("ALL_COMBINATIONS", None)
            os.environ["E1_PLUS"] = ", ".join(e1p)
            os.environ["E1_MINUS"] = ", ".join(e1m)
            os.environ["E2_PLUS"] = ", ".join(e2p)
            os.environ["E2_MINUS"] = ", ".join(e2m)

        os.environ["TOTAL_CURRENT"] = str(args.get("total_current", 1.0))
        os.environ["CURRENT_STEP"] = str(args.get("current_step", 0.1))
        if args.get("channel_limit") is not None:
            os.environ["CHANNEL_LIMIT"] = str(args["channel_limit"])
        else:
            os.environ.pop("CHANNEL_LIMIT", None)

        from tit.opt.ex.main import main as ex_main

        ex_main()
        return 0


if __name__ == "__main__":
    raise SystemExit(ExSearchCLI().run())
