"""
Example to run TESoptimize for Temporal Interference (TI) to optimize the 
focality in the ROI vs non-ROI

Copyright (c) 2024 SimNIBS developers. Licensed under the GPL v3.
"""
import os
import shutil
import numpy as np
from simnibs import opt_struct, ElementTags

# dataset from https://github.com/simnibs/example-dataset/releases/download/v4.0-lowres/ernie_lowres_V2.zip
# to be a bit faster for the demo

for background_intensity in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]:
    """ Run optimization multiple times and keep best solution """
    n_multistart = 5
    optim_funvalue_list = np.zeros(n_multistart)
    output_folder_list = [
        f"tes_optimize_ti_focality_hipp_t0.6_{background_intensity}/{i_opt:02}" for i_opt in range(n_multistart)
    ]

    for i_opt in range(n_multistart):
        ''' Initialize structure '''
        opt = opt_struct.TesFlexOptimization()
        opt.subpath = 'm2m_ernie'                               # path of m2m folder containing the headmodel
        opt.output_folder = output_folder_list[i_opt]
        opt.open_in_gmsh = False

        ''' Set up goal function '''
        opt.goal = "focality"                                   # optimize the focality of "max_TI" in the ROI ("max_TI" defined by e_postproc)
        opt.threshold = [background_intensity, 0.6]             # define threshold(s) of the electric field in V/m in the non-ROI and the ROI:
                                                                # if one threshold is defined, it is the goal that the e-field in the non-ROI is lower than this value and higher than this value in the ROI
                                                                # if two thresholds are defined, the first one is the threshold of the non-ROI and the second one is for the ROI
        opt.e_postproc = "max_TI"                               # postprocessing of e-fields
                                                                # "max_TI": maximal envelope of TI field magnitude
                                                                # "dir_TI_normal": envelope of normal component
                                                                # "dir_TI_tangential": envelope of tangential component
        ''' Define first electrode pair '''
        electrode_layout = opt.add_electrode_layout("ElectrodeArrayPair")   # Pair of TES electrode arrays (here: 1 electrode per array)
        electrode_layout.radius = [10]                                      # radii of electrodes
        electrode_layout.current = [0.002, -0.002]                          # electrode currents

        ''' Define second electrode pair '''
        electrode_layout = opt.add_electrode_layout("ElectrodeArrayPair")
        electrode_layout.radius = [10]
        electrode_layout.current = [0.002, -0.002]

        ''' Define ROI '''
        roi = opt.add_roi()
        roi.method = "volume_from_surface"
        roi.surface_type = "custom"
        roi.surface_path = "lh_hippocampus_roi.msh"
        roi.tissues = [ElementTags.GM]
        roi.surface_inclusion_radius = 5

        ''' Define non-ROI '''
        # make all GM except the hippocampus the non-ROI
        non_roi = opt.add_roi()
        non_roi.method = "volume_from_surface"
        non_roi.surface_type = "custom"
        non_roi.surface_path = "lh_hippocampus_roi.msh"
        non_roi.tissues = [ElementTags.GM]
        non_roi.surface_inclusion_radius = 5

        # unfortunately, this needs a bit of "internal" knowledge so far
        non_roi.subpath = opt.subpath
        non_roi._prepare()
        non_roi.invert() # invert selection --> all tetrahedra except the ROI
        non_roi.apply_tissue_mask(ElementTags.GM, "intersection") # restrict selection to GM
        # write out for visual control
        non_roi.write_visualization('','non-roi')

        ''' Run optimization '''
        opt.run()
        optim_funvalue_list[i_opt] = opt.optim_funvalue

    print(f"{optim_funvalue_list=}")

    """ Identify best solution """
    best_opt_idx = np.argmin(optim_funvalue_list)
    print(f"{best_opt_idx=}")

    """ Keep best solution and remove the others """
    for i_opt in range(n_multistart):
        if i_opt == best_opt_idx:
            shutil.copytree(
                output_folder_list[i_opt],
                os.path.split(output_folder_list[i_opt])[0],
                dirs_exist_ok=True,
            )
        shutil.rmtree(output_folder_list[i_opt])
