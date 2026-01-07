#!/usr/bin/env simnibs_python
"""
Analyzer CLI implementation.

Kept here (not in tit/cli/) so the analyzer package owns its CLI behavior.
The `tit/cli/analyzer.py` file is just a thin wrapper.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from tit.cli.base import ArgumentDefinition, BaseCLI, InteractivePrompt
from tit.cli import utils
from tit.core import get_path_manager


class AnalyzerCLI(BaseCLI):
    def __init__(self) -> None:
        super().__init__("Analyze simulation results (mesh or voxel) for a single subject.")

        self.add_argument(ArgumentDefinition(name="subject", type=str, help="Subject ID", required=True))
        self.add_argument(ArgumentDefinition(name="simulation", type=str, help="Simulation name", required=True))
        self.add_argument(ArgumentDefinition(name="space", type=str, choices=["mesh", "voxel"], default="mesh", help="mesh|voxel"))
        self.add_argument(ArgumentDefinition(name="analysis_type", type=str, choices=["spherical", "cortical"], default="spherical", help="spherical|cortical"))
        # Mesh can derive field path from montage_name; voxel always needs field_path.
        # Field path is now automatically determined
        self.add_argument(ArgumentDefinition(name="output_dir", type=str, help="Output directory", required=False))
        self.add_argument(ArgumentDefinition(name="visualize", type=bool, help="Generate visualizations", default=False))

        # spherical
        self.add_argument(ArgumentDefinition(name="coordinates", type=float, nargs=3, help="x y z", required=False))
        self.add_argument(ArgumentDefinition(name="radius", type=float, help="Radius (mm)", required=False))
        self.add_argument(ArgumentDefinition(name="coordinate_space", type=str, choices=["MNI", "subject"], default="subject"))

        # cortical
        self.add_argument(ArgumentDefinition(name="atlas_name", type=str, choices=["DK40", "HCP_MMP1", "a2009s"], default="DK40"))
        self.add_argument(ArgumentDefinition(name="atlas_path", type=str, help="Atlas path (voxel cortical)", required=False))
        self.add_argument(ArgumentDefinition(name="whole_head", type=bool, help="Whole head (cortical)", default=False))
        self.add_argument(ArgumentDefinition(name="region", type=str, help="Region name (cortical)", required=False))

    def run_interactive(self) -> int:
        pm = get_path_manager()
        if not pm.project_dir:
            raise RuntimeError("Project directory not resolved. Set PROJECT_DIR_NAME or PROJECT_DIR in Docker.")

        utils.echo_header("Analyzer (interactive)")

        subject_id = self.select_one(
            prompt_text="Select subject",
            options=pm.list_subjects(),
            help_text="Choose from available subjects in your project",
        )
        simulation_name = self.select_one(
            prompt_text="Select simulation",
            options=pm.list_simulations(subject_id),
            help_text="Choose from available simulations for this subject",
        )

        space = self._prompt_for_value(InteractivePrompt(name="space", prompt_text="Space", choices=["mesh", "voxel"], default="mesh"))
        analysis_type = self._prompt_for_value(
            InteractivePrompt(name="analysis_type", prompt_text="Analysis type", choices=["spherical", "cortical"], default="spherical")
        )

        # Automatically determine field file using backend logic
        from tit.analyzer.field_selector import select_field_file
        m2m_dir = Path(pm.path("m2m", subject_id=subject_id))
        try:
            field_path, _ = select_field_file(str(m2m_dir), simulation_name, space, analysis_type)
        except FileNotFoundError as e:
            raise RuntimeError(f"No suitable field file found: {e}")

        args: Dict[str, Any] = dict(
            subject=subject_id,
            simulation=simulation_name,
            space=space,
            analysis_type=analysis_type,
        )

        if analysis_type == "spherical":
            x = utils.ask_float("X", default="0")
            y = utils.ask_float("Y", default="0")
            z = utils.ask_float("Z", default="0")
            args["coordinates"] = f"{x} {y} {z}"
            args["radius"] = utils.ask_float("Radius (mm)", default="10")
            args["coordinate_space"] = self._prompt_for_value(
                InteractivePrompt(name="coordinate_space", prompt_text="Coordinate space", choices=["MNI", "subject"], default="subject")
            )
        else:
            if space == "mesh":
                args["atlas_name"] = self._prompt_for_value(
                    InteractivePrompt(name="atlas_name", prompt_text="Atlas", choices=["DK40", "HCP_MMP1", "a2009s"], default="DK40")
                )
            else:
                atlas_dir = Path(pm.project_dir) / "resources" / "atlas" if pm.project_dir else None
                atlas_files: List[str] = []
                if atlas_dir and atlas_dir.is_dir():
                    atlas_files = [str(p) for p in sorted(atlas_dir.glob("*.nii*"))]
                args["atlas_path"] = utils.choose_or_enter(prompt="Atlas path", options=atlas_files, help_text="Select an atlas file or choose 'Enter manually…'")
            args["whole_head"] = utils.ask_bool("Analyze whole head?", default=False)
            if not args["whole_head"]:
                args["region"] = utils.ask_required("Region name")

        args["visualize"] = utils.ask_bool("Generate visualizations?", default=False)

        # Default output dir: keep CLI consistent with GUI.
        args["output_dir"] = str(self._default_output_dir(pm, args))

        argv_preview = [
            "simnibs_python",
            "-m",
            "tit.analyzer.main_analyzer",
            "--space",
            str(args["space"]),
            "--analysis_type",
            str(args["analysis_type"]),
            "--output_dir",
            str(args["output_dir"]),
            "--m2m_subject_path",
            str(Path(pm.project_dir) / "derivatives" / "SimNIBS" / f"sub-{subject_id}" / f"m2m_{subject_id}"),
            "--montage_name",
            str(simulation_name),
        ]
        if not utils.review_and_confirm(
            "Review (analyzer)",
            items=[
                ("Subject", subject_id),
                ("Simulation", simulation_name),
                ("Space", str(args["space"])),
                ("Analysis type", str(args["analysis_type"])),
                ("Output dir", str(args["output_dir"])),
                ("Visualize", "yes" if args.get("visualize") else "no"),
            ],
            command=argv_preview,
            default_yes=True,
        ):
            utils.echo_warning("Cancelled.")
            return 0

        return self.execute(args)

    def execute(self, args: Dict[str, Any]) -> int:
        pm = get_path_manager()
        if not pm.project_dir:
            raise RuntimeError("Project directory not resolved. Set PROJECT_DIR_NAME or PROJECT_DIR in Docker.")

        cfg = self._normalize(args)

        argv: List[str] = ["--space", cfg["space"], "--analysis_type", cfg["analysis_type"]]
        # If not provided explicitly, default to the same layout as the GUI.
        if not cfg.get("output_dir"):
            cfg["output_dir"] = str(self._default_output_dir(pm, cfg))
        argv += ["--output_dir", str(cfg["output_dir"])]

        if cfg["analysis_type"] == "spherical":
            xyz = cfg["coordinates"]
            argv += ["--coordinates", str(xyz[0]), str(xyz[1]), str(xyz[2])]
            argv += ["--radius", str(cfg["radius"])]
            argv += ["--coordinate-space", cfg.get("coordinate_space", "subject")]
        else:
            if cfg["space"] == "mesh":
                argv += ["--atlas_name", cfg.get("atlas_name", "DK40")]
            else:
                argv += ["--atlas_path", cfg.get("atlas_path", "")]
            if cfg.get("whole_head"):
                argv += ["--whole_head"]
            else:
                argv += ["--region", cfg.get("region", "")]

        if cfg["space"] == "mesh":
            argv += ["--montage_name", cfg["simulation"]]
        if cfg.get("visualize"):
            argv += ["--visualize"]

        project_dir = Path(pm.project_dir)
        m2m_dir = project_dir / "derivatives" / "SimNIBS" / f"sub-{cfg['subject']}" / f"m2m_{cfg['subject']}"
        argv += ["--m2m_subject_path", str(m2m_dir)]

        from tit.analyzer import main_analyzer

        utils.run_main_with_argv("tit.analyzer.main_analyzer", argv, main_analyzer.main)
        return 0

    @staticmethod
    def _default_output_dir(pm, cfg: Dict[str, Any]) -> Path:
        """
        Default output directory that matches the GUI layout:
          <Simulations>/<montage>/Analyses/<Mesh|Voxel>/<analysis_name>
        """
        # Centralized in PathManager so GUI/CLI naming stays identical.
        sim_dir = pm.path_optional("simulation", subject_id=str(cfg["subject"]), simulation_name=str(cfg["simulation"]))
        if not sim_dir:
            raise RuntimeError(f"Could not resolve simulation directory for sub-{cfg['subject']} / {cfg['simulation']}")

        out = pm.get_analysis_output_dir(
            subject_id=str(cfg["subject"]),
            simulation_name=str(cfg["simulation"]),
            space=str(cfg["space"]),
            analysis_type=str(cfg["analysis_type"]),
            coordinates=cfg.get("coordinates"),
            radius=cfg.get("radius"),
            coordinate_space=str(cfg.get("coordinate_space") or "subject"),
            whole_head=bool(cfg.get("whole_head", False)),
            region=cfg.get("region"),
            atlas_name=cfg.get("atlas_name"),
            atlas_path=cfg.get("atlas_path"),
        )
        if not out:
            raise RuntimeError("Could not compute analyzer output directory")
        return Path(out)

    @staticmethod
    def _normalize(args: Dict[str, Any]) -> Dict[str, Any]:
        cfg = dict(args)

        if cfg["analysis_type"] == "spherical":
            # Keep direct mode ergonomic: default to the interactive defaults (0,0,0) and 10mm.
            coords = cfg.get("coordinates")
            if coords is None:
                cfg["coordinates"] = [0.0, 0.0, 0.0]
            elif isinstance(coords, (list, tuple)):
                if len(coords) != 3:
                    raise RuntimeError("--coordinates must be 3 values: x y z")
                cfg["coordinates"] = [float(coords[0]), float(coords[1]), float(coords[2])]
            else:
                parts = str(coords).split()
                if len(parts) != 3:
                    raise RuntimeError("--coordinates must be 3 values: x y z")
                cfg["coordinates"] = [float(parts[0]), float(parts[1]), float(parts[2])]

            if cfg.get("radius") is None:
                cfg["radius"] = 10.0
        else:
            if cfg["space"] == "voxel" and not cfg.get("atlas_path"):
                raise RuntimeError("--atlas-path is required for voxel cortical analysis")
            if not cfg.get("whole_head") and not cfg.get("region"):
                raise RuntimeError("--region is required unless --whole-head")
            # Field path is now automatically determined

        return cfg


if __name__ == "__main__":
    raise SystemExit(AnalyzerCLI().run())

