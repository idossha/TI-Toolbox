
from tit.opt.leadfield import LeadfieldGenerator


SUBJECT_ID = "101"
lfg = LeadfieldGenerator(SUBJECT_ID, electrode_cap="GSN-HydroCel-185")
lf = lfg.generate()
