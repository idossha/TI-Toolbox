#!/usr/bin/env simnibs_python

from tit.opt.leadfield import LeadfieldGenerator


SUBJECTS = ["ernie"]

for subject_id in SUBJECTS:
    lfg = LeadfieldGenerator(subject_id, electrode_cap="GSN-HydroCel-185")
    lf = lfg.generate()
