"""Entry point: simnibs_python -m tit.stats.nifti_average config.json

Thin headless runner around :func:`tit.stats.nifti.load_grouped_subjects_ti_toolbox`,
following the same shape as the other ``tit.<module>.__main__`` entry points
(:mod:`tit.sim.__main__`, :mod:`tit.opt.ex.__main__`, ...): read the spec, initialise
:class:`~tit.paths.PathManager`, build the typed config via
:func:`tit.config_io.deserialize_config`, run, emit stage/artifact/result/exit events, exit
``0``/``1``.

Implements the "NIfTI Group Averaging" panel of the desktop app: compute one mean
NIfTI per group in :class:`~tit.stats.nifti_average_config.NiftiAverageConfig`'s *subjects*,
then every requested (or, absent an explicit list, every pairwise) group difference.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys

import nibabel as nib
import numpy as np

from tit import constants as const
from tit.config_io import deserialize_config
from tit.jobs import locks
from tit.stats.nifti import load_grouped_subjects_ti_toolbox
from tit.stats.nifti_average_config import NiftiAverageConfig


def main() -> None:
    """Run group NIfTI averaging from a JSON config passed as the first CLI argument."""
    from tit.logger import setup_logging, add_stream_handler

    setup_logging()
    add_stream_handler("tit.stats.nifti_average")
    add_stream_handler(
        "tit.stats.nifti"
    )  # says when a subject's NIfTI is produced on demand
    logger = logging.getLogger("tit.stats.nifti_average")

    from tit.jobs import events
    from tit.paths import get_path_manager

    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    get_path_manager(data.pop("project_dir"))
    config = deserialize_config(NiftiAverageConfig, data)
    subject_ids = sorted({s.subject_id for s in config.subjects})
    lock_cm = locks.hold_for_job("nifti_average", subject_ids, data)

    exit_code = 1
    try:
        with lock_cm:
            events.emit_stage("nifti_average")

            pm = get_path_manager()
            output_dir = os.path.join(
                pm.project_dir,
                const.DIR_DERIVATIVES,
                const.DIR_TI_TOOLBOX,
                "nifti_average",
                config.output_name,
            )
            subject_configs = [
                {
                    "subject_id": s.subject_id,
                    "simulation_name": s.simulation_name,
                    "group": s.group,
                }
                for s in config.subjects
            ]
            logger.info(f"Loading {len(subject_configs)} subject/simulation NIfTIs")
            groups_data, template_img, groups_ids = load_grouped_subjects_ti_toolbox(
                subject_configs,
                nifti_file_pattern=config.nifti_file_pattern,
                dtype=np.float32,
            )

            # A re-run under an existing name replaces that run (the app asks first): an
            # average or difference of a group the new run does not have must not stay
            # beside its outputs and be listed as one of them. Cleared only once every
            # input has been read, so a run that cannot read its inputs replaces nothing.
            if os.path.isdir(output_dir):
                shutil.rmtree(output_dir)
            os.makedirs(output_dir)

            group_averages: dict[str, np.ndarray] = {}
            for group_name, data_4d in groups_data.items():
                logger.info(
                    f"Group {group_name}: averaging {data_4d.shape[-1]} subjects"
                )
                avg_data = np.mean(data_4d, axis=-1).astype(np.float32)
                group_averages[group_name] = avg_data
                output_path = os.path.join(output_dir, f"average_{group_name}.nii.gz")
                nib.save(
                    nib.Nifti1Image(avg_data, template_img.affine, template_img.header),
                    output_path,
                )
                events.emit_artifact(
                    output_path, kind="nifti", label=f"average ({group_name})"
                )

            # The config resolved every pair to two of its groups (a hyphenated label
            # included) and refused the rest, so each requested map is written.
            differences: list[str] = []
            for group1, group2 in config.difference_pairs():
                diff_data = (group_averages[group1] - group_averages[group2]).astype(
                    np.float32
                )
                output_path = os.path.join(
                    output_dir, f"difference_{group1}_minus_{group2}.nii.gz"
                )
                nib.save(
                    nib.Nifti1Image(
                        diff_data, template_img.affine, template_img.header
                    ),
                    output_path,
                )
                events.emit_artifact(
                    output_path, kind="nifti", label=f"{group1} - {group2}"
                )
                differences.append(f"{group1} - {group2}")

            config_path_out = os.path.join(output_dir, "config.json")
            with open(config_path_out, "w") as f:
                json.dump(
                    {
                        "output_name": config.output_name,
                        "nifti_file_pattern": config.nifti_file_pattern,
                        "space": config.space.value,
                        "groups": groups_ids,
                        "differences": differences,
                    },
                    f,
                    indent=2,
                )
            events.emit_artifact(config_path_out, kind="json", label="config")

            exit_code = 0
            events.emit_result(
                {
                    "success": True,
                    "output_dir": output_dir,
                    "groups": sorted(group_averages),
                    "differences": differences,
                }
            )
    except Exception as exc:  # noqa: BLE001 - report, don't crash the process silently
        logger.error(f"nifti_average failed: {exc}")
        events.emit_result({"success": False, "error": str(exc)})
        exit_code = 1
    finally:
        events.emit_exit(exit_code)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
