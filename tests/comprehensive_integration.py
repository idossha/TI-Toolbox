#!/usr/bin/env simnibs_python
"""Comprehensive release-gate integration pipeline.

This script is intentionally *not* part of the default pytest suite.  It runs
real computational steps against the Dockerfile.test environment and should be
launched through ``tests/run_comprehensive_integration.sh``.

Covered phases:
1. real DICOM conversion through dcm2niix
2. real SimNIBS CHARM on the baked anatomical fixture
3. real TI simulation on ErnieExtended fixture data
4. real flex-search with the focality objective
5. real leadfield generation
6. real exhaustive search with a pooled six-electrode candidate set
7. real mesh and voxel Analyzer runs
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
import time
from pathlib import Path

from tit.analyzer import Analyzer
from tit.opt import ExConfig, FlexConfig, run_ex_search, run_flex_search
from tit.opt.leadfield import LeadfieldGenerator
from tit.paths import get_path_manager, reset_path_manager
from tit.pre import run_pipeline
from tit.pre.dicom2nifti import run_dicom_to_nifti
from tit.sim import Montage, SimulationConfig, run_simulation

LOG = logging.getLogger("tit.comprehensive_integration")


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def _phase(name: str):
    class Phase:
        def __enter__(self):
            self.start = time.time()
            LOG.info("\n%s\nSTART %s\n%s", "=" * 80, name, "=" * 80)

        def __exit__(self, exc_type, exc, tb):
            elapsed = time.time() - self.start
            if exc_type is None:
                LOG.info("DONE %s (%.1fs)", name, elapsed)
            else:
                LOG.exception("FAILED %s after %.1fs", name, elapsed)
            return False

    return Phase()


def _clear_directory(path: Path) -> None:
    """Remove directory contents without removing *path* itself.

    The work directory is often a Docker bind-mount root, so rmtree(path) can
    fail with EBUSY even though deleting its contents is safe.
    """
    path.mkdir(parents=True, exist_ok=True)
    for item in path.iterdir():
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink()


def _copy_fixture_project(src: Path, dest: Path) -> None:
    _clear_directory(dest)
    ignore = shutil.ignore_patterns("Analyses", "*.html", "logs")
    for item in src.iterdir():
        if item.name in {"Analyses", "logs"} or item.name.endswith(".html"):
            continue
        target = dest / item.name
        if item.is_dir() and not item.is_symlink():
            shutil.copytree(item, target, ignore=ignore)
        else:
            shutil.copy2(item, target)


def _default_dicom_source(fixture_project: Path) -> Path:
    """Return a deterministic DICOM fixture available inside Dockerfile.test."""
    project_fixture = (
        fixture_project / "sourcedata" / "sub-dicom_fixture" / "T1w" / "dicom"
    )
    if project_fixture.is_dir() and any(project_fixture.iterdir()):
        return project_fixture

    # Fallback for the currently published test image: nibabel ships tiny DICOMs
    # in SimNIBS's Python environment. Dockerfile.test/entrypoint_test.sh now
    # also copies these into /mnt/test_projectdir for future image builds.
    import nibabel

    nibabel_fixture = Path(nibabel.__file__).resolve().parent / "tests" / "data"
    dicoms = sorted(nibabel_fixture.glob("*.dcm"))
    if dicoms:
        return nibabel_fixture
    raise FileNotFoundError("No DICOM fixture found in Dockerfile.test environment")


def _prepare_dicom_source(project: Path, subject: str, source: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"DICOM source not found: {source}")

    modality = project / "sourcedata" / f"sub-{subject}" / "T1w"
    dicom_dir = modality / "dicom"
    dicom_dir.mkdir(parents=True, exist_ok=True)

    if source.is_file():
        shutil.copy2(source, modality / source.name)
        return

    files = [
        p
        for p in source.rglob("*")
        if p.is_file() and p.suffix.lower() in {".dcm", ".dicom"}
    ]
    if not files:
        raise FileNotFoundError(f"No files found under DICOM source: {source}")

    # Keep nested layouts small and deterministic for dcm2niix.
    for file in files:
        rel = file.relative_to(source)
        target = dicom_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)


def _run_dicom_conversion(project: Path, dicom_source: Path, subject: str) -> None:
    _prepare_dicom_source(project, subject, dicom_source)
    LOG.info("Prepared DICOM directory fixture: %s", dicom_source)

    run_dicom_to_nifti(str(project), subject, logger=LOG)
    anat_dir = project / f"sub-{subject}" / "anat"
    converted = sorted(anat_dir.glob(f"sub-{subject}_T1w*"))
    if not converted:
        raise AssertionError(f"DICOM conversion did not create output in {anat_dir}")
    LOG.info("DICOM conversion outputs: %s", ", ".join(str(p) for p in converted))


def _run_charm(project: Path, subject: str) -> None:
    run_pipeline(
        [subject],
        convert_dicom=False,
        create_m2m=True,
        run_recon=False,
        run_tissue_analysis=False,
    )
    m2m = project / "derivatives" / "SimNIBS" / f"sub-{subject}" / f"m2m_{subject}"
    if not m2m.is_dir():
        raise AssertionError(f"CHARM did not create m2m directory: {m2m}")


def _run_simulation(subject: str) -> str:
    simulation = "comprehensive_ti"
    montage = Montage(
        name=simulation,
        mode=Montage.Mode.NET,
        electrode_pairs=[("Fp1", "Fp2"), ("C3", "C4")],
        eeg_net="EEG10-10_Cutini_2011.csv",
    )
    config = SimulationConfig(
        subject_id=subject,
        montages=[montage],
        conductivity="scalar",
        intensities=[1.0, 1.0],
        electrode_shape="ellipse",
        electrode_dimensions=[8.0, 8.0],
        gel_thickness=4.0,
        rubber_thickness=2.0,
        map_to_mni=True,
    )
    results = run_simulation(config, logger=LOG)
    if not results or results[0]["status"] != "completed":
        raise AssertionError(f"Simulation failed or returned no result: {results}")
    return simulation


def _run_flex_focality(project: Path, subject: str) -> None:
    output = (
        project
        / "derivatives"
        / "SimNIBS"
        / f"sub-{subject}"
        / "flex-search"
        / "comprehensive_focality"
    )
    cfg = FlexConfig(
        subject_id=subject,
        goal=FlexConfig.OptGoal.FOCALITY,
        postproc=FlexConfig.FieldPostproc.MAX_TI,
        current_mA=2.0,
        electrode=FlexConfig.ElectrodeConfig(),
        roi=FlexConfig.SphericalROI(x=0.0, y=-20.0, z=40.0, radius=10.0),
        non_roi_method=FlexConfig.NonROIMethod.EVERYTHING_ELSE,
        thresholds="0.05,0.10",
        output_folder=str(output),
        n_multistart=1,
        max_iterations=1,
        population_size=2,
        tolerance=0.5,
        cpus=1,
        enable_mapping=True,
        eeg_net="EEG10-10_Cutini_2011.csv",
        disable_mapping_simulation=True,
    )
    result = run_flex_search(cfg)
    if not result.success:
        raise AssertionError(f"Flex focality search failed: {result}")


def _run_leadfield_and_ex_search(project: Path, subject: str) -> None:
    cap = "EEG10-10_Cutini_2011"
    leadfield = LeadfieldGenerator(subject, electrode_cap=cap).generate(cleanup=True)
    if not leadfield.exists():
        raise AssertionError(f"Leadfield not created: {leadfield}")

    pm = get_path_manager()
    roi_dir = Path(pm.rois(subject))
    roi_dir.mkdir(parents=True, exist_ok=True)
    roi_file = roi_dir / "comprehensive_roi.csv"
    roi_file.write_text("0,-20,40\n", encoding="utf-8")

    cfg = ExConfig(
        subject_id=subject,
        leadfield_hdf=leadfield.name,
        roi_name=roi_file.name,
        electrodes=ExConfig.PoolElectrodes(["Fp1", "Fp2", "F3", "F4", "C3", "C4"]),
        total_current=2.0,
        current_step=1.0,
        channel_limit=1.0,
        roi_radius=10.0,
        run_name="comprehensive_ex_pool6",
    )
    result = run_ex_search(cfg)
    if (
        not result.success
        or not result.results_csv
        or not Path(result.results_csv).exists()
    ):
        raise AssertionError(f"Ex-search failed: {result}")


def _run_analysis(subject: str, simulation: str) -> None:
    for space in ("mesh", "voxel"):
        analyzer = Analyzer(subject, simulation, space=space, tissue_type="GM")
        result = analyzer.analyze_sphere(
            center=(0.0, -20.0, 40.0),
            radius=10.0,
            coordinate_space="subject",
            visualize=True,
        )
        if result.n_elements <= 0:
            raise AssertionError(f"{space} analysis returned empty ROI: {result}")
        LOG.info(
            "%s analysis roi_mean=%.6f roi_max=%.6f",
            space,
            result.roi_mean,
            result.roi_max,
        )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-project", default="/mnt/test_projectdir")
    parser.add_argument("--work-dir", default="/tmp/tit_comprehensive_integration")
    parser.add_argument("--subject", default="ernie_extended")
    parser.add_argument("--dicom-subject", default="comprehensive_dicom")
    parser.add_argument(
        "--dicom-source",
        default=os.environ.get("TIT_COMPREHENSIVE_DICOM_SOURCE"),
        help="DICOM directory or supported compressed file visible inside the container. Defaults to the Dockerfile.test fixture.",
    )
    parser.add_argument("--skip-dicom", action="store_true")
    parser.add_argument("--skip-charm", action="store_true")
    parser.add_argument("--skip-flex", action="store_true")
    parser.add_argument("--skip-leadfield-ex", action="store_true")
    parser.add_argument("--keep-work", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    args = parse_args(argv or sys.argv[1:])

    if os.environ.get("TIT_RUN_COMPREHENSIVE") != "1":
        raise SystemExit(
            "Refusing to run heavy comprehensive integration without TIT_RUN_COMPREHENSIVE=1"
        )

    fixture = Path(args.fixture_project)
    project = Path(args.work_dir)
    if not fixture.is_dir():
        raise FileNotFoundError(f"Fixture project not found: {fixture}")

    with _phase("prepare isolated project copy"):
        _copy_fixture_project(fixture, project)
        reset_path_manager()
        get_path_manager(str(project))
        LOG.info("Working project: %s", project)

    if not args.skip_dicom:
        dicom_source = (
            Path(args.dicom_source)
            if args.dicom_source
            else _default_dicom_source(fixture)
        )
        with _phase("DICOM conversion via dcm2niix"):
            _run_dicom_conversion(project, dicom_source, args.dicom_subject)

    if not args.skip_charm:
        # CHARM uses the anatomical T1 baked into the test image. The tiny DICOM
        # fixture is for conversion coverage only and is not a valid head MRI.
        charm_subject = "comprehensive_charm"
        anat_dir = project / f"sub-{charm_subject}" / "anat"
        anat_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            project
            / "derivatives"
            / "SimNIBS"
            / f"sub-{args.subject}"
            / f"m2m_{args.subject}"
            / "T1.nii.gz",
            anat_dir / f"sub-{charm_subject}_T1w.nii.gz",
        )
        with _phase("SimNIBS CHARM"):
            _run_charm(project, charm_subject)

    with _phase("real TI simulation"):
        simulation = _run_simulation(args.subject)

    if not args.skip_flex:
        with _phase("flex-search focality"):
            _run_flex_focality(project, args.subject)

    if not args.skip_leadfield_ex:
        with _phase("leadfield generation + ex-search pooled six electrodes"):
            _run_leadfield_and_ex_search(project, args.subject)

    with _phase("Analyzer mesh and voxel"):
        _run_analysis(args.subject, simulation)

    if not args.keep_work:
        LOG.info("Removing work directory: %s", project)
        shutil.rmtree(project, ignore_errors=True)
    else:
        LOG.info("Keeping work directory: %s", project)

    LOG.info("Comprehensive integration completed successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
