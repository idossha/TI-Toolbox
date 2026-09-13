"""SimNIBS worker for explicit EEG forward inputs from an external study layout.

Run ``simnibs_python -m tit.source._forward_inputs --help``. Scientific logic
lives in ``prepare_forward``; this worker only loads MNE metadata and arguments.
"""

from __future__ import annotations

import argparse

import mne

from tit.source.config import ForwardConfig
from tit.source.forward import prepare_forward


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("subject_id")
    parser.add_argument("head_model_dir")
    parser.add_argument("output_dir")
    parser.add_argument("--info", help="FIF recording/Info with digitized fiducials")
    parser.add_argument("--trans", help="FIF head-to-MRI transform")
    parser.add_argument("--eeg-net", required=True)
    parser.add_argument("--spacing", type=int, default=5)
    parser.add_argument("--cpus", type=int, default=1)
    parser.add_argument("--output-stem")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    config = ForwardConfig(
        eeg_net=args.eeg_net,
        fsaverage_spacing=args.spacing,
        cpus=args.cpus,
        overwrite=args.overwrite,
    )
    info = mne.io.read_info(args.info, verbose=False) if args.info else None
    trans = mne.read_trans(args.trans, verbose=False) if args.trans else None
    outputs = prepare_forward(
        args.subject_id,
        config,
        output_dir=args.output_dir,
        head_model_dir=args.head_model_dir,
        info=info,
        trans=trans,
        output_stem=args.output_stem,
    )
    for output in outputs:
        print(output)


if __name__ == "__main__":
    main()
