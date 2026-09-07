# fsaverage Surface Resources

Vendored `central` surface meshes for the three fsaverage resolutions the
group-level surface-stats pipeline (`tit/stats/surface.py`) needs for
triangle-adjacency (cluster connectivity), replacing a runtime download.

## Source

Extracted from SimNIBS 4.6.0's own bundled package data
(`simnibs/resources/templates/{fsaverage10k_surf,fsaverage40k_surf,fsaverage_surf}/{lh,rh}.central.gii`),
not from FreeSurfer or nilearn. SimNIBS is GPL-3.0 licensed; these files are
geometry only (vertex coordinates + triangle faces), no code.

This is a deliberate choice, not just a convenience: `tit/source/fsaverage.py`
projects each subject's fields onto fsaverage via SimNIBS's own
`cross_subject_map(..., subsampling_to=spacing)`, so the field caches
`tit/stats/surface.py` clusters are already indexed in *SimNIBS's* fsaverage
vertex ordering. Building the adjacency graph from the same source keeps the
graph and the data it clusters on the same vertex numbering; sourcing the
adjacency mesh from nilearn's separately-distributed fsaverage instead would
risk a silent vertex-order mismatch between the two (unverified either way,
since no lane compared the two orderings directly -- picking the SimNIBS
source removes the question rather than answering it).

## Files

| Directory | fsaverage resolution | Vertices/hemisphere | Total nodes (`FSAVG_NODES`) |
|---|---|---|---|
| `5/` | fsaverage5 | 10,242 | 20,484 |
| `6/` | fsaverage6 | 40,962 | 81,924 |
| `7/` | fsaverage7 (native, ico7) | 163,842 | 327,684 |

Each directory holds `lh.central.gii` / `rh.central.gii` (GIFTI, vertex
coordinates + triangle faces). Only the triangle topology (`faces`) is used
by `build_fsaverage_adjacency`; coordinates are read but not otherwise
consumed. Vertex/face counts and total size verified in
`dev/spikes/README.md`.

Total size: ~18 MB (0.5 MB + 2.1 MB + 15.7 MB for `5/`, `6/`, `7/`
respectively).

## Loader

`tit.stats.surface.build_fsaverage_adjacency(spacing)` tries, in order:
1. This vendored directory (via `tit.paths.resolve_resource_path("fsaverage", str(spacing))`).
2. `nilearn.datasets.fetch_surf_fsaverage` (the previous runtime-download
   behavior — kept as a fallback for a host missing the bundled resource,
   e.g. a dev checkout without `resources/fsaverage/`).
3. A `RuntimeError` naming both failed sources, if neither is available.
