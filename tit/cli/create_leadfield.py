#!/usr/bin/env simnibs_python
"""
TI-Toolbox Create Leadfield CLI.

- Interactive default (no args)
- Direct mode via flags
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from tit.cli.base import ArgumentDefinition, BaseCLI
from tit.cli import utils
from tit.core import get_path_manager


class CreateLeadfieldCLI(BaseCLI):
    def __init__(self) -> None:
        super().__init__("Create leadfield matrices for a subject.")
        self.add_argument(ArgumentDefinition(name="subject", type=str, help="Subject ID", required=True))
        self.add_argument(ArgumentDefinition(name="eeg_net", type=str, help="EEG cap CSV filename (e.g., EGI_template.csv)", required=True))
        self.add_argument(ArgumentDefinition(name="tissues", type=str, help="Comma-separated tissue tags (default 1,2)", default="1,2"))

    def run_interactive(self) -> int:
        pm = get_path_manager()
        if not pm.project_dir:
            raise RuntimeError("Project directory not resolved. In Docker set PROJECT_DIR_NAME so /mnt/<name> exists.")

        utils.echo_header("Create Leadfield (interactive)")
        subject_id = self.select_one(
            prompt_text="Select subject",
            options=pm.list_subjects(),
            help_text="Choose from available subjects in your project",
        )
        caps = pm.list_eeg_caps(subject_id)
        eeg_net = self.select_one(
            prompt_text="Select EEG cap",
            options=caps,
            help_text="Choose an EEG cap CSV from m2m/<id>/eeg_positions",
        )
        tissues = "1,2"
        if not utils.review_and_confirm(
            "Review (create leadfield)",
            items=[("Subject", subject_id), ("EEG cap", eeg_net), ("Tissues", tissues)],
            default_yes=True,
        ):
            utils.echo_warning("Cancelled.")
            return 0
        return self.execute({"subject": subject_id, "eeg_net": eeg_net, "tissues": tissues})

    def execute(self, args: Dict[str, Any]) -> int:
        from tit.opt.leadfield import LeadfieldGenerator

        pm = get_path_manager()
        if not pm.project_dir:
            raise RuntimeError("Project directory not resolved. In Docker set PROJECT_DIR_NAME so /mnt/<name> exists.")

        subject_id = str(args["subject"])
        m2m_dir = pm.get_m2m_dir(subject_id)
        if not m2m_dir:
            raise RuntimeError(f"m2m directory not found for subject {subject_id}")

        eeg_pos_dir = pm.get_eeg_positions_dir(subject_id)
        if not eeg_pos_dir:
            raise RuntimeError(f"EEG positions directory not found for subject {subject_id}")

        eeg_net = str(args["eeg_net"])
        eeg_cap_path = str(Path(eeg_pos_dir) / eeg_net)
        if not Path(eeg_cap_path).exists():
            raise RuntimeError(f"EEG cap CSV not found: {eeg_cap_path}")

        tissues = [int(x.strip()) for x in str(args.get("tissues", "1,2")).split(",") if x.strip()]
        if not tissues:
            tissues = [1, 2]

        out_dir = pm.get_leadfield_dir(subject_id)
        if not out_dir:
            raise RuntimeError("Leadfield output dir could not be resolved.")

        gen = LeadfieldGenerator(m2m_dir, electrode_cap=eeg_net)
        gen.generate_leadfield(output_dir=str(out_dir), tissues=tissues, eeg_cap_path=eeg_cap_path)
        utils.echo_success(f"Leadfield created in: {out_dir}")
        return 0


if __name__ == "__main__":
    raise SystemExit(CreateLeadfieldCLI().run())


