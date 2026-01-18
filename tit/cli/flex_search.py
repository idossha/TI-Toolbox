#!/usr/bin/env simnibs_python
"""
TI-Toolbox Flex-Search CLI.

This file intentionally contains *no* flex business logic.

- Interactive (no args): prompt for a minimal set, then run `simnibs_python -m tit.opt.flex ...`
- Direct (args present): forward args unchanged to `simnibs_python -m tit.opt.flex ...`
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from tit.cli.base import BaseCLI, InteractivePrompt
from tit.cli import utils


class FlexSearchCLI(BaseCLI):
    def __init__(self) -> None:
        super().__init__("Run flex-search optimization (delegates to tit.opt.flex).")

    @staticmethod
    def _call_flex(args: List[str]) -> int:
        return subprocess.call(["simnibs_python", "-m", "tit.opt.flex", *args])

    def run_direct(self) -> int:
        return self._call_flex(sys.argv[1:])

    def execute(self, args):  # type: ignore[override]
        # Not used: direct mode overrides `run_direct()` and interactive calls `_call_flex()` directly.
        return 0

    def run_interactive(self) -> int:
        from tit.core import get_path_manager

        pm = get_path_manager()
        if not pm.project_dir:
            raise RuntimeError(
                "Project directory not resolved. Set PROJECT_DIR_NAME or PROJECT_DIR in Docker."
            )

        utils.echo_header("Flex Search (interactive)")

        def _list_subject_surface_atlases(subject_id: str, hemi: str) -> List[str]:
            """Get list of available atlas names for a subject."""
            from tit.opt.flex.utils import find_subject_atlases

            atlas_map = find_subject_atlases(subject_id, hemi, pm.project_dir)
            return sorted(atlas_map.keys())

        subject_id = self.select_one(
            prompt_text="Select subject",
            options=pm.list_subjects(),
            help_text="Choose from available subjects in your project",
        )
        roi_method = self._prompt_for_value(
            InteractivePrompt(
                name="roi_method",
                prompt_text="ROI method",
                choices=["spherical", "atlas", "subcortical"],
                default="spherical",
            )
        )

        # ROI configuration is done via environment variables in tit.opt.flex (not CLI flags).
        env_items: List[tuple[str, str]] = []
        if roi_method == "spherical":
            x = utils.ask_float("ROI center X", default="0")
            y = utils.ask_float("ROI center Y", default="0")
            z = utils.ask_float("ROI center Z", default="0")
            r = utils.ask_float("ROI radius", default="10")
            use_mni = utils.ask_bool("Coordinate space = MNI?", default=False)
            os.environ["ROI_X"] = str(x)
            os.environ["ROI_Y"] = str(y)
            os.environ["ROI_Z"] = str(z)
            os.environ["ROI_RADIUS"] = str(r)
            os.environ["USE_MNI_COORDS"] = "true" if use_mni else "false"
            env_items += [
                ("ROI_X", str(x)),
                ("ROI_Y", str(y)),
                ("ROI_Z", str(z)),
                ("ROI_RADIUS", str(r)),
                ("USE_MNI_COORDS", os.environ["USE_MNI_COORDS"]),
            ]
        elif roi_method == "atlas":
            hemi = self._prompt_for_value(
                InteractivePrompt(
                    name="hemi",
                    prompt_text="Hemisphere",
                    choices=["lh", "rh"],
                    default="lh",
                )
            )
            from tit.opt.flex.utils import find_subject_atlases

            atlas_map = find_subject_atlases(subject_id, hemi, pm.project_dir)
            atlas_names = list(atlas_map.keys())

            if not atlas_names:
                atlas_name = utils.ask_required(
                    "Atlas name (no atlases found automatically)"
                )
                atlas_path = atlas_name  # User will provide full path
            else:
                atlas_name = utils.choose_or_enter(
                    prompt="Atlas name",
                    options=atlas_names,
                    help_text="Select an atlas or choose 'Enter manually…'",
                )
                atlas_path = atlas_map.get(
                    atlas_name, atlas_name
                )  # Use path if found, otherwise user input

            # Option to list regions in the selected atlas
            if atlas_path and os.path.isfile(atlas_path):
                if utils.ask_bool(
                    "List available regions in this atlas?", default=False
                ):
                    from tit.opt.flex.utils import list_atlas_regions

                    try:
                        regions = list_atlas_regions(atlas_path)
                        utils.echo_header(f"Regions in {atlas_name}")
                        for idx, name in regions:
                            print(f"  {idx}: {name}")
                        print()
                    except Exception as e:
                        utils.echo_warning(f"Could not list regions: {e}")

            roi_label = utils.ask_required("ROI label", default="1")
            os.environ["ATLAS_PATH"] = str(atlas_path)
            os.environ["SELECTED_HEMISPHERE"] = str(hemi)
            os.environ["ROI_LABEL"] = str(roi_label)
            env_items += [
                ("ATLAS_PATH", str(atlas_path)),
                ("SELECTED_HEMISPHERE", str(hemi)),
                ("ROI_LABEL", str(roi_label)),
            ]
        else:
            vol_dir = (
                Path(pm.project_dir) / "resources" / "atlas" if pm.project_dir else None
            )
            vol_files: List[str] = []
            if vol_dir and vol_dir.is_dir():
                vol_files = [str(p) for p in sorted(vol_dir.glob("*.nii*"))]
            vol_atlas = utils.choose_or_enter(
                prompt="Volume atlas path",
                options=vol_files,
                help_text="Select a volume atlas or choose 'Enter manually…'",
            )
            vol_label = utils.ask_required("Volume ROI label", default="10")
            os.environ["VOLUME_ATLAS_PATH"] = str(vol_atlas)
            os.environ["VOLUME_ROI_LABEL"] = str(vol_label)
            env_items += [
                ("VOLUME_ATLAS_PATH", str(vol_atlas)),
                ("VOLUME_ROI_LABEL", str(vol_label)),
            ]

        goal = self._prompt_for_value(
            InteractivePrompt(
                name="goal",
                prompt_text="Goal",
                choices=["mean", "focality", "max"],
                default="mean",
            )
        )
        threshold_strategy: Optional[str] = None
        thresholds: Optional[str] = None
        non_roi: Optional[str] = None
        if goal == "focality":
            threshold_strategy = self._prompt_for_value(
                InteractivePrompt(
                    name="threshold_strategy",
                    prompt_text="Focality thresholds",
                    choices=["dynamic", "manual"],
                    default="dynamic",
                    help_text="Dynamic: let SimNIBS adapt thresholds automatically. Manual: provide numeric thresholds.",
                )
            )
            non_roi = self._prompt_for_value(
                InteractivePrompt(
                    name="non_roi_method",
                    prompt_text="Non-ROI method",
                    choices=["everything_else", "specific"],
                    default="everything_else",
                )
            )
            if threshold_strategy == "manual":
                thresholds = utils.ask_required(
                    "Focality thresholds (e.g. 0.2 or 0.2,0.5)"
                )

            # If user wants a specific non-ROI region, collect its definition via env vars
            if non_roi == "specific":
                if roi_method == "spherical":
                    nx = utils.ask_float("Non-ROI center X", default="0")
                    ny = utils.ask_float("Non-ROI center Y", default="0")
                    nz = utils.ask_float("Non-ROI center Z", default="0")
                    nr = utils.ask_float("Non-ROI radius", default="10")
                    use_mni_non_roi = utils.ask_bool(
                        "Non-ROI coordinate space = MNI?", default=False
                    )
                    os.environ["NON_ROI_X"] = str(nx)
                    os.environ["NON_ROI_Y"] = str(ny)
                    os.environ["NON_ROI_Z"] = str(nz)
                    os.environ["NON_ROI_RADIUS"] = str(nr)
                    os.environ["USE_MNI_COORDS_NON_ROI"] = (
                        "true" if use_mni_non_roi else "false"
                    )
                    env_items += [
                        ("NON_ROI_X", str(nx)),
                        ("NON_ROI_Y", str(ny)),
                        ("NON_ROI_Z", str(nz)),
                        ("NON_ROI_RADIUS", str(nr)),
                        (
                            "USE_MNI_COORDS_NON_ROI",
                            os.environ["USE_MNI_COORDS_NON_ROI"],
                        ),
                    ]
                elif roi_method == "atlas":
                    non_roi_label = utils.ask_required("Non-ROI label", default="1")
                    # By default use the same atlas file unless user selects otherwise
                    non_roi_atlas_files = _list_subject_surface_atlases(
                        subject_id, os.environ.get("SELECTED_HEMISPHERE", "lh")
                    )
                    non_roi_atlas_path = utils.choose_or_enter(
                        prompt="Non-ROI atlas path (.annot)",
                        options=non_roi_atlas_files,
                        default=os.environ.get("ATLAS_PATH"),
                        help_text="Select an atlas for the non-ROI or choose 'Enter manually…'",
                    )
                    os.environ["NON_ROI_LABEL"] = str(non_roi_label)
                    os.environ["NON_ROI_ATLAS_PATH"] = str(non_roi_atlas_path)
                    env_items += [
                        ("NON_ROI_LABEL", str(non_roi_label)),
                        ("NON_ROI_ATLAS_PATH", str(non_roi_atlas_path)),
                    ]
                else:
                    non_roi_label = utils.ask_required(
                        "Non-ROI volume label", default="10"
                    )
                    vol_dir = (
                        Path(pm.project_dir) / "resources" / "atlas"
                        if pm.project_dir
                        else None
                    )
                    vol_files: List[str] = []
                    if vol_dir and vol_dir.is_dir():
                        vol_files = [str(p) for p in sorted(vol_dir.glob("*.nii*"))]
                    non_roi_atlas_path = utils.choose_or_enter(
                        prompt="Non-ROI volume atlas path",
                        options=vol_files,
                        default=os.environ.get("VOLUME_ATLAS_PATH"),
                        help_text="Select a volume atlas for the non-ROI or choose 'Enter manually…'",
                    )
                    os.environ["VOLUME_NON_ROI_LABEL"] = str(non_roi_label)
                    os.environ["VOLUME_NON_ROI_ATLAS_PATH"] = str(non_roi_atlas_path)
                    env_items += [
                        ("VOLUME_NON_ROI_LABEL", str(non_roi_label)),
                        ("VOLUME_NON_ROI_ATLAS_PATH", str(non_roi_atlas_path)),
                    ]

        postproc = self._prompt_for_value(
            InteractivePrompt(
                name="postproc",
                prompt_text="Post-processing",
                choices=["max_TI", "dir_TI_normal", "dir_TI_tangential"],
                default="max_TI",
            )
        )
        current = utils.ask_float("Current (mA)", default="2.0")
        electrode_shape = self._prompt_for_value(
            InteractivePrompt(
                name="electrode_shape",
                prompt_text="Electrode shape",
                choices=["rect", "ellipse"],
                default="ellipse",
            )
        )
        dimensions = utils.ask_required(
            "Electrode dimensions (mm) (x,y)", default="8,8"
        )
        thickness = utils.ask_float("Electrode thickness (mm)", default="4.0")

        args: List[str] = [
            "--subject",
            subject_id,
            "--goal",
            goal,
            "--postproc",
            postproc,
            "--current",
            str(current),
            "--electrode-shape",
            electrode_shape,
            "--dimensions",
            dimensions,
            "--thickness",
            str(thickness),
            "--roi-method",
            roi_method,
        ]
        if goal == "focality":
            args += ["--non-roi-method", str(non_roi or "everything_else")]
            if threshold_strategy == "manual" and thresholds:
                args += ["--thresholds", thresholds]

        cmd = ["simnibs_python", "-m", "tit.opt.flex", *args]
        if not utils.review_and_confirm(
            "Review (flex-search)",
            items=[
                ("Subject", subject_id),
                ("ROI method", roi_method),
                ("Goal", goal),
                ("Post-processing", postproc),
                ("Current (mA)", str(current)),
                ("Electrode shape", electrode_shape),
                ("Dimensions (mm)", dimensions),
                ("Thickness (mm)", str(thickness)),
                (
                    "Focality thresholds",
                    (
                        "dynamic"
                        if (goal == "focality" and threshold_strategy == "dynamic")
                        else (thresholds or "-")
                    ),
                ),
            ],
            env=env_items,
            command=cmd,
            default_yes=True,
        ):
            utils.echo_warning("Cancelled.")
            return 0

        return self._call_flex(args)


if __name__ == "__main__":
    raise SystemExit(FlexSearchCLI().run())
