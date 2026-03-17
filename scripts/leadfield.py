#!/usr/bin/env simnibs_python

import tit
tit.init()

from tit.opt.leadfield import LeadfieldGenerator


SUBJECTS = ["101", "ernie"]

for subject_id in SUBJECTS:
    lfg = LeadfieldGenerator(subject_id, electrode_cap="GSN-HydroCel-185")
    lf = lfg.generate()
