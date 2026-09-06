"""Entry point: simnibs_python -m tit.plotting.nilearn config.json

Thin headless runner around this package's ``create_pdf_entry_point_group`` /
``create_glass_brain_entry_point_group`` helpers, following the same shape as the other
``tit.<module>.__main__`` entry points (:mod:`tit.sim.__main__`, :mod:`tit.opt.ex.__main__`,
...): read the spec, initialise :class:`~tit.paths.PathManager`, build the typed config via
:func:`tit.config_io.deserialize_config`, run, emit stage/artifact/result/exit events, exit
``0``/``1``.

Mirrors the "Nilearn Visuals" GUI extension (``tit/gui/extensions/nilearn_viz.py``) without any
Qt dependency: group-average the requested subject/simulation NIfTIs, then render the multi-slice
PDF (and, optionally, a glass-brain PDF) from that average.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from contextlib import nullcontext
from datetime import datetime

import nibabel as nib
import numpy as np

from tit import constants as const
from tit.config_io import deserialize_config
from tit.plotting.nilearn.config import NilearnConfig
from tit.plotting.nilearn.cutoffs import (
    blank_figure_warning,
    field_summary,
    resolve_cutoffs,
)
from tit.plotting.nilearn.img_glass import create_glass_brain_entry_point_group
from tit.plotting.nilearn.img_slices import create_pdf_entry_point_group
from tit.stats.nifti import load_group_data_ti_toolbox

#: Same default the GUI extension uses (MNI-space TI_max); this runner has no
#: equivalent of ``tit.stats.nifti_average_config.NiftiAverageSpace`` since it
#: always visualises the MNI group average.
_NIFTI_FILE_PATTERN = "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"


def _hold_locks(kind: str, subject_ids: list[str], config_dict: dict):
    """Best-effort lock scaffold: a no-op unless running as a ``tit.jobs`` job."""
    from tit.paths import get_path_manager

    try:
        from tit.jobs import locks
        from tit.jobs.runner import ENV_JOB_ID
    except ImportError:
        return nullcontext()
    job_id = os.environ.get(ENV_JOB_ID)
    if not job_id:
        return nullcontext()
    requests = locks.keys_for(kind, subject_ids, config_dict)
    return locks.hold(get_path_manager().project_dir, job_id, requests)


def main() -> None:
    """Run Nilearn Visuals from a JSON config passed as the first CLI argument."""
    from tit.logger import setup_logging, add_stream_handler

    setup_logging()
    add_stream_handler("tit.plotting.nilearn")
    logger = logging.getLogger("tit.plotting.nilearn")

    from tit.jobs import events
    from tit.paths import get_path_manager

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    get_path_manager(data.pop("project_dir"))
    config = deserialize_config(NilearnConfig, data)
    subject_ids = sorted({p.subject_id for p in config.subject_simulation_pairs})
    lock_cm = _hold_locks("nilearn", subject_ids, data)

    exit_code = 1
    try:
        with lock_cm:
            events.emit_stage("nilearn_visuals")

            pm = get_path_manager()
            subject_configs = [
                {"subject_id": p.subject_id, "simulation_name": p.simulation_name}
                for p in config.subject_simulation_pairs
            ]
            logger.info(f"Loading {len(subject_configs)} subject/simulation NIfTIs")
            data_4d, template_img, subject_ids = load_group_data_ti_toolbox(
                subject_configs,
                nifti_file_pattern=_NIFTI_FILE_PATTERN,
                dtype=float,
            )
            averaged_data = np.mean(data_4d, axis=-1)
            averaged_img = nib.Nifti1Image(
                averaged_data, template_img.affine, template_img.header
            )

            # Preflight, before a single figure is drawn: both cutoffs become absolute
            # V/m here (the renderers' own `max_cutoff=None -> 99.9th percentile` rule
            # is applied here instead, so the min<max check below sees the real pair).
            nonzero = averaged_data[averaged_data > 0]
            logger.info(f"Field range: {field_summary(nonzero)}")
            min_cutoff, max_cutoff = resolve_cutoffs(
                nonzero,
                config.min_cutoff,
                config.max_cutoff,
                use_percentiles=config.use_percentiles,
            )
            logger.info(
                f"Display range: {min_cutoff:.4f}-{max_cutoff:.4f} V/m"
                + (" (data-driven default)" if config.min_cutoff is None else "")
            )
            blank = blank_figure_warning(nonzero, min_cutoff)
            if blank:
                logger.warning(blank)

            output_dir = os.path.join(
                pm.project_dir,
                const.DIR_DERIVATIVES,
                const.DIR_TI_TOOLBOX,
                "nilearn_visuals",
                config.subdir_name,
            )
            os.makedirs(output_dir, exist_ok=True)
            base_filename = f"group_averaged_{len(subject_ids)}_subjects"

            nifti_path = os.path.join(output_dir, f"{base_filename}.nii.gz")
            nib.save(averaged_img, nifti_path)
            events.emit_artifact(nifti_path, kind="nifti", label="group average")

            params_path = os.path.join(output_dir, f"{base_filename}_parameters.txt")
            with open(params_path, "w") as f:
                f.write("TI-Toolbox Nilearn Visuals -- Group Averaged Data\n")
                f.write(
                    f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                )
                for pair in subject_configs:
                    f.write(f"{pair['subject_id']}: {pair['simulation_name']}\n")
                f.write(f"\nCutoff range: {min_cutoff:.4f} - {max_cutoff:.4f} V/m\n")
                f.write(f"Atlas: {config.atlas_name}\n")
            events.emit_artifact(params_path, kind="txt", label="parameters")

            pdf_path = create_pdf_entry_point_group(
                averaged_img,
                base_filename,
                output_dir,
                min_cutoff,
                max_cutoff,
                config.atlas_name,
                config.selected_regions,
                output_callback=logger.info,
            )
            if pdf_path:
                events.emit_artifact(pdf_path, kind="pdf", label="multi-slice views")

            glass_brain_path = None
            if config.create_glass_brain:
                glass_brain_path = create_glass_brain_entry_point_group(
                    averaged_img,
                    base_filename,
                    output_dir,
                    min_cutoff,
                    max_cutoff,
                    config.glass_brain_cmap,
                    output_callback=logger.info,
                )
                if glass_brain_path:
                    events.emit_artifact(
                        glass_brain_path, kind="pdf", label="glass brain"
                    )

            if not pdf_path and not glass_brain_path:
                raise RuntimeError("Visualization failed -- check the log for detail")

            exit_code = 0
            events.emit_result(
                {
                    "success": True,
                    "output_dir": output_dir,
                    "n_subjects": len(subject_ids),
                    "min_cutoff": min_cutoff,
                    "max_cutoff": max_cutoff,
                    "pdf": pdf_path,
                    "glass_brain": glass_brain_path,
                }
            )
    except Exception as exc:  # noqa: BLE001 - report, don't crash the process silently
        logger.error(f"nilearn visuals failed: {exc}")
        events.emit_result({"success": False, "error": str(exc)})
        exit_code = 1
    finally:
        events.emit_exit(exit_code)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
