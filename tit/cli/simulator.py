#!/usr/bin/env simnibs_python
"""
TI-Toolbox Simulator CLI.

CLI orchestrator:
- Interactive: flex vs montage; U/M; montage discovery + optional creation; then run `tit.sim.run_simulation`
- Direct: flags for automation
"""

from __future__ import annotations

from typing import Any, Dict, List
from pathlib import Path
import json
import os
import logging
import sys
import inspect

from tit.cli.base import ArgumentDefinition, BaseCLI, InteractivePrompt
from tit.cli import utils
from tit.core import get_path_manager
from tit.core import constants as const


def _resolve_eeg_cap_filename(subject_id: str, eeg_net_arg: str) -> str:
    """
    Resolve an EEG cap argument to a canonical CSV filename in eeg_positions.

    Accepts either:
    - "GSN-HydroCel-185" (stem)
    - "GSN-HydroCel-185.csv" (filename)
    Performs case-insensitive match within the subject's eeg_positions directory.

    Returns the canonical filename (with .csv extension) if found; otherwise
    returns the original input (or input + ".csv") without raising.
    """
    pm = get_path_manager()
    raw = str(eeg_net_arg or "").strip()
    if not raw:
        return raw

    eeg_dir = Path(pm.path("eeg_positions", subject_id=str(subject_id)))
    if not eeg_dir.is_dir():
        return raw

    # Prefer explicit filename, but allow passing stem.
    candidates = [raw]
    if not raw.lower().endswith(".csv"):
        candidates.append(raw + ".csv")

    # Direct (case-sensitive) hit.
    for c in candidates:
        if (eeg_dir / c).is_file():
            return c

    # Case-insensitive hit.
    wanted = {c.lower() for c in candidates}
    for p in eeg_dir.glob("*.csv"):
        if p.name.lower() in wanted or p.stem.lower() in {Path(c).stem.lower() for c in candidates}:
            return p.name

    # Not found: return the most reasonable normalized name.
    return candidates[-1]


class SimulatorCLI(BaseCLI):
    def __init__(self) -> None:
        super().__init__("Run TI/mTI simulations (delegates to tit.sim.simulator).")

        self.add_argument(ArgumentDefinition(name="list_subjects", type=bool, help="List subjects", default=False))
        self.add_argument(ArgumentDefinition(name="list_eeg_caps", type=bool, help="List EEG caps for --subject", default=False))
        # Accept common singular typo too (--list-montage)
        self.add_argument(ArgumentDefinition(name="list_montages", type=bool, help="List montages for --eeg (and flex-search runs if --sub is provided)", default=False, flags=["--list-montages", "--list-montage"]))

        self.add_argument(ArgumentDefinition(name="subject", type=str, help="Subject ID", required=False, flags=["--subject", "--sub"]))
        self.add_argument(ArgumentDefinition(name="eeg_net", type=str, help="EEG cap CSV filename", default="GSN-HydroCel-185.csv", flags=["--eeg-net", "--eeg"]))
        self.add_argument(ArgumentDefinition(name="framework", type=str, choices=["montage", "flex"], default="montage"))
        # Ergonomic aliases that avoid argparse abbreviation confusion (BaseCLI sets allow_abbrev=False)
        self.add_argument(ArgumentDefinition(name="montage", type=bool, help="Shorthand for --framework montage", default=False))
        self.add_argument(ArgumentDefinition(name="flex", type=bool, help="Shorthand for --framework flex", default=False))
        self.add_argument(ArgumentDefinition(name="mode", type=str, choices=["U", "M"], default="U", help="U (TI) or M (mTI)"))
        self.add_argument(ArgumentDefinition(name="montages", type=str, nargs="+", help="One or more montage names (supports comma-separated values too).", required=False))
        self.add_argument(ArgumentDefinition(name="create_montage", type=bool, help="Create montage if missing (interactive-like)", default=False))

        self.add_argument(ArgumentDefinition(name="conductivity", type=str, choices=["scalar", "vn", "dir", "mc"], default="scalar"))
        self.add_argument(ArgumentDefinition(name="intensity", type=str, help="Intensity (mA). For mTI use format 'a,b,c,d' if supported.", default="2.0"))
        self.add_argument(ArgumentDefinition(name="electrode_shape", type=str, choices=["rect", "ellipse"], help="rect|ellipse", default="ellipse"))
        self.add_argument(ArgumentDefinition(name="dimensions", type=str, help="e.g. 8,8", default="8,8"))
        self.add_argument(ArgumentDefinition(name="thickness", type=float, help="mm", default=4.0))

    def run_interactive(self) -> int:
        pm = get_path_manager()

        utils.echo_header("Simulator (interactive)")
        subject_id = self.select_one(prompt_text="Select subject", options=pm.list_subjects(), help_text="Choose a subject")

        framework = self._prompt_for_value(
            InteractivePrompt(name="framework", prompt_text="Framework", choices=["montage", "flex"], default="montage", help_text="montage = predefined montage_list.json; flex = from flex-search outputs")
        )
        mode = "U"
        if framework == "montage":
            mode = self._prompt_for_value(
                InteractivePrompt(name="mode", prompt_text="Simulation mode", choices=["U", "M"], default="U", help_text="U = TI (2-pair), M = mTI (4-pair)")
            )
        eeg_net = ""

        montage_names: str = ""
        flex_use_mapped: bool = True
        flex_use_optimized: bool = True
        if framework == "montage":
            from tit.sim.montage_loader import list_montage_names
            from tit.sim import utils as sim_utils

            eeg_net = self.select_one(
                prompt_text="Select EEG cap",
                options=(pm.list_eeg_caps(subject_id) or [self._default_eeg_cap()]),
                help_text="Choose an EEG cap CSV filename",
            )

            available = list_montage_names(pm.project_dir, eeg_net, mode=mode) if pm.project_dir else []
            if not available:
                utils.echo_warning("No montages found for this EEG cap / mode.")
                if utils.ask_bool("Create a new montage now?", default=True):
                    name = utils.ask_required("Montage name")
                    n_pairs = 2 if mode == "U" else 4
                    pairs: List[List[str]] = []
                    eeg_pos_dir = pm.path_optional("eeg_positions", subject_id=subject_id)
                    labels: List[str] = []
                    if eeg_pos_dir:
                        labels = utils.load_eeg_cap_labels(Path(eeg_pos_dir) / eeg_net)
                    if not labels:
                        raise RuntimeError("Could not load electrode labels from EEG cap; cannot create montage interactively.")

                    # Show electrode labels in a compact multi-column view (max 10 rows/column)
                    utils.echo_info("Available electrodes (use labels, e.g. FC1, FC3):")
                    utils.display_table(labels, max_rows=10, col_width=12)

                    # Map for case-insensitive matching to canonical labels
                    canon = {lab.strip().upper(): lab for lab in labels}

                    utils.echo_info(f"Create montage '{name}': enter pair 1, then pair 2{' (and more)' if n_pairs > 2 else ''}.")
                    for i in range(n_pairs):
                        while True:
                            raw = utils.ask_required(f"Please enter two electrodes for pair {i+1}", default=None)
                            parts = [p.strip() for p in raw.split(",") if p.strip()]
                            if len(parts) != 2:
                                utils.echo_error("Please enter exactly two electrode labels separated by a comma (e.g. FC1, FC3).")
                                continue
                            a_raw, b_raw = parts[0].upper(), parts[1].upper()
                            if a_raw == b_raw:
                                utils.echo_error("Electrodes must be different.")
                                continue
                            a = canon.get(a_raw)
                            b = canon.get(b_raw)
                            if not a or not b:
                                utils.echo_error("One or both electrode labels were not recognized. Please use the labels shown above.")
                                continue
                            pairs.append([a, b])
                            break

                    sim_utils.upsert_montage(project_dir=pm.project_dir, eeg_net=eeg_net, montage_name=name, electrode_pairs=pairs, mode=mode)
                    available = list_montage_names(pm.project_dir, eeg_net, mode=mode)
                else:
                    raise RuntimeError("No montages available.")

            selected = self.select_many(prompt_text="Select montages", options=available, help_text="Choose one or more montages")
            montage_names = ",".join(selected)
        else:
            # flex: discover flex-search outputs in standard locations (same as GUI)
            searches = pm.list_flex_search_runs(subject_id)

            if not searches:
                utils.echo_warning("No flex-search outputs found for this subject (missing flex-search/*/electrode_positions.json).")
                montage_names = ""
            else:
                selected_searches = self.select_many(
                    prompt_text="Select flex-search outputs",
                    options=searches,
                    help_text="Choose one or more flex-search output folders to simulate.",
                )
                flex_use_optimized = utils.ask_bool("Simulate optimized electrodes (XYZ coordinates)?", default=True)
                flex_use_mapped = utils.ask_bool("Simulate mapped electrodes (EEG-net labels)?", default=True)
                if flex_use_mapped:
                    eeg_net = self.select_one(
                        prompt_text="Select EEG cap",
                        options=(pm.list_eeg_caps(subject_id) or [self._default_eeg_cap()]),
                        help_text="Choose an EEG cap CSV filename",
                    )
                if not flex_use_mapped and not flex_use_optimized:
                    raise RuntimeError("Must select at least one electrode type (mapped or optimized).")
                montage_names = ",".join(selected_searches)

        conductivity = self._prompt_for_value(
            InteractivePrompt(name="conductivity", prompt_text="Conductivity", choices=["scalar", "vn", "dir", "mc"], default="scalar")
        )
        intensity = utils.ask_required("Intensity (mA)", default="2.0")
        shape = self._prompt_for_value(
            InteractivePrompt(name="shape", prompt_text="Electrode shape", choices=["ellipse", "rect"], default="ellipse")
        )
        dims = utils.ask_required("Dimensions (mm) e.g. 8,8", default="8,8")
        thickness = utils.ask_float("Thickness (mm)", default="4.0")

        if not utils.review_and_confirm(
            "Review (simulator)",
            items=[
                ("Subject", subject_id),
                ("Framework", framework),
                ("Mode", mode),
                ("EEG cap", eeg_net if eeg_net else "-"),
                ("Montages", montage_names if montage_names else ("ALL (flex)" if framework == "flex" else "-")),
                ("Conductivity", conductivity),
                ("Intensity", intensity),
                ("Electrode shape", shape),
                ("Dimensions", dims),
                ("Thickness (mm)", str(thickness)),
                ("Mapped electrodes", "yes" if (framework == "flex" and flex_use_mapped) else "no"),
                ("Optimized electrodes", "yes" if (framework == "flex" and flex_use_optimized) else "no"),
            ],
            default_yes=True,
        ):
            utils.echo_warning("Cancelled.")
            return 0

        return self.execute(
            dict(
                subject=subject_id,
                eeg_net=(eeg_net if eeg_net else self._default_eeg_cap()),
                framework=framework,
                mode=mode,
                montages=montage_names,
                flex_use_mapped=flex_use_mapped,
                flex_use_optimized=flex_use_optimized,
                conductivity=conductivity,
                intensity=intensity,
                electrode_shape=shape,
                dimensions=dims,
                thickness=thickness,
            )
        )

    @staticmethod
    def _default_eeg_cap() -> str:
        return "GSN-HydroCel-185.csv"

    def execute(self, args: Dict[str, Any]) -> int:
        pm = get_path_manager()
        if not pm.project_dir:
            raise RuntimeError("Project directory not resolved. Set PROJECT_DIR_NAME or PROJECT_DIR in Docker.")

        if args.get("list_subjects"):
            subs = pm.list_subjects()
            utils.echo_header("Available Subjects")
            utils.display_table(subs)
            return 0

        if args.get("list_eeg_caps"):
            sid = args.get("subject")
            if not sid:
                raise RuntimeError("--sub is required for --list-eeg-caps")
            caps = pm.list_eeg_caps(str(sid))
            utils.echo_header(f"EEG caps for {sid}")
            utils.display_table(caps)
            return 0

        if args.get("list_montages"):
            eeg_net_arg = str(args.get("eeg_net") or self._default_eeg_cap())
            # If a subject is provided, normalize EEG cap name against eeg_positions.
            sid = args.get("subject")
            eeg_net = _resolve_eeg_cap_filename(str(sid), eeg_net_arg) if sid else eeg_net_arg
            from tit.sim.montage_loader import list_montage_names as _list_names

            # montage_list.json keys usually include ".csv". If user passed a stem, also try the ".csv" key.
            u_names = _list_names(str(pm.project_dir), eeg_net, mode="U")
            m_names = _list_names(str(pm.project_dir), eeg_net, mode="M")
            if not eeg_net.lower().endswith(".csv"):
                u_names = sorted(set(u_names) | set(_list_names(str(pm.project_dir), eeg_net + ".csv", mode="U")))
                m_names = sorted(set(m_names) | set(_list_names(str(pm.project_dir), eeg_net + ".csv", mode="M")))
            utils.echo_header(f"Montages (eeg-net: {eeg_net})")
            utils.echo_section("U mode (TI / 2 pairs)")
            utils.display_table(u_names)
            utils.echo_section("M mode (mTI / 4 pairs)")
            utils.display_table(m_names)

            # If a subject was provided, also show available flex-search runs for that subject.
            if sid:
                runs = pm.list_flex_search_runs(str(sid))
                utils.echo_section(f"Flex-search runs (sub: {sid})")
                utils.display_table(runs)
            return 0

        # Run simulation using tit.sim (keeps critical steps intact)
        sid = args.get("subject")
        if not sid:
            raise RuntimeError("--sub is required")
        # Framework selection: explicit shorthand flags win.
        if args.get("montage") and args.get("flex"):
            raise RuntimeError("Choose only one of --montage or --flex")
        framework = "montage"
        if args.get("flex"):
            framework = "flex"
        elif args.get("montage"):
            framework = "montage"
        else:
            framework = str(args.get("framework") or "montage")
        mode = str(args.get("mode") or "U").upper()
        eeg_net_arg = str(args.get("eeg_net") or self._default_eeg_cap())
        # Normalize EEG cap to existing eeg_positions filename when possible.
        eeg_net = _resolve_eeg_cap_filename(str(sid), eeg_net_arg)

        from tit.sim import (
            ConductivityType,
            ElectrodeConfig,
            IntensityConfig,
            SimulationConfig,
            run_simulation,
        )
        from tit.sim.config import MontageConfig
        from tit.tools import map_electrodes as map_tool

        raw_montages = args.get("montages")
        tokens: List[str] = []
        if raw_montages is None:
            tokens = []
        elif isinstance(raw_montages, (list, tuple)):
            for t in raw_montages:
                tokens.extend([x.strip() for x in str(t).split(",") if x.strip()])
        else:
            tokens = [x.strip() for x in str(raw_montages).split(",") if x.strip()]
        montage_names = list(dict.fromkeys(tokens))  # stable-unique
        if framework == "montage" and not montage_names:
            raise RuntimeError("--montages is required for framework=montage")

        # Build configs
        dims = [float(x.strip()) for x in str(args.get("dimensions") or "8,8").split(",") if x.strip()]
        electrode = ElectrodeConfig(
            shape=str(args.get("electrode_shape") or "ellipse"),
            dimensions=dims,
            thickness=float(args.get("thickness") or 4.0),
        )
        intensities = IntensityConfig.from_string(str(args.get("intensity") or "2.0"))

        config = SimulationConfig(
            subject_id=str(sid),
            project_dir=str(pm.project_dir),
            conductivity_type=ConductivityType(str(args.get("conductivity") or "scalar")),
            intensities=intensities,
            electrode=electrode,
            eeg_net=("flex_mode" if framework == "flex" else eeg_net),
            # NOTE: all other SimulationConfig options are left as backend defaults
        )

        # Load montages
        montages: List[MontageConfig] = []
        if framework == "montage":
            from tit.sim.montage_loader import load_montages as _load_regular
            from tit.sim.montage_loader import list_montage_names as _list_names
            from tit.sim import utils as sim_utils

            montages = _load_regular(montage_names=montage_names, project_dir=str(pm.project_dir), eeg_net=eeg_net, include_flex=False)

            # If missing and user asked to create, prompt for montage definitions now.
            if (not montages) and bool(args.get("create_montage")):
                available_labels: List[str] = []
                eeg_pos_dir = pm.path_optional("eeg_positions", subject_id=str(sid))
                if eeg_pos_dir:
                    cap_path = Path(eeg_pos_dir) / eeg_net
                    if cap_path.is_file():
                        available_labels = utils.load_eeg_cap_labels(cap_path)
                if not available_labels:
                    raise RuntimeError(f"Could not load electrode labels for EEG cap '{eeg_net}'. Ensure it exists under eeg_positions for sub {sid}.")

                utils.echo_header("Create montage(s)")
                utils.echo_info(f"EEG cap: {eeg_net}")
                utils.echo_info("Available electrodes (sample):")
                utils.display_table(available_labels, max_rows=10, col_width=12)
                canon = {lab.strip().upper(): lab for lab in available_labels}
                n_pairs = 2 if mode == "U" else 4

                for name in montage_names:
                    pairs: List[List[str]] = []
                    utils.echo_section(f"Montage: {name} ({mode})")
                    for i in range(n_pairs):
                        while True:
                            raw = utils.ask_required(f"Enter two electrodes for pair {i+1} (comma-separated)", default=None)
                            parts = [p.strip() for p in raw.split(",") if p.strip()]
                            if len(parts) != 2:
                                utils.echo_error("Please enter exactly two electrode labels separated by a comma (e.g. FC1, FC3).")
                                continue
                            a_raw, b_raw = parts[0].upper(), parts[1].upper()
                            if a_raw == b_raw:
                                utils.echo_error("Electrodes must be different.")
                                continue
                            a = canon.get(a_raw)
                            b = canon.get(b_raw)
                            if not a or not b:
                                utils.echo_error("One or both electrode labels were not recognized. Please use labels from the EEG cap.")
                                continue
                            pairs.append([a, b])
                            break
                    sim_utils.upsert_montage(project_dir=str(pm.project_dir), eeg_net=eeg_net, montage_name=name, electrode_pairs=pairs, mode=mode)
                    utils.echo_success(f"Saved montage '{name}' to montage_list.json")

                # Reload after creation
                montages = _load_regular(montage_names=montage_names, project_dir=str(pm.project_dir), eeg_net=eeg_net, include_flex=False)

            if not montages:
                available = _list_names(str(pm.project_dir), eeg_net, mode=mode)
                available_s = ", ".join(available) if available else "(none)"
                raise RuntimeError(
                    f"No montages were loaded for eeg-net={eeg_net}, mode={mode}. "
                    f"Requested: {', '.join(montage_names)}. Available: {available_s}. "
                    f"Tip: run `simulator --list-montages --eeg {eeg_net}` "
                    f"or re-run with --create-montage to define it."
                )
        else:
            # Flex mode: montage_names holds selected flex-search folders
            flex_root = Path(pm.path("flex_search", subject_id=str(sid)))
            if not flex_root.is_dir():
                raise RuntimeError(f"No flex-search directory found: {flex_root}")

            # Decide what to simulate: by default, simulate both mapped and optimized if possible.
            # (interactive puts selected search folders in args['montages'])
            use_mapped = bool(args.get("flex_use_mapped", True))
            use_optimized = bool(args.get("flex_use_optimized", True))
            # Backward compatible: if not provided, keep default True/True

            def _parse_flex_search_name(search_name: str, electrode_type: str) -> str:
                # Ported from GUI simulator_tab._parse_flex_search_name for consistent naming.
                search_name = search_name.strip()
                try:
                    if search_name.startswith("sphere_"):
                        parts = search_name.split("_")
                        if len(parts) >= 3:
                            hemisphere = "spherical"
                            coords_part = parts[1] if len(parts) > 1 else "coords"
                            goal = parts[-2] if len(parts) >= 3 else "optimization"
                            post_proc = parts[-1] if len(parts) >= 3 else "maxTI"
                            return f"flex_{hemisphere}_{coords_part}_{goal}_{post_proc}_{electrode_type}"
                    if search_name.startswith("subcortical_"):
                        parts = search_name.split("_")
                        if len(parts) >= 5:
                            hemisphere = "subcortical"
                            atlas = parts[1]
                            region = parts[2]
                            goal = parts[3]
                            post_proc = parts[4]
                            return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"
                    if "_" in search_name and len(search_name.split("_")) >= 5:
                        parts = search_name.split("_")
                        if len(parts) >= 5 and parts[0] in ["lh", "rh"]:
                            hemisphere = parts[0]
                            atlas = parts[1]
                            region = parts[2]
                            goal = parts[3]
                            post_proc = parts[4]
                            return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"
                    if search_name.startswith(("lh.", "rh.")):
                        parts = search_name.split("_")
                        if len(parts) >= 3:
                            hemisphere_region = parts[0]
                            atlas = parts[1]
                            goal_postproc = "_".join(parts[2:])
                            if "." in hemisphere_region:
                                hemisphere, region = hemisphere_region.split(".", 1)
                            else:
                                hemisphere = "unknown"
                                region = hemisphere_region
                            if "_" in goal_postproc:
                                goal_parts = goal_postproc.split("_")
                                region = goal_parts[0]
                                goal = goal_parts[1] if len(goal_parts) > 1 else "optimization"
                                post_proc = "_".join(goal_parts[2:]) if len(goal_parts) > 2 else "maxTI"
                            else:
                                goal = goal_postproc
                                post_proc = "maxTI"
                            return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"
                    if search_name.startswith("subcortical_") and len(search_name.split("_")) == 4:
                        parts = search_name.split("_")
                        hemisphere = "subcortical"
                        atlas = parts[1]
                        region = parts[2]
                        goal = parts[3]
                        post_proc = "maxTI"
                        return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"
                    if "_" in search_name:
                        parts = search_name.split("_")
                        hemisphere = "spherical"
                        atlas = "coordinates"
                        region = "_".join(parts[:-1]) if len(parts) > 1 else search_name
                        goal = parts[-1] if parts else "optimization"
                        post_proc = "maxTI"
                        return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"
                    return f"flex_unknown_unknown_{search_name}_optimization_maxTI_{electrode_type}"
                except Exception:
                    return f"flex_unknown_unknown_{search_name}_optimization_maxTI_{electrode_type}"

            for search_name in montage_names:
                search_dir = flex_root / search_name
                positions_file = search_dir / "electrode_positions.json"
                if not positions_file.is_file():
                    continue
                with positions_file.open() as f:
                    positions_data = json.load(f)

                if use_optimized:
                    optimized_positions = positions_data.get("optimized_positions") or []
                    if len(optimized_positions) >= 4:
                        positions_for_ti = optimized_positions[:4]
                        name = _parse_flex_search_name(search_name, "optimized")
                        montages.append(
                            MontageConfig(
                                name=name,
                                electrode_pairs=[(positions_for_ti[0], positions_for_ti[1]), (positions_for_ti[2], positions_for_ti[3])],
                                is_xyz=True,
                                eeg_net="flex_mode",
                            )
                        )

                if use_mapped:
                    eeg_dir = Path(pm.path("eeg_positions", subject_id=str(sid)))
                    eeg_net_path = eeg_dir / eeg_net
                    if not eeg_net_path.is_file():
                        continue
                    mapping_file = search_dir / f"electrode_mapping_{eeg_net.replace('.csv', '')}.json"
                    if mapping_file.is_file():
                        with mapping_file.open() as f:
                            mapping_data = json.load(f)
                    else:
                        # Create mapping on demand (same behavior as GUI)
                        opt_positions, channel_array_indices = map_tool.load_electrode_positions_json(str(positions_file))
                        net_positions, net_labels = map_tool.read_csv_positions(str(eeg_net_path))
                        mapping_data = map_tool.map_electrodes_to_net(opt_positions, net_positions, net_labels, channel_array_indices)
                        map_tool.save_mapping_result(mapping_data, str(mapping_file), eeg_net_name=eeg_net)

                    mapped_labels = mapping_data.get("mapped_labels") or []
                    if len(mapped_labels) >= 4:
                        electrodes_for_ti = mapped_labels[:4]
                        name = _parse_flex_search_name(search_name, "mapped")
                        montages.append(
                            MontageConfig(
                                name=name,
                                electrode_pairs=[(electrodes_for_ti[0], electrodes_for_ti[1]), (electrodes_for_ti[2], electrodes_for_ti[3])],
                                is_xyz=False,
                                eeg_net=eeg_net,
                            )
                        )

            if not montages:
                raise RuntimeError("No flex-search montages constructed from selected outputs.")

        # Console logger (CLI should print output like other CLI commands)
        logger = logging.getLogger("TI-Simulator")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
            h = logging.StreamHandler(sys.stdout)
            h.setLevel(logging.INFO)
            h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
            logger.addHandler(h)

        # Backward-compatible: only pass logger if backend supports it.
        kwargs: Dict[str, Any] = {}
        try:
            if "logger" in inspect.signature(run_simulation).parameters:
                kwargs["logger"] = logger
        except Exception:
            # If signature introspection fails, fall back to passing no kwargs.
            kwargs = {}

        results = run_simulation(config, montages, **kwargs)
        utils.echo_header("Simulation Results")
        if not results:
            utils.echo_warning("No simulations were run (empty montage list).")
            return 1

        completed = [r for r in results if r.get("status") == "completed"]
        failed = [r for r in results if r.get("status") != "completed"]
        for r in completed:
            out_mesh = r.get("output_mesh") or "-"
            utils.echo_success(f"{r.get('montage_name', 'unknown')}: completed (output_mesh: {out_mesh})")
        for r in failed:
            err = r.get("error") or "unknown error"
            utils.echo_error(f"{r.get('montage_name', 'unknown')}: failed ({err})")

        ok = len(failed) == 0
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(SimulatorCLI().run())


