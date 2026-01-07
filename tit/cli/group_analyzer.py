#!/usr/bin/env simnibs_python
"""
TI-Toolbox Group Analyzer CLI.

Thin wrapper around `tit.opt.ex.main.main()` which is env-driven.

- Interactive default (no args)
- Direct mode via flags
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Sequence
from datetime import datetime

from tit.cli.base import ArgumentDefinition, BaseCLI, InteractivePrompt
from tit.cli import utils
from tit.core import get_path_manager


def _run_group_analyzer_with_argv(argv: Sequence[str]) -> int:
    from tit.analyzer import group_analyzer

    utils.run_main_with_argv("tit.analyzer.group_analyzer", argv, group_analyzer.main)
    return 0


class GroupAnalyzerCLI(BaseCLI):
    def __init__(self) -> None:
        super().__init__("Run analysis across multiple subjects and compare results.")

        # Accept either:
        # - comma-separated: --subs 101,102
        # - space-separated: --subs 101 102
        self.add_argument(ArgumentDefinition(name="subjects", type=str, nargs="+", help="Subject IDs (comma-separated or space-separated). Requires at least 2.", required=True))
        self.add_argument(ArgumentDefinition(name="simulation", type=str, help="Simulation name", required=True))
        self.add_argument(ArgumentDefinition(name="space", type=str, choices=["mesh", "voxel"], default="mesh", help="mesh|voxel"))
        self.add_argument(ArgumentDefinition(name="analysis_type", type=str, choices=["spherical", "cortical"], default="spherical", help="spherical|cortical"))
        # This is the *base* directory the group analyzer uses to place each subject's analysis output.
        # The recommended value is the SimNIBS derivatives directory (e.g. .../derivatives/SimNIBS),
        # which matches the GUI behavior and keeps results under each simulation's Analyses/ folder.
        self.add_argument(ArgumentDefinition(name="output_dir", type=str, help="Base output directory (default: <project>/derivatives/SimNIBS)", required=False))

        # spherical
        self.add_argument(ArgumentDefinition(name="coordinates", type=str, help="x y z", required=False))
        self.add_argument(ArgumentDefinition(name="radius", type=float, help="Radius (mm)", required=False))
        self.add_argument(ArgumentDefinition(name="coordinate_space", type=str, choices=["MNI", "subject"], default="MNI", help="MNI|subject"))

        # cortical
        self.add_argument(ArgumentDefinition(name="atlas_name", type=str, help="Atlas name (mesh cortical)", required=False))
        self.add_argument(ArgumentDefinition(name="atlas_path", type=str, help="Atlas path (voxel cortical)", required=False))
        self.add_argument(ArgumentDefinition(name="whole_head", type=bool, help="Analyze whole head", default=False))
        self.add_argument(ArgumentDefinition(name="region", type=str, help="Region name (if not whole head)", required=False))

        # output toggles
        self.add_argument(ArgumentDefinition(name="quiet", type=bool, help="Quiet mode", default=False))
        self.add_argument(ArgumentDefinition(name="visualize", type=bool, help="Generate visualizations", default=False))

    def run_interactive(self) -> int:
        pm = get_path_manager()

        utils.echo_header("Group Analyzer (interactive)")

        subjects = pm.list_subjects()
        selected = self.select_many(prompt_text="Select subjects", options=subjects, help_text="Choose at least 2 subjects")
        if len(selected) < 2:
            raise RuntimeError("Group analysis requires at least 2 subjects.")

        # Prefer listing available simulations that exist for all selected subjects
        sim_sets = [set(pm.list_simulations(sid)) for sid in selected]
        common_sims = sorted(set.intersection(*sim_sets)) if sim_sets else []
        if common_sims:
            simulation = self.select_one(
                prompt_text="Select simulation",
                options=common_sims,
                help_text="Simulations common to all selected subjects",
            )
        else:
            simulation = utils.ask_required("Simulation name")

        space = self._prompt_for_value(
            InteractivePrompt(name="space", prompt_text="Space", choices=["mesh", "voxel"], default="mesh")
        )
        analysis_type = self._prompt_for_value(
            InteractivePrompt(name="analysis_type", prompt_text="Analysis type", choices=["spherical", "cortical"], default="spherical")
        )

        default_out = pm.path("simnibs")
        output_dir = utils.choose_or_enter(
            prompt="Base output dir",
            options=[default_out],
            default=default_out,
            help_text="This is the base dir used to write per-subject outputs (recommended: derivatives/SimNIBS).",
        )

        args: Dict[str, Any] = {
            "subjects": ",".join(selected),
            "simulation": simulation,
            "space": space,
            "analysis_type": analysis_type,
            "output_dir": output_dir,
        }

        if analysis_type == "spherical":
            x = utils.ask_float("X", default="0")
            y = utils.ask_float("Y", default="0")
            z = utils.ask_float("Z", default="0")
            args["coordinates"] = f"{x} {y} {z}"
            args["radius"] = utils.ask_float("Radius (mm)", default="10")
            args["coordinate_space"] = self._prompt_for_value(
                InteractivePrompt(name="coordinate_space", prompt_text="Coordinate space", choices=["MNI", "subject"], default="MNI")
            )
        else:
            args["whole_head"] = utils.ask_bool("Analyze whole head?", default=False)
            if not args["whole_head"]:
                args["region"] = utils.ask_required("Region name")
            if space == "mesh":
                args["atlas_name"] = utils.ask_required("Atlas name", default="DK40")
            else:
                atlas_dir = Path(pm.project_dir) / "resources" / "atlas" if pm.project_dir else None
                atlas_files: List[str] = []
                if atlas_dir and atlas_dir.is_dir():
                    atlas_files = [str(p) for p in sorted(atlas_dir.glob("*.nii*"))]
                args["atlas_path"] = utils.choose_or_enter(prompt="Atlas path", options=atlas_files, help_text="Select an atlas file or choose 'Enter manually…'")

        if not utils.review_and_confirm(
            "Review (group analyzer)",
            items=[
                ("Subjects", ",".join(selected)),
                ("Simulation", str(simulation)),
                ("Space", str(space)),
                ("Analysis type", str(analysis_type)),
                ("Output dir", str(output_dir)),
            ],
            default_yes=True,
        ):
            utils.echo_warning("Cancelled.")
            return 0

        return self.execute(args)

    def execute(self, args: Dict[str, Any]) -> int:
        pm = get_path_manager()
        if not pm.project_dir:
            raise RuntimeError("Project directory not resolved. In Docker set PROJECT_DIR_NAME so /mnt/<name> exists.")
        proj = Path(pm.project_dir)

        subject_ids = utils.split_csv_or_tokens(args.get("subjects"))
        if len(subject_ids) < 2:
            raise RuntimeError("--subs must contain at least two ids")

        output_dir = args.get("output_dir") or pm.path("simnibs")
        argv: List[str] = ["--space", str(args["space"]), "--analysis_type", str(args["analysis_type"]), "--output_dir", str(output_dir)]

        if args.get("quiet"):
            argv.append("--quiet")
        if args.get("visualize"):
            argv.append("--visualize")

        if args["analysis_type"] == "spherical":
            xyz = str(args.get("coordinates") or "").split()
            if len(xyz) != 3:
                raise RuntimeError("--coordinates must be 'x y z' for spherical analysis")
            if args.get("radius") is None:
                raise RuntimeError("--radius is required for spherical analysis")
            argv += [
                "--coordinates",
                xyz[0],
                xyz[1],
                xyz[2],
                "--radius",
                str(args["radius"]),
                "--coordinate-space",
                str(args.get("coordinate_space") or "MNI"),
            ]
        else:
            if args["space"] == "mesh":
                atlas_name = args.get("atlas_name")
                if not atlas_name:
                    raise RuntimeError("--atlas-name is required for mesh cortical analysis")
                argv += ["--atlas_name", str(atlas_name)]
            if args.get("whole_head"):
                argv.append("--whole_head")
            else:
                region = args.get("region")
                if not region:
                    raise RuntimeError("--region is required unless --whole-head")
                argv += ["--region", str(region)]

        simulation = str(args["simulation"])
        for sid in subject_ids:
            m2m = proj / "derivatives" / "SimNIBS" / f"sub-{sid}" / f"m2m_{sid}"
            if args["space"] == "mesh":
                # For mesh, group_analyzer expects the montage name (not a mesh filepath),
                # so it can auto-construct the correct field path (TI vs mTI) just like the GUI.
                argv += ["--subject", sid, str(m2m), simulation]
            else:
                # For voxel, pass an actual field file path. Prefer the same backend selector used elsewhere.
                from tit.analyzer.field_selector import select_field_file
                field, _ = select_field_file(str(m2m), simulation, "voxel", str(args["analysis_type"]))
                if args["analysis_type"] == "cortical":
                    atlas_path = args.get("atlas_path")
                    if not atlas_path:
                        raise RuntimeError("--atlas-path is required for voxel cortical analysis")
                    argv += ["--subject", sid, str(m2m), str(field), str(atlas_path)]
                else:
                    argv += ["--subject", sid, str(m2m), str(field)]

        return _run_group_analyzer_with_argv(argv)


if __name__ == "__main__":
    raise SystemExit(GroupAnalyzerCLI().run())


