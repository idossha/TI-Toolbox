# N0.5 — FreeSurfer binaries out of the Python code — Stage N0 spike report

Status: **proven** (materialised by the orchestrator from the lane's structured return, 2026-09-03; the lane could not write files named REPORT.md).

## Headline

Both FreeSurfer binary replacements (mri_convert --reslice_like -> nibabel.processing.resample_from_to(order=0); mri_segstats -> new tit/atlas/segstats.py) validated voxel-for-voxel against live FreeSurfer 7.4.1 output on sub-ernie's real recon-all data: 0/13,631,488 differing voxels on two real resample ground-truth files, and exact label-id/voxel-count match on four real segstats ground-truth atlases (aparc.DKTatlas+aseg 102/102, aparc.a2009s+aseg 188/188, ThalamicNuclei 48/48, charm labeling.nii.gz 46-shared/46 with 10 more correctly recovered). nilearn's runtime fsaverage download in tit/stats/surface.py replaced with 18MB of SimNIBS's own bundled fsaverage (vertex/face counts and adjacency-graph sanity all verified). Full host suite 3122 passed / 17 skipped / 0 failed (up from 3053 passed baseline); black clean on all touched files. Could not write REPORT.md to disk (scratchpad or dev/spikes/) -- the Write tool hard-blocks report-shaped .md files for subagents regardless of path -- so the full report is inline in this turn's text response instead.

## Measured numbers

- mri_convert replacement voxel diff, aparc.DKTatlas+aseg -> m2m_ernie T1 grid: 0/13,631,488 total, 0/1,338,724 labelled (nibabel.processing.resample_from_to vs cached real mri_convert output)
- mri_convert replacement voxel diff, lh.hippoAmygLabels-T1.v22 -> m2m_ernie T1 grid: 0/13,631,488 total, 0/5,430 labelled
- resample_from_to timing: 0.29s (DKT atlas), 0.16s (hippoAmyg atlas)
- mri_segstats replacement label-id-set match: aparc.DKTatlas+aseg 102/102, aparc.a2009s+aseg 188/188, ThalamicNuclei 48/48, labeling.nii.gz 46 shared exact + 10 more correctly recovered (56 total vs live's incomplete 46)
- mri_segstats replacement voxel-count mismatches across all 4 live-compared atlases: 0
- max relative volume difference across all compared labels: 0.0 (the one apparent 0.25 outlier is mri_segstats' own 1-decimal print rounding on a 1-voxel/0.125mm3 region, not a real diff)
- fsaverage vendored size: 18MB total (resources/fsaverage/{5,6,7}/{lh,rh}.central.gii), sourced from SimNIBS 4.6.0's own bundled templates
- fsaverage vertex/face counts verified: 5=10242/hemi (20484 total, matches _FSAVG_NODES), 6=40962/hemi (81924), 7=163842/hemi (327684); faces 20480/81920/327680 per hemi
- fsaverage adjacency sanity: symmetric at all 3 resolutions, mean degree 5.999-6.000, min 5 / max 6 (icosphere pentagon/hexagon pattern)
- host pytest full suite: 3122 passed, 17 skipped, 0 failed, 33.67s (baseline before this lane's rewrite: 3053 passed, 2 failed on the now-replaced mri_segstats-subprocess tests)
- this lane's own 4 test files: 112 passed, 0 failed (test_atlas_segstats.py 21, test_analyzer_voxel_resample.py 8, test_atlas_coverage.py 58 whole file, test_stats_surface.py 25 whole file)
- black --check on 8 touched files: all clean (0 would-reformat)
- grep -rn 'mri_convert|mri_segstats' tit/atlas tit/analyzer/analyzer.py: 0 hits post-rewrite

## Files changed

- tit/atlas/segstats.py (new)
- tit/atlas/voxel.py (list_regions rewritten, subprocess import removed)
- tit/analyzer/analyzer.py (_resample_if_needed + _find_voxel_region_id rewritten, subprocess/tempfile imports removed)
- tit/stats/surface.py (build_fsaverage_adjacency split into _load_fsaverage_mesh_bundled/_load_fsaverage_mesh_nilearn with 3-tier fallback)
- resources/fsaverage/5/lh.central.gii (new)
- resources/fsaverage/5/rh.central.gii (new)
- resources/fsaverage/6/lh.central.gii (new)
- resources/fsaverage/6/rh.central.gii (new)
- resources/fsaverage/7/lh.central.gii (new)
- resources/fsaverage/7/rh.central.gii (new)
- resources/fsaverage/README.md (new)
- tests/test_atlas_segstats.py (new)
- tests/test_analyzer_voxel_resample.py (new)
- tests/test_atlas_coverage.py (edited)
- tests/test_stats_surface.py (edited)

## Verification

- nibabel.processing.resample_from_to(order=0) reproduces real mri_convert --reslice_like cached output exactly (0 diff) on 2 real atlases -- both as a standalone call and end-to-end through the actual rewritten Analyzer._resample_if_needed static method
- compute_segstats + resolve_lut_for_atlas reproduce live mri_segstats --ctab-default --sum label-id sets and voxel counts exactly on 4 real atlases, run via docker run idossha/ti-toolbox_freesurfer:v7.4.1 against real sub-ernie recon-all data and charm's labeling.nii.gz
- Analyzer._find_voxel_region_id verified live against real aparc.DKTatlas+aseg.mgz: name substring match, case-insensitivity, digit passthrough, not-found ValueError, all through the actual rewritten method
- vendored fsaverage GIFTI files read via real nibabel on host: vertex/face counts match _FSAVG_NODES exactly at all 3 resolutions; adjacency graph built from them is symmetric with correct icosphere degree distribution
- build_fsaverage_adjacency's bundled->nilearn->error fallback chain exercised live on host (all 3 branches)
- full host pytest suite green (3122 passed / 0 failed) and black --check clean on every touched file

## Blockers and risks

- Could not write REPORT.md to any path (scratchpad or in-repo dev/spikes/native/fs-binaries/) -- the Write tool refuses report-shaped .md files for subagents ('Subagents should return findings as text, not write report files') regardless of destination; the full report is given as text in this turn instead of a committed file
- Thalamic-nuclei region names (8100-series) fall back to 'Label N' placeholders because the bundled resources/atlas/FreeSurferColorLUT.txt (2012-vintage) predates that FreeSurfer atlas -- ids/counts/volumes are exact, only display names are missing; fixing requires editing resources/atlas/FreeSurferColorLUT.txt, which is outside this lane's resources/** grant (vendoring-fsaverage only)
- SimNIBS's vendored fsaverage vertex ordering was not empirically diffed against nilearn's own fsaverage5/6/7 (no network access exercised this session) -- the 'same source as cross_subject_map' correctness argument is architectural, not empirically confirmed
- mri_segstats's no-license-needed behavior was only confirmed with a license file present at /Users/idohaber/datasets/000/.freesurfer_license.txt; a lab with zero license file was not tested (moot for the native default path, which drops mri_segstats entirely)

## Follow-ups for Stage N1

- Extend resources/atlas/FreeSurferColorLUT.txt (or add a dedicated sidecar) with FreeSurfer 7.x thalamic-nuclei (8100-series) id/name entries if the optional Docker-FreeSurfer thalamic-nuclei path is kept past Stage N1 -- owned by whoever holds resources/atlas/
- Empirically diff SimNIBS's bundled fsaverage vertex ordering vs nilearn's/real FreeSurfer's to fully close the vertex-ordering-consistency argument for build_fsaverage_adjacency
- Re-verify tit.paths.resolve_resource_path / MNI_ATLAS_DIR resolution (Lane N0.6 is concurrently editing tit/atlas/constants.py) once packaged into the native app, not just container/host paths
- Confirm mri_segstats's license-free behavior holds with zero license file present, if the optional legacy-FreeSurfer Docker path is kept
