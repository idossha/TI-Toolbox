#!/usr/bin/env simnibs_python
"""
TI-Toolbox Pre-process CLI.

Docker-first:
- Interactive default (no args)
- Direct mode via flags
- Project dir is auto-resolved via `tit.core.get_path_manager().project_dir`
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from tit.cli.base import ArgumentDefinition, BaseCLI
from tit.cli import utils
from tit.core import get_path_manager
from tit.pre.structural import run_pipeline
from tit.pre.common import ensure_subject_dirs


def _ensure_subject_dirs(project_dir: Path, subject_id: str) -> None:
    ensure_subject_dirs(str(project_dir), subject_id)


class PreProcessCLI(BaseCLI):
    def __init__(self) -> None:
        super().__init__(
            "Run preprocessing pipeline (structural / m2m / atlas / tissue analysis)."
        )
        self.add_argument(
            ArgumentDefinition(
                name="subjects",
                type=str,
                nargs="+",
                help="Subject IDs (comma-separated or space-separated).",
                required=True,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="convert_dicom",
                type=bool,
                help="Convert dicom to nifti",
                default=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="run_recon",
                type=bool,
                help="Run FreeSurfer recon-all",
                default=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="parallel_recon",
                type=bool,
                help="Run recon-all in parallel across subjects",
                default=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="create_m2m",
                type=bool,
                help="Create SimNIBS m2m folder (charm)",
                default=False,
            )
        )
        self.add_argument(
            ArgumentDefinition(
                name="run_tissue_analysis",
                type=bool,
                help="Run tissue analyzer",
                default=False,
            )
        )

    def run_interactive(self) -> int:
        pm = get_path_manager()

        utils.echo_header("Pre-process (interactive)")
        project_dir = Path(pm.project_dir)
        # Try to list existing subject folders (does not require m2m yet)
        existing: List[str] = []
        for base in [
            project_dir / "sourcedata",
            project_dir / "derivatives" / "SimNIBS",
            project_dir,
        ]:
            if base.is_dir():
                for p in sorted(base.glob("sub-*")):
                    if p.is_dir():
                        existing.append(p.name.replace("sub-", ""))
        existing = list(dict.fromkeys(existing))

        if existing:
            selected = self.select_many(
                prompt_text="Select subjects",
                options=existing,
                help_text="Pick one or more subject IDs",
            )
            subjects = ",".join(selected)
        else:
            subjects = utils.ask_required("Subjects (comma-separated, e.g. 101,102)")

        convert_dicom = utils.ask_bool("Convert DICOM?", default=False)
        run_recon = utils.ask_bool("Run recon-all?", default=False)
        parallel_recon = utils.ask_bool("Use --parallel recon-all?", default=False)
        create_m2m = utils.ask_bool("Create m2m (charm)?", default=False)
        run_tissue_analysis = utils.ask_bool("Run tissue analysis?", default=False)

        if not utils.review_and_confirm(
            "Review (pre-process)",
            items=[
                ("Subjects", subjects),
                ("Convert DICOM", "yes" if convert_dicom else "no"),
                ("Run recon-all", "yes" if run_recon else "no"),
                ("Parallel recon", "yes" if parallel_recon else "no"),
                ("Create m2m", "yes" if create_m2m else "no"),
                ("Tissue analysis", "yes" if run_tissue_analysis else "no"),
            ],
            default_yes=True,
        ):
            utils.echo_warning("Cancelled.")
            return 0

        return self.execute(
            dict(
                subjects=subjects,
                convert_dicom=convert_dicom,
                run_recon=run_recon,
                parallel_recon=parallel_recon,
                create_m2m=create_m2m,
                run_tissue_analysis=run_tissue_analysis,
            )
        )

    def execute(self, args: Dict[str, Any]) -> int:
        pm = get_path_manager()
        project_dir = Path(pm.project_dir)

        subject_ids = utils.split_csv_or_tokens(args.get("subjects"))
        if not subject_ids:
            raise RuntimeError("No subjects provided.")

        for sid in subject_ids:
            _ensure_subject_dirs(project_dir, sid)
        return run_pipeline(
            str(project_dir),
            subject_ids,
            convert_dicom=bool(args.get("convert_dicom", False)),
            run_recon=bool(args.get("run_recon", False)),
            parallel_recon=bool(args.get("parallel_recon", False)),
            create_m2m=bool(args.get("create_m2m", False)),
            run_tissue_analysis=bool(args.get("run_tissue_analysis", False)),
        )


if __name__ == "__main__":
    raise SystemExit(PreProcessCLI().run())
