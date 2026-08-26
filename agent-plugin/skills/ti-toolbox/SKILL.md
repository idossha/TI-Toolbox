---
name: ti-toolbox
description: Orientation for the Temporal Interference Toolbox (TI-Toolbox, Python package `tit`). Use whenever the user mentions TI-Toolbox, TI stimulation simulation/optimization, SimNIBS-based TI workflows, flex-search, ex-search, mTI, or a BIDS project with derivatives/SimNIBS. Explains how the toolbox runs, where docs live, and which MCP tools to call.
user-invocable: false
---

# TI-Toolbox — Agent Orientation

**TI-Toolbox** simulates, optimizes and analyzes temporal-interference (TI) brain
stimulation on subject-specific head models. It wraps SimNIBS, FreeSurfer and
(optionally) QSIPrep/QSIRecon behind a PyQt GUI, a Python API (`tit`) and JSON
config runners. Docs: https://idossha.github.io/TI-Toolbox/ · Repo:
https://github.com/idossha/TI-Toolbox · Cite: Haber et al. 2025, *Brain Stimulation*,
doi:10.1016/j.brs.2025.103016.

## Ground rules (read before answering anything)

1. **Everything scientific runs inside Docker.** The `idossha/simnibs:v<version>`
   container has SimNIBS 4.x, Python 3.11 (`simnibs_python`), numpy 1.26, nibabel,
   scipy, and `tit`. It has **no FSL, no ANTs**. The host Python cannot import `tit`
   with SimNIBS. Run scripts with `docker exec -it simnibs_container bash` then
   `simnibs_python script.py`. The user's project is mounted at `/mnt/<project>/`.
2. **Do not guess API signatures.** Dataclass fields change between releases. Call the
   MCP tool `read_source_file` (e.g. `tit/sim/config.py`, `tit/opt/config.py`) or
   `read_wiki_page("scripting")` and quote what you find.
3. **Do not guess what the user has on disk.** Call `inspect_project` with their
   project root before diagnosing "my simulation/optimization doesn't show up".
4. **Prefer the wiki over memory** for feature behaviour: `search_wiki` → `read_wiki_page`.
   The wiki is the same Markdown that renders at `/wiki/<slug>/`.
5. Check `get_toolbox_version` / `read_changelog` when behaviour may depend on version.

## MCP tools (server `ti-toolbox`)

| Need | Tool |
|------|------|
| First call in a session | `get_quick_facts` |
| Which page covers X? | `search_wiki`, `list_wiki_pages` |
| Read a page / one section | `read_wiki_page(page, section?)` |
| Exact class/function definition | `find_symbol` (local checkout) or `read_source_file` |
| Grep the source | `search_source` (local checkout) |
| What data does the user have? | `inspect_project(project_root, subject?)` |
| Montages / project JSON configs | `read_project_config(project_root, "montage_list.json")` |
| What changed in vX.Y.Z? | `read_changelog(version)` |

If the MCP server is unavailable, fetch the same Markdown from
`https://raw.githubusercontent.com/idossha/TI-Toolbox/main/docs/wiki/<slug>.md`.

## Wiki map (slugs)

- Workflow: `pre-processing`, `diffusion-processing`, `simulator`, `flex-search`,
  `ex-search`, `mti`, `analyzer`, `reports`, `visualizers`, `gui`, `scripting`
- Tools: `atlases`, `atlas-resampling`, `montage_visualizer`, `electrode-mapping`,
  `electrode-placement`, `nilearn-visuals`, `cluster-permutation-testing`,
  `nifti-group-averaging`, `tissue-analyzer`, `quick-notes`, `blender`, `logging`
- Dev: `extension`, `testing-pipeline`, `python_env`, `desktop-app`

## The pipeline in one paragraph

**Pre-process** (DICOM/NIfTI → `sub-<id>/anat` → FreeSurfer recon-all →
SimNIBS CHARM head mesh `m2m_<id>`) → **Optimize** electrode positions
(**flex-search**: differential evolution over the scalp; **ex-search**: exhaustive
over a leadfield + candidate electrode pool; **mex-search**: multipolar variant) →
**Simulate** a montage (2 pairs = TI, 4 pairs = mTI; fields `TI_max`, optional
`TI_avg`/`TI_normal`, safety `hf_peak`/`hf_sar`) → **Analyze** (spherical or atlas
ROI stats in mesh or voxel space, group analysis) → **Stats** (cluster-based
permutation, volumetric MNI or fsaverage surface) → **Report** (HTML).

## On-disk layout (BIDS + derivatives)

```
<project>/
  sourcedata/<id>/                       raw DICOM
  sub-<id>/anat/sub-<id>_T1w.nii.gz      raw NIfTI (+T2w, ct)
  code/ti-toolbox/config/*.json          montage_list.json, eeg nets, settings
  derivatives/
    freesurfer/sub-<id>/                 recon-all
    qsiprep/, qsirecon/                  diffusion (optional)
    SimNIBS/sub-<id>/
      m2m_<id>/                          head model (<id>.msh, eeg_positions/)
      leadfields/                        for ex-search
      Simulations/<montage>/TI/{mesh,niftis}  + Analyses/{Mesh,Voxel}/ + fsaverage/
      flex-search/<run>/                 electrode_positions.json, flex_meta.json
      ex-search/<run>/ , m-ex-search/<run>/
    ti-toolbox/{reports,stats,logs,tissue_analysis}/
```

Path logic lives in `tit/paths.py` (`PathManager`; `get_path_manager(project_root, subject)`).

## Entry points

```bash
simnibs_python -m tit.sim       config.json   # simulation
simnibs_python -m tit.opt.flex  config.json   # flex-search
simnibs_python -m tit.opt.ex    config.json   # ex-search
simnibs_python -m tit.opt.mex   config.json   # multipolar ex-search
simnibs_python -m tit.analyzer  config.json
simnibs_python -m tit.stats     config.json
simnibs_python -m tit.pre       config.json
```
The GUI writes exactly these JSON files and runs the same commands, so anything the
GUI does is reproducible from a script. Python-level usage is in the `ti-scripting`
skill.

## Common user pitfalls to check first

**For any error message, first call `read_wiki_page("troubleshooting")`** (or `search_wiki` with the error text). That page is the maintainer-verified archive of known problems, causes and fixes; prefer its answer over your own diagnosis.

- Running host `python` instead of `simnibs_python` inside the container.
- Montage names must match `montage_list.json` exactly; EEG net names are real
  filenames (e.g. `GSN-HydroCel-185.csv`).
- ex-search needs a pre-computed leadfield for the same EEG net.
- Anisotropic conductivity (`vn`/`dir`/`mc`) needs QSIRecon-derived tensors.
- `TI_normal` is mesh-only; voxel analysis of it is an error by design.
- macOS 26+ has known Gmsh/Freeview GUI issues (see installation docs).
- Support channels: GitHub Issues/Discussions, Discord (links in README).
