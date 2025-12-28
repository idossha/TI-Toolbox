#!/usr/bin/env simnibs_python
"""
Test script comparing Bucketed vs All-Combinations (Pooled) modes in Ex-Search

This script demonstrates the difference between:
1. Bucketed Mode: Electrodes grouped into E1+/-, E2+/- (original)
2. All-Combinations Mode: All possible 4-electrode assignments (new)

Using 12 total electrode selections for fair comparison.

Author: Claude Code Agent
Date: 2025-12-28
"""

import numpy as np
import os
import sys
import time
from itertools import product

# Add TI-Toolbox to path
project_root = os.path.join(os.path.dirname(__file__), 'ti-toolbox')
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from simnibs.utils import TI_utils as TI
from core import get_path_manager
from core.roi import find_roi_element_indices, find_grey_matter_indices, calculate_roi_metrics


def load_leadfield_data():
    """
    Load real leadfield data from ernie subject.

    Returns:
        leadfield: Leadfield matrix
        mesh: SimNIBS mesh object
        idx_lf: Leadfield indices
        leadfield_path: Path to leadfield HDF5 file
    """
    print("=" * 80)
    print("Loading Leadfield Data")
    print("=" * 80)

    # Use PathManager to get proper paths
    pm = get_path_manager()
    leadfield_dir = pm.get_leadfield_dir("ernie")

    if not leadfield_dir:
        raise ValueError("Could not determine leadfield directory for ernie subject")

    leadfield_file = os.path.join(leadfield_dir, "ernie_leadfield_EEG10-20_Okamoto_2004.hdf5")
   

    # Check if file exists
    print(f"Looking for leadfield in: {leadfield_dir}")

    if not os.path.exists(leadfield_file):
        raise FileNotFoundError(
            f"Leadfield HDF5 file not found: {leadfield_file}\n"
            f"Please ensure ernie leadfield data is available.\n"
            f"Run leadfield generation for ernie subject first."
        )

    # Load leadfield using SimNIBS TI_utils
    print(f"Loading leadfield from: {leadfield_file}")
    print("This may take a moment...")

    leadfield, mesh, idx_lf = TI.load_leadfield(leadfield_file)

    print(f"  Leadfield shape: {leadfield.shape}")
    print(f"  Mesh elements: {mesh.elm.nr}")
    print(f"  Leadfield indices: {len(idx_lf)}")
    print("=" * 80)

    return leadfield, mesh, idx_lf, leadfield_file


def get_ernie_electrode_names():
    """
    Return the known electrode names for ernie subject (EEG10-20 cap).

    Returns:
        List of electrode names (23 total)
    """
    # Known electrode names for ernie subject
    electrode_names = [
        'Fp1', 'Fp2', 'Fz', 'F3', 'F4', 'F7', 'F8',
        'Cz', 'C3', 'C4', 'T7', 'T8',
        'Pz', 'P3', 'P4', 'P7', 'P8',
        'O1', 'O2',
        'Nz', 'Iz',
        'LPA', 'RPA'
    ]
    return electrode_names


def setup_roi(mesh, roi_center_mni=[0, 0, 40], roi_radius_mm=5.0):
    """
    Set up ROI for testing.

    Args:
        mesh: SimNIBS mesh object
        roi_center_mni: ROI center in MNI coordinates
        roi_radius_mm: ROI radius in mm

    Returns:
        roi_indices: Element indices within ROI
        roi_volumes: Element volumes within ROI
        gm_indices: Grey matter element indices
        gm_volumes: Grey matter element volumes
    """
    print("\n" + "=" * 80)
    print("Setting Up ROI")
    print("=" * 80)
    print(f"ROI center (MNI): {roi_center_mni}")
    print(f"ROI radius: {roi_radius_mm} mm")

    # Find ROI elements
    roi_indices, roi_volumes = find_roi_element_indices(
        mesh, roi_center_mni, radius=roi_radius_mm
    )
    print(f"ROI elements: {len(roi_indices)}")

    # Find grey matter elements for focality calculation
    gm_indices, gm_volumes = find_grey_matter_indices(mesh, grey_matter_tags=[2])
    print(f"Grey matter elements: {len(gm_indices)}")
    print("=" * 80)

    return roi_indices, roi_volumes, gm_indices, gm_volumes


def test_bucketed_mode(leadfield, mesh, idx_lf, electrodes, roi_indices, roi_volumes,
                       gm_indices, gm_volumes, total_current=2.0, current_step=0.5):
    """
    Test bucketed mode: 2 electrodes per group (E1+, E1-, E2+, E2-).

    Total: 2×2×2×2 = 16 electrode combinations (PROOF OF CONCEPT)
    """
    print("\n" + "=" * 80)
    print("TEST 1: BUCKETED MODE (Original) - PROOF OF CONCEPT")
    print("=" * 80)

    # Select 8 electrodes and split into 4 groups of 2
    selected_electrodes = electrodes[:8]
    E1_plus = selected_electrodes[0:2]
    E1_minus = selected_electrodes[2:4]
    E2_plus = selected_electrodes[4:6]
    E2_minus = selected_electrodes[6:8]

    print(f"E1+ electrodes: {E1_plus}")
    print(f"E1- electrodes: {E1_minus}")
    print(f"E2+ electrodes: {E2_plus}")
    print(f"E2- electrodes: {E2_minus}")

    # Fixed current ratio (proof of concept - no variations)
    current_ratios = [(1.0, 1.0)]  # 1 mA per channel
    print(f"\nCurrent ratio (fixed): {current_ratios[0]} mA")

    # Calculate total combinations
    n_electrode_combinations = len(E1_plus) * len(E1_minus) * len(E2_plus) * len(E2_minus)
    n_current_ratios = len(current_ratios)
    total_combinations = n_electrode_combinations * n_current_ratios

    print(f"\nElectrode combinations: {len(E1_plus)} × {len(E1_minus)} × {len(E2_plus)} × {len(E2_minus)} = {n_electrode_combinations}")
    print(f"Current ratios: {n_current_ratios}")
    print(f"TOTAL COMBINATIONS: {total_combinations}")
    print("=" * 80)

    # Run simulations
    results = []
    start_time = time.time()

    combinations_iter = product(E1_plus, E1_minus, E2_plus, E2_minus, current_ratios)

    for idx, (e1_plus, e1_minus, e2_plus, e2_minus, (current_ch1_mA, current_ch2_mA)) in \
            enumerate(combinations_iter, 1):

        # Calculate TI fields (convert mA to A)
        ef1 = TI.get_field([e1_plus, e1_minus, current_ch1_mA/1000], leadfield, idx_lf)
        ef2 = TI.get_field([e2_plus, e2_minus, current_ch2_mA/1000], leadfield, idx_lf)
        TImax_full = TI.get_maxTI(ef1, ef2)

        # Calculate ROI metrics
        roi_metrics = calculate_roi_metrics(
            TImax_full[roi_indices], roi_volumes,
            ti_field_gm=TImax_full[gm_indices], gm_volumes=gm_volumes
        )

        results.append({
            'montage': f"{e1_plus}_{e1_minus}_and_{e2_plus}_{e2_minus}",
            'current_ch1': current_ch1_mA,
            'current_ch2': current_ch2_mA,
            'TImax_ROI': roi_metrics['TImax_ROI'],
            'TImean_ROI': roi_metrics['TImean_ROI'],
            'Focality': roi_metrics.get('Focality', 0.0)
        })

        if idx % 20 == 0:
            print(f"  Processed {idx}/{total_combinations} combinations...")

    elapsed = time.time() - start_time

    # Find best result
    best = max(results, key=lambda x: x['TImean_ROI'])

    print(f"\nCompleted in {elapsed:.2f} seconds ({elapsed/total_combinations:.4f}s per combination)")
    print("\nBEST RESULT:")
    print(f"  Montage: {best['montage']}")
    print(f"  Current Ch1: {best['current_ch1']:.1f} mA")
    print(f"  Current Ch2: {best['current_ch2']:.1f} mA")
    print(f"  TImax ROI: {best['TImax_ROI']:.6f} V/m")
    print(f"  TImean ROI: {best['TImean_ROI']:.6f} V/m")
    print(f"  Focality: {best['Focality']:.6f}")
    print("=" * 80)

    return {
        'mode': 'Bucketed',
        'n_combinations': total_combinations,
        'time': elapsed,
        'best': best,
        'all_results': results
    }


def test_pooled_mode(leadfield, mesh, idx_lf, electrodes, roi_indices, roi_volumes,
                     gm_indices, gm_volumes, total_current=2.0, current_step=0.5):
    """
    Test all-combinations (pooled) mode: All possible 4-electrode assignments from 8 electrodes.

    Total: C(8,4) × 4! = 70 × 24 = 1,680 combinations (PROOF OF CONCEPT)
    """
    print("\n" + "=" * 80)
    print("TEST 2: ALL-COMBINATIONS MODE (Pooled/New) - PROOF OF CONCEPT")
    print("=" * 80)

    # Select 8 electrodes - all can be in any position
    selected_electrodes = electrodes[:8]

    print(f"All electrodes: {selected_electrodes}")
    print(f"Total available: {len(selected_electrodes)}")

    # Fixed current ratio (proof of concept - no variations)
    current_ratios = [(1.0, 1.0)]  # 1 mA per channel
    print(f"\nCurrent ratio (fixed): {current_ratios[0]} mA")

    # Calculate total combinations
    # All possible 4-electrode assignments from 12 electrodes with replacement
    electrode_combinations = list(product(selected_electrodes, repeat=4))
    n_electrode_combinations = len(electrode_combinations)
    n_current_ratios = len(current_ratios)
    total_combinations = n_electrode_combinations * n_current_ratios

    print(f"\nElectrode combinations: {len(selected_electrodes)}^4 = {n_electrode_combinations}")
    print(f"Current ratio: {n_current_ratios} (fixed)")
    print(f"TOTAL COMBINATIONS: {total_combinations}")
    print("=" * 80)

    # Run simulations
    results = []
    start_time = time.time()

    # Filter out invalid combinations where any electrode appears more than once
    # Each electrode must be unique in the montage (E1+, E1-, E2+, E2-)
    valid_combinations = [(e1_plus, e1_minus, e2_plus, e2_minus)
                         for (e1_plus, e1_minus, e2_plus, e2_minus) in electrode_combinations
                         if len(set([e1_plus, e1_minus, e2_plus, e2_minus])) == 4]

    n_valid = len(valid_combinations)
    n_invalid = len(electrode_combinations) - n_valid
    total_combinations_actual = n_valid * len(current_ratios)

    print(f"\nFiltering invalid combinations:")
    print(f"  Total electrode combinations: {len(electrode_combinations)}")
    print(f"  Invalid (electrode appears >1 time): {n_invalid}")
    print(f"  Valid combinations (4 unique electrodes): {n_valid}")
    print(f"  ACTUAL TOTAL TO TEST: {total_combinations_actual}")
    print("=" * 80)

    combinations_iter = ((e1_plus, e1_minus, e2_plus, e2_minus, (current_ch1_mA, current_ch2_mA))
                        for (e1_plus, e1_minus, e2_plus, e2_minus) in valid_combinations
                        for (current_ch1_mA, current_ch2_mA) in current_ratios)

    for idx, (e1_plus, e1_minus, e2_plus, e2_minus, (current_ch1_mA, current_ch2_mA)) in \
            enumerate(combinations_iter, 1):

        # Calculate TI fields (convert mA to A)
        ef1 = TI.get_field([e1_plus, e1_minus, current_ch1_mA/1000], leadfield, idx_lf)
        ef2 = TI.get_field([e2_plus, e2_minus, current_ch2_mA/1000], leadfield, idx_lf)
        TImax_full = TI.get_maxTI(ef1, ef2)

        # Calculate ROI metrics
        roi_metrics = calculate_roi_metrics(
            TImax_full[roi_indices], roi_volumes,
            ti_field_gm=TImax_full[gm_indices], gm_volumes=gm_volumes
        )

        results.append({
            'montage': f"{e1_plus}_{e1_minus}_and_{e2_plus}_{e2_minus}",
            'current_ch1': current_ch1_mA,
            'current_ch2': current_ch2_mA,
            'TImax_ROI': roi_metrics['TImax_ROI'],
            'TImean_ROI': roi_metrics['TImean_ROI'],
            'Focality': roi_metrics.get('Focality', 0.0)
        })

        if idx % 500 == 0:
            elapsed_so_far = time.time() - start_time
            rate = idx / elapsed_so_far if elapsed_so_far > 0 else 0
            eta = (total_combinations_actual - idx) / rate if rate > 0 else 0
            print(f"  Processed {idx}/{total_combinations_actual} combinations... "
                  f"({100*idx/total_combinations_actual:.1f}% | ETA: {eta/60:.1f} min)")

    elapsed = time.time() - start_time

    # Find best result
    best = max(results, key=lambda x: x['TImean_ROI'])

    print(f"\nCompleted in {elapsed:.2f} seconds ({elapsed/total_combinations_actual:.4f}s per combination)")
    print("\nBEST RESULT:")
    print(f"  Montage: {best['montage']}")
    print(f"  Current Ch1: {best['current_ch1']:.1f} mA")
    print(f"  Current Ch2: {best['current_ch2']:.1f} mA")
    print(f"  TImax ROI: {best['TImax_ROI']:.6f} V/m")
    print(f"  TImean ROI: {best['TImean_ROI']:.6f} V/m")
    print(f"  Focality: {best['Focality']:.6f}")
    print("=" * 80)

    return {
        'mode': 'All-Combinations',
        'n_combinations': total_combinations_actual,
        'time': elapsed,
        'best': best,
        'all_results': results
    }


def compare_results(bucketed_result, pooled_result):
    """Compare bucketed vs pooled mode results"""
    print("\n" + "=" * 80)
    print("COMPARISON SUMMARY")
    print("=" * 80)

    print("\nMode                 | Combinations | Time (s) | Best TImean (V/m) | Best Focality")
    print("-" * 90)
    print(f"Bucketed (Original)  | {bucketed_result['n_combinations']:12d} | {bucketed_result['time']:8.2f} | "
          f"{bucketed_result['best']['TImean_ROI']:17.6f} | {bucketed_result['best']['Focality']:13.6f}")
    print(f"Pooled (New)         | {pooled_result['n_combinations']:12d} | {pooled_result['time']:8.2f} | "
          f"{pooled_result['best']['TImean_ROI']:17.6f} | {pooled_result['best']['Focality']:13.6f}")

    # Calculate differences
    time_ratio = pooled_result['time'] / bucketed_result['time']
    combinations_ratio = pooled_result['n_combinations'] / bucketed_result['n_combinations']
    field_improvement = ((pooled_result['best']['TImean_ROI'] / bucketed_result['best']['TImean_ROI']) - 1) * 100

    print("\n" + "=" * 80)
    print("Key Metrics:")
    print("=" * 80)
    print(f"  Combinations ratio (Pooled/Bucketed): {combinations_ratio:.1f}x")
    print(f"  Time ratio (Pooled/Bucketed): {time_ratio:.1f}x")
    print(f"  Field strength improvement: {field_improvement:+.2f}%")

    print("\n" + "=" * 80)
    print("Analysis:")
    print("=" * 80)

    if field_improvement > 0:
        print(f"✓ Pooled mode found {field_improvement:.2f}% better solution")
        print(f"  - Tested {combinations_ratio:.0f}x more combinations")
        print(f"  - Took {time_ratio:.1f}x longer to compute")
    else:
        print(f"  Both modes found similar solutions (within {abs(field_improvement):.2f}%)")

    print("\nBucketed Mode:")
    print(f"  - Best: {bucketed_result['best']['montage']}")
    print(f"  - Currents: Ch1={bucketed_result['best']['current_ch1']:.1f}mA, Ch2={bucketed_result['best']['current_ch2']:.1f}mA")

    print("\nPooled Mode:")
    print(f"  - Best: {pooled_result['best']['montage']}")
    print(f"  - Currents: Ch1={pooled_result['best']['current_ch1']:.1f}mA, Ch2={pooled_result['best']['current_ch2']:.1f}mA")

    print("=" * 80)


def main():
    """Run comparison test"""
    print("\n" + "#" * 80)
    print("# Ex-Search: Bucketed vs All-Combinations - PROOF OF CONCEPT")
    print("#" * 80)
    print("\n🔬 QUICK PROOF OF CONCEPT TEST")
    print("=" * 80)
    print("\nThis test compares two electrode selection strategies:")
    print("  1. Bucketed Mode: 8 electrodes split into 4 groups of 2")
    print("     - E1+ (2 electrodes) × E1- (2) × E2+ (2) × E2- (2)")
    print("     - Total: 2^4 = 16 electrode combinations")
    print("\n  2. All-Combinations Mode: Any of 8 electrodes in any position")
    print("     - All valid 4-electrode assignments from 8 electrodes")
    print("     - Total: C(8,4) × 4! = 70 × 24 = 1,680 combinations")
    print("     - Ratio: 1,680 / 16 = 105x larger")
    print("\n  Note: No current ratio variations (fixed at 1.0 mA per channel)")
    print("=" * 80)
    print("\n" + "#" * 80)

    try:
        # Load leadfield data
        leadfield, mesh, idx_lf, leadfield_path = load_leadfield_data()

        # Get electrode count from loaded leadfield
        n_electrodes = leadfield.shape[0]
        print(f"\nNumber of electrodes in leadfield: {n_electrodes}")

        # Get known electrode names for ernie subject
        electrodes = get_ernie_electrode_names()
        print(f"Available electrodes: {len(electrodes)}")
        print(f"Electrode names: {', '.join(electrodes)}")

        # Verify electrode count matches
        if len(electrodes) != n_electrodes:
            print(f"⚠️  Warning: Electrode name list ({len(electrodes)}) doesn't match leadfield size ({n_electrodes})")
            print(f"   Using first {n_electrodes} electrode names from list")
            electrodes = electrodes[:n_electrodes]

        # Verify we have at least 8 electrodes
        if len(electrodes) < 8:
            raise ValueError(f"Need at least 8 electrodes, but only {len(electrodes)} available")

        # Select 8 electrodes for testing (excluding fiducials: Nz, Iz, LPA, RPA)
        # Use actual EEG electrodes only - PROOF OF CONCEPT
        eeg_electrodes = [e for e in electrodes if e not in ['Nz', 'Iz', 'LPA', 'RPA']]
        selected_8 = eeg_electrodes[:8]

        print(f"\n🔬 PROOF OF CONCEPT: Using 8 EEG electrodes (2 per bucket)")
        print(f"  {', '.join(selected_8)}")
        print(f"  Bucketed: 2×2×2×2 = 16 combinations")
        print(f"  Pooled: C(8,4)×4! = 70×24 = 1,680 combinations")
        print(f"  Ratio: 1,680/16 = 105x")

        # Update electrodes list to use selected 8
        electrodes = selected_8

        # Setup ROI
        roi_indices, roi_volumes, gm_indices, gm_volumes = setup_roi(mesh)

        # Run tests
        bucketed_result = test_bucketed_mode(
            leadfield, mesh, idx_lf, electrodes,
            roi_indices, roi_volumes, gm_indices, gm_volumes
        )

        pooled_result = test_pooled_mode(
            leadfield, mesh, idx_lf, electrodes,
            roi_indices, roi_volumes, gm_indices, gm_volumes
        )

        # Compare results
        compare_results(bucketed_result, pooled_result)

        print("\n" + "#" * 80)
        print("# TEST COMPLETED SUCCESSFULLY")
        print("#" * 80)
        print("\nBoth modes executed successfully!")
        print("Results demonstrate the trade-off between:")
        print("  - Search space size (computational cost)")
        print("  - Solution quality (field strength)")
        print("=" * 80)

    except Exception as e:
        print("\n" + "#" * 80)
        print("# TEST FAILED")
        print("#" * 80)
        print(f"\nError: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
