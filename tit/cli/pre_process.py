#!/usr/bin/env simnibs_python
"""
TI-Toolbox Pre-process CLI.

Docker-first:
- Interactive default (no args)
- Direct mode via flags
- Project dir is auto-resolved via `tit.core.get_path_manager().project_dir`
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List

from tit.cli.base import ArgumentDefinition, BaseCLI
from tit.cli import utils
from tit.core import get_path_manager


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _script_path(name: str) -> Path:
    return _repo_root() / "tit" / "pre" / name


def _ensure_subject_dirs(project_dir: Path, subject_id: str) -> None:
    # Centralize directory conventions in PathManager.
    pm = get_path_manager()
    pm.project_dir = str(project_dir)

    for modality in ("T1w", "T2w"):
        Path(pm.path("sourcedata_dicom", subject_id=subject_id, modality=modality)).mkdir(parents=True, exist_ok=True)

    Path(pm.path("bids_anat", subject_id=subject_id)).mkdir(parents=True, exist_ok=True)
    Path(pm.path("freesurfer_subject", subject_id=subject_id)).mkdir(parents=True, exist_ok=True)
    Path(pm.path("simnibs"), f"sub-{subject_id}").mkdir(parents=True, exist_ok=True)


def _run_structural(
    project_dir: Path,
    subject_ids: List[str],
    *,
    convert_dicom: bool,
    run_recon: bool,
    parallel_recon: bool,
    create_m2m: bool,
) -> int:
    structural = _script_path("structural.sh")
    if not structural.exists():
        raise RuntimeError(f"Missing structural script: {structural}")

    cmd: List[str] = [str(structural)]
    for sid in subject_ids:
        cmd.append(str(project_dir / f"sub-{sid}"))

    if run_recon:
        cmd.append("recon-all")
        if parallel_recon:
            cmd.append("--parallel")
    if convert_dicom:
        cmd.append("--convert-dicom")
    if create_m2m:
        cmd.append("--create-m2m")

    return subprocess.call(cmd)


def _run_atlas_creation(project_dir: Path, subject_ids: List[str]) -> int:
    """Run atlas creation for the given subjects."""
    atlas_script = _script_path("subject_atlas.sh")
    if not atlas_script.exists():
        raise RuntimeError(f"Missing atlas script: {atlas_script}")

    cmd: List[str] = [str(atlas_script)]
    for sid in subject_ids:
        cmd.append(str(project_dir / f"sub-{sid}"))

    return subprocess.call(cmd)


def _run_tissue_analysis(project_dir: Path, subject_ids: List[str]) -> int:
    """Run tissue analysis for the given subjects."""
    pm = get_path_manager()
    pm.project_dir = str(project_dir)

    tissue_script = _script_path("tissue-analyzer.sh")
    if not tissue_script.exists():
        raise RuntimeError(f"Missing tissue analyzer script: {tissue_script}")

    for sid in subject_ids:
        # Get the tissue labeling file path using path manager
        label_nii_path = pm.path("tissue_labeling", subject_id=sid)

        if not pm.is_file("tissue_labeling", subject_id=sid):
            raise RuntimeError(f"Labeling.nii.gz not found for subject {sid} at {label_nii_path}")

        # Ensure output directory exists using path manager
        tissue_out_dir = pm.ensure_dir("tissue_analysis_output", subject_id=sid)

        # Run tissue analysis
        cmd = [str(tissue_script), label_nii_path, "-o", tissue_out_dir]
        exit_code = subprocess.call(cmd)
        if exit_code != 0:
            return exit_code

    return 0


class PreProcessCLI(BaseCLI):
    def __init__(self) -> None:
        super().__init__("Run preprocessing pipeline (structural / m2m / atlas / tissue analysis).")
        self.add_argument(ArgumentDefinition(name="subjects", type=str, nargs="+", help="Subject IDs (comma-separated or space-separated).", required=True))
        self.add_argument(ArgumentDefinition(name="convert_dicom", type=bool, help="Convert dicom to nifti", default=False))
        self.add_argument(ArgumentDefinition(name="run_recon", type=bool, help="Run FreeSurfer recon-all", default=False))
        self.add_argument(ArgumentDefinition(name="parallel_recon", type=bool, help="Pass --parallel to recon-all", default=False))
        self.add_argument(ArgumentDefinition(name="create_m2m", type=bool, help="Create SimNIBS m2m folder (charm)", default=False))

        # keep these toggles but do not re-implement heavy logic here (reduce bloat)
        self.add_argument(ArgumentDefinition(name="create_atlas", type=bool, help="Create subject atlases (calls subject_atlas)", default=False))
        self.add_argument(ArgumentDefinition(name="run_tissue_analysis", type=bool, help="Run tissue analyzer (tissue-analyzer.sh)", default=False))

    def run_interactive(self) -> int:
        pm = get_path_manager()

        utils.echo_header("Pre-process (interactive)")
        project_dir = Path(pm.project_dir)
        # Try to list existing subject folders (does not require m2m yet)
        existing: List[str] = []
        for base in [project_dir / "sourcedata", project_dir / "derivatives" / "SimNIBS", project_dir]:
            if base.is_dir():
                for p in sorted(base.glob("sub-*")):
                    if p.is_dir():
                        existing.append(p.name.replace("sub-", ""))
        existing = list(dict.fromkeys(existing))

        if existing:
            selected = self.select_many(prompt_text="Select subjects", options=existing, help_text="Pick one or more subject IDs")
            subjects = ",".join(selected)
        else:
            subjects = utils.ask_required("Subjects (comma-separated, e.g. 101,102)")

        convert_dicom = utils.ask_bool("Convert DICOM?", default=False)
        run_recon = utils.ask_bool("Run recon-all?", default=False)
        parallel_recon = utils.ask_bool("Use --parallel recon-all?", default=False)
        create_m2m = utils.ask_bool("Create m2m (charm)?", default=False)
        create_atlas = utils.ask_bool("Create atlas?", default=False)
        run_tissue_analysis = utils.ask_bool("Run tissue analysis?", default=False)

        if not utils.review_and_confirm(
            "Review (pre-process)",
            items=[
                ("Subjects", subjects),
                ("Convert DICOM", "yes" if convert_dicom else "no"),
                ("Run recon-all", "yes" if run_recon else "no"),
                ("Parallel recon", "yes" if parallel_recon else "no"),
                ("Create m2m", "yes" if create_m2m else "no"),
                ("Create atlas", "yes" if create_atlas else "no"),
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
                create_atlas=create_atlas,
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

        # Run structural preprocessing (DICOM conversion, recon-all, m2m creation)
        exit_code = _run_structural(
            project_dir,
            subject_ids,
            convert_dicom=bool(args.get("convert_dicom", False)),
            run_recon=bool(args.get("run_recon", False)),
            parallel_recon=bool(args.get("parallel_recon", False)),
            create_m2m=bool(args.get("create_m2m", False)),
        )
        if exit_code != 0:
            return exit_code

        # Run atlas creation if requested
        if bool(args.get("create_atlas", False)):
            exit_code = _run_atlas_creation(project_dir, subject_ids)
            if exit_code != 0:
                return exit_code

        # Run tissue analysis if requested
        if bool(args.get("run_tissue_analysis", False)):
            exit_code = _run_tissue_analysis(project_dir, subject_ids)
            if exit_code != 0:
                return exit_code

        return 0


if __name__ == "__main__":
    raise SystemExit(PreProcessCLI().run())


