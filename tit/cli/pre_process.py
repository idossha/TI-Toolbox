#!/usr/bin/env python3
"""
TI-Toolbox Pre-process CLI (Click).

Replaces `tit/cli/pre-process.sh`.

This CLI orchestrates calls to existing pipeline scripts (e.g. `tit/pre/structural.sh`)
in a more scriptable and testable way.

Direct mode (GUI compatibility):
  simnibs_python -m tit.cli.pre_process --run-direct

Env vars (legacy):
  SUBJECTS="101,102"  PROJECT_DIR="/mnt/<proj>"
  CONVERT_DICOM=true|false
  RUN_RECON=true|false
  PARALLEL_RECON=true|false
  CREATE_M2M=true|false
  CREATE_ATLAS=true|false
  RUN_TISSUE_ANALYSIS=true|false
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List, Optional

import click

from tit.cli import utils

def _default_project_dir_from_env() -> Optional[Path]:
    return utils.default_project_dir_from_env()


def _script_path(name: str) -> Path:
    # tit/cli/pre_process.py -> repo_root is ../../
    repo_root = Path(__file__).resolve().parents[2]
    candidate = repo_root / "tit" / "pre" / name
    return candidate


def _ensure_subject_dirs(project_dir: Path, subject_id: str) -> None:
    bids_subject = f"sub-{subject_id}"
    (project_dir / "sourcedata" / bids_subject / "T1w" / "dicom").mkdir(parents=True, exist_ok=True)
    (project_dir / "sourcedata" / bids_subject / "T2w" / "dicom").mkdir(parents=True, exist_ok=True)
    (project_dir / bids_subject / "anat").mkdir(parents=True, exist_ok=True)
    (project_dir / "derivatives" / "freesurfer" / bids_subject).mkdir(parents=True, exist_ok=True)
    (project_dir / "derivatives" / "SimNIBS" / bids_subject).mkdir(parents=True, exist_ok=True)


def _run_structural(
    project_dir: Path,
    subject_ids: List[str],
    convert_dicom: bool,
    run_recon: bool,
    parallel_recon: bool,
    create_m2m: bool,
) -> int:
    structural = _script_path("structural.sh")
    if not structural.exists():
        raise click.ClickException(f"Missing structural script: {structural}")

    cmd: List[str] = [str(structural)]

    # Add subject directories (structural.sh accepts one or more subject dirs)
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


def _run_atlas_creation(project_dir: Path, subject_id: str, atlases: List[str]) -> None:
    bids_subject = f"sub-{subject_id}"
    m2m_dir = project_dir / "derivatives" / "SimNIBS" / bids_subject / f"m2m_{subject_id}"
    if not m2m_dir.exists():
        raise click.ClickException(f"m2m folder not found for {subject_id}: {m2m_dir}")

    output_dir = m2m_dir / "segmentation"
    output_dir.mkdir(parents=True, exist_ok=True)

    for atlas in atlases:
        cmd = ["subject_atlas", "-m", str(m2m_dir), "-a", atlas, "-o", str(output_dir)]
        rc = subprocess.call(cmd)
        if rc != 0:
            raise click.ClickException(f"subject_atlas failed for {subject_id} atlas={atlas}")


def _run_tissue_analysis(project_dir: Path, subject_id: str) -> None:
    bids_subject = f"sub-{subject_id}"
    m2m_dir = project_dir / "derivatives" / "SimNIBS" / bids_subject / f"m2m_{subject_id}"
    label = m2m_dir / "Labeling.nii.gz"
    if not label.exists():
        raise click.ClickException(f"Labeling.nii.gz not found for {subject_id}: {label}")

    tissue = _script_path("tissue-analyzer.sh")
    if not tissue.exists():
        raise click.ClickException(f"Missing tissue analyzer script: {tissue}")

    out_dir = project_dir / "derivatives" / "ti-toolbox" / "tissue_analysis" / bids_subject
    out_dir.mkdir(parents=True, exist_ok=True)
    rc = subprocess.call(["bash", str(tissue), str(label), "-o", str(out_dir)])
    if rc != 0:
        raise click.ClickException(f"Tissue analysis failed for {subject_id}")


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option("--run-direct", is_flag=True, help="Run using legacy env vars (non-interactive).")
@click.option("--project-dir", type=click.Path(path_type=Path), default=None, help="Project directory (BIDS root).")
@click.option("--subjects", type=str, default=None, help="Comma-separated subject IDs, e.g. 101,102")
@click.option("--convert-dicom/--no-convert-dicom", default=False)
@click.option("--run-recon/--no-run-recon", default=False, help="Run FreeSurfer recon-all")
@click.option("--parallel-recon/--no-parallel-recon", default=False, help="Pass --parallel to structural.sh recon-all")
@click.option("--create-m2m/--no-create-m2m", default=False, help="Create SimNIBS m2m folder (charm)")
@click.option("--create-atlas/--no-create-atlas", default=False, help="Create subject atlases (a2009s/DK40/HCP_MMP1)")
@click.option("--run-tissue-analysis/--no-run-tissue-analysis", default=False)
def cli(
    run_direct: bool,
    project_dir: Optional[Path],
    subjects: Optional[str],
    convert_dicom: bool,
    run_recon: bool,
    parallel_recon: bool,
    create_m2m: bool,
    create_atlas: bool,
    run_tissue_analysis: bool,
) -> None:
    """Preprocess MRI data for TI-Toolbox."""
    if run_direct:
        proj = project_dir or _default_project_dir_from_env()
        if proj is None:
            proj_raw = os.environ.get("PROJECT_DIR")
            if proj_raw:
                proj = Path(proj_raw)
        if proj is None:
            raise click.ClickException("Project directory not found. Set --project-dir or PROJECT_DIR/PROJECT_DIR_NAME.")

        subjects_env = os.environ.get("SUBJECTS")
        if not subjects_env:
            raise click.ClickException("Missing SUBJECTS env var in direct mode")
        subject_ids = [s.strip() for s in subjects_env.split(",") if s.strip()]

        convert_dicom = utils.bool_env("CONVERT_DICOM", default=False)
        run_recon = utils.bool_env("RUN_RECON", default=False)
        parallel_recon = utils.bool_env("PARALLEL_RECON", default=False)
        create_m2m = utils.bool_env("CREATE_M2M", default=False)
        create_atlas = utils.bool_env("CREATE_ATLAS", default=False)
        run_tissue_analysis = utils.bool_env("RUN_TISSUE_ANALYSIS", default=False)
    else:
        proj = project_dir or _default_project_dir_from_env()
        if proj is None:
            proj = Path(click.prompt("Project directory (BIDS root)", type=click.Path(path_type=Path)))

        if not subjects:
            subjects = click.prompt("Subjects (comma-separated IDs, e.g. 101,102)", type=str)
        subject_ids = [s.strip() for s in subjects.split(",") if s.strip()]

    if not subject_ids:
        raise click.ClickException("No subjects specified")

    if parallel_recon and not run_recon:
        raise click.ClickException("--parallel-recon requires --run-recon")

    # Create directories (matches legacy behavior)
    for sid in subject_ids:
        _ensure_subject_dirs(proj, sid)

    # Run structural pipeline
    rc = _run_structural(
        project_dir=proj,
        subject_ids=subject_ids,
        convert_dicom=convert_dicom,
        run_recon=run_recon,
        parallel_recon=parallel_recon,
        create_m2m=create_m2m,
    )
    if rc != 0:
        raise SystemExit(rc)

    # Post steps per subject
    if create_atlas:
        for sid in subject_ids:
            _run_atlas_creation(proj, sid, atlases=["a2009s", "DK40", "HCP_MMP1"])

    if run_tissue_analysis:
        for sid in subject_ids:
            _run_tissue_analysis(proj, sid)

    # Best-effort report generation (mirrors legacy script)
    for sid in subject_ids:
        try:
            from tit.tools.report_util import create_preprocessing_report

            create_preprocessing_report(str(proj), sid)
        except Exception:
            # Non-fatal (matches bash script behavior)
            pass


if __name__ == "__main__":
    cli()


