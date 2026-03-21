#!/usr/bin/env simnibs_python
"""Integration test for Analyzer in mesh space.

Run inside Docker:
    simnibs_python scripts/test_mesh_analyzer.py <subject_id> <simulation>

Example:
    simnibs_python scripts/test_mesh_analyzer.py 101 test

Every cortical test generates a .msh overlay so you can verify
the selected ROI visually in Gmsh.
"""

import sys
import traceback

from tit.analyzer import Analyzer
from tit.paths import get_path_manager


def run_test(name, fn):
    """Run a test function, print PASS/FAIL."""
    try:
        result = fn()
        print(f"  PASS  {name}")
        print(f"        roi_mean={result.roi_mean:.4f}  roi_max={result.roi_max:.4f}  "
              f"n_elements={result.n_elements}")
        return True
    except Exception as e:
        print(f"  FAIL  {name}")
        print(f"        {e}")
        traceback.print_exc()
        return False


def main():
    if len(sys.argv) < 3:
        print("Usage: simnibs_python scripts/test_mesh_analyzer.py <subject_id> <simulation>")
        print("       Optional: pass project_dir as 3rd arg (default: /mnt/000)")
        sys.exit(1)

    subject_id = sys.argv[1]
    simulation = sys.argv[2]
    project_dir = sys.argv[3] if len(sys.argv) > 3 else "/mnt/000"

    from tit.logger import add_stream_handler, setup_logging
    setup_logging("INFO")
    add_stream_handler("tit.analyzer")

    get_path_manager(project_dir)

    print(f"Subject: {subject_id}  Simulation: {simulation}  Project: {project_dir}")
    print()

    passed = 0
    failed = 0

    def tally(ok):
        nonlocal passed, failed
        if ok:
            passed += 1
        else:
            failed += 1

    # ------------------------------------------------------------------
    # Spherical analysis
    # ------------------------------------------------------------------
    print("=" * 60)
    print("SPHERICAL (mesh)")
    print("=" * 60)

    analyzer = Analyzer(subject_id, simulation, space="mesh")

    tally(run_test("sphere — subject coords, r=20", lambda: analyzer.analyze_sphere(
        center=(0.0, 0.0, 0.0), radius=20.0,
        coordinate_space="subject", visualize=True,
    )))

    tally(run_test("sphere — MNI coords, r=15", lambda: analyzer.analyze_sphere(
        center=(-30.0, -20.0, 50.0), radius=15.0,
        coordinate_space="MNI", visualize=True,
    )))

    # ------------------------------------------------------------------
    # Cortical analysis — DK40
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("CORTICAL — DK40  (visualize=True, check .msh files)")
    print("=" * 60)

    # Single region, lh
    tally(run_test("DK40 single lh: cuneus-lh", lambda: analyzer.analyze_cortex(
        atlas="DK40", region="cuneus-lh", visualize=True,
    )))

    # Single region, rh
    tally(run_test("DK40 single rh: cuneus-rh", lambda: analyzer.analyze_cortex(
        atlas="DK40", region="cuneus-rh", visualize=True,
    )))

    # Bare name (both hemispheres)
    tally(run_test("DK40 bare name: precentral", lambda: analyzer.analyze_cortex(
        atlas="DK40", region="precentral", visualize=True,
    )))

    # Multiple regions, same hemisphere
    tally(run_test("DK40 multi same hemi: cuneus-lh + lingual-lh", lambda: analyzer.analyze_cortex(
        atlas="DK40", region=["cuneus-lh", "lingual-lh"], visualize=True,
    )))

    # Multiple regions, cross hemisphere
    tally(run_test("DK40 multi cross hemi: cuneus-lh + cuneus-rh", lambda: analyzer.analyze_cortex(
        atlas="DK40", region=["cuneus-lh", "cuneus-rh"], visualize=True,
    )))

    # Multiple regions, both from rh
    tally(run_test("DK40 multi rh: precuneus-rh + lingual-rh", lambda: analyzer.analyze_cortex(
        atlas="DK40", region=["precuneus-rh", "lingual-rh"], visualize=True,
    )))

    # ------------------------------------------------------------------
    # Cortical analysis — a2009s
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("CORTICAL — a2009s (Destrieux)  (visualize=True)")
    print("=" * 60)

    from simnibs.utils.transformations import atlas2subject
    try:
        a2009s_raw = atlas2subject(analyzer.m2m_path, "a2009s", split_labels=True)
        a2009s_lh = sorted(a2009s_raw.get("lh", {}).keys())
        a2009s_rh = sorted(a2009s_raw.get("rh", {}).keys())
        print(f"  a2009s regions: {len(a2009s_lh)} lh, {len(a2009s_rh)} rh")

        if a2009s_lh:
            r1 = a2009s_lh[0]
            tally(run_test(f"a2009s single lh: {r1}", lambda: analyzer.analyze_cortex(
                atlas="a2009s", region=f"{r1}-lh", visualize=True,
            )))

        if a2009s_rh:
            r1 = a2009s_rh[0]
            tally(run_test(f"a2009s single rh: {r1}", lambda: analyzer.analyze_cortex(
                atlas="a2009s", region=f"{r1}-rh", visualize=True,
            )))

        if len(a2009s_lh) >= 2:
            r1, r2 = a2009s_lh[0], a2009s_lh[1]
            tally(run_test(f"a2009s multi lh: {r1} + {r2}", lambda: analyzer.analyze_cortex(
                atlas="a2009s", region=[f"{r1}-lh", f"{r2}-lh"], visualize=True,
            )))

        # Cross hemisphere with shared name
        shared = sorted(set(a2009s_lh) & set(a2009s_rh))
        if shared:
            r = shared[0]
            tally(run_test(f"a2009s cross hemi: {r}", lambda: analyzer.analyze_cortex(
                atlas="a2009s", region=r, visualize=True,
            )))
    except Exception as e:
        print(f"  SKIP  a2009s — {e}")

    # ------------------------------------------------------------------
    # Cortical analysis — HCP_MMP1
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("CORTICAL — HCP_MMP1  (visualize=True)")
    print("=" * 60)

    # Single region
    tally(run_test("HCP_MMP1 single lh: V1-lh", lambda: analyzer.analyze_cortex(
        atlas="HCP_MMP1", region="V1-lh", visualize=True,
    )))

    tally(run_test("HCP_MMP1 single rh: V1-rh", lambda: analyzer.analyze_cortex(
        atlas="HCP_MMP1", region="V1-rh", visualize=True,
    )))

    # Bare name (both hemispheres)
    tally(run_test("HCP_MMP1 bare: V1", lambda: analyzer.analyze_cortex(
        atlas="HCP_MMP1", region="V1", visualize=True,
    )))

    # Multi same hemi
    tally(run_test("HCP_MMP1 multi lh: V1-lh + V2-lh", lambda: analyzer.analyze_cortex(
        atlas="HCP_MMP1", region=["V1-lh", "V2-lh"], visualize=True,
    )))

    # Multi cross hemi
    tally(run_test("HCP_MMP1 multi cross: V1-lh + V1-rh", lambda: analyzer.analyze_cortex(
        atlas="HCP_MMP1", region=["V1-lh", "V1-rh"], visualize=True,
    )))

    # Multi mixed
    tally(run_test("HCP_MMP1 multi mixed: V1-lh + V2-rh + 4-lh", lambda: analyzer.analyze_cortex(
        atlas="HCP_MMP1", region=["V1-lh", "V2-rh", "4-lh"], visualize=True,
    )))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    total = passed + failed
    print(f"RESULTS: {passed}/{total} passed, {failed} failed")
    print("=" * 60)
    print()
    print("All .msh overlay files are in:")
    pm = get_path_manager()
    analyses_dir = f"{pm.simnibs()}/sub-{subject_id}/Simulations/{simulation}/Analyses/Mesh"
    print(f"  {analyses_dir}/")
    print()
    print("Open any *_ROI.msh in Gmsh to verify the ROI is correct.")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
