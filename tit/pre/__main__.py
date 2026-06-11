"""
CLI entry point for the preprocessing package.

Usage::

    simnibs_python -m tit.pre config.json

Reads a JSON configuration file and delegates to ``run_pipeline``.

See Also
--------
tit.pre.structural.run_pipeline : Pipeline function invoked by this entry point.
"""

import json
import sys

from tit.paths import get_path_manager
from tit.pre.structural import run_pipeline


def main() -> None:
    """Parse a JSON config and run the preprocessing pipeline."""
    if len(sys.argv) < 2:
        sys.exit("Usage: simnibs_python -m tit.pre <config.json>")

    config_path = sys.argv[1]
    try:
        with open(config_path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"Could not read config file {config_path}: {exc}")

    for key in ("project_dir", "subject_ids"):
        if key not in data:
            sys.exit(f"Config file {config_path} is missing required key: {key}")

    from tit.logger import setup_logging, add_stream_handler

    setup_logging()
    add_stream_handler("tit.pre")

    get_path_manager(data.pop("project_dir"))

    exit_code = run_pipeline(
        subject_ids=data["subject_ids"],
        convert_dicom=data.get("convert_dicom", False),
        run_recon=data.get("run_recon", False),
        parallel_recon=data.get("parallel_recon", False),
        parallel_cores=data.get("parallel_cores"),
        create_m2m=data.get("create_m2m", False),
        run_tissue_analysis=data.get("run_tissue_analysis", False),
        run_qsiprep=data.get("run_qsiprep", False),
        run_qsirecon=data.get("run_qsirecon", False),
        qsiprep_config=data.get("qsiprep_config"),
        qsi_recon_config=data.get("qsi_recon_config"),
        extract_dti=data.get("extract_dti", False),
        run_subcortical_segmentations=data.get("run_subcortical_segmentations", False),
        skip_existing_outputs=data.get("skip_existing_outputs", False),
        replace_existing_outputs=data.get("replace_existing_outputs", False),
    )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
