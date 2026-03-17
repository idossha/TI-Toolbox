"""Entry point: simnibs_python -m tit.pre config.json"""


import json
import sys

from tit.pre.structural import run_pipeline


def main() -> None:
    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    from tit.logger import add_stream_handler

    add_stream_handler("tit.pre")

    exit_code = run_pipeline(
        project_dir=data["project_dir"],
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
    )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
