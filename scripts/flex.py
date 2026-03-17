#!/usr/bin/env simnibs_python
 
from tit.opt.flex import FlexConfig, run_flex_search

import tit
tit.init()


SUBJECTS = ["ernie"]

for subject_id in SUBJECTS:
    flex_config = FlexConfig(
        subject_id=subject_id,
        project_dir=PROJECT_DIR,
        goal="mean",
        postproc="max_TI",
        current_mA=2.0,
        electrode=FlexConfig.ElectrodeConfig(),
        roi=FlexConfig.SphericalROI(x=10, y=0, z=0, radius=10.0),
    )
    run_flex_search(flex_config)

