---
layout: releases
title: Changelog
permalink: /releases/changelog/
toc_group: major
---

Detailed technical changelog for all versions of the Temporal Interference Toolbox. Entries include implementation changes, compatibility notes, and fixes. For a short summary of the newest version and its downloads, see the [Latest release]({{ site.baseurl }}/releases/) page; each version below links to its own release notes.

### Unreleased

#### 3-D scene

- **Fixed: the Simulator's 3-D view always shows what you are working on** — it could show an EEG net no job had chosen (on a fresh page, or the net last picked anywhere on the page), keep showing a **New montage** after you clicked a job, or start a new montage on a net you never picked. The view now follows the last thing you touched: a job (the row or any control in it), the **New montage** form or the **New placement** form, and it is drawn on that job's own subject's head (the reference head stands in, and says so, while the subject's is being built or missing). A job shows only the electrodes its cells name — none while it has no net, flex run or free-hand set, with a line saying what to choose — and its montage's channels; a net the job's subject does not carry (a cap applied to another subject in **EEG caps**) is reported as missing rather than drawn on someone else's head. **New montage** opens on that job's net, or on none until you choose one in the form, and shows the form's net and channels as you edit them; **New placement** starts on that job's subject and shows the positions placed so far; **Cancel** or **Save** returns to the job. Clicking a job while a form is open shows the job and keeps the form and its edits; clicking the form, or an electrode on the head, shows the form again. What the view shows carries the accent tint and bar. No button throws a draft away: **New montage** with one open shows it again, **New placement** opens over it, and a montage's **Edit** shows the open draft with a note to save or cancel it first. **Add job** adds a job like the selected one (its subject and net) and selects it; **Duplicate** selects the copy; removing a job or opening its settings leaves the selection alone, and removing the selected job selects its neighbour. A job switched from Montage to Free-hand or Flex result and back keeps its net, and a cleared net or montage cell shows "Choose…" instead of the old name. Jobs, montages and simulations are unchanged.
- **Fixed: EEG electrodes stand on the scalp at every skin opacity** — with the **Skin** slider at full opacity (the Simulator's default), every EEG electrode in the 3-D view was drawn as a half-disc and those at the edge of the head nearly disappeared. Each electrode is now a small 3-D electrode (the model the Blender montage export uses, 6 mm wide) standing on the scalp at its position, upright along the scalp, touching the skin from every viewing angle including the edge of the head, and its name label sits on top of it. With **Electrode names** on, a name is shown only while its electrode is (names used to stay on electrodes the head hid near its edge). Electrodes on the far side of the head are still hidden by it, clicking an electrode still selects it, channel colours and hover are unchanged, and placement dots and sphere centres are still drawn as dots exactly where they were placed. Montages, simulations and results are unchanged.
- **Added: see a montage's electrodes at their actual size** — the Simulator's 3-D view has an **Actual size** switch beside **Electrode names**, the two side by side in one box under the legend. On, the view shows only the montage's electrodes (while you write a **New montage**, the rest of the net stays as small markers you can still click), each at the job's electrode shape and width × height with its rubber layer on a pale gel layer of the job's gel thickness (no gel layer at 0 mm), bent to follow the scalp so the gel touches the skin across the whole electrode; editing **Job settings ▸ Electrodes** redraws them at once, before **Done**. Off (the default) shows the whole net as before. A rectangular electrode's width runs around the head (horizontally), as the 3-D view has no orientation for it. The switch is not remembered between sessions, and simulations are unchanged.

#### Channels and montages

- **Changed: channels and their electrodes have one name everywhere** — channel k is made of electrodes **Ek+** and **Ek-** (channel 1 is E1+ and E1-, channel 2 is E2+ and E2-, and so on for mTI), and a pair of electrodes is called a **channel**, never "pair 1", "electrode A/B" or "Ch 1A/1B". The Simulator's **New montage** form lists **Channel 1**, **Channel 2** … with an E1+, E1-, E2+, E2- slot each and an **Add 2 channels** button; the 3-D view's chips read `E1+ F3 · E1- F4` and its status line "Click an electrode to set E1+ (Channel 1)."; a job row's second line, the Results channel chips, the free-hand editor (**Add channel**) and the Optimizer (**Count**: **2 channels (TI)** / **4 channels (mTI)**; mEx **Channel current**, **Within each channel** / **Across channels**) use the same names. New simulation, flex-search and ex-search reports list `Channel 1 (blue)` with `E1+ AF3 · E1- PO10`, the montage cap image's legend reads `Channel 1`, `Channel 2` … instead of `Ch 1A`, `Ch 1B` …, and the Viewer names a per-channel field "· channel 1". Only names on screen changed: montage files, configs, scripts, API fields and output file names (including mTI's `TDCS_A`) are unchanged, and reports and images written before keep their old labels until the run is repeated. The wiki, the Python API reference and the agent skills use the same names.
- **Added: pick a new montage's electrodes on the head** — while **New montage** is open, the Simulator's 3-D view shows the net chosen in the form's **EEG net** (changing it redraws, keeps the electrodes both nets have and empties the slots of those the new net lacks), and clicking an electrode sets the highlighted slot, in the order E1+, E1-, E2+, E2- …, in that channel's colour. Opening a slot's picker makes it the next one a click sets; clicking a set electrode again clears it; an electrode already used in one slot is shown as "Already E1+" and cannot be picked for another; typing in the form and clicking on the head edit the same montage. With **Actual size** on, the electrodes you have set are drawn at the job's electrode size and the rest of the net stays clickable.

#### Electrodes

- **Changed: the default gel (saline) layer is 1 mm** — a new job's electrodes now sit on 1 mm of gel instead of 4 mm, in the Simulator's **Job settings ▸ Electrodes**, the Optimizer's Flex **Electrodes** section, a new leadfield, and for a script or an agent that leaves `gel_thickness` out (`SimulationConfig`, `FlexConfig.ElectrodeConfig`, `LeadfieldConfig`). 1 mm of gel on 2 mm of rubber is SimNIBS's own default for flex-search electrodes. The field under and around an electrode depends on its gel, so a new simulation that relies on the default differs from one run before this change; set `gel_thickness=4.0` to reproduce it. Existing runs, their reports and any job that sets the gel are unchanged; rubber (2 mm), shape (ellipse) and size (8 × 8 mm) are unchanged.
- **Added: a "?" beside every Electrodes section** — in **Job settings**, the Optimizer's Flex form, the leadfield strip and the new Generate-leadfield step, a **?** opens a short explanation of shape, width × height, gel and rubber thickness, a diagram of the layers, and links to the SimNIBS electrode reference and to Saturnino, Antunes & Thielscher (2015, NeuroImage), which open in your browser.
- **Added: choose the electrode before generating a leadfield** — in the Optimizer, **Generate leadfield** on an Ex row (or **Generate** in its leadfield strip) now opens a step with the electrode's shape, width × height and gel thickness, starting at the defaults above, and queues the job only when you click **Generate**. The leadfield is computed with that electrode at every position of the net and records it beside the file (`<subject>_leadfield_<net>.json`), tied to that one leadfield by its size and modification time; the **Net / leadfield** cell and the leadfield strip show it ("GSN-HydroCel-185 · 2.0 GB · ellipse 8×8 mm, gel 1 mm"), and an Ex or mEx run copies it into its `run_config.json` as `leadfield_electrode`, so the run keeps it after the leadfield is regenerated. A leadfield whose file no longer matches its record (replaced or regenerated outside the toolbox) shows "electrode not recorded" rather than another file's electrode, and so does a leadfield computed before this change: the toolbox did not choose an electrode for it, so SimNIBS used its own (a 10 mm round electrode of one 4 mm layer), not the Simulator's. It still loads and runs as before; generate it again (with **overwrite** from a script) to match your Simulator electrodes. The Ex search itself is unchanged.

#### Simulation outputs

- **Changed: a simulation saves `TI_max`, `hf_peak` and `hf_rms` by default** — a new Simulator job ticks **TI_max**, **hf_peak** and **hf_rms** under **Job settings ▸ Output fields**, and a script or an agent that leaves `output_fields` out gets the same; for a carrier-only control the default is **hf_peak** and **hf_rms**, so `SimulationConfig(..., carrier_only=True)` needs nothing else. `TI_avg` and `hf_power_density` are still ticked only when you want them. All of them go into the simulation's one field mesh, `<montage>_TI.msh` (`<montage>_mTI.msh`, with `mTI_max`, for mTI). A job that lists its own output fields runs exactly as before.
- **Changed: NIfTI volumes are opt-in, one file per field** — a simulation no longer converts its fields to NIfTI unless **Job settings ▸ Output files ▸ Write NIfTI volumes (one per field)** is ticked (`map_to_vol=True`, which was recorded but ignored until now). Ticked, every field of the field mesh gets one 3-D NIfTI for the brain tissue and for its grey- and white-matter parts, under the names it had before (`grey_<montage>_TI_subject_TI_max.nii.gz`, …), with each channel's `magnE`, and the run stops with an error if the NIfTIs written are not exactly the mesh's fields. **Also in MNI space** (`map_to_mni`), shown under it, writes the MNI-space copies and the T1 in MNI space; MNI output is itself a NIfTI, so ticking it (or a config or older job spec with `map_to_mni` alone) turns **Write NIfTI volumes** on too. A default simulation is faster and smaller; its report voxelises the grey- and white-matter envelope in a scratch folder for its figure and keeps nothing. Simulations run before keep their NIfTIs.
- **Added: what a simulation did not save is computed when a step needs it** — when an analysis needs a field the simulation did not save (the **Field** you pick, or `hf_peak` and `hf_rms` for the carrier metrics), or a voxel analysis, the cluster-permutation test, NIfTI group averaging, Nilearn visuals or the sub-cortical Visual Exporter needs a NIfTI that was not written, the job computes it from the simulation's channel meshes (`high_Frequency/mesh/`) with the code the Simulator uses, saves it into the simulation (the field mesh and its central surface; the NIfTI in `TI/niftis/` or `mTI/niftis/`) and then runs. It says so once, in the job's output — "hf_peak and hf_rms were not saved for L_Insula; computing them from the channel fields and saving them to L_Insula_TI.msh." — and an analysis also in its **Results** pane ("Produced for this analysis: …", `on_demand_note` in `results.csv`). The next step finds the field saved; a simulation that wrote NIfTIs also gets the new field's NIfTIs (and MNI copies if it wrote them), so it keeps one NIfTI per mesh field, while one without NIfTIs gets only those a voxel step reads. Everything is written to a hidden staging folder and moved into place, the field mesh last, so a job stopped midway leaves nothing half-written and the next one redoes the work. A voxel analysis uses a NIfTI the simulation already has (an older or renamed one included) before computing anything, so a folder that kept only its NIfTIs still analyses. A job whose analysed field cannot be computed (its channel meshes are gone) is refused before it is queued, naming the missing files; carrier fields that cannot be computed leave the carrier metrics empty, with the reason in `carrier_note`. `hf_power_density` cannot be computed afterwards (the conductivity of the solve is not kept), so tick it before the run; a carrier-only control has no `TI_max`. The Analyzer's **Field** list offers every field it can produce, plainly, and marks an unsaved `hf_power_density` "(not saved)"; for a carrier-only control it offers the carrier fields only, and **Auto** is `hf_peak` there ("Auto (hf_peak)") instead of `TI_max`. A field mesh whose field list cannot be read is an error naming it. A simulation report that cannot draw its envelope figure says why on the page. A default simulation no longer leaves empty `niftis/` folders. Values of fields a simulation saved are unchanged.
- **Changed: the Viewer opens a simulation on its field mesh** — the simulation scene shows the field mesh as grey matter only (the other tissues are hidden, one tick away in TetraVox) coloured by `TI_max` (`mTI_max` for mTI, `hf_peak` for a carrier-only control), with the window taken from its grey-matter values when the run wrote no NIfTI; the other saved fields are a field switch away in TetraVox. A run that wrote NIfTIs still opens them too.
- **Changed: a simulation writes one cortical surface mesh and finishes sooner** — each run writes `TI/mesh/surfaces/<montage>_TI_central.msh` (`mTI/…_mTI_central.msh`), the subject's central cortical surface, left then right hemisphere, with every saved field and `TI_normal` on it, instead of SimNIBS's per-channel surface overlays (`surface_overlays/`, FreeSurfer `lh.*`/`rh.*` files), a separate `<montage>_normal.msh`, `grey_`/`white_` copies of the field mesh, Gmsh `.opt` views and, for mTI, the per-pair `TI_AB`/`TI_CD` meshes. On Ernie (2 channels, emulated image) the surface step takes 91 s instead of 515 s, the run 731 s instead of 1011 s, and the folder holds 17 files and 1.25 GB instead of 53 files and 1.52 GB. The surface values equal SimNIBS's own `msh2cortex` and the old `TI_normal` to within 3e-15 V/m, and fsaverage projections are unchanged. Grey- and white-matter NIfTIs keep their names (they are cut from the field mesh), and mesh analyses, `TI_normal`, the Visual Exporter and the Viewer read the new surface. A simulation run before is upgraded when a step needs it: its surface is rewritten from its field mesh, with `TI_normal` taken from its old `_normal.msh` (or computed from its channel meshes), after checking the head model was not segmented again; its old files are left in place.
- **Changed: `hf_sar` is replaced by `hf_rms`, the RMS carrier field in V/m** — a simulation saves `hf_rms` = √(½ Σ|E_c|²), the RMS in-situ carrier field over time, instead of `hf_sar` (Σ|E_c|², in (V/m)²), and the fsaverage projection and every analysis read `hf_rms`. It is not a compliance metric: compare `hf_peak` with exposure limits (see *Convention* below). Ticking it in **Job settings ▸ Output fields**, `output_fields=["hf_rms"]` in a script, and its analyses work as `hf_sar` did. A simulation run before keeps its `hf_sar` on disk, but nothing reads it: an analysis that needs `hf_rms` computes it from the run's channel meshes and saves it, as for any field the run did not save. Scripts that read `hf_sar` from a mesh must read `hf_rms` (`hf_sar` = 2 × `hf_rms`²).
- **Changed: field names are shown with subscripts** — the app shows TI<sub>max</sub>, mTI<sub>max</sub>, TI<sub>normal</sub>, TI<sub>avg</sub>, HF<sub>peak</sub>, HF<sub>rms</sub> and p<sub>HF</sub> (for `hf_power_density`) in **Job settings ▸ Output fields**, **Settings ▸ Simulator**, the Analyzer's **Field** list and the Results pane; the Viewer's scene gives TetraVox the same labels and units for every field of a field mesh (a TetraVox that does not know them shows the saved names, as before). Saved names in files, configs, CSVs and scripts are unchanged.

#### Simulator defaults

- **Added: set your own defaults for new simulation jobs** — **Settings ▸ Simulator** has the controls of a job's **Job settings** (electrode shape, width × height and gel, conductivity model and tissue values, output fields with carrier-only, **Write NIfTI volumes** with **Also in MNI space**, **Map fields to fsaverage**) with the same rules, and every new Simulator job starts from them. A job's own **Job settings** change that job only, and its **Reset to defaults** returns to your defaults; **Restore factory defaults** in Settings returns to the app's. Changes apply at once and are kept across restarts, so the tab has no **Save changes** button. Jobs already queued or run, and jobs whose Job settings you changed, keep their values; agents and scripts still get the app's defaults. A new row no longer copies the settings of the job you configured last (**Duplicate** still copies a job).

#### Analyzer and ex-search

- **Added: the focality of the stimulation beside the focality of the modulation** — an analysis of `TI_max`, `mTI_max`, `TI_avg` or `TI_normal` now also reports `hf_peak_focality` (the target mean of `hf_peak` over its grey-matter mean), `hf_rms_focality` (the same on the RMS carrier field `hf_rms`), `ti_selectivity` (`roi_focality` ÷ `hf_peak_focality`: above 1 the envelope is more focal than its carriers) and the carrier hot-spot size `hf_peak_focality_50_area` … `hf_peak_focality_95_area`, with the carrier means `hf_peak_roi_mean`, `hf_peak_gm_mean`, `hf_rms_roi_mean` and `hf_rms_gm_mean` in V/m. They use the same target, reference elements and weights as `roi_focality`, appear in `results.csv`, in the Results pane under **Stimulation (carrier) focality** and **Carrier hot spot**, and as `HFpeak_Focality`, `HFrms_Focality` and `TI_Selectivity` in `group_summary.csv`. They come from the same simulation's `hf_peak` and `hf_rms`, which a simulation saves by default and an analysis computes when it did not (see *Simulation outputs*); a carrier with NaN values, a zero reference mean or a NIfTI on another grid is left out, with its reason in `carrier_note` in `results.csv` and in a muted line in the Results pane. Nothing is estimated, and every existing statistic is unchanged.
- **Added: HF focality and TI selectivity for every Ex and mEx candidate** — `final_output.csv` has two more columns after `Composite_Index`: `HFpeak_Focality` (`Focality` computed on `hf_peak`, the peak carrier field of every channel, over the same ROI and grey-matter elements) and `TI_Selectivity` (`Focality` ÷ `HFpeak_Focality`). **Results ▸ Evaluated candidates** shows them as **HF<sub>peak</sub> focality** and **TI selectivity** (sortable), and the ex-search report's top table lists them. They are reported only: `Composite_Index`, the ranking and the winner are unchanged, and runs written before keep their CSV and show neither. A candidate with no ROI or grey-matter elements, or no carrier field in grey matter, has empty cells rather than 0. Each candidate takes slightly longer: about +10 ms per Ex candidate and +30 to +60 ms per mEx candidate on 200,000 elements (+25 % and +5 to +10 %), as `hf_peak` for 3 to 8 channels now tries every sign pattern, about 14× faster than before.

#### Cluster permutation

- **Fixed: a permutation that reproduces the observed grouping always counts toward a cluster's p-value** — v3.1.2 meant to count it, but compared the two cluster masses to a tolerance far finer than the single-precision t maps they are computed from, so such a permutation could still be left out and the cluster's p came out one count too small (for example 0.015 instead of 0.02 with 199 permutations). It now counts whenever it is drawn, in volume and fsaverage runs. A result is affected only if its run drew such a permutation, and then its p is low by 1 / (permutations + 1) for each one left out; re-run a cluster permutation whose p sits just below alpha. Maps, clusters and the null distribution are unchanged.

#### EEG forward model

- **Added: build a forward model in a recording's head frame** — from Python, `prepare_forward(subject, cfg, info=raw.info)` coregisters the head model to a recording's digitized fiducials instead of the EEG net's template ones, and `trans=` takes an explicit head→MRI transform as is (it must map MNE head to MRI coordinates); pass one or the other. An `info` without digitized LPA, Nasion and RPA, or whose fiducials MNE filled in itself, is refused before any computation instead of producing a wrong transform. Either one rebuilds the forward and reuses the cached FEM leadfield. Without them the forward is built exactly as before; the **Source** extension and JSON configs are unchanged.

#### Removed

- **Removed: the `map_to_surf`, `tissues_in_niftis` and `open_in_gmsh` simulation settings** — none of them changed what a simulation writes (every run writes one central surface, the NIfTIs are fixed by `map_to_vol` / `map_to_mni`, and the image has no Gmsh window to open), so `SimulationConfig` no longer has them, a run's `documentation/config.json` no longer records them, and **Results** no longer shows "Mapped to: surface" or "Tissues" for a simulation. A `config.json` that carries them still runs with `simnibs_python -m tit.sim config.json` (the keys are ignored), and older runs open as before. A script that passes them to `SimulationConfig(...)` must drop them, and a job submitted with them is refused, naming the key: rerunning a simulation job that was queued from **Results ▸ Evaluated candidates** before this version fails, so simulate the candidate again from **Results** instead. `map_to_vol`, `map_to_mni` and `map_to_fsavg` are unchanged.

#### tit.calc and simulation values

- **Changed (breaking for scripts): `tit.calc` is five functions** — `envelope(fields, direction)`, `envelope_max(fields, *, perpendicular_to=None, return_direction=False)`, `envelope_mean(fields)`, `hf_peak(fields, *, coherent=False)` and `hf_power(fields, *, coherent=False)`. `get_TI_vectors`, `get_TI_avg`, `get_TI_dir`, `psi` and the `tit.fields` module are removed, with no aliases: use `envelope_max(..., return_direction=True)` for the vectors, `envelope_mean` for `TI_avg`, `envelope` for a fixed direction. `hf_power` is the time-averaged mean square `½Σ|E_c|²`, and the saved `hf_rms` is its square root (see *Simulation outputs*). Field input that holds NaN or infinity now raises `ValueError`.
- **Fixed: `mTI_max` and mEx-search scores no longer under-report the maximum** — the old direction search stopped short of the true maximum of the joint mTI envelope; `envelope_max` finds it exactly. On real sub-101 grey matter (K = 2 from four real channel fields) 6.5 % of elements were more than 0.1 % low, the worst by about 10–15 % and in isolated low-field elements; the grey-matter mean moves by +0.02 to +0.06 % and the 99.9th percentile by less than 0.006 %. Re-run mTI simulations and mEx-searches if exact element values matter; peak and mean figures barely move.
- **Fixed: 2-channel `TI_avg` is exact** — it is now the closed form `|E1| + |E2| − ½(|E1+E2| + |E1−E2|)` instead of an average over 192 directions. Per element it moves by up to 4.6 % (99th percentile 1.8 %); the grey-matter mean moves by −0.09 % to +0.49 %. `TI_max` and `TI_normal` are unchanged to 1e-12: they are now computed by `tit.calc` (same values as SimNIBS, same speed), and so is the ex-search score.
- **Fixed: flex-search `dir_TI_tangential` optimised the wrong quantity** — it maximised `√(TI_max² − TI_normal²)`, which is not the tangential envelope (more than 10 % off at about 35 % of elements). It is now the maximum envelope over the directions in the surface plane, `envelope_max(fields, perpendicular_to=normals)`. A flex-search run with the tangential goal before this change optimised the wrong quantity; re-run it. Takes effect once the Docker image is rebuilt with this version.
- **Fixed: `hf_peak` with more than 8 channel fields is exact** — the old direction sweep could under-report it.
- **Fixed: the Visual Exporter's `TI_normal` arrows are the simulation's `TI_normal`** — each arrow is now the envelope along the surface normal (`tit.calc.envelope` of every channel field), drawn along the normal, instead of the projection of the `TI` vector onto the normal, which is a different number wherever the fields are oblique to the cortex. Every arrow now points out of the cortex, along the outward normal of the central surface (its triangle winding), where the projection pointed in or out with the sign of the `TI` vector's normal component. A zero-area triangle of the central surface has no normal and gets a zero arrow, not one along +z. Re-export `TI_normal.ply` (and a combined PLY that includes it) made by earlier versions; the other arrow files are unchanged.
- **Added: `hf_power_density` simulation output** — the absorbed (Joule) power density of the carriers, `½ Σ E_cᵀ σ E_c` in W/m³, using the simulation's own conductivities, anisotropic tensors included; shown as p<sub>HF</sub>. It is not SAR (that is this divided by the density, IEEE C95.1-2019, and no SAR limit applies below 100 kHz). Tick it under **Job settings ▸ Output fields** before the run: unlike the other fields it cannot be computed afterwards. It is not projected to fsaverage.
- **Changed: mEx-search scoring is about 3.5× slower per candidate** — it now scores the exact mTI maximum with a numba kernel (about 0.7 s per 200,000 elements against 0.2 s). numba ships in the image and `tit.calc` requires it: outside the image, `import tit.calc` without numba fails with an import error instead of running a far slower path. The run-time estimate shown before **Run** counts the slower scoring.
- **Fixed: the fsaverage projection no longer guesses a run's carrier mode** — when a simulation's `documentation/config.json` is missing, unreadable or corrupt, projecting it to fsaverage now fails for that subject and names the file, instead of treating the run as ordinary TI (which would add a carrier-only control's carriers the wrong way in `hf_peak` and `hf_rms`). A config without the `carrier_only` setting, as older runs have, is still projected as ordinary TI.
- **Convention** — all E-fields, `TI_max` and `hf_peak` are zero-to-peak for zero-to-peak channel currents; `hf_rms` is an RMS over time. `hf_peak` is the field to compare with exposure limits: ICNIRP 2010 and IEEE C95.1-2019 tabulate RMS in-situ E-field limits at 1–10 kHz with a peak limit of √2 × RMS and sum amplitudes across carriers, so compare `hf_peak` with √2 times the table, after the standards' own spatial averaging (ICNIRP 2 × 2 × 2 mm³ cube and 99th percentile, IEEE 5 mm line); a per-element value is not the compliance quantity. `hf_rms` against the RMS tables underestimates by up to √N for N carriers.

**Remediation.** Affected: any `mTI_max` from a multipolar simulation, any mEx-search score, any 2-channel `TI_avg`, and flex-search runs with the `dir_TI_tangential` goal, from every earlier version. How to spot them: a script calling `get_TI_vectors`, `get_TI_avg`, `get_TI_dir` or `psi`, or importing `tit.fields`, fails with an import error; the rest has no marker. Re-run mTI simulations and mEx-searches if exact element values matter, rescale nothing, and re-run tangential flex-searches. `TI_max`, `TI_normal` and `hf_peak` (up to 8 fields) values are unchanged; `hf_sar` is replaced by `hf_rms` (see *Simulation outputs*). The release page of the version that ships this takes this paragraph.

---
### v3.1.2 — October 22, 2026 <span class="release-pill">Latest</span> {#v312--october-22-2026}

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v3.1.2/">Release notes →</a>

A patch release for everyone on v3.1.1 that fixes many edge cases. Settings and inputs that
used to fail only after a job had started are now refused before it runs, with the reason shown
on the page, and outputs such as reports, EEG caps, Results entries, analysis folders and group
maps were checked and corrected so they describe what was really run. A much larger automated
test suite now covers these cases, and the image warps vector fields to and from MNI space again
and ships the Nilearn atlases, so atlas outlines draw offline. Update the desktop app and the
image together: the image carries the server the app talks to.

#### EEG caps

- **Fixed: an uploaded EEG cap is checked the way SimNIBS reads it** — each row's type is spelled exactly `Electrode`, `ReferenceElectrode` or `Fiducial`, electrode names are unique with no spaces around them, a later `Fiducial` row may not reuse an electrode's name at another point, and there is at least one `Electrode` row; blank rows and an Excel byte-order mark are removed before the file is stored. A file name the server refuses shows the naming rule, a name the project already uses asks **Skip** or **Replace**, and SimNIBS's landmark file `Fiducials.csv` is never listed as a cap. A cap SimNIBS cannot read gives a message, not an internal error (a server without SimNIBS answers 503 on the caps routes); **Inspect** answers within a minute even before the scalp surface is ready (the scalp-distance column then fills on the next **Inspect**); and SimNIBS's EEG10-20_extended_SPM12 cap is not flagged as collapsed (T3/T7, T4/T8, T5/P7 and T6/P8 are two names for one site). Applying a cap refreshes the Simulator's and Optimizer's net pickers at once. See [EEG Caps]({{ site.baseurl }}/wiki/eeg-caps/).
- **Fixed: GSN-HydroCel-185 and GSN-HydroCel-256 name their left and right ear points correctly** — the two were swapped. Re-apply these caps in **EEG caps** to update a subject's EEG positions; their electrodes are unchanged.
- **Fixed: a net whose electrodes collapsed onto one scalp point is refused instead of used** — a net from a cap applied before v3.1.1 can hold many electrodes on one point. A simulation, flex-search mapping, leadfield or ex-search over such a net is now refused before it runs, the 3-D view and the Blender montage export refuse it too, and each refusal says to re-apply the cap in **EEG caps**. Nets that sit correctly are unchanged.

#### Reports

- **Fixed: the simulation report is written for every kind of montage and states what was simulated** — it is now written for every kind of montage, flex-search (free-position) and free-hand montages included, whose electrodes it lists by position in millimetres. It lists only the currents the montage used and totals each channel's current by size (a reversed current no longer lowers the total), names custom tissue conductivities instead of claiming SimNIBS's standard values, reports a carrier-only control as a carrier-only control rather than as temporal interference, and centres its envelope figure on the grey-matter hot spot that holds the peak. Simulation outputs are unchanged; rebuild a missing report by re-running the simulation.
- **Fixed: every report is listed with the job that wrote it, and kept** — the DTI QC report is attached to its pre-processing job like the charm, simulation and search reports; two reports of one kind for one subject that finish in the same second (two parallel ex-search jobs, say) are kept as two instead of the second replacing the first; a report that fails to write (a full disk) leaves no empty entry in the Reports list; and a report opens exactly as written, so a SimNIBS charm report with Windows line endings or a byte that is not UTF-8 is no longer altered or refused. Pre-processing reports of a subject that so far has only DICOMs staged are listed too.

#### SimNIBS in the image

- **Fixed: vector fields warp to and from MNI space again** — in the v3 images, warping a vector volume with SimNIBS (`subject2mni` or `mni2subject` on a mesh carrying `E` or `J`, or on a 3-component NIfTI; `run_simnibs` with `map_to_MNI` in a notebook) stopped with `ValueError: Unable to avoid copy while creating an array as requested`. A build-time patch written for the old NumPy 1 environment overrode SimNIBS 4.6's own code; the image now runs SimNIBS's code as shipped. TI-Toolbox's simulations, analyses, searches, EEG caps and head models only warp scalar fields and give bit-identical results.

#### Flex-search

- **Fixed: focality searches with a non-ROI of a different type from the ROI run again** — a **Specific region** non-ROI can now be a different kind of region from the ROI (for example a sphere ROI against a cortical atlas region, the form's default non-ROI); each is built as what it is, and a volumetric sphere non-ROI is now really volumetric. Before, these searches failed when they started. Searches where both regions are the same type, and **Everything else** non-ROIs, behave as before. **Optimizer ▸ Flex ▸ Objective ▸ Non-ROI**.
- **Fixed: Mean and Max flex-searches write their report** — a flex-search with the **Mean** or **Max** goal records no background field, and since v3.0.2 its report stopped on that empty column with `could not convert string to float: ''`, although the search itself finished. The report now shows the target's mean and 99.9th percentile without a background figure. Search results, and the reports of focality searches, are unchanged; rebuild a missing report with `simnibs_python -m tit.reporting.generators.flex_search <project> <subject> <run folder>`.
- **Fixed: flex-search settings that used to fail after the job started are refused when you submit, and the Optimizer says why** — a single threshold-based focality run without thresholds; more than two, reversed, non-positive or non-finite thresholds; a zero, negative or NaN current, electrode size, gel thickness, sphere radius or minimum distance; an unequal ellipse; a non-ROI identical to the ROI; an Adaptive or Multi-threshold job whose goal is not threshold-based focality; and a run name the project cannot store (for example `Thalamus (L)`) are refused with a message naming the field. The flex form shows the reason under the field and keeps **Run** disabled (a blank or malformed fixed threshold and a 0 mm minimum distance included), and an ellipse electrode now has a single **Diameter** input. Adaptive and Multi-threshold focality with **Optimize current ratio** can now be submitted, and a thresholds value given as a number (by an agent or in a notebook) is read as that value instead of crashing the job. **Optimizer ▸ Flex**.
- **Fixed: a failed or oddly named flex run no longer hides results** — a failed run writes `null` instead of `Infinity` in `flex_meta.json` and its events, so its result now reaches the desktop, and a badly named run folder no longer hides the subject's other flex runs.
- **Fixed: re-running flex-search into an existing run folder replaces the previous run** — its restart histories, EEG-net mapping and final simulations are replaced. Before, it failed with `FileExistsError` after an aborted run, or mixed the old outputs into the new run. Files you added to the folder are kept.
- **Fixed: the flex-search report describes the run that exists** — it no longer fails on a run whose `candidate_history` holds a `.DS_Store` or AppleDouble file, a missing restart or a stale extra one; restarts are matched by folder name, a failed run states the configured current, and a focality (ROC) report states its thresholds in V/m.
- **Fixed: a union of the same label from two MNI atlases keeps each atlas's region.**
- **Changed: an Adaptive or Multi-threshold flex job is one run folder with one report** — its Mean TImax calibration is kept in `<run>/mean_calibration/` and is no longer a separate Results entry or Simulator source.
- **Added: the flex run records say more** — `flex_meta.json` records `n_pairs` and the mapped `eeg_net` (`null` without mapping), and a Multi-threshold job's manifest has a `pareto` section: every threshold pair with its thresholds in V/m, score and status, plus the promoted point.
- **Changed: the Min distance help says how SimNIBS measures it** — between the skin nodes under each electrode, not edge to edge; the FlexConfig docs say the same. **Optimizer ▸ Flex ▸ Electrodes ▸ Min distance**.
- **Fixed: a flex search run with mapped electrodes shows its mapping in the Simulator** — a search with **Run simulation with mapped electrodes** saved its mapping as `electrode_mapping.json`, but the Simulator, Results and plans only look for `electrode_mapping_<net>.json`, so the run looked as if it had never been mapped and **Map to net** computed the mapping again. New runs save it as `electrode_mapping_<net>.json` (for example `electrode_mapping_GSN-HydroCel-185.json`), and runs made before are read from their `electrode_mapping.json` as they are, without renaming anything. **Optimizer ▸ Flex ▸ After the search ▸ Run simulation with mapped electrodes**, then **Simulator ▸ Flex result**.
- **Fixed: mapping a flex-search result onto an EEG net gives a montage that runs** — an electrode that landed on a 10-10 cap's reference electrode (Cz) is mapped to the nearest real electrode instead of to a label the simulation then refused. A mapping that would put two electrodes on one label, or a net with no or too few electrodes, a missing coordinate or a repeated label, is refused with a message naming the net and the problem instead of producing a job that cannot run correctly.
- **Added: the Simulator warns when mapping moves an electrode far** — when mapping a flex-search result onto a net moves an electrode more than 20 mm from where the optimiser placed it, the Simulator says so and shows the distance to 0.1 mm. **Simulator ▸ Flex result ▸ Map to net**.

#### Ex-search and mEx-search

- **Changed: Ex "All combinations" mode evaluates each physical montage once** — 3 pairings per four-electrode set, or 6 when the current splits are not symmetric, instead of 24 polarity and order duplicates. Pool runs are 4 to 8 times shorter, and the report's top-25 table lists distinct montages. **Optimizer ▸ Ex ▸ All combinations**.
- **Fixed: every current split is evaluated, and runs record their exact currents** — with a current step finer than 0.1 mA, ex-search evaluated only the splits that differ at one decimal (a 0.05 mA step kept 20 of 39); every split is now evaluated, and `final_output.csv` records its exact currents (1.75 / 0.25 mA, not 1.8 / 0.2). Simulating an mEx result whose pair current is not a multiple of 0.1 mA now drives all four pairs at that current, runs written before this fix included; before, two of the pairs used the value rounded to 0.1 mA.
- **Fixed: bucket mode no longer evaluates montages that repeat an electrode** — a channel from an electrode to itself, which carries no field, or two channels sharing one electrode.
- **Fixed: the left/right symmetric search pairs true mirrors on subject-space caps** — the midsagittal plane is now fitted to the cap instead of assumed at x = 0, so Fz maps to itself, P4 to P3 and TP10 to TP9.
- **Fixed: the cost line states the number of rows the run writes** — eight identical mEx buckets give 40,320, not 16,777,216. A row with no runnable montage or split, or with a current outside its range, cannot be run and says why.
- **Fixed: a cancelled search ends at once and leaves no run that looks finished** — cancelling an ex-search or mEx-search job stops it at once, and Results no longer shows the partial run as finished.
- **Fixed: a target that misses the head model stops the search before it starts** — an ex/mEx search whose target does not overlap the head model now stops with an error naming the ROI. Before, it searched with every montage scoring 0.
- **Fixed: several separate targets in one row run into their own folders** — an Ex or mEx row with several separate targets wrote every target into one `ex-search/<run name>` folder; each target now runs into `<run name>_<ROI>`, and the Run name help says so. A row with one target keeps its run name exactly.
- **Fixed: mEx searches write a report** — it lists all four channels and their currents, and the results CSV now includes the channel 3 and 4 currents.
- **Fixed: ex-search reports render every run and state true facts** — a run with a single montage, tied zero scores, or rows with missing or invalid numbers no longer fails silently; the page says how many rows were left out, and the search median is the true median. The report states the real per-channel current limit when none was set (no longer "at most 0 mA"), takes electrode size and conductivity from the leadfield's own SimNIBS log rather than another net's, and describes combined, MNI and atlas targets as what they are, not as a sphere.
- **Fixed: electrode maps always show the winning montage** — a best montage using AFz, Iz, I1, I2 or E256 was silently left out and a lower-ranked montage ringed as the best; montages with a missing or infinite score are now left out instead of distorting the ranking and colour scale.
- **Fixed: rebuilding a run's electrode maps finds the subject's EEG cap** — `python -m tit.opt.ex.results <run folder>` now finds the cap file from the run folder, so runs made inside the container, or saved with only the leadfield's file name, no longer fail with "Could not infer an EEG-position CSV".
- **Fixed: no Tissue type choice for an Ex/mEx subcortical target** — the exhaustive search always scores every head-model element inside the region, so the choice never had any effect.
- **Fixed: the symmetry help describes Cross pairs correctly** — it said Cross pairs *additionally* requires pairs 1↔3 and 2↔4 to mirror each other; Cross pairs in fact *replaces* the within-pair rule: pair 3 mirrors pair 1 and pair 4 mirrors pair 2, pole by pole, and a pair's own two electrodes need not mirror each other. The search itself is unchanged. **Optimizer ▸ mEx ▸ Symmetry ▸ (?)**.
- **Changed: ex-search runs one balanced current split by default, so a search takes about a seventh of the time** — the Optimizer's Ex method now starts at total 2.0 mA, step 0.2 mA and channel limit 1.0 mA, so each montage runs at 1.0 / 1.0 mA and iterations equal montages (the old 1.6 mA limit ran 7 splits per montage). An exhaustive search over every 10-10 montage found the best montage almost always best at 1:1, at most 0.8 % better at another split for the mean goal. To test splits, raise **Optimizer ▸ Ex ▸ Current ▸ Channel limit** above half the total. From Python, `ExConfig(channel_limit=None)` (the default) now means the balanced split instead of a sweep up to total − step; set a limit to sweep as before. Configs and scripts with an explicit channel limit run exactly as before, and existing results and reports are unchanged. See [Current ratios]({{ site.baseurl }}/wiki/ex-search/#current-ratios).

#### Target picker

- **Fixed: the Explode button now reads Collapse while the atlas is exploded** — it kept saying **Explode** after the regions had spread apart, so nothing said how to bring them back; it now switches to **Collapse** and back. Optimizer and Analyzer target panes, MNI mode.
- **Fixed: a target follows its row to another subject** — moving or duplicating an Optimizer or Analyzer row onto another subject now clears the old subject's subject-space sphere or mask and its saved ROIs (in the Optimizer, the flex non-ROI too), with a note saying so. Before, the old subject's coordinates were measured or optimised in the new subject's head.
- **Fixed: a saved ROI comes back as it was saved** — it is listed with the coordinate space and radius it was saved with (an MNI ROI no longer comes back as subject space), and NaN or infinite coordinates are refused.

#### Analyzer

- **Fixed: Subcortical targets in the Analyzer run** — every Analyzer job with a **Subcortical** target stopped with "analysis_type='subcortical' is not implemented". It now measures the selected regions of the chosen volume atlas: in **Subject** space the subject's own atlases (charm's `labeling.nii.gz`, FreeSurfer/FastSurfer volumes including the hippocampal and thalamic subfields, label volumes in `m2m_<id>/masks/`), in **MNI** space the shipped MNI atlases, transformed with the subject's own registration as an MNI mask is. With **Combine regions into one ROI** the regions are one ROI, otherwise one analysis each, and group analyses take the target too. Results go to `Analyses/<Mesh|Voxel>/subcortical_<region>_<atlas>/` and appear in **Results**. A deep structure has no cortical surface: analyze it in **Voxel** space (in **Mesh** space the job stops with "does not overlap the gray-matter surface"). A region named exactly as an atlas label now gets that label before a longer name containing it ("subiculum" measured "parasubiculum" before), and a target whose atlas or region cannot be found is refused before the job starts. **Analyzer ▸ Job settings ▸ Subcortical**.
- **Fixed: each group analysis keeps its own results** — every group analysis wrote `group_summary.csv` and `group_comparison.pdf` into one folder, `derivatives/ti-toolbox/logs/group_analysis/`, so each run replaced the last, and a group run over several spheres or several separate regions (one job each) kept only the last target's results. Each run now has its own folder, `derivatives/ti-toolbox/group_analysis/<simulation>_<space>_<target>_<YYYYMMDD>_<HHMMSS>/`, holding its summary, plot and log (two runs started in the same second get two folders); it is listed under **Results ▸ Group ▸ Group analyses** and the job links its files as before. Each subject's analyzer log holds only that subject's analysis, and a missing normal-component value is left empty instead of written as 0, so voxel groups no longer show a zero Normal panel and a mesh subject without normals no longer lowers the group average. Per-subject results are unchanged, and older results in `logs/group_analysis/` stay where they are. Scripts: `PathManager.logs_group()` is replaced by `PathManager.group_analysis(name)`; `run_group_analysis(output_dir=...)` still writes where it is told.
- **Fixed: the Analyzer's target editor no longer offers what the Analyzer ignores** — a sphere target showed **Volumetric evaluation** with a tissue choice, and a subcortical target a **Tissue type**, but the Analyzer never read them: the row's **Space** and **Job settings ▸ Tissue** decide what is measured. They are gone from the Analyzer (the Optimizer keeps them). Several spheres in one row are measured as one analysis each, never as a union, and the row's target line now says "(separate jobs)", as it already did for separate regions; the picker's help says so too instead of "Multiple rows union into one combined target", which stays true in the Optimizer. Analyses are unchanged. **Analyzer ▸ Job settings**.
- **Fixed: an empty or invalid target is one clear error** — an ROI with no positive field value (a sphere outside the head, an absent atlas label, a disjoint tissue) now stops with an error naming the region and the space or tissue, and nothing is written; before, mesh space returned zeros and voxel space crashed in numpy. A sphere needs a positive finite radius and a centre of three finite numbers in the config, the API, the Analyzer's target check and the Python API, and a group run refuses a bad sphere, or a subject-space sphere, once before any subject. A voxel DK40 analysis of a region the DKT volume parcellation lacks (banks of the STS, corpus callosum, frontal pole, temporal pole) is refused when the job is submitted.
- **Changed: a voxel region name that matches several atlas labels is refused** — a bare `insula`, in both hemispheres, is refused with the candidates listed instead of silently measuring the left hemisphere.
- **Fixed: mesh analysis of TI_normal runs** — it reads the normal mesh instead of failing with `KeyError`, and a field the central surface lacks is refused by name before the job starts. The **Field** dropdown offers only fields the analyzer accepts.
- **Changed: mesh `n_elements` counts the positive ROI nodes**, as voxel analyses always did, and NaN or ±infinite values no longer enter the focality percentiles.
- **Fixed: an analysis of another field or tissue gets its own folder** — it is named with `_<field>`, `_WM` or `_both` instead of replacing the envelope/grey-matter analysis. A bare mesh region is named by the request (`cortical_insula_DK40`, previously `cortical_2regions_DK40_<hash>`), a region listed twice is named once, and labels with `(` or `,` are written with a hash so Results can open them. Existing folders keep their names. The run plan names every folder the analyzer writes, a group analysis's summary folder included, so replacing an existing group output needs the overwrite confirmation.
- **Fixed: the histogram and the numbers agree** — the histogram draws its 50/75/90/95 % cutoff lines at the area-weighted 99.9th percentile the results table reports, so they match on surfaces with uneven node areas, and `hf_sar` analyses are labelled in (V/m)² instead of V/m in the Results pane, the histogram and the 3-D scene colour bar.
- **Fixed: the Analyzer's job count matches what Run submits** — a row with two spheres or two separate regions counts as two analysis jobs.

#### Group statistics

- **Fixed: NIfTI group averaging honours its Space choice** — the **NIfTI pattern** field was pre-filled with the MNI file and always sent, so choosing **Subject volume** still averaged the MNI volumes (while recording `"space": "subject"`), and the subject-space default named a file no simulation writes (`grey_<sim>_TI_max.nii.gz`). The pattern field is now empty by default and shows the chosen space's file as its placeholder (`grey_<sim>_TI_subject_TI_max.nii.gz` for Subject); changing **Space** clears it, and a pattern you type still wins. Each subject's own volumes are on that subject's voxel grid, so **Subject volume** works when every row is the same subject (comparing its simulations); to average across subjects use **MNI volume**. **NIfTI group averaging ▸ Analysis configuration**.
- **Fixed: cluster permutation and NIfTI group averaging read mTI simulations** — both looked for every simulation's volumes in `TI/niftis/`, so a run over an mTI simulation was refused before it started with "re-run with map_to_mni", which no re-run could satisfy. An mTI simulation is now read from `mTI/niftis/` with its own file names (`grey_<sim>_mTI_MNI_MNI_mTI_max.nii.gz`); a NIfTI pattern you type in the 2-pair spelling is read the same way (`_TI_` becomes `_mTI_`), and one already spelled for mTI is used as is. When a simulation has no MNI volumes, the message now says to tick **Generate MNI NIfTI outputs** under **Simulator ▸ Job settings ▸ Standard-space outputs** and re-run it. 2-pair TI simulations are read exactly as before.
- **Fixed: Correlation analyses in the Cluster permutation panel run** — a **Correlation** job started from the panel ran as a group comparison and failed on its first subject (`missing ... 'response'`), because its configuration did not say which analysis it was. The panel now sends `_type` (`CorrelationConfig` or `GroupComparisonConfig`) and the statistics runner, the plan and the job queue read it, so a correlation runs as a correlation and writes `derivatives/ti-toolbox/stats/correlation/<name>/`; a config's `mode` key chooses the same analysis in the plan as in the runner. A correlation, from the panel or a script, now also writes `permutation_details.txt` (each permutation's effect-size shuffle and largest cluster), as a group comparison always has. Group comparisons are unchanged; scripts that pass `"mode": "correlation"` work as before, and `serialize_config` now writes `_type` for both. **Cluster permutation ▸ Analysis type ▸ Correlation**.
- **Fixed: a correlation that lists one subject twice uses every row** — with two simulations of one person, the volume path gave every row of that subject the last row's effect size and weight, so r, the permutation null and `analysis_summary.txt` were computed on the wrong vector. Each row now keeps its own values.
- **Fixed: cluster results state the test that ran** — a negative-correlation cluster's peak r is its most negative r (the largest absolute r, with its sign) in the result, `analysis_summary.txt` and the fsaverage `significant_clusters.csv`, not the cluster's weakest r, and the correlation summary states the two-sided test that ran instead of "positive correlations only". The group-comparison summary lists the same sign-separated clusters the permutation test found, each with its signed mass and p-value, ordered by absolute mass; before, two touching clusters of opposite sign were merged into one entry with no mass or p. A permutation that reproduces the observed grouping now always counts toward a cluster's p-value; rounding in the order its values were summed could leave it out and give a slightly too small p.
- **Fixed: fsaverage group comparisons fail the way volume ones do** — a 1-vs-1 design raises "No voxel could be tested" (it reported success with 0 clusters), unequal paired groups raise "Paired test requires equal sample sizes" (a numpy broadcast error before), and zero-variance vertices are excluded, so no infinite statistic reaches the cluster table or `null_distribution.csv`.
- **Fixed: the null-distribution figure is honest** — observed clusters are placed on the null's scale and coloured by the configured alpha, which the legend shows, and no empty histogram is drawn when no cluster formed: the summary then says the threshold was not computed, and `result.cluster_threshold` is NaN instead of 0.0.
- **Fixed: participant CSVs keep zero-padded subject IDs** — `001` stays `001` instead of becoming `1`, a file saved by Excel with a byte-order mark or with spaces around cells is read correctly, and a row missing its group label is refused with its line number.
- **Changed: group analyses refuse numbers that cannot give a valid result** — a permutation count too small for any p-value to fall below alpha (20 at alpha 0.05, 100 at 0.01), an alpha or cluster-forming threshold outside (0, 1), a response other than 0/1, a paired test with unequal groups, non-finite or constant effect sizes, and non-positive weights are refused. Numpy numbers and a whole-valued 1000.0 count are accepted. The **Cluster permutation** panel blocks Run on a 2-row correlation or an unequal paired design with the server's reason, and offers **Replace and rerun** for an existing analysis name.
- **Fixed: re-running a group tool replaces its earlier folder** — a NIfTI-average re-run that cannot read its inputs leaves the earlier run's files. NIfTI averaging trims group labels, resolves hyphenated difference pairs, refuses pairs naming no group, one group twice or a repeated pair, and locks its output folder; group jobs read-lock the simulations they read.

#### Nilearn visuals

- **Fixed: Nilearn visuals draws the field and its atlas outlines by default, offline, for TI and mTI simulations** — the panel started at 0.3–5 V/m, above the whole field of a typical TI simulation (they peak around 0.1–0.3 V/m), so its PDFs came out blank. Both cutoffs now start empty, and an empty cutoff is taken from the averaged field: the 95th (minimum) and 99.9th (maximum) percentile of its non-zero voxels. Type a value to set a cutoff in V/m, or tick the checkbox to give it as a percentile of those voxels; switching between the two clears both. The figures print weak-field cutoffs with three significant figures (not "0.01-0.01"). The three outline atlases (Harvard-Oxford cortical and subcortical, Schaefer 2018) now ship with TI-Toolbox in `resources/atlas/`, so nothing is downloaded at image build or at run time and outlines appear without network access; if one cannot be loaded, the job log says why and the figure is drawn without outlines. Outlines are drawn in cool colours so they are no longer mistaken for field. mTI simulations can now be visualised from their `mTI_max` field, alone or averaged with TI simulations. Output files and the `derivatives/ti-toolbox/nilearn_visuals/<name>/` folder are unchanged. **Settings ▸ Extensions ▸ Nilearn visuals**, then **Extensions ▸ Nilearn visuals**. In scripts, the `tit.plotting.nilearn` helpers' `min_cutoff` now defaults to the same data-driven value instead of 0.3 V/m.
- **Fixed: Nilearn visuals refuses a job it cannot draw before it runs** — a path-like output folder, an empty display range (minimum cutoff at or above the maximum) and a repeated subject/simulation pair are refused, and **Generate images** stays disabled with the reason.
- **Changed: Nilearn visuals outlines the MNI atlases the ROI picker offers** — Schaefer 2018 now has 400 parcels (it had 100), the Harvard-Oxford cortical atlas is split into left and right regions (96, it had 48), and all three are 1 mm maps (Harvard-Oxford was 2 mm). Saved configs keep working: the `atlas_name` values are unchanged. In scripts, a `selected_regions` list for the cortical or Schaefer atlas now names other regions, because their label numbers changed. **Extensions ▸ Nilearn visuals ▸ Atlas selection**.
- **Removed: the AAL atlas from Nilearn visuals** — its download host was often unreachable, so it could not be offered offline. Pick Harvard-Oxford (cortical or subcortical) or Schaefer 2018 instead. A saved config or script that names `atlas_name` `"aal"` is refused before it runs, with the list of atlases offered. **Extensions ▸ Nilearn visuals ▸ Atlas selection**.

#### Simulator

- **Fixed: a free-hand placement with eight or more positions runs as mTI from a plan too** — a plan (an AI agent's proposal, or `POST /api/plan/sim` with a free-hand montage source) used only the first four positions of a saved free-hand placement, so an 8-position placement ran as 2-pair TI while the Simulator ran the same placement as 4-pair mTI. Plans now pair every position in the order it was saved (1+2, 3+4, …), exactly as the Simulator does, and a placement with any count other than 4 or a multiple of 4 from 8 up is left out of the plan with a warning naming its count. Four-position placements saved by the app run as before.
- **Fixed: the free-hand editor no longer saves a placement that cannot run** — **Save placement** accepted 6 or 10 positions (3 or 5 pairs), and the job then failed when it started with "Invalid number of electrode pairs: 5". It now saves 4 positions (2 pairs, TI) or 8, 12, 16 … (an even number of pairs from 4, mTI), and it refuses two positions with the same label, naming the label, because a saved placement keeps one position per label (the second was silently dropped). **Save** also stays disabled until every electrode has been placed on the scalp and no two electrodes are on the same spot. Validation, plans and job submission now also refuse a montage with an odd number of pairs, with the same message, instead of accepting it and failing at run time. Valid placements, and existing ones, are unchanged. **Simulator ▸ New placement**.
- **Fixed: the montage editor no longer saves a montage that cannot run** — editing a montage with 5 or 7 pairs (from a hand-written montage list) let it save, and the simulation was then refused with "Expected an even number of electrode pairs". **Save** now needs exactly 2 pairs (TI) or an even number from 4 (mTI), and the editor says so; it also refuses a montage that uses one electrode twice or a name the project cannot store, with the reason. The server refuses to save any montage or free-hand placement the simulator cannot run (wrong pair shape or count, a kind or type that does not fit the pair count, repeated electrodes, a type other than U/M, an odd electrode count, NaN or infinite coordinates, a label that is not text), and saving a montage under the other polarity replaces it instead of keeping the name as both a TI and an mTI montage. **Simulator ▸ New montage** / editing a montage.
- **Fixed: the Simulator runs exactly the currents a job row shows** — a blank current runs at 1 mA instead of 0 mA, and an mTI row sends one current per channel instead of failing on submit. The run's `config.json` lists only the currents the montage used, and records custom tissue conductivities.
- **Fixed: a simulation that cannot run is refused before any FEM solve** — a job row cannot run, and says why, with a channel at 0 mA or below, an unsupported number of electrode pairs (1, 3, 5, …), a TI-saved montage with four or more pairs, or an electrode used twice. The server also refuses more than 26 electrode pairs, two montages with the same name, free-hand electrodes less than 1 mm apart, a NaN or infinite coordinate, and a non-finite current on a used channel; before, these failed after the solves or ran.
- **Fixed: re-running a montage with overwrite leaves exactly what its config.json says** — the earlier run's MNI volumes, `hf_peak`/`hf_sar` fields and fsaverage projections are removed; run history and `Analyses/` are kept. Without overwrite, `run_simulation` refuses a montage that already has a result before solving any montage of the config. An existing fsaverage projection is planned as replaced only when overwrite is set, as the runner does.
- **Fixed: mTI with 10 or more channels names its carrier meshes J to Z** — instead of A0 to A9.
- **Fixed: every simulation gets the right montage image** — simulations on the 10-10 caps get their image when an electrode is AFz, caps named without the `.csv` suffix get one too, and re-running an mTI simulation with different electrodes no longer leaves the previous run's rings on the image.
- **Fixed: NIfTI export runs when a montage name or subject id contains "normal"** — for example `abnormal` or `normal01`. Only the surface-only `*_normal` meshes are skipped.
- **Fixed: the tissue conductivity editor no longer claims its values apply to every montage in the run** — settings belong to one job, or to the defaults for jobs without their own.

#### Results

- **Fixed: Results and the Analyzer use the field names the simulator wrote** — simulation volumes are listed as `hf_peak`, `hf_sar`, `TI_avg` and `mTI_max` instead of truncated names (`peak`, `sar`, `avg`, `max`) that the analyzer then rejected with "Unknown field". High-frequency `magnE` volumes of anisotropic (`vn`, `dir`, `mc`) simulations are listed and shown in the viewer, not only scalar-conductivity ones. Voxel analysis, group tools and Results find a simulation's subject-space NIfTIs whatever the simulation is called (`MNI_target`, `hippo_MNI`, `grey_matter`), such subject files are no longer tagged as MNI, and group analysis of an mTI simulation opens its `TI_avg` volumes.
- **Changed: Results lists only simulation NIfTIs named the way the simulator writes them** — volumes from v2.0–2.2 projects, or files you added yourself, no longer appear under a guessed field; their names are written to the debug log.
- **Fixed: a simulation opens its own report** — it took every report whose path contained its name, so a simulation called `TI` got the charm report. Simulation reports from before the report title named its run are not linked to a simulation.
- **Fixed: every analysis appears with its own numbers, pictures and scene** — analyses run without visualization (the scripting default) are listed; re-running an ROI with another field shows the new field; the same ROI analysed in mesh and voxel space is two analyses; analyses show their histogram and scene pictures, not only older PDF figures; and **Open in viewer** opens the analysis's own scene. The analysis pane shows the whole-tissue mean, maximum and percentiles in their own group named after the tissue, and labels the focality extent as a share of the 99.9th percentile rather than of the maximum.
- **Fixed: Results ▸ Group lists every group run** — a group comparison and a correlation with the same name are both selectable, NIfTI averaging runs appear with their average and difference maps, and the group-statistics pane shows the cluster threshold of size-statistic runs and the settings, groups and significant clusters of surface (fsaverage) runs. In **Overview ▸ Recent jobs**, a finished group-statistics, Nilearn or NIfTI-average job opens on the Group row (it opened the first subject's tree or Jobs), and the subject you had open stays selected.
- **Fixed: Results shows fresh outputs and explains instead of showing a blank tree** — after a run is re-run with **Replace**, Results shows the new settings, key numbers and group statistics (the old values stayed until the app restarted). If a subject's or the group's outputs cannot be read, Results shows the server's reason, and a subject only staged in `sourcedata/` shows "no outputs yet".
- **Fixed: search previews describe the run** — a flex run's preview names the ROI atlas file, labels, hemisphere and every sphere centre, and shows the EEG net; the ex-search preview lists an mEx run's channels 3 and 4 and a pool run's electrodes.

#### Pre-processing

- **Fixed: leftovers no longer count as done** — an interrupted FastSurfer, charm, QSIPrep or tissue-analysis run, or a zero-byte DTI tensor, no longer shows as done on **Subjects** and **Overview**; **Skip existing outputs** stops and asks you to choose replace instead of keeping it, and the plan warns for that stage. Each stage's "exists" in the plan is now the output skip and replace act on, not just a folder, and an empty `m2m_<id>` folder no longer blocks charm.
- **Fixed: QSIRecon re-runs can be skipped or replaced** — skip, replace and the plan now look in `derivatives/qsirecon/derivatives/qsirecon-*/sub-<id>`, where QSIRecon writes and its own guard refuses, not in `derivatives/qsirecon/sub-<id>`.
- **Fixed: DICOM conversion finds every DICOM and never reports an empty success** — extensionless and Siemens `.IMA` DICOMs are recognised by the DICOM file marker; when nothing converts from folders that hold files, it stops and names the folder. **Skip existing outputs** skips per modality, so a T2w added after the T1w is converted, and the job waits on a missing T1w or DWI only while that input's DICOMs are still to be converted.
- **Changed: tissue analysis follows skip and replace like the other stages** — re-running it over an existing analysis with neither policy stops instead of overwriting silently.
- **Fixed: tissue analysis measures thickness across the tissue, in any orientation** — bone, skin and CSF thickness are measured across the tissue instead of averaging each voxel's distance to the edge, so a 6 mm skull reads about 6 mm rather than about 4 mm. Volumes, thickness and figures are the same whatever orientation the head model is stored in: it no longer drops almost the whole head when the brain sits low in the image, labels the figure axes with the right anatomical directions, and prints voxel sizes as plain numbers.
- **Fixed: tissue-analysis figures show the tissue** — the thickness views cut through the tissue's centre instead of the volume's middle (which put the axial view in the skull base), draw the whole band coloured by thickness instead of a dotted one-voxel mid-line, use colour maps whose thinnest values are visible on white, give each possible thickness its own histogram bar, and keep the statistics box off the bars. The numbers are unchanged.
- **Fixed: submission refuses what pre-processing would refuse hours later** — QSIRecon atlases when QSIPrep will not write the MNI transform they need, QSIRecon without a QSIPrep result, and tissue analysis without a charm segmentation. A subject list or a number given as text (subject `"001"` instead of `["001"]`, memory `"16"`) is refused with a message naming the setting, instead of running on subjects 0, 0 and 1 or passing a broken memory limit to QSIPrep.
- **Fixed: FreeSurfer starts when Docker has 16 GB of memory** — it refused because the system reports slightly less than 16 GiB.
- **Fixed: a floating-point FastSurfer segmentation lists the same regions as its NIfTI copy** in the atlas region list.

#### Visual exporter

- **Fixed: mTI simulations export** — cortical regions, field vectors and the montage scene read the run's own mTI central surface, its `mTI_max` field and every channel (A, B, C, …). Before, these exports failed reading a TI surface that mTI never writes.
- **Fixed: sub-cortical field-coloured PLYs are coloured from the unmasked subject-space field** — and from `mTI_max` for mTI runs. Before, the colour source depended on the simulation's name (some names picked the grey-matter-masked copy), and mTI runs got no PLY.
- **Fixed: an export that would fail is refused before it is queued** — job preflight now refuses, naming the same file the runner would, a missing surface, carrier meshes, simulation record, net CSV, conductivity, scalp mesh or labeling volume. A montage export of a simulation placed by coordinates is refused with "This simulation has no recorded EEG net." (it failed with `KeyError 'eeg_net'` after writing files), a cortical-region export whose names match no atlas key names those entries and lists the available regions (it exported every region), magnitude-scale percentiles that do not rise (blue ≤ green ≤ red) are refused instead of clamped, and a config without `_type` is refused at validate, plan and submit.
- **Fixed: an explicit output_dir is honoured for region and vector exports** — the plan reported it and the job wrote to the default folder; a blank `output_dir` means the default in every mode.
- **Fixed: a field vector pointing straight down draws a downward arrow.**
- **Changed: a sub-cortical export that names a simulation that does not exist refuses before writing anything** — it used to warn and export uncoloured meshes.

#### Privacy

- **Fixed: `TIT_NO_TELEMETRY=1` on your computer turns telemetry off inside the container too** — the variable was not passed into the container, so with telemetry enabled in Settings the server and its jobs kept sending usage events even though you had set it. The desktop app (when it starts the container), `loader.sh`, `loader.py` and `tit launch` now forward it; `1`, `true` or `yes` stops all sending. The desktop app sees only its own environment: started from a terminal or by the loader it picks the variable up, but opened from the Dock or Finder on macOS it does not, so there use **Settings ▸ Project ▸ Telemetry ▸ Send anonymous usage data** (or `launchctl setenv TIT_NO_TELEMETRY 1`, then reopen the app). A container that is already running keeps its environment until TI-Toolbox restarts it. Unset, nothing changes.
- **Fixed: usage data no longer carries subject identifiers, user names or network paths in error messages** — with telemetry on, a failed operation sends its error type and the first 80 characters of its message; file paths were removed from that message, but a subject named in it was not, so failures such as "charm failed for subject 101" or FastSurfer's and group statistics' equivalents sent the subject's id. Subject identifiers (`sub-<id>`, `m2m_<id>`, `subject <id>`, `subject_id=<id>`, every id in a list of subjects, and the failing job's own subject ids wherever they appear) are now replaced by `<id>` before anything is sent, and Windows and network-share paths and user names that contain spaces are removed too; the error fingerprint is computed from the scrubbed message, so the same failure on two subjects now counts as one. The **Settings ▸ Project ▸ Telemetry** text says exactly what is sent. Nothing changes with telemetry off.
- **Fixed: telemetry turns on only for an explicit yes, and never breaks a job** — a setting of `"false"`, `1` or `null` keeps it off, and Settings refuses values that are not true or false. A damaged telemetry settings file or an unwritable settings folder no longer makes simulations and other tracked operations fail, and an error message with a very long unbroken string (base64 or hex) no longer makes the failing job hang for seconds while the report is prepared.

#### Desktop app

- **Removed: the Quick notes switch in Settings ▸ Extensions** — it turned nothing on or off: the notes drawer was always there. Quick notes stays available everywhere with **⌘⇧N** (Ctrl+Shift+N) or **Open quick notes** in the command palette, and your notes are unchanged. A project whose settings still list the old switch opens and saves as before.
- **Fixed: Quick notes keeps text typed just before the drawer, the window or the app closes** — or the window reloads.
- **Fixed: an extension toggle applies at once, without reloading the window** — running notebook kernels and unsaved work on other pages survive, and the "Reload now" banner is gone. **Settings ▸ Extensions**.
- **Fixed: Stop Docker stack asks before stopping running or queued jobs** — and cancels them first if you confirm; **Cancel** leaves the project open. **Settings ▸ Server**.
- **Fixed: quitting while a project's server is still starting leaves no container running** — and a container whose server never answered is stopped when you quit. The Docker card in Settings now says that quitting stops the container (it said quitting left it running).
- **Fixed: a release-candidate or development build is offered its final release** — the two versions were compared as equal. A disabled update check names the real reason (`TIT_UPDATE_CHECK=0`) instead of calling every build a development build.
- **Fixed: the Viewer keeps to the subject you chose** — after a change of subject it drops the other subject's FastSurfer, FreeSurfer, QSIPrep and raw BIDS files as well as SimNIBS ones, and the server refuses a scene that mixes two subjects' files. A project folder named like a subject (`sub-pilot`) is no longer mistaken for one.
- **Fixed: the keyboard sheet and Help describe TetraVox** — **⌘⇧V** (Ctrl+Shift+V) opens or brings forward TetraVox, and the mouse and arrow keys of an in-app viewer canvas that no longer exists are no longer listed.

#### Jobs

- **Fixed: a job that needs more memory than Docker gives the container no longer waits forever** — a FreeSurfer run or a Blender montage export (about 16 GB) on a container with less memory, or a simulation of many montages, sat at *Waiting on the resource budget* indefinitely. It now runs alone: it starts once no other job is running, and nothing else starts beside it until it finishes. Its log opens with *"needs about 16 GB of memory, more than the 7.8 GB this container has: it will run alone, once no other job is running, and may still run out of memory (give Docker more memory to avoid that)"*. FreeSurfer still refuses to start below its own 16 GiB minimum, with its own message. Jobs that fit run as before. Give Docker more memory in **Docker Desktop ▸ Settings ▸ Resources** to run such jobs beside others.
- **Fixed: job memory claims cover measured peaks** — a simulation claims 9 GB whatever its montage count, and flex-search 3 GB plus 3.5 GB per restart. A NaN, infinite, negative, zero or fractional CPU, memory or thread claim, or CPU-limit setting, falls back to the default instead of stalling or over-admitting the queue.
- **Fixed: two jobs from one Run press can no longer write the same folder** — two Simulator rows with one montage name for one subject, two identical Analyzer analyses, or two Ex/mEx or flex searches under one run name silently replaced each other's results. Run is blocked with a sentence naming the jobs and the folder, and the server refuses such a job group, or an approved agent proposal, with HTTP 422.
- **Fixed: a plan the server refuses blocks Run, with the server's own sentence** — on the Pre-processing, Simulator, Analyzer and Optimizer pages; a page stayed on "Resolving the plan…" with Run enabled, or submitted every row anyway. The Optimizer validates every search before it queues any, not one per kind, and a validation request that fails blocks Run instead of letting the search through unchecked.
- **Fixed: submit and rerun check a config like Validate does** — a misspelled config key is refused with HTTP 422 naming it instead of silently running the default, and rerun applies the same input checks as submit. Older pre-processing keys (`run_recon` and the like) are still accepted, and a pre-processing group now runs the FastSurfer stage `run_recon` asks for.
- **Fixed: cancelling or forcing a job while it starts sticks** — the job stays cancelled and the process just launched for it is stopped; it could come back as running and finish as succeeded.
- **Fixed: the job store survives bad records and keeps its bookkeeping straight** — one damaged job record no longer stops every later job from starting (it is skipped with a warning and left on disk); jobs removed by the 200-job/30-day retention no longer stay in the list with empty logs; deleting a finished job no longer makes queued jobs that wait on it end as skipped; a job submitted before the job manager starts is not marked as interrupted by a restart; and a plan whose dependency label is misspelled or defined later is refused instead of running the job without its dependency.
- **Fixed: the leadfield job holds its subject locks and always records its exit** — a leadfield that finished or crashed while the server was down is reconciled as succeeded or failed, not lost, and the plan view shows its lock conflicts. Leadfields of a subject whose id starts the net's name (subject `E` with EEG10-10) are found again, so the Optimizer no longer says there is none or recomputes it.
- **Fixed: a tools job cannot write outside the project through a short option** — such as `-o/tmp/x` or `-vo/tmp/x`.
- **Fixed: the System page's Terminate button stops only processes TI-Toolbox starts** — its jobs, SimNIBS, FastSurfer, dcm2niix and the QSIPrep, QSIRecon and FreeSurfer containers. An unrelated process, such as a shell running `echo first` or an editor open on `notes_fast.txt`, could be stopped before.
- **Fixed: the folder button beside a job's console opens the job's results folder** — on the Simulator, Optimizer, Analyzer and Pre-processing pages' Terminal and on the Jobs page's Raw log and detail header. While a job ran it opened `code/ti-toolbox/jobs/<id>/`, the job's own record, and a finished simulation or search opened the folder above its results. It now opens the simulation's `Simulations/<name>/`, the search's run folder or the analysis folder, from the moment the run has created it; the button says **Open output folder**, or **Open job folder** for a job with no single results folder (a simulation of several montages, a search whose run name the runner picks and has not yet reported, a folder not created yet). `GET /api/jobs/{id}` carries it as `output_dir`.
- **Fixed: the jobs rail labels every error type the server reports** — forced and spawn errors included; notifications and the rail no longer list job kinds or error types the server never produces.
- **Fixed: the storage page counts QSIPrep and QSIRecon scratch folders as rebuildable cache** instead of "Other", and a damaged storage cache file no longer breaks the page.

#### AI assistant

- **Fixed: the Assistant page answers from your version's documentation** — Claude Code or Codex started from **Assistant** read the TI-Toolbox wiki, developer docs and `tit` source from GitHub's `main` branch, which can describe features and settings your installed version does not have. It now reads them at your app's release tag (`v3.1.2` for this release). If you set `TI_TOOLBOX_REF` yourself, your choice is kept. The plugin installed from the marketplace in your own terminal is unchanged (set `TI_TOOLBOX_REF` there to pin it).
- **Fixed: agent jobs run what the app would** — pre-processing jobs started by the assistant use the QSIPrep, QSIRecon and FreeSurfer choices saved in Settings, an approved proposal step of a cohort kind (group statistics, NIfTI average, Nilearn, EEG source, group analysis) queues one job instead of one per subject, and the ti-scripting skill's pre-processing example calls `run_pipeline` with `run_fastsurfer` instead of keywords that raised `TypeError`.
- **Fixed: the Assistant terminal links paths in a project folder with spaces or brackets** — for example `OneDrive - UW` or `Dropbox (Personal)`.

#### Launching and installation

- **Fixed: a SIF built from the Apptainer recipe has the same software as the Docker image** — `container/blueprint/apptainer.def` was a v2-era recipe that built its own environment and installed Blender's `bpy` into SimNIBS's Python, which pulled NumPy below 2 and made every MNI warp fail, charm's `final_tissues_MNI` included. It now builds the SIF from the release image (`idossha/ti-toolbox:v3.1.2`), adds nothing to it, and its build test runs the image's own runtime check; `apptainer_run.sh`'s Slurm template runs `simnibs_python -m tit.sim <config.json>`. Apptainer is still not a validated way to run v3 (see [HPC deployment]({{ site.baseurl }}/installation/hpc-apptainer/)); the desktop app and the Docker image are unchanged.
- **Fixed: `loader.py` runs the launcher of its own release** — on every start a downloaded `loader.py` installed its launcher from GitHub's `main` branch, which can be ahead of the released desktop app and image. It now installs it from the release it belongs to (the `v3.1.2` tag for this release), and `loader.sh` without a `docker-compose.yml` beside it downloads that release's copy instead of `main`'s. `loader.py` still needs the network to start, and its `--stop`, `--status` and `--logs` still work offline; a `loader.py` inside a checkout still runs that checkout, and `TIT_SOURCE_REF` still selects another branch, tag or commit. See [Bash and Python launchers]({{ site.baseurl }}/installation/bash-cli/).
- **Fixed: starting TI-Toolbox no longer stops containers it did not start** — the desktop app, `loader.sh` and `loader.py` treated any running container made from the TI-Toolbox image (or named like one) as a TI-Toolbox session: a container you ran yourself with `docker run idossha/ti-toolbox:…`, a FreeSurfer job's helper container, or another launcher's GPU check. When it was the only one, it was picked without asking, and **Recreate** (the default, or `--existing recreate`) stopped and removed it, killing whatever ran there. All three launchers now offer, attach to and stop only containers labelled as a TI-Toolbox session with service `tit` (`loader.sh` also finds sessions that carry only a project or host-directory label); others are never listed or stopped. And `--existing recreate` without `--container` now replaces the running session only if it belongs to the project you asked for: if another project's session is the one running, the launch stops, names that project and changes nothing (name it with `--container` to replace it). Choosing **Attach** or **Recreate** in the desktop dialog or the terminal prompt works as before, and closing the app still stops only its own container.
- **Fixed: the three launchers give a project path the same project name** — `loader.sh`, `tit launch` and the desktop app named non-ASCII and emoji paths differently (the `tit.project` label and the container name), so `--status`, `--stop` and attach can now find a session another launcher started. A container started by an older `loader.sh` for a non-ASCII path, or by an older `tit launch` for an emoji path, is still offered for attach or recreate, but lookups by project do not find it.
- **Changed: every launcher uses one settings folder** — on macOS, `tit launch` and `loader.sh` mount `~/.config/ti-toolbox`, as the desktop app does, instead of following `XDG_CONFIG_HOME`; on Windows, `tit launch` uses `%APPDATA%\ti-toolbox`. A telemetry opt-out made through one launcher applies to every launcher.
- **Fixed: launchers refuse bad ports, timeouts and paths before any Docker call** — `python loader.py` and `tit launch` refuse, with one line and exit 1, a port outside 1–65535, a timeout that is not above zero, the filesystem root, and a project path containing `:` or a newline, so `--existing recreate --project /` no longer stops the selected container before crashing. The desktop app refuses an invalid `TIT_LAUNCH_PORT`, `TIT_DEV_PORT`, `TIT_LAUNCH_TIMEOUT` or `TIT_STACK_HEALTH_TIMEOUT_MS` with a message naming the variable (it published port 0 or timed out at once), and compose ports outside 1–65535. `loader.sh --port 08765` uses port 8765, and both loaders hand the desktop app the startup timeout in whole seconds, rounded up (`loader.sh` on Linux no longer fails for a `--timeout` of 2147483648 seconds or more).
- **Fixed: `loader.sh` hands the desktop app a full image reference** — a bare `TIT_IMAGE_TAG` or `--image` tag was passed as the image (`v3.0.0`), and `TIT_IMAGE_TAG` is no longer forwarded; a local `--image tit:dev` runs as given on every launch path.
- **Fixed: a GPU probe container that Docker cannot remove no longer aborts starting the stack** — for example "removal already in progress"; the desktop app and `tit launch` log a warning and keep the probe's GPU verdict.
- **Fixed: example-data archives are unpacked safely** — archives that contain FIFOs or device nodes are refused, and a refused archive leaves the project exactly as it was, including a head model a forced re-fetch was meant to replace. A forced re-fetch of the Ernie head model keeps an existing `m2m_Ernie` folder name on macOS instead of renaming it to `m2m_ernie`.

#### Scripting

- **Fixed: `run_ex_search` and `run_m_ex_search` leave Ctrl-C working** — calling them from a notebook no longer disables Ctrl-C and Kernel Interrupt for the rest of the session.
- **Fixed: the example scripts and wiki code run** — the pre-processing, pipeline and flex example scripts call the `run_pipeline` keywords and the `FlexConfig` import that exist (they raised `TypeError` and `ImportError`), and Python examples in the wiki, README, agent skills and example scripts are now checked against the real `tit` API.
- **Changed: `load_montages` raises for a name saved under both uni- and multi-polar** instead of silently returning the multi-polar one, and `upsert_montage` moves a name between polarities instead of keeping both. `load_montages` still accepts `include_flex` but ignores it, and no longer reads the `FLEX_MONTAGES_FILE` environment variable.
- **Changed: an analyzer config that falls back to the old layout logs which field did not match** the current schema, as a warning in the job log.
- **Removed: helpers nothing in TI-Toolbox called** — `tit.pre.qsi.check_dti_tensor_exists`, the QSIRecon `list_available_*` helpers, `tit.analyzer.spheres`, the flex-montage loader in `tit.sim.utils`, the PyQt-era update check `tit.tools.check_for_update`, and the single-subject Nilearn helpers `create_pdf_entry_point`, `create_glass_brain_entry_point`, `create_html_entry_point` and `html_report` with their per-module command lines and package `__version__` (`NilearnVisualizer` no longer takes a subject id or creates `nilearn_visuals/` on construction).
- **Removed: 19 constants nothing read from `tit.constants`** — `DIR_SIMNIBS`, `DIR_FLEX_SEARCH`, `DIR_ANALYSIS`, `FILE_EGI_TEMPLATE`, `EXT_NIFTI`, `EXT_MESH`, `PREFIX_SESSION`, `DEFAULT_RADIUS_MM`, `SIM_TYPE_TI`, `SIM_TYPE_MTI`, `ATLAS_DK40`, `ATLAS_A2009S`, `ATLAS_ASEG`, `ATLAS_APARC_ASEG`, `PLOT_DPI`, `PLOT_FIGSIZE_DEFAULT`, `TIMESTAMP_FORMAT_DEFAULT`, `TIMESTAMP_FORMAT_READABLE` and `QSI_DEFAULT_CPUS` (use `QSI_DEFAULT_OMP_THREADS`).

#### Documentation

- **Fixed: the documentation site's search finds pages again** — it answered "No results" for every query, because the published site had no search index.
- **Fixed: new projects link to the documentation site at its real address** — their README and `dataset_description.json` pointed to a URL that returned "page not found"; they now use https://idossha.github.io/TI-Toolbox/.
- **Fixed: the site publishes only public pages** — internal developer planning notes are no longer published.
- **Fixed: reference pages describe what exists** — the example simulation report on the Reports wiki page is rebuilt by this release; the API reference's constants page lists only constants that exist, with their real values and a code sample that runs; and the API descriptions for notebooks, free-hand configs, percentile windows and the Viewer scene name routes and writers that exist (`POST /api/view/open` writes a `.tetravox.json` scene file for the host TetraVox app; it does not launch a viewer).

#### For contributors

- **Changed: the contributor docs match the repository** — AGENTS.md, CONTRIBUTING.md and desktop/README.md use npm rather than pnpm, say `--dev` opens the Electron window and describe today's desktop main process; the CI workflows README has no internal build mode and says Bandit results go to the job summary; the pull-request template lists the real test gates.
- **Changed: the guards can fail** — coverage no longer silently excludes whole functions whose text contains "pass" (exclude patterns are anchored, dead omit and ignore patterns are gone, Codecov declares only the flag CI uploads); the contract guard compares request bodies in both directions, ratchets its warnings against a committed baseline and, in CI, fails instead of skipping the generated desktop API types, which desktop-checks diffs after `npm ci`; real JSON responses of the server, job and proposal records included, are validated against `contracts/openapi.yaml`; and `dev/check_cited_paths.sh` checks that every repository path AGENTS.md, docs/dev/TESTING.md, the wiki and the shipped skills cite resolves.
- **Added: the mock-server Electron e2e suite has a CI job** — offscreen in CircleCI, run on demand with the `run_e2e_mock` pipeline parameter until it fits the Linux executor; its JUnit report must show zero failures and only allowlisted skips, and every CI job keeps its test reports and artifacts on failing runs.
- **Fixed: the desktop mock server matches the real server** — its catalog of reports (ids, kinds, paths and CSP), simulations, analyses, group runs, ROIs and run files, and its analyzer plans (`Analyses/<Mesh|Voxel>/<folder>`, with the overwrite confirmation). `dev/make_contract_fixtures.py` and `dev/regen_mock_reports.py` regenerate the desktop's contract fixtures and the mock's report pages from the real server code, and their `--check` mode runs in the host suite.
### v3.1.1 — October 20, 2026

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v3.1.1/">Release notes →</a>

A patch release for everyone on v3.1.0; update the desktop app and the image together (the image
carries the server the app talks to, including the new `/api/caps` endpoints). The headline: a new
optional **EEG caps** panel applies an EEG cap to a head model you already have, without rebuilding
it, and shows how each net sits on the scalp. It comes with corrected GSN-HydroCel-128, BioSemi-64,
BioSemi-128 and BioSemi-256 caps, which were in the wrong coordinate frame and put central
electrodes in a hole on the scalp: **re-apply** those four caps in the panel to subjects that use
them (see [the v3.1.1 release notes]({{ site.baseurl }}/releases/v3.1.1/)). The simulation report is
written again. Other projects, nets and results open unchanged.

#### EEG caps

- **New: apply EEG caps to an existing head model, and check how a net sits on the scalp** — the new optional **EEG caps** panel (**Settings ▸ Extensions ▸ EEG caps**) warps the image's MNI caps, or an MNI cap CSV you add to the project (kept in `code/ti-toolbox/eeg_caps/`), onto a subject exactly as charm does at the end of a head-model build, in a few seconds and without rebuilding the head model. The table lists each cap as **on subject** or **not on subject**, with the date it was applied; a cap already on the subject is replaced only after you confirm. Picking a net draws it on the subject's scalp with a sortable table of electrode spacing and scalp distance, a warning for electrodes closer than 2 mm or duplicate labels, and an optional second net to compare (nearest electrode and distance). The panel opens on the first subject with a head model and its first net already inspected and drawn, and reuses the 3-D view's cached scalp so it loads in well under a second once a subject's head has been shown. The table labels each cap's source (**TI-Toolbox**, **SimNIBS**, **uploaded**), and an **(i)** on each card explains the panel. Existing head models and nets are untouched until you apply a cap. See [EEG Caps]({{ site.baseurl }}/wiki/eeg-caps/).
- **Fixed: the GSN-HydroCel-128, BioSemi-64, BioSemi-128 and BioSemi-256 EEG nets sit on the head again** — these four caps were in Brainstorm's head frame, not MNI space (axes swapped, about 5 cm too high), so charm put their central electrodes on one point of the scalp (43 GSN-HydroCel-128 electrodes collapsed into a hole). They are now converted to MNI space with Brainstorm's own ICBM152 head-to-MNI transform, and their LPA/RPA rows are named correctly. Head models built before the fix keep the wrong positions in `m2m_<id>/eeg_positions/` until the cap is re-applied in the **EEG caps** panel (or the head model is rebuilt) with the v3.1.1 image. Other nets are unchanged.

#### Reports

- **Fixed: the simulation report is written again** — it failed for every subject with `matmul: Input operand 1 has a mismatch in its core dimension 0`, because it read the MNI-space envelope NIfTI instead of the subject-space one. Simulation outputs are unchanged; rebuild a missing report by re-running the simulation.

### v3.1.0 — October 9, 2026

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v3.1.0/">Release notes →</a>

A feature release for everyone on v3.0.x; update the desktop app and the image together (the image
carries the server the app talks to, including the new plan and job-server endpoints). The
headline: your own Claude Code or Codex can now drive TI-Toolbox, from an **Assistant** page inside
the app or from your own terminal, and nothing it asks for runs until you approve its plan on
**Jobs**. The app also tells you when a new release is out, the Simulator gains carrier-only
(ΔF = 0) control simulations, fsaverage projections and surface statistics become viewable `.msh`
files, and FreeSurfer runs on Windows again. **Re-run** only fsaverage work: older `_fields.npz`
fsaverage projections and `surface_maps.npz` surface statistics are no longer read, so re-run the
fsaverage projection of those simulations and any surface cluster-permutation analysis (see
[the v3.1.0 release notes]({{ site.baseurl }}/releases/v3.1.0/)). Other projects, saved scenes and
results open unchanged.

#### AI assistant

- **New: let your own AI agent run TI-Toolbox for you** — with the desktop app open on your project, Claude Code (on your Claude Pro/Max login) or Codex (on your ChatGPT login) turns a plain request such as *"organise the scans in ~/Downloads/scan as sub-101, preprocess them, optimise for the bilateral thalamus, then simulate the best montage"* into TI-Toolbox jobs. It copies raw scans with its own file tools (your CLI asks before each copy; nothing is moved or overwritten) into `sourcedata/sub-<id>/<T1w|T2w|ct|dwi>/`, asking you when a series' modality is unclear; it finds a target region by name in the subject's own atlases and then in the MNI atlases the Optimizer offers (*thalamus* finds *Left-Thalamus*, not *Hypothalamus*) and builds the target the way the Optimizer's region picker does; and when a request leaves the subject, the target, what to run or the goal open, it asks you one question instead of guessing. Every job it runs appears live in **Jobs** with an **agent** badge, writes the same outputs and reports as a job you start yourself, and is recorded as `created_by: "agent"`; a setting the agent leaves out takes the value the run page starts with (for an ex-search, the Optimizer's 0.2 mA current step and 1.6 mA channel limit). TI-Toolbox never handles your AI credentials. This comes with agent plugin 0.6.0, which adds the `ti-toolbox-jobs` job server and the `ti-run-pipelines` skill beside the read-only knowledge server: Claude Code users run `/plugin update ti-toolbox@ti-toolbox`, or use the Assistant page with nothing to install; Codex users register the second server as shown in [Let your assistant run pipelines](https://idossha.github.io/TI-Toolbox/wiki/ai-assistant/#let-your-assistant-run-pipelines). Jobs you start in the app are unchanged, and scripts that submit to `/api/jobs` without `created_by` are still recorded as `gui`.
- **New: you approve your agent's plans before anything runs** — the agent proposes the work as a plan instead of starting it. The plan appears as a card at the top of **Jobs**; the side bar's Jobs item counts the plans waiting, the **Overview** lists each one (*"Claude Code proposes …"*) with **Review**, and a notice pops up when one arrives (a system notification when the app is in the background). The card shows each step's subjects and key settings in plain terms (goal, target region by name, current, electrodes, run name, currents), the folders it writes, an estimated time, which steps wait for which, and, in red, any existing result it would replace. **Approve and run** queues it, and the app runs the later steps itself as the earlier ones succeed (a simulation of a flex-search result picks up that run's electrodes and currents), so the agent need not stay connected. Before approving you can **Edit** a step on the card (subjects, run name, current, any config field, allow replacing), choose **Open in form** to edit it on the Pre-processing, Simulator or Optimizer page with every control there and **Save to plan**, or **Reject…** it with a note the agent reads. After approval the card follows each step live and links its jobs; a failed plan stays a full card with **Retry step** until you dismiss it, and done or rejected plans fold into a **Finished plans (N)** list. Finished plans are kept as long as finished jobs (30 days, or the newest 200). While a plan waits the agent ends its turn instead of blocking the chat, and is woken when you approve or reject it and as each step finishes, reporting output folders, key numbers and report paths (Codex, which cannot wait in the background, checks for about 45 s and then asks you to say "status"). To let the agent submit jobs directly, turn on **Settings ▸ Project ▸ AI assistant ▸ Agent may submit without approval** (off by default). See [Approving a plan](https://idossha.github.io/TI-Toolbox/wiki/ai-assistant/#approving-a-plan).
- **New: an Assistant page that runs your own Claude Code or Codex inside the app** — open **Assistant** in the rail (above System), pick **Claude Code** or **Codex** and **Start**: a real terminal runs your own `claude` or `codex` in the project folder, already connected to the open TI-Toolbox, with this app version's TI-Toolbox skills and job tools attached for that session only. There is nothing to install or configure in TI-Toolbox; nothing is written to `~/.claude` or `~/.codex`, and an already installed plugin is not registered twice. If the assistant is not installed or not signed in, the page says what to do (`/login` inside the pane for Claude Code). **Effort** (Low by default; Medium, High or My CLI default) and, for Claude Code, **Model** (Sonnet by default; Opus, Haiku, Fable or My CLI default) are remembered per assistant and apply on the next Start or Restart. Example prompts such as **Bilateral thalamus pipeline** are typed into the assistant for you to edit and send; a file path inside the project that the assistant prints is a link that reveals the file in Finder/Explorer or opens the folder; and **Open in system terminal** starts the same session in Terminal (macOS), a console window (Windows) or, on Linux, `$TERMINAL` or the first of the common terminals it finds. The page works with Docker and native sessions alike and needs the desktop app and a project on this computer; closing or switching the project ends its sessions. See [The Assistant page](https://idossha.github.io/TI-Toolbox/wiki/ai-assistant/#the-assistant-page-in-the-desktop-app).

#### Desktop app

- **New: TI-Toolbox tells you when a new version is out** — the desktop app checks GitHub once when it starts; when a newer release exists it says *"TI-Toolbox X.Y.Z is available (you have A.B.C)"* with **Download**, which opens the release page so you can download the new installer, and **Later**, which hides it until the next launch. The version you have is always shown at the bottom of the side bar, with a dot when an update is available; click it for **Settings ▸ Updates**, which shows your version, the newest release, the status (*Up to date*, *Update available* or *Couldn't check*, for example when offline) and **Check again**. **Help ▸ About** shows the same. Nothing is downloaded or installed for you, and the check sends no project data. In a browser session the side bar shows the version and nothing is checked.
- **Fixed: an open atlas list no longer closes when a job finishes** — while you were choosing an atlas in a target editor (Optimizer, Analyzer), a job finishing in the background reloaded the atlas list and closed the dropdown under your pointer. The list now stays open and updates in place; the first load still shows a placeholder.
- **Fixed: the narrow icon rail no longer scrolls sideways** — its rows were half a pixel wider than the rail, so it could be scrolled sideways by a pixel and showed a horizontal scrollbar where the system always shows scrollbars. Row positions are unchanged.

#### Simulator

- **New: carrier-only control simulations (ΔF = 0)** — a Simulator job can now run as a carrier-only control: both pairs at the same frequency and in phase, so there is no beat. Tick **Job settings ▸ Output fields ▸ Carrier-only control (ΔF = 0, coherent carriers)**, or pass `SimulationConfig(carrier_only=True, output_fields=["hf_peak", "hf_sar"])`. The carriers then add as one fixed field: `hf_peak` is `|E1+E2|` and `hf_sar` is `|E1+E2|²` (Cassarà 2025 Part II: coherent superposition at identical frequencies), where the TI worst case `max(|E1+E2|, |E1-E2|)` would overstate the peak wherever the two fields are more than 90° apart. No envelope field (`TI_max`, `TI_avg`, `TI_normal`) is computed, and the option is for 2-pair TI only (disabled for mTI jobs). The run records `carrier_only` in its `documentation/config.json`, and fsaverage projection honours it. `tit.fields.hf_peak`/`hf_sar` gain `coherent=`. Existing simulations and scripts are unchanged. See [Carrier-only control](https://idossha.github.io/TI-Toolbox/wiki/simulator/#carrier-only-control).
- **Changed: Map to net reuses a flex-search run's saved mapping** — mapping a run to an EEG net it was already mapped to reads its saved `electrode_mapping_<net>.json` instead of recomputing it, and every place that turns a flex-search run into a montage (the Simulator's **Flex result** row and **Map to net**, plans, scripts) pairs its electrodes by the stimulation channel the optimiser recorded. Montages from TI-Toolbox's flex-search are unchanged.
- **Fixed: a Simulator row for a flex-search result starts with that run's own currents** — picking **Flex result** (or switching its placement or EEG net) filled 1 mA per channel whatever the run used. The row now starts with the run's optimised current split, else the run's `current_mA` per channel, else 1 mA, and you can still edit the currents.

#### fsaverage and statistics

- **Changed: fsaverage projections are now viewable `.msh` surfaces** — **Map fields to fsaverage** (Simulator job settings) and the Source panel's fsaverage mapping now write `Simulations/<sim>/fsaverage/sub-<id>_sim-<sim>_space-fsaverage<N>_fields.msh`: the fsaverage central surfaces (left hemisphere, then right) with `TI_max`, `TI_normal`, `hf_peak` and `hf_sar` as node fields, the same layout SimNIBS uses for its own fsaverage overlays. Open it in the Viewer (an MNI-space scene lists it under the simulation's meshes; the Jobs rail offers **Open in Tetravox**) or in Gmsh, with its `.msh.opt` view beside it; a same-name `.json` records the subject, simulation, fields and carrier-only flag. Cluster permutation in fsaverage space reads the `.msh`, with the same numbers. **Older `_fields.npz` fsaverage projections are no longer read:** a surface cluster-permutation run over those simulations stops before it starts and names the missing `.msh` — re-run their fsaverage projection (the Simulator's **Map fields to fsaverage**, or `simnibs_python -m tit.source` in `fsavg_map` mode). The old `.npz` files are left on disk untouched. A projection file is about 4× larger than before (2.5 MB at fsaverage5, 41 MB at fsaverage7).
- **Changed: surface cluster-permutation results are a viewable `.msh` plus CSV tables** — a cluster-permutation run with **Analysis space ▸ fsaverage** now writes `surface_stats.msh` (the fsaverage surface with `t`, `p`, `sig_mask`, `cluster_id`, `r` for correlation, and the mean field per group or across subjects), opened in the Viewer (**Open in Tetravox** on the job) or Gmsh, with `surface_stats.json` recording the analysis settings and subjects. Beside `significant_clusters.csv` it writes `null_distribution.csv` (the max cluster statistic of each permutation) and `cluster_subject_values.csv` (each subject's mean field in each significant cluster, with its group or response) for follow-up statistics in R or a spreadsheet. `cluster_id` matches the ids in `significant_clusters.csv`. Statistics are unchanged. **`surface_maps.npz` is no longer written or read:** re-run a surface analysis to get the new outputs; old files are left on disk. Scripts: `tit.plotting.nilearn.render_surface_stats_result` now takes the path of `surface_stats.msh`.

#### Windows

- **Fixed: FreeSurfer stopped at once on Windows** — with a Windows project folder, FreeSurfer failed immediately with "LOCAL_PROJECT_DIR must be an absolute host path." FreeSurfer, QSIPrep and QSIRecon now give their containers your project folder as Windows writes it (`C:\Users\…`), bound with `--mount`. macOS and Linux are unchanged.
- **Fixed: saved Viewer scenes on Windows** — a saved scene's file paths are written with backslashes only (they mixed `\` and `/`), and a scene whose paths differ from the project folder only in drive-letter case or slash direction (`c:\users\…`, `C:/Users/…`) is recognised as inside the project instead of being left unchecked. A folder whose name only starts with the project's name is no longer taken for the project.
- **Fixed: the agent plugin's tools start on Windows** — the plugin ran its servers with `python3`, which Windows usually lacks, so Claude Code and Codex on Windows saw no TI-Toolbox tools. The **Assistant** page finds your Python (`py`, `python` or `python3`) and uses it; for the plugin installed from the marketplace, set `TIT_PYTHON` once (`setx TIT_PYTHON py`). macOS and Linux are unchanged.

#### Other fixes

- **Fixed: Glasser, Schaefer and MASSP regions in MNI space had FreeSurfer's names** — the Optimizer's and Analyzer's region list for these three shipped MNI atlases named each label from FreeSurfer's colour table (Glasser's first region read "Left-Cerebral-Exterior" instead of "L-V1", and a Schaefer cortical parcel was named after the thalamus). They now use each atlas's own table. The label numbers, and so a saved target's region, are unchanged; only the names you pick from change. Other atlases are unchanged.
- **Fixed: the flex-search and ex-search reports failed for a target picked on a cortical atlas** — a search whose region came from a surface annotation (for example `lh.CHN_DK40.annot`) finished, but writing its report stopped with `Cannot work out file type of ".../lh.CHN_DK40.annot"`, because the report read the annotation as a volume. The report now names the region from the annotation (`lh.insula`, atlas `CHN_DK40 (lh)`) and gives the target's size in cortical surface vertices; volume, subcortical and sphere targets are unchanged. Rebuild an affected report with `simnibs_python -m tit.reporting.generators.flex_search <project> <subject> <run>`.
- **Fixed: a job can no longer write its results outside the project** — a run name or output folder that points elsewhere on disk (an absolute path outside the project, or a name with `../`) is now refused when the job is planned or submitted, with "Outputs must stay inside the project folder …", including when replacing outputs is allowed. Run names and folders inside the project work as before.

#### Updated 2026-10-12

These fixes were delivered in an updated `v3.1.0` image on October 12, 2026; there is no new release. Existing v3.1.0 installs only need a restart of the software (quit TI-Toolbox and open it again; it pulls the refreshed `idossha/ti-toolbox:v3.1.0` image on start), not a new release download.

**Fixed**

- **A reverse phase-encoding DWI scan is converted for QSIPrep's distortion correction** — DICOM conversion now also reads `sourcedata/sub-<id>/fmap/` (a `dicom/` subfolder works, as for the other modalities) and writes the short reverse-PE scan there as the BIDS fieldmap QSIPrep documents, `fmap/sub-<id>_dir-PA_epi.nii.gz` with its JSON sidecar (and `.bval`/`.bvec` when the scan has them), carrying an `IntendedFor` that names the DWI; QSIPrep then corrects the DWI with TOPUP. Before, that folder was ignored and no `fmap/` was created. The `dir-` label (`AP`, `PA`, `LR`, `RL`, `SI`, `IS`) is read from the scan's phase-encoding direction and orientation, never assumed; a scan missing either is left unnamed and the log says what to add. Two full diffusion series with opposite phase encoding in `dwi/dicom/` become `dwi/sub-<id>_dir-AP_dwi` and `dwi/sub-<id>_dir-PA_dwi`, which QSIPrep pairs for TOPUP; before, the second was written as `sub-<id>_dwia`, which is not a BIDS name and was never used. A fieldmap series holding both polarities (GE `epi_pepolar`) gets both `dir-AP` and `dir-PA` files. A single DWI keeps its name `sub-<id>_dwi`. New subjects get an empty `sourcedata/sub-<id>/fmap/dicom/` beside the other drop folders. Subjects you already converted, and fieldmaps you placed in `sub-<id>/fmap/` by hand, are used as before. **Pre-processing ▸ Convert DICOM to NIfTI**.
- **Threshold-based focality runs again in Adaptive and Multi-threshold mode** — since v3.0.0 a flex-search started from **Optimizer ▸ Goal: Threshold-based focality** with **Adaptive thresholds** (the default) or **Multi-threshold** skipped the mean-intensity calibration and ran a single focality search with no thresholds, so it failed at once with SimNIBS's `ValueError: Please define TESoptimize.threshold for focallity optimization!`. Both modes now run as documented: a mean run first, then one focality run (Adaptive) or one per ROI/non-ROI percentage pair (Multi-threshold, 3 runs with the defaults) with thresholds taken as those percentages of the mean run's ROI intensity. **Fixed thresholds** and every other goal are unchanged, and no completed result moves: the affected runs never produced output. Update the image; the desktop app is unchanged.
- **Flex-search accepts a net picked for the skin visualization** — with **Optimizer ▸ Solver ▸ Skin visualization ▸ Plot EEG net electrodes** (flex-search) ticked, every net chosen under **Visualization EEG net** was refused with *"Could not queue the search. Missing inputs: Skin visualization EEG net"*, on every operating system. The net is now looked up in the subject's `eeg_positions` folder, the same place the mapped EEG net is, and its electrodes are drawn on the valid-skin-region figure. Flex-search runs without the box ticked are unchanged.

### v3.0.2 — September 28, 2026

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v3.0.2/">Release notes →</a>

A patch release for everyone on v3.0.x; update the desktop app and the image together (the
image adds DIPY for the new DTI fit). The highlights: DTI conductivity tensors are now placed and
oriented correctly, so anisotropic (`vn`, `dir`, `mc`) simulations from v2.3.0 through v3.0.1 need
**Extract DTI tensor** and then those simulations re-run (see the
[v3.0.2 release notes]({{ site.baseurl }}/releases/v3.0.2/)); QSIRecon is no longer needed for the
tensor; simulations, flex-search, ex-search and DTI QC get lean, cited reports; and charm no longer
freezes on many-core machines. Script users: the report-building classes and the combined
preprocessing report are removed. Other projects, saved scenes and results open unchanged.

#### DTI

- **Fixed: anisotropic (DTI) conductivity tensors were misplaced and misoriented** — the tensor TI-Toolbox wrote into `m2m_<id>/DTI_coregT1_tensor.nii.gz` was aligned to the head model by a shift only, although QSIPrep's space is also rotated (about 21° on the test subject); the tensors were not rotated with it, and resampling spread values outside the brain. On the test subject tensors sat 18 mm off on average with a 38° median error in fibre direction. The DTI step now fits the tensor itself with DIPY from QSIPrep output and maps it with QSIPrep's exact transforms, rotating every tensor; it writes `DTI_coregT1_qc.json` and refuses to write a tensor that fails its QC gate. **Affected:** `vn`, `dir` and `mc` simulations from v2.3.0 through v3.0.1; isotropic (`scalar`) results are unchanged. **Re-run** the DTI step (**Pre-processing ▸ Extract DTI tensor**, with *Replace and rerun*) and then those simulations; QSIPrep output can be reused.
- **The DTI tensor no longer needs QSIRecon** — **Extract DTI tensor** now runs straight after QSIPrep (and charm). QSIRecon is an optional advanced step for tractography, scalar maps and connectivity; its preselected `dsi_studio_gqi` spec now produces scalar maps only, without the 5-million-streamline tractography. Choosing connectivity atlases needs QSIPrep run with the new **MNI normalization** option. The Docker image gains `dipy` for the fit.
- **QSIPrep chooses its settings from your data** — distortion correction is always on: TOPUP with a reverse phase-encoding fieldmap (TI-Toolbox adds `IntendedFor`, and a derived `TotalReadoutTime`, to that fieldmap's sidecar when missing), otherwise fieldmap-less SyN; a DWI fieldmap that exists but cannot be used stops the run with the reason. Unringing is `rpg` for partial-Fourier data, otherwise `mrdegibbs`; output resolution is the DWI's native voxel size; MNI normalization is skipped unless needed. Every option stays in **Configure QSIPrep**; a value you saved there before is kept.
- **QSIPrep refuses to start on Apple Silicon** — it always failed there at SynthSeg, an hour in, because emulation lacks the AVX instructions it needs. It now stops at once and explains how to run QSIPrep on an x86-64 Linux or Windows machine and bring the output back; the DTI step runs anywhere.
- **A clearer DTI quality-control report** — the report the DTI step writes (**Results ▸ sub-… ▸ DTI QC report**) now opens with the date the tensor was written and a verdict in terms of what the page shows ("Quality gate passed · 2 advisories need attention", or the failed check by name), the one published-range gate (white-matter diffusivity, with its citations), and a plain callout for anything to act on, such as QSIPrep having run without distortion correction and which fieldmap sidecars lack `IntendedFor`. Below come a short preprocessing list, a T1w-versus-FA flicker in three planes, a direction-colour slice scrubber and FA/MD by tissue; software self-checks, the flip test, motion, methods with references and provenance are under **Technical details**. Every check shows its role (gate, software check, advisory, reported) and its reason. The report follows the app's light or dark theme, works offline and weighs about 1.2 MB. To rebuild an existing subject's report without refitting: `simnibs_python -m tit.reporting.generators.dti_qc <project> <subject>`. The tensor itself is unchanged.
- **Fixed: a DTI step that failed its quality gate left no report** — the report is now written first (verdict: failed, tensor not written) and then the step stops with the error, as before.

#### Reports

- **Every simulation writes a report** — after each montage the Simulator writes **Results ▸ sub-… ▸ Simulation report**, also linked on the job in **Jobs**. It opens with the grey-matter envelope (its 99.9th percentile and median) and where its maximum is (MNI coordinate), and the montage on the same EEG-cap drawing the app uses, with the current per channel and in total. Then the conductivity model (and whether the DTI tensor was read) and the envelope in three planes through the hot spot. The report has no checks or advisories. Per-carrier fields, methods with references and the run's configuration are under **Technical details**. About 0.3 MB. To rebuild one: `simnibs_python -m tit.reporting.generators.simulation <project> <subject> <simulation>`. Simulation outputs are unchanged. The 10-10 cap drawing now also places PO9 and PO10, so montages using them get a montage image.
- **A readable flex-search report** — **Results ▸ sub-… ▸ Flex-search report** now names the target (for example "Thalamus left + Thalamus right", with its atlas, size and centre) instead of "Target ROI", and says what the score means in words: "target mean 1.82× the background mean" rather than a bare "score −1.82". It shows the key numbers from the accepted candidate, the run's own target and valid-scalp figures, the optimised electrode positions (free scalp positions, so no cap drawing), the dose record with the searched current split, and one row per optimiser run. The final per-channel fields, methods with references and `flex_meta.json` are under **Technical details**. The report is written after the run's manifest, so it is complete, and it weighs about 0.3 MB instead of 7.4 MB (the target and valid-skin figures are embedded at report size). Rebuild one with `simnibs_python -m tit.reporting.generators.flex_search <project> <subject> <run folder>`. Optimisation results are unchanged.
- **Ex-search writes a report** — when an exhaustive search finishes, **Results ▸ sub-… ▸ Ex-search report** (and the job in **Jobs**) shows the winning montage, ranked by composite (ROI mean × focality), with its electrodes and current per channel and its dose record (electrode size from the leadfield, currents per channel and in total, the current sweep); one chart of every montage's ROI mean against focality with the top 25 marked; the top 25 as a table you can sort by any column; and the ROI and ranking in plain words. Methods with references and `run_config.json` are under **Technical details**. About 0.3 MB for a 47,916-montage search; the search's own PNG plots are unchanged. Rebuild one with `simnibs_python -m tit.reporting.generators.ex_search <project> <subject> <run name>`.
- **The head-model report is SimNIBS's own charm report** — when charm finishes, its `charm_report.html` (segmentation and registration viewer, references) is copied into the subject's reports and shown as **Results ▸ sub-… ▸ Head model (charm) report**, and on the charm job in **Jobs**. The original stays in `m2m_<id>`, where SimNIBS and your own tools expect it. Head models built before this update keep their report in m2m only; nothing is migrated.
- **Fixed: report titles and fonts in the app** — DTI QC reports are listed as "DTI QC report" instead of "Dti qc", and reports may use their embedded fonts.
- **Removed: the combined preprocessing report** — preprocessing no longer writes `pre_processing_report_*.html` (its DICOM, atlas, tissue, QSIPrep, QSIRecon and FreeSurfer sections included). Its two reports are the charm report and the DTI QC report. Pipelines run as before; old preprocessing reports already on disk stay listed in **Results**. Scripts: `PreprocessingReportGenerator`, `create_preprocessing_report` and `simnibs_python -m tit.pre.report` are gone, and the server no longer accepts a `report` job kind (old `report` jobs still show in **Jobs**).
- **Removed: the report-building classes** — scripts can no longer assemble reports by hand: `SimulationReportGenerator`, `FlexSearchReportGenerator`, `create_flex_search_report(data=…)`, `ReportAssembler` and the reportlets are gone from `tit.reporting`. The pipelines write their reports themselves; to rebuild one from existing outputs use `tit.reporting.generators.simulation.create_simulation_report(project, subject, simulation)` (and `flex_search`, `ex_search`), or the `simnibs_python -m tit.reporting.generators.<name>` commands. Reports already on disk still open in **Results**.
- **Removed: print layouts for reports** — reports no longer carry an A4 print layout (PDF export is not offered); printing from the browser prints the page as it appears on screen.
- **Removed: `tit.plotting.generate_static_overlay_images`** — its only user was the old DTI report. Report slice figures now come from `tit.plotting.slices`, which draws every panel in one convention (subject left on image left).

#### Head model

- **Fixed: head-model creation (charm) could freeze indefinitely on many-core machines** — on a machine with a large number of CPU cores, running `charm` to build a head model could hang forever partway through, with the log showing an OpenBLAS thread-metadata warning. Charm's own threading is unaffected; the underlying numerical library now stays single-threaded internally as intended.

### v3.0.1 — September 23, 2026

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v3.0.1/">Release notes →</a>

A patch release for everyone on v3.0.0; update the desktop app and the image together. The
highlights: job-completion notifications, Apple Silicon Macs downloading the image again, an
**Explode** view and one-hemisphere regions for MNI atlases, and run pages that keep the Jobs
table readable at any window size. Projects, saved scenes and results from v3.0.0 open unchanged.

#### Notifications

- **A system notification when a job finishes** — the desktop app now says what finished and for whom, e.g. **Simulation finished** · _sub-101 · montage L_Insula_ or **Flex optimization failed** · _sub-102_, instead of the old "Job finished" with a job id. **Settings → Project → Notifications** turns them off, limits them to failures, switches to a minimal title-only form, or picks the sound: one of three short TI-Toolbox sounds (Pulse by default, Chime, Tick; a failure plays it lower), the system sound, or none, with **Preview** beside it. A saved sound-on setting becomes Pulse and sound-off becomes None. Clicking one brings the app to the front. Cancelled jobs and jobs that had finished before the app opened never notify; each subject of a multi-subject run notifies as it finishes. **Send test notification** in the same card shows a sample banner with the chosen sound and says whether it appeared, or why not with the fix. Browser sessions are unchanged (no notifications). Developers: a checkout's Electron is re-signed on `npm install` so macOS lets it notify (existing checkouts: `npm --prefix desktop run sign:dev-electron`).

#### Launch

- **Fixed: the app downloads its container on Apple Silicon Macs** — on an M-series Mac with no cached image, starting TI-Toolbox could stop with "no matching manifest for linux/arm64/v8" instead of downloading the TI-Toolbox image. The image is built for Intel/AMD (linux/amd64) and runs under emulation on Apple Silicon; the desktop app now always asks Docker for that platform when it downloads and creates the container, as `loader.sh` and `tit launch` already did, and the shared `docker-compose.yml` names it too. Intel Macs, Windows and Linux are unchanged, and an image you already have is reused as before. Images are now also published as a plain linux/amd64 image, so older app builds download it again as well.

#### Atlases

- **Explode an MNI atlas to reach deep regions** — in MNI space the Optimizer's and Analyzer's 3D pane has an **Explode** button next to **Clear selection**. The scalp fades out and every atlas region slides outward from the centre, mostly sideways so the left and right hemispheres separate, with the view zooming out to keep them in frame; press it again and they slide back and the scalp returns. Regions keep their shape, hovering and clicking work while exploded, and the selection is not changed. It follows the system's reduced-motion setting, resets when you change atlas or leave MNI space, and is not offered for a subject's own head.
- **Picking an MNI atlas region selects one side, not both** — in MNI space the CIT168 and Harvard-Oxford cortical atlases gave each structure one label covering both hemispheres, so choosing "Putamen" (in the picker or by clicking the 3D pane) selected, and optimized for, both putamens. Both atlases now list each structure per hemisphere ("Left-…", "Right-…"): **CIT168 subcortical nuclei (left/right)** has 32 regions and **Harvard-Oxford cortical, lateralized** (FSL's own lateralized release) has 96. Pick both sides when you want both. Other atlases and Subject mode are unchanged; they already had one side per region, apart from midline structures such as the cerebellar vermis. A saved configuration or script that names the old `CIT168_labeling_MNI152NLin2009cAsym.nii.gz` or `HarvardOxford-cort-maxprob-thr25-1mm.nii.gz` now stops with a message naming the replacement file, rather than quietly running on different regions.

#### Interface

- **Run pages keep the Jobs table readable at any split** — dragging the Terminal/Scene divider on the Simulator, Optimizer, Analyzer, Pre-processing or an extension panel could squeeze the Jobs table until its headers and selects read "SUE", "F.." or "M", or stretch it across the whole screen. The Jobs side now stays between 640 and 800 px wide and the Terminal/Scene side keeps at least 400 px; a width you dragged on a bigger window is shown as the widest allowed on a smaller one and comes back when the window grows. Below a 1140 px wide window the page stacks the Terminal/Scene under the Jobs table (previously 1100 px). Expand, collapse (**⌘⇧I**) and the terminal's sideways scrolling are unchanged.
- **Run asks about existing outputs on the first press** — pressing Run in the **Analyzer**, **Simulator** or **Optimizer** for a job whose output was already on disk could show "Could not queue the analysis: Simulation outputs already exist…" when the page's plan had not caught up with the disk (a run that had just finished, or a plan still resolving), and only a second press opened the Skip / Replace and rerun dialog. The first press now opens the dialog in that case too. **Skip** now really queues just the new jobs; before, it resubmitted the finished ones as well and the server refused the batch. Nothing is replaced without choosing **Replace and rerun**, as before. The server's refusal names the job kind, e.g. "Outputs of this analyzer job already exist", instead of calling every output a simulation.
- **Saved-scene pictures follow the scene** — a scene re-saved in TetraVox now gets a fresh preview in **Viewer ▸ Saved scenes** when you switch back to TI-Toolbox; previously the first picture was kept forever. The scene's info card also drops repeated rows: **Modified** and **Datasets** appear only when they differ from **Saved** and **Layers**. Scene files and their `.png` sidecars keep their names.
- **The app always loads the interface the server has** — the page that starts the interface was sent without caching rules, so after an update or rebuild the desktop app could keep running the previous interface for hours (new buttons missing, fixed bugs still there) until its cache expired. It is now checked with the server on every load. Nothing else is re-downloaded: the interface's files keep their cacheable, versioned names.

#### Resources

- **TI-Toolbox uses 70 % of your cores by default, and you can change it** — a new **CPU limit** in **Settings → Project → Execution** (10–100 %, shown as e.g. "70 % · 7 of 10 cores") caps the CPUs all running jobs share. Previously a search defaulted to every core but one and several jobs together could take the whole machine. Ex-/mex-search and cluster-permutation workers, flex-search, FastSurfer/FreeSurfer/CHARM/QSI threads and NIfTI conversion now default to this limit; an explicit `n_jobs`/`cpus`/thread value still works but is capped at it. A change applies to jobs started afterwards; running jobs are not touched. Scripts and notebooks honour the same saved setting. Memory limits are unchanged. API: `GET`/`PUT /api/cpu-limit`.
- **One job per product at a time; "Subjects in parallel" is gone** — Pre-processing, Simulator, Optimizer and Analyzer each run one job at a time, whether the jobs come from one multi-subject run or separate runs; the subjects of a run are processed one after another, and any parallelism happens inside a job under the CPU limit. The **Subjects in parallel** field is removed from **Settings → Project → Execution**, and `parallel_subjects` from `POST /api/jobs/groups` and `POST /api/plan/pre`. A value saved by an older version, or sent by an older client, is ignored.

#### Launching on Windows and WSL

- **Desktop app finds Docker Desktop on Windows** — v3.0.0 reported "Docker was not found on this machine" whenever the active Docker context was `desktop-linux`, because its `npipe:////./pipe/…` endpoint was handed to Node with four leading slashes. The app now collapses any `npipe:` spelling to `//./pipe/<name>`, checks Docker Desktop's install directories for `docker.exe` when the Start-Menu PATH is stale, and probes the context pipe and then `dockerDesktopLinuxEngine` and `docker_engine` with `/_ping` before giving up. A missing pipe now reads "Docker is installed but not running" with Docker Desktop and WSL 2 guidance; the chosen endpoint is written to `main.log`.
- **TetraVox is TI-Toolbox's own copy, on every platform** — the desktop app now installs TetraVox for itself on Windows too (the official `win-x64.zip`, alongside the macOS zips and the Linux tarball), verifying each download against the SHA-256 digest GitHub publishes for the asset, and it launches only that copy. The Locate… picker, `PATH` lookup and system-location search are gone; **Settings → Viewer** gains **Update**, which replaces the copy with the newest release and is refused while TetraVox is open. TI's copy keeps its own settings and window, so a TetraVox you installed yourself is neither used nor disturbed. Previously Windows reported "Automatic TetraVox setup requires an official updater-compatible package".
- **Update TetraVox from Settings or from TetraVox itself** — **Settings → Viewer** now shows the newest TetraVox release next to yours and offers **Update to X** (or **Check for updates** when you are current). Inside TI-Toolbox's TetraVox, its own **Software Update** window now appears when a newer release exists; **Update to X** there closes TetraVox, and TI-Toolbox downloads and verifies the release and reopens TetraVox with the last scene it opened. **Skip This Version** is remembered per version. TI-Toolbox still does every install, the same SHA-256-verified way. The in-TetraVox window needs a TetraVox release newer than 0.6.1; older copies keep their updater off and update from Settings as before. A TetraVox you installed yourself no longer blocks TI-Toolbox's Update.
- **TI-Toolbox's TetraVox no longer shares your TetraVox settings file or extensions** — TI-Toolbox's copy (and its offscreen picture captures) now keeps TetraVox's rc file and installed extensions in its own folder instead of your `~/.tetravox`, as it already did for window settings. A TetraVox you installed yourself keeps its settings and extensions untouched; TI-Toolbox's copy starts without them. An already open TI viewer picks this up the next time it is launched.
- **Loaders inside WSL2** — `loader.sh` and `loader.py` treat WSL as a Windows host: the default UI is the browser, the session URL is printed and opened on the Windows side (`wslview`, then PowerShell, then `cmd.exe`), the Linux AppImage is never downloaded, and `--desktop` is refused with a message naming the Windows installer. WSL is detected from `WSL_DISTRO_NAME`/`WSL_INTEROP`, not the kernel string, so a Docker Desktop container is never mistaken for it. `--build` and `--web` no longer demand a project first.

### v3.0.0 — September 20, 2026

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v3.0.0/">Release notes →</a>

v3 replaces the PyQt5 interface with an Electron desktop app backed by the same `tit` scientific
Python package used by scripts and notebooks. See [Installation]({{ site.baseurl }}/installation/)
for downloads and [Desktop Application]({{ site.baseurl }}/wiki/desktop-app/) for the workflow.

#### Application and project management

- **Desktop workspace** — workflow pages retain drafts, selections, scroll positions and scene state during a project session. Navigation follows the processing order, controls work in both themes, and failed previews offer an explicit retry without losing opacity settings. Packaged launches open the bundled Overview correctly; Linux `.deb` packaging includes the required homepage and maintainer metadata.
- **[Overview]({{ site.baseurl }}/wiki/overview/)** — open or switch projects from a subject-readiness matrix with project details, derivative storage totals, an activity calendar and eight recent jobs linked to their results or logs. This replaces Subject Info; older settings that name that panel still load.
- **[Jobs]({{ site.baseurl }}/wiki/jobs/)** — long-running operations have persistent state, progress, artifacts and failure details. CPU and memory peak/average measurements cover the whole process tree and survive completion and server restarts; Linux memory accounting avoids double-counting shared pages. The six data columns share available width, narrow tables scroll, and Stage appears in job details rather than the table. Selecting a job restores its details; artifacts list the actual output folder. Confirmed deletion retains failed filesystem removals for retry. After a server restart, interrupted jobs settle as failed unless a completed exit was recorded; they are not resumed automatically.
- **Job consoles** — completed transcripts and final errors remain visible, live output no longer loses its middle, and reconnects resume without blocking status updates. Scrolling upward disables Follow; enabling it returns to the tail. Stage messages announce starts and completion times without repeated heartbeat lines.
- **Submission and resource planning** — missing inputs are rejected before queueing with their expected paths and recovery instructions. Plans and workers use the container's admitted CPU budget, preprocessing parallelism is bounded by that budget, and duration estimates identify their measured baseline or remain blank when none exists.
- **[Results]({{ site.baseurl }}/wiki/results/)** — browse outputs by subject, preview reports and images inline, and open scenes directly in native TetraVox without leaving the page.
- **Settings and extensions** — Project, Pre-processing, Extensions, Viewer and Server tabs group configuration; preprocessing preferences persist across projects and links retain their requested tab. Optional Source, Cluster permutation, NIfTI group averaging, Nilearn visuals and 3D exporter tools share an Extensions navigation group, with inputs beside their plans and live logs.
- **[Notebooks]({{ site.baseurl }}/wiki/notebooks/) and scripting** — Jupyter uses the container's SimNIBS Python. One packaged example workflow is seeded into projects and refreshed only when the local copy is unedited; API examples live under `examples/scripts/`. The Pipeline canvas was removed before release: saved graphs no longer open or execute, while notebooks, jobs and results remain available.
- **[Example data]({{ site.baseurl }}/wiki/example-data/)** — `ernie` and `mni152` each offer independently downloadable NIfTI and head-model parts through the new-project chooser, **Help ▸ Example data**, Python or CLI. Downloads use the dedicated example-data repository, verify content, reuse existing subjects regardless of label case and queue selected parts without creating jobs or reinitializing projects. `fetch_ernie` fetches both parts; the REST download route is `/api/example-data/{dataset_id}/{part_id}`.
- **Rebuildable caches** — viewer data, warped masks and storage scans live under `.ti-toolbox/cache/`, excluded through `.bidsignore` and identified in Overview storage. Existing caches migrate automatically; results, settings, notebooks, saved scenes and job history stay in place.

#### Launching and preprocessing

- **Launchers and container lifecycle** — Bash and Python loaders share the v3 launcher and default to the desktop project picker; `--project` opens a specific project, while `--browser` and `--no-open` require one. Standalone use needs only a loader and adjacent `docker-compose.yml`; cached management commands work offline. `--dev [DIR]` mounts the selected checkout and builds a missing or stale renderer unless `TIT_DEV_NO_BUILD=1`; the separate development loaders are removed. Container reuse or replacement is explicit, an image mismatch cannot replace a running project's active jobs automatically, and closing Electron stops its session after checking running or queued jobs.
- **Core runtime** — `idossha/ti-toolbox:v3.0.0` contains SimNIBS 4.6, FastSurfer and the server-served UI. The desktop manages Docker through its Engine API. The legacy GUI and launcher, Qt, X11 setup and Freeview/Gmsh launchers are removed; see the [v2 legacy notice]({{ site.baseurl }}/wiki/legacy-v2/) for older workflows.
- **FastSurfer segmentation** — the default structural segmentation produces DKT parcellations using accessible CUDA, managed native Apple MPS or CPU. Apple GPU installation requires consent in **Settings ▸ Pre-processing**; enablement and thread preferences persist across projects. A stale desktop connection falls back to container CPU before execution, while a host lost during a running job fails that job instead of restarting it. See the [FastSurfer guide]({{ site.baseurl }}/wiki/fastsurfer/).
- **Optional FreeSurfer and licensing** — full reconstruction and T1 thalamic or hippocampal/amygdala subregions run in temporary, separately imaged workers, replacing the persistent service and volume while retaining outputs in the project. TI-Toolbox supplies its bundled license automatically to FreeSurfer, QSIPrep and QSIRecon; personal registration prompts are removed and script/cluster overrides remain supported. FastSurfer segmentation needs no license. For scripts, `run_recon` is a deprecated alias for `run_fastsurfer`; `parallel_recon`, `parallel_cores` and `run_subcortical_segmentations` are dropped. Optional reconstruction uses the explicit `run_freesurfer` configuration and subregion fields.
- **CHARM and QSI configuration** — persistent preprocessing settings expose CHARM denoising, final segmentation resolution and scalp mesh facet size, preserving installed SimNIBS defaults when unset. QSIPrep and QSIRecon use bounded, readable forms with persistent actions; thread controls show available capacity and queued jobs retain their submitted allocation.

#### Visualization and targeting

- **Native TetraVox viewer** — full scenes and volume inspection open in a separate native window; run-page surface previews remain embedded. Desktop startup reuses a compatible installation or performs verified initial setup on supported package targets, with locate/retry controls in **Settings ▸ Viewer**. TetraVox owns subsequent updates: the browser embed, TI-managed updater and rollback controls are removed. Handoffs are serialized and ask before replacing a running scene; browser sessions can download scenes for manual opening. Automatic Linux/Windows setup and native foreground/load acknowledgment remain packaged-release checks.
- **Saved scenes** — the Viewer provides independently scrolling builder and library panels, deletion, reference-health checks, offscreen thumbnails and file/layer details. **Save scene** captures the live native scene, including directly opened files, camera and layer edits, into the active project; it requires compatible native saving support. Native snapshots reopen with scene-relative datasets, existing saved scenes need no migration, and preview generation leaves the active view untouched. Save selection and Recent are removed.
- **Target selection and previews** — Optimizer and Analyzer share synchronized Subject/MNI controls, atlas selection and region colors. Subject space uses the selected subject's available anatomy; MNI uses reference anatomy. Cortical and subcortical atlas targets are interactive across Flex, Ex and mEx; custom `.nii`/`.nii.gz` masks accept file drops or paths, with MNI masks registered separately for each subject. Explicit coordinate placement remains in subject space; non-atlas inspection opens in TetraVox.
- **Atlas catalog** — Harvard-Oxford cortical/subcortical, Diedrichsen cerebellum and Schaefer 400/7 MNI volumes join the catalog, with template, type, licensing and citation metadata controlling picker placement. Morel is no longer bundled; existing configurations naming it stop with an explanation. Schaefer is picker-only in the guide preview. See [Brain Atlases]({{ site.baseurl }}/wiki/atlases/) for attribution and optional user-supplied atlases.
- **ROI preparation and confirmation** — selected MNI labels are binarized, transformed once, cleaned in subject space and cached for reuse by optimization and analysis. Warping operates on the relevant grid region while preserving SimNIBS voxel results. Island cleanup applies consistently to previews and calculations, always retains the largest component and can change measurements for fragmented regions; `TIT_ROI_KEEP_ISLANDS=1` restores raw segmentation. Optimizers save one `roi.tetravox.json` with target metadata and existing data references, plus a compressed transformed mask when needed and an optional native thumbnail. This replaces intermediate ROI plates and sidecars; `TIT_NO_ROI_PLATE=1` or the legacy `TIT_NO_ROI_CONFIRMATION=1` disables confirmation artifacts.
- **3D export** — subject-specific atlas, segmentation, montage and field context is previewed before export. Montage rendering uses standalone Blender 4.4.3 to preserve scientific Python dependencies; full-net jobs reserve 16 GiB and other modes 2 GiB. Final baked-image acceptance remains pending; see [memory guidance]({{ site.baseurl }}/wiki/blender/#full-net-montage-memory).

#### Simulation, optimization and analysis

- **Simulator** — per-job rows support duplication, subject-specific scalp placement, editable XYZ/cap montages and confirmed single or bulk deletion of saved montages without deleting results. Anisotropic models expose tensor ratio and conductivity limits. MNI export is opt-in alongside fsaverage mapping; output conversion tolerates macOS metadata sidecars. **Replace and rerun** confirms replacement and clears stale session markers without the removed **Allow unsafe overrides** setting; Skip and Cancel remain available.
- **Optimizer** — one page combines Flex and Ex/mEx methods, per-job targets and leadfield generation. Subjects stay selectable before leadfields exist, completed generation refreshes automatically, and Ex/mEx execution requires a completed leadfield. Ex/mEx provides clickable cap electrodes with synchronized channel-colored buckets, separate montage/current-split evaluation counts, and corrected planning and standard leadfield filename handling.
- **Flex objectives and candidate review** — goals include Mean TImax, Max TImax (99.9%), threshold-free focality with a mean non-ROI denominator and explicit intensity weighting, and fixed/adaptive/multi-threshold focality. Historical p95 and legacy scores retain distinct definitions and must not be compared as the same metric. Results links evaluated candidates, intensity–focality plots, exact poses/current splits and replayable Simulator drafts with cap displacement distances. Unsupported unequal-axis ellipses and invalid optimizer results are rejected; scalar mutation settings work, and final electrode simulations honor gel thickness plus 2 mm rubber. See [Flex search]({{ site.baseurl }}/wiki/flex-search/) for objective definitions.
- **Analyzer outputs** — mesh and voxel analyses write `results.csv`, `analysis.json`, the measured ROI overlay, one weighted `histogram.png` and one `scene.tetravox.json` showing that overlay on the subject anatomy. A compatible native viewer can add `scene.png`; older separate ROI/field scenes, PDF histograms and screenshot traces are no longer emitted into the result folder.
- **Scientific corrections** — cluster inference, voxel focality units and affine/grid validation are corrected. Single-subject groups now contribute zero within-group variance rather than turning the entire comparison into a null map; **re-run affected single-subject-group comparisons from v2.2.3–v2.5.0**. Cluster results from v2.2.3–v2.5.0 should be re-run: opposite-sign clusters that touched were merged, the two-sided and left-tailed permutation null used the least extreme cluster instead of the most extreme, and a sampled p-value could be exactly 0 (right-tailed `greater` tests are unaffected by the first two). Voxel-space `focality_*_area` values from v2.3.0–v2.5.0 were 10× too large (cm² computed from a volume); v3 reports cm³, so divide old values by 10 or re-run (mesh values are unchanged). `hf_peak_is_exact` exposes whether carrier peak estimation is exact; above eight carriers it is a lower bound, not a conservative safety estimate. The positional `tit.calc` API from v2.5.0 is unchanged.

#### Security and API compatibility

- **Input and filesystem safety** — named inputs reject path-shaped values, project access checks resolve symlinks before reads/writes, mask names are bounded, documentation text is rendered safely and search stays on the documentation origin. HTTPS downloads verify certificates using configured or trusted CA bundles; there is no unverified TLS fallback.
- **Runtime capabilities** — `/api/capabilities` reports container tools including FastSurfer; obsolete X11, Freeview, Gmsh and FreeSurfer capability flags are removed. Native viewer availability is detected on the host, not exposed as the retired `tetravox_embed` capability; subject-level `has_freesurfer` remains available.

---
### v2.5.0 — August 31, 2026

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v2.5.0/">Release notes →</a>

**Release Date**: August 31, 2026

#### Additions

- `TI_normal` for mTI — multipolar simulations now write the normal-component envelope (`{montage}_mTI_normal.msh`) by default, computed by evaluating the multi-carrier envelope along the cortical surface normal; the analyzer's `normal_*` ROI statistics populate for mTI exactly as for standard TI.
- fsaverage projection for mTI — `map_to_fsavg` no longer skips multipolar runs: the modulation depth is read from the mTI central surface and `hf_peak`/`hf_sar` are derived from all N channel volume meshes.
- Multipolar exhaustive search (mex-search) — a multipolar counterpart to ex-search (`tit/opt/mex`), with a TI/mTI toggle, symmetric (bilateral) buckets, atlas-region and MNI-space ROI targeting, and a shared searchable ROI picker across ex-search and mTI.
- Threshold-free focality goal for flex-search — a new opt-in focality objective plus an opt-in current-ratio search, replacing threshold-dependent focality scoring.
- Selectable output fields — the simulator now writes only the fields you choose (TI_max by default) instead of a fixed set, with field definitions documented in the help popup.
- Custom subject masks as ROI targets — label volumes placed under `m2m_<id>/masks/` are auto-discovered and offered as subcortical ROI targets in flex/ex/mex-search and the analyzer.
- Unified TI/mTI field metrics — carrier grouping, hf_peak sign handling, and the TI/mTI metric surface were corrected and unified across calc, sim and the analyzer, closing several description/code mismatches; a literature-grounded field-metrics note documents the math.
- DWI preflight validation — gradient tables and sidecars are validated and QSIPrep node crashfiles are logged before/at container failure, catching bad DWI conversions early.
- Interactive atlas browser and multipolar TI documentation pages on the docs site, including subject-space atlas assets and a redesigned full-width docs theme with per-page subnav and KaTeX equation rendering.
- Claude Code / AI-assistant plugin (`agent-plugin/`) — an MCP server and marketplace listing so AI coding assistants understand the TI-Toolbox codebase, plus a maintainer-verified Troubleshooting Archive.
- Faster ex/mex-search — unit-current channel fields are now computed once per montage and reused across current splits, the TI/mTI envelope is evaluated on ROI∪GM only (not the whole head), and candidates run on a forked worker pool (`n_jobs`). Ex-search: 0.39 s → 0.05 s per evaluation (~8×; a 4,375-evaluation bucket search dropped from 28 min to 3 min). Mex-search: 58 s → ~1.4–2 s per candidate (~30–40×) via a fused numba kernel for the K≥2 mTI direction search.
- Ex/mex-search electrode-map visuals — every ex/mex-search run now writes an electrode participation heatmap and montage strength/focality maps, ported from work by [Larissa Albantakis](https://github.com/Albantakis) on her [ex-search-multipolar branch](https://github.com/Albantakis/TI-Toolbox/tree/ex-search-multipolar).
- Zenodo DOIs added for the archived software release.

#### Changes

- **Breaking:** `tit.calc` consolidated to exactly three envelope functions — `get_TI_vectors(fields, psi=None)` (K ≥ 1 carriers; the K = 1 exact closed form is applied internally), `get_TI_avg(fields, psi=None)`, and `get_TI_dir(fields, directions, psi=None)`. Scripts calling `get_TI_vectors(E1, E2)` positionally must switch to `get_TI_vectors([E1, E2])`; `get_mTI_vectors` is now `get_TI_vectors`, `get_mTI_dir` is `get_TI_dir`, and the deprecated `get_nTI_vectors` shim and the unused `get_magnitude_am` were removed, as was the legacy `channels=` carrier-regrouping parameter.
- Carrier wiring removed — mTI is always positional (each two consecutive electrodes compose a channel, each two consecutive channels compose a carrier): the mex-search "Carrier Wiring" combo, `MTI_CHANNEL_ARCHITECTURES`, and the `channels` JSON config keys are gone (old configs with the key are ignored).
- Documentation vocabulary unified across the simulator, analyzer and ex-search pages: **electrodes → channels (2 electrodes each) → carriers (shared by 2 channels)**; TI = 4 electrodes / 2 channels / 1 carrier, mTI = 8 electrodes / 4 channels / 2 carriers.

#### Fixes

- Analyzer sim-list bug fix, plus analyzer/ex-search layout cleanups (paired Tissue/Space and Field/Type controls, either/or ROI selection, dead vertical space removed).
- Ex-search now rejects empty ROI configs, tolerates header rows in MNI ROI CSVs, and fails cleanly on zero candidates instead of silently returning nothing.
- Flex-search summary.txt no longer prints a raw Python function repr on the Goal line.
- QSIPrep/QSIRecon fixes — the root BIDS dataset description is always created, a missing T1w is reported up front, QSIRecon's log directory is no longer mistaken for existing output, and a converted DWI arriving without its gradient table now warns instead of failing silently.
- DICOM import — a converted DWI missing its gradient table is now caught and reported.
- Atlas resampling in the analyzer — atlases and tissue masks are now matched to the field on shape **and** affine and resampled nearest-neighbour, replacing a shape-only check and an interpolating `mri_convert` call that also required FreeSurfer binaries absent from the simulation container. See the note below.
- Docs — corrected stale ROI, tissue, atlas, CLI and testing-pipeline claims across the wiki, scripting, ex-search and analyzer pages; fixed release download links and a blank atlas viewer for cached scripts.
- Dev loader — `loader_dev.sh` rewritten as a working Python-free bash loader after regressions.

#### Note: atlas resampling in the analyzer

The analyzer's grid check compared shape only, so an atlas with matching dimensions but a different affine could pass through untouched and produce statistics for the wrong tissue, silently. Resampling also used `mri_convert --reslice_like`, whose default trilinear interpolation blends discrete region ids into ids that belong to no region. The check now compares the affine too, resampling is nearest-neighbour, and neither step needs FreeSurfer binaries that the simulation container does not ship.

<a href="{{ site.baseurl }}/assets/imgs/atlas-resampling/atlas_resample_v250_old_vs_new.png">
  <img src="{{ site.baseurl }}/assets/imgs/atlas-resampling/atlas_resample_v250_old_vs_new.png" alt="Old versus new atlas resampling in v2.5.0" style="width: 100%; max-width: 950px;">
</a>

**This is a robustness fix, not a result-changing one.** Interpolation order only matters when the atlas and field lattices do not coincide, which for the 1 mm FreeSurfer parcellations, the thalamic nuclei and every MNI atlas they do — old and new are bit-identical there. The one exception is the 0.333 mm hippocampal and amygdala subfields, shown above: even in that worst case the reported **field changes by ~0.5%** (mean −0.6%, max −1.2%) while the ROI *volume* changes by −42%, because trilinear erodes the region's boundary. Field statistics from earlier versions stand; ROI voxel counts and volumes from a hippocampal or amygdala subfield ROI are worth regenerating. Details on the [Brain Atlases]({{ site.baseurl }}/wiki/atlases/#atlas-resampling) page.

#### Download Links

**Desktop App (v2.5.0):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.5.0/TI-Toolbox-2.5.0.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.5.0/TI-Toolbox-2.5.0-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.5.0/TI-Toolbox.Setup.2.5.0.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.5.0/TI-Toolbox-2.5.0.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.5.0/ti-toolbox_2.5.0_amd64.deb)

**Other:**
- Docker Image: `docker pull idossha/simnibs:v2.5.0`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

---

### v2.4.0 — July 20, 2026

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v2.4.0/">Release notes →</a>

**Release Date**: July 20, 2026

#### Additions

- **Combine multiple ROIs in optimization** — flex-search and exhaustive-search can now target the union of several same-type regions (cortical by name including cross-hemisphere, subcortical by label, or multiple spheres) through a searchable region picker with region chips.
- **TI safety metrics (Cassarà et al. 2025)** — peak carrier field and SAR-driver maps are now written as subject- and MNI-space NIfTI volumes alongside TI_max.
- **Surface-based group statistics** — run group comparisons and correlations directly on the fsaverage cortical surface with cluster-based permutation testing and inflated-cortex rendering; TI fields now auto-project to fsaverage after each simulation.
- **CT and NIfTI ingestion** — preprocessing can now import head CT scans and pre-converted NIfTI files (T1w/T2w/CT/DWI), not only DICOMs.
- **3D Visualizer subcortical field export** — export subcortical structures colored by a simulation field (PLY) using a searchable label picker.
- **Simulator skip/replace policy** — choose to skip or overwrite existing simulation outputs instead of aborting with an error.
- **Montage visualizer clarity** — connection arcs now show which channels interfere (TI partners), with a channel color legend.
- **Faster simulations** — mesh-to-NIfTI conversion is parallelized, cutting end-to-end simulation time by roughly 30%.

#### Fixes

- **DICOM import crash** — fixed a crash on projects seeded with macOS junk (AppleDouble) files.
- **QSIPrep preprocessing failures** — the root BIDS dataset description is now always created, and a missing T1w is reported up front instead of failing deep in the workflow.
- **3D exporter file loss** — fixed the exporter deleting cortical region files after export.
- **FreeSurfer data volume versioning** — the volume is now versioned by image tag so image updates correctly re-seed it.

#### Download Links

**Desktop App (v2.4.0):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.4.0/TI-Toolbox-2.4.0.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.4.0/TI-Toolbox-2.4.0-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.4.0/TI-Toolbox-2.4.0.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.4.0/TI-Toolbox-2.4.0.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.4.0/TT-Toolbox-2.4.0.deb)

**Other:**
- Docker Image: `docker pull idossha/simnibs:v2.4.0`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

---

### v2.3.2 — June 11, 2026

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v2.3.2/">Release notes →</a>

**Release Date**: June 11, 2026

#### Additions

- New Source tool (extension): build MNE EEG forward solutions and project TI fields onto the fsaverage template.
- Preprocessing now automatically converts DWI DICOMs to BIDS NIfTI alongside T1w/T2w.

#### Fixes

- FreeSurfer recon-all no longer falsely reports its output as already existing on a fresh project.

#### Download Links

**Desktop App (v2.3.2):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.2/TI-Toolbox-2.3.2.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.2/TI-Toolbox-2.3.2-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.2/TI-Toolbox-2.3.2.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.2/TI-Toolbox-2.3.2.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.2/TT-Toolbox-2.3.2.deb)

**Other:**

- Docker Image: `docker pull idossha/simnibs:v2.3.2`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

---

### v2.3.1 — May 8, 2026

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v2.3.1/">Release notes →</a>

**Release Date**: May 8, 2026

Focused maintenance release for preprocessing robustness, GUI reliability, QSI container compatibility, flex-search validation tools, and NIfTI viewer usability.

#### Fixes & Maintenance

##### Flex-search and Simulation Workflow

- **Flex-search simulation identity and UI naming** — simulator-generated flex-search runs now keep a unique storage key while showing compact, readable run labels and hover metadata in the GUI, following the run-id/run-name split used by tools such as [MLflow](https://mlflow.org/docs/latest/api_reference/python_api/mlflow.html).
- **Flex-search valid skin region controls** — flex-search now exposes `skin_region_margin_mm`, optional landmark guarding, GUI controls, and report imagery so users can inspect and tune the valid scalp placement region used by optimization.

##### Reports and Visualization

- **Report and visualization follow-ups** — simulation reports use clearer missing-visualization states and simulations continue when optional montage visualization cannot be generated.
- **Analyzer discovery improvements** — Analyzer refreshes simulation lists when shown and after simulation completion, with clearer messages when TI/mTI post-processing outputs are missing.

##### NIfTI Viewer

- **Electrode NIfTI overlays** — the NIfTI Viewer can create and auto-load a single label-mask overlay showing saved electrode placements from `documentation/config.json`. Labels are channel-based, use the same color order as montage PNGs, and are saved next to montage images under `TI/montage_imgs/` or `mTI/montage_imgs/` depending on simulation mode.

##### GUI Reliability

- **GUI lifecycle reliability** — preprocessing, simulation, flex-search, ex-search, Analyzer, and NIfTI Viewer tabs now refresh dependent outputs more consistently and avoid reporting success after failed subprocesses.

##### Preprocessing and QSI

- **DICOM preprocessing hardening** — DICOM discovery now searches nested `.dcm`/`.dicom` files and supports basic compressed inputs (`.zip`, `.tar`, `.tar.gz`, `.tgz`) in the documented `sourcedata/sub-{id}/{T1w,T2w}/dicom/` layout.
- **Preprocessing existing-output handling** — the GUI now detects existing outputs before rerunning DICOM conversion, CHARM, FreeSurfer `recon-all`, QSIPrep, QSIRecon, or DTI extraction. Users can cancel, skip existing outputs, or explicitly replace them and rerun. The same policy is available to scripts through `skip_existing_outputs` and `replace_existing_outputs`.
- **QSI Docker preflight** — QSIPrep and QSIRecon now validate Docker/DooD setup early, before starting long-running container work.
- **QSI containers updated** — QSIPrep and QSIRecon now target PennLINC `26.0.0`, with CLI compatibility handling for QSIPrep `concat` and QSIRecon `--input-type qsiprep`.

##### Telemetry and Release Operations

- **Telemetry error grouping** — operation telemetry now emits a per-run `run_id` plus a stable, path-sanitized `error_fingerprint`, making recurring failures easier to group without sending tracebacks or local paths.
- **Telemetry-driven preflight checks** — common user/environment problems are validated before telemetry-tracked work starts for simulation, flex-search, and empty preprocessing subject selections, reducing noisy error reports while preserving real exceptions.
- **Telemetry consent persistence** — GUI telemetry consent is stored in the user-level config mount and should no longer reappear every launch once answered.
- **Launcher telemetry normalization** — host OS and architecture values are canonicalized across the Electron launcher and `loader.py`, keeping telemetry slices consistent across entrypoints.
- **Community link** — README and release help links now point to the active TI-Toolbox Discord server.
- **Release-gate tests** — added Dockerfile.test-based integration checks plus a self-contained comprehensive release-gate entry point using only test-environment fixtures.

#### Download Links

**Desktop App (v2.3.1):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.1/TI-Toolbox-2.3.1.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.1/TI-Toolbox-2.3.1-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.1/TI-Toolbox.Setup.2.3.1.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.1/TI-Toolbox-2.3.1.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.1/ti-toolbox_2.3.1_amd64.deb)

**Other:**

- Docker Image: `docker pull idossha/simnibs:v2.3.1`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

---

### v2.3.0 — March 17, 2026

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v2.3.0/">Release notes →</a>

**Release Date**: March 17, 2026

A major release with new analysis capabilities, broader simulation support, diffusion pipeline integration, and a modernized codebase built on SimNIBS 4.6.0.

#### Preprocessing & Segmentation

- **Subcortical sub-nuclei segmentation** — hippocampal and thalamic sub-nuclei are now automatically segmented as part of the FreeSurfer recon-all pipeline.
- **QSIPrep / QSIRecon integration** — diffusion MRI preprocessing and reconstruction are now available through the GUI and CLI, including DTI extraction for anisotropic simulations. This still needs further validation, but works well internally.
- **MASSP2021 nuclei atlas** — added under the MNI resources as a built-in subcortical atlas for targeting thalamic and brainstem nuclei. Can be selected in the group-level visualization step.

#### Simulation & Optimization

- **Upgraded to SimNIBS 4.6.0** — the underlying finite-element engine is now at its latest version, bringing improved meshing and solver accuracy.
- **Anisotropic conductivity in optimization** — flex-search now supports all 4 SimNIBS conductivity models (isotropic, volume-normalized, direct, and mean-conductivity). Select via the GUI dropdown or the `anisotropy_type` config parameter. Fine-tune with `aniso_maxratio` and `aniso_maxcond`.
- **White matter / gray matter tissue targeting** — flex-search lets you choose whether to optimize over gray matter, white matter, or both.
- **Focality Pareto sweep** — new tool to systematically explore the trade-off between field intensity and focality across a grid of threshold combinations, producing a Pareto plot and summary table.
- **Batch simulation** — run multiple simulation configurations in sequence from a single GUI session.

#### Analysis

- **Combined multi-ROI analysis** — select multiple atlas regions and analyze them as a single combined ROI. Outputs use a `+`-joined naming convention (e.g., `precentral+postcentral/`).
- **Tissue-type selection in analysis** — choose GM, WM, or both when running voxel-space analyses.

#### Infrastructure & Usability

- **Singularity / Apptainer support** — run TI-Toolbox on HPC clusters without Docker.
- **HTML report generation** — automated reports for simulation and preprocessing results.
- **Redesigned GUI** — modernized styling, consistent console output, and reusable ROI/electrode/solver widgets across all tabs.
- **Simplified Python scripting API** — cleaner imports and flat configuration dataclasses make scripting simulations, optimizations, and analyses more straightforward. See the updated API documentation for examples.
- **Improved CI/CD and test suite** — comprehensive automated testing with coverage tracking.

#### Breaking Changes (for scripters)

- The Python API has been significantly simplified. If you have scripts that import from `tit`, please refer to the updated [API documentation]({{ site.baseurl }}/wiki/scripting/) for the new import paths and configuration classes. Key changes:

#### Download Links

**Desktop App (v2.3.0):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.0/TI-Toolbox-2.3.0.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.0/TI-Toolbox-2.3.0-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.0/TI-Toolbox.Setup.2.3.0.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.0/TI-Toolbox-2.3.0.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.3.0/ti-toolbox_2.3.0_amd64.deb)
**Other:**

- Docker Image: `docker pull idossha/simnibs:v2.3.0`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

---

### v2.2.4 — January 16, 2026

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v2.2.4/">Release notes →</a>

**Release Date**: January 16, 2026

#### Additions

- N/A

#### Fixes

- **Loader Program**: Fixed example data and initiliazation of the BIDS files. Also, should be handling X11 more gracefully.

#### Download Links

**Desktop App (v2.2.4):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.4/TI-Toolbox-2.2.4.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.4/TI-Toolbox-2.2.4-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.4/TI-Toolbox.Setup.2.2.4.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.4/TI-Toolbox-2.2.4.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.4/ti-toolbox_2.2.4_amd64.deb)
**Other:**

- Docker Image: `docker pull idossha/simnibs:v2.2.4`
- Source Code: [GitHub Repository](https://github.com/idossha/TI-Toolbox)

---

### v2.2.3 — January 7, 2026

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v2.2.3/">Release notes →</a>

**Original Release Date**: January 07, 2026
**Effective Release Date**: January 14, 2026 (re-uploaded tag with preprocessing refactored to deal with recon-all problem without releasing and official new image. Should be updated automatically to all users without breaking behavior).

#### Additions

- **New Blender Tool for Full Blend File Creation**: Complete Blender integration with automated blend file generation, electrode positioning, and visualization setup. Streamlined workflow for creating publication-ready 3D visualizations directly from simulation results.
- **Ex-search**: Added an option to run the a truly exhaustive search option as all selected electrodes are pooled together instead of placed in stationary buckets. Refer to ex-search wiki tab for more information.
- **New Correlation Mode for Cluster-Based Permutation Testing**: Enhanced statistical analysis capabilities with correlation-based cluster permutation testing, providing more robust statistical inference for connectivity and relationship analyses.
- **Unified Command-Line Experience**: All CLI tools now support both interactive mode (run without arguments) and direct mode (with flags). Consistent colored output, clear prompts, and intelligent option discovery across all commands.
- **Multi-Processing Simulator**: Parallel processing capabilities for faster simulation runs, optimized resource utilization, and scalable performance across different hardware configurations.
- **Enhanced Testing Suite Coverage**: Comprehensive test coverage expansion including simulator workflows, statistical analysis pipelines, and integration testing for improved reliability and stability.
- **Improved Security CI/CD Pipeline**: Strengthened GitHub Actions workflows with enhanced security scanning, automated vulnerability detection, and improved code quality gates throughout the development pipeline.
- **Refactored pre-processing tools**: Removed all bash scripts to improved maintainability and reduce complexity. Updated all relevant benchmarks, tests, and docs.

#### Fixes

- **Experimental Movea Tool**: Temporarily removed the experimental movea tool to focus development efforts on core functionality and stability.
- **Bug Fixes & Reliability**: Fixed GUI crashes and timeout issues. Improved path handling and import reliability. Updated electrode templates for better compatibility. Enhanced security scanning and CI/CD workflows.
- **Documentation Updates**: New CLI and GUI documentation pages. Improved Blender integration instructions. Added visualizer documentation. Better organization of documentation images.

#### Download Links

**Desktop App (v2.2.3):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.3/TI-Toolbox-2.2.3.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.3/TI-Toolbox-2.2.3-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.3/TI-Toolbox.Setup.2.2.3.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.3/TI-Toolbox-2.2.3.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.3/ti-toolbox_2.2.3_amd64.deb)
**Other:**

- Docker Image: `docker pull idossha/simnibs:v2.2.3`

---

### v2.2.2 — December 25, 2025

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v2.2.2/">Release notes →</a>

**Release Date**: December 25, 2025

#### Additions

- **Simulator Refactoring**: Complete rewrite from bash to Python with modular architecture including progress callbacks, better error handling, and improved logging.
- **Enhanced Cluster Permutation Testing**: New ACES-like correlation investigation, support for continuous variables, enhanced reporting, and improved GUI integration.
- **Comprehensive Testing Infrastructure**: new test files with code coverage integration, headless operation support, and improved CI/CD pipeline.
- **Improved 3D Visualization**: Enhanced visual exporter with automatic electrode placement, metadata extraction, GLB format export, and Docker-based Blender integration.
- **Pythonic CLI Migration**: New Click-based command-line interfaces for simulator and cluster permutation tools with better argument validation.
- **GUI Enhancements**: Improved threading across all tabs with real-time progress updates, better error handling, and enhanced responsiveness.

#### Fixes

- **Various Bug Fixes**: Fixed silent timeout issues in CI, corrected coverage integration, improved error handling in all major modules, better cleanup of temporary files, and enhanced logging.
- **Windows Electron**: A more robust executable delivery on Windows.

#### Download Links

**Desktop App (v2.2.2):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.2/TI-Toolbox-2.2.2.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.2/TI-Toolbox-2.2.2-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.2/TI-Toolbox.Setup.2.2.2.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.2/TI-Toolbox-2.2.2.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.2/ti-toolbox_2.2.2_amd64.deb)
**Other:**

- Docker Image: `docker pull idossha/simnibs:v2.2.2`

---

### v2.2.1 — December 4, 2025

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v2.2.1/">Release notes →</a>

**Release Date**: December 04, 2025

#### Backward compatibility change to be aware:

- **Electode Mapping**: We changed the mapping functionality from the **flex-seach** to the **simulator**. This to provide a more flexible and dynamic framework. Now, the flex-search outputs the: `electrode_positions.json` file and the mapping functionality happeneds on the simulator side using the new method `ti-toolbox/tools/map_electrodes.py`. Thus, one can use a single flex-search to conveniently map to multiple nets.

#### Additions

- **Desktop App**: Recognizing the importance of Desktop delivery, we redesign our executables with Electron. For more info please see `package`.
- **Benchmarks**: Added benchmarking tool with sensible defaults that users can run on their systems
- **AMV**: Improved automatic montage visualization that now supports all available nets with a higher resolution image.
- **Flex-search**: Added more control over electrode geometry now supporting rectengular and width control.
- **Flex-search**: Exapnded hyper-parameter control. tolerance and mutation rate.
- **Ex-search**: Enhanced the ex-search with current ratio optimization, enabling more robust optimization process. The exhaustive search now evaluates possible electrode montages and current ratios according to the formula:

$$
N_{\text{total}} = N_{\text{elec}}^{4} \cdot N_{\text{current}},
\qquad
N_{\text{current}} = \left\lvert \left\{ (I_1, I_2) \;\middle\vert\; I_1 + I_2 = I_{\text{total}} \;\wedge\; I_{\text{step}} \le I_1, I_2 \le I_{\text{limit}} \right\} \right\rvert
$$

#### Fixes

- **Various Bug Fixes**: protection overwrites, documentation, output formatting, UI improvements, parallel processing, electrode management

#### Download Links

**Desktop App (v2.2.1):**
[macOS Intel](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.1/TI-Toolbox-2.2.1.dmg) ·
[macOS Apple Silicon](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.1/TI-Toolbox-2.2.1-arm64.dmg) ·
[Windows](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.1/TI-Toolbox.Setup.2.2.1.exe) ·
[Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.1/TI-Toolbox-2.2.1.AppImage) ·
[Linux deb](https://github.com/idossha/TI-Toolbox/releases/download/v2.2.1/ti-toolbox_2.2.1_amd64.deb)

**Other:**

- Docker Image: `docker pull idossha/simnibs:v2.2.1`

---

### v2.2.0 — November 7, 2025

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v2.2.0/">Release notes →</a>

**Release Date**: November 07, 2025

#### Additions

- **Core Infrastructure & Architecture**: The project underwent a complete restructure, removing old launcher directories and consolidating to a unified ti-toolbox structure. A new core module system was introduced in ti-toolbox/core/ with reusable components including paths.py, calc.py, constants.py, errors.py, process.py, utils.py, nifti.py, mesh.py, and viz.py. The project moved away from executable compilation and now focuses exclusively on bash entry point.
- **GUI Extensions System**: A new modular extension system was introduced in ti-toolbox/gui/extensions/ providing several powerful tools. The Cluster-Based Permutation Testing (CBP) extension offers statistical analysis for group comparisons. Nilearn Visuals enables brain visualization using nilearn with glass brain views, surface plots, and slices. The NIfTI Group Averaging tool allows averaging multiple NIfTI files across subjects. The Visual Exporter provides export capabilities to Blender-compatible formats (PLY, STL) with a full tutorial. Additional extensions include Quick Notes for in-app note-taking with persistence, Subject Info Viewer for displaying metadata and processing status, and an Electrode Placement Tool for interactive electrode positioning.
- **3D Visualization & Export**: A 3D Exporter module was added in ti-toolbox/3d_exporter/ containing four specialized tools. TI_quick_volumetric.py provides fast volumetric field exports, cortical_regions_to_ply.py handles region-specific mesh exports, cortical_regions_to_stl.py outputs STL format for 3D printing, and vector_ply.py enables vector field visualization in Blender.
- **MOVEA Optimization**: MOVEA-like integration was implemented for multi-objective optimization of electrode placement. The system now uses a centralized leadfield with unified leadfield target locations across all optimization tools. A complete MOVEA GUI tab provides an interface for optimization workflows.
- **Analysis Tool**: Group Analyzer received significant improvements including enhanced multi-subject analysis capabilities with MNI coordinate support.
- **Statistics Module**: A statistics package was created in ti-toolbox/stats/. The cluster_permutation.py module implements non-parametric cluster-based permutation testing.
- **Simulator Improvements**: The simulator received substantial enhancements including a new free-hand mode that allows direct electrode coordinate input without montage selection. The entire simulator was refactored for a cleaner codebase with better error handling.
- **Optimization Tools**: The flex-search tool was restructured and modularized into ti-toolbox/opt/flex/. A multi-start approach was implemented allowing multiple iterations to find the best solution. The ex-search tool received enhancements for better ROI handling and faster analysis.
- **GUI Enhancements**: Multiple GUI improvements enhance the user experience. A centralized Path Manager handles path operations across all GUI tabs. Console output was standardized for consistent logging and status updates. Confirmation dialogs now appear before long-running processes. A debug mode provides optional verbose output for troubleshooting. An OpenGL fallback system provides automatic compatibility handling for macOS issues.
- **Documentation**: More documentation was added covering new features. New wiki pages document cluster permutation testing, electrode placement, MOVEA optimization, tissue analyzer, visual exporter, nilearn visuals, nifti group averaging, and quick notes. A pipeline flow diagram provides visual representation of the complete workflow. A detailed Blender tutorial offers step-by-step guidance for 3D visualization. Installation documentation was streamlined with updated setup instructions and removal of executable references. The gallery was updated with new screenshots showcasing all GUI features.
- **CI/CD & Testing**: A CI/CD pipeline was implemented with automated testing and Codecov integration for code coverage tracking. The test suite was expanded covering most modules, including new test files for calc, constants, core integration, mesh, errors, ex-analyzer, nifti, paths, process, utils, and MOVEA optimizer with integration tests. CircleCI integration now provides automated testing on every commit with proper permissions and workflows.
- **Development Tools**: Developer experience was improved with enhanced dev environment setup in dev/bash_dev/ for contributors. Version control management was improved for better consistency across all files. The project standardized on the simnibs_python interpreter for all Python operations. Container communication between FreeSurfer and SimNIBS was enhanced for better data sharing.

#### Fixes

- **Bug Fixes & Refinements**: Numerous bug fixes and refinements were implemented including BIDS structure compliance improvements, resolution of deadlock issues in GUI tabs, improved overwrite protection across all tools, fixed electrode naming consistency, better handling of network volumes, X11 and OpenGL fixes for cross-platform compatibility, and reduced console bloat with improved logging throughout the application.
- **Removals & Cleanup**: Significant cleanup was performed removing all executable launcher code (over 7,000 lines), eliminating old MATLAB dependencies, removing outdated documentation and assets, cleaning up redundant development files.

#### Download Links

- Docker Image: `docker pull idossha/simnibs:v2.2.0`
- **[loader.sh](https://github.com/idossha/TI-toolbox/blob/v2.2.0/loader.sh)** - Main launch script
- **[docker-compose.yml](https://github.com/idossha/TI-toolbox/blob/v2.2.0/docker-compose.yml)** - Docker configuration

---

### v2.1.3 — October 8, 2025

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v2.1.3/">Release notes →</a>

**Release Date**: October 08, 2025

#### Additions

- - **Executable Launcher**: pre-flight check for existing containers to avoid start conflicts.
- - **Executable Launcher**: validation of path input (for mannual inputs)
- - **Flex-search**: dynamic focality thresholding for better output
- - **Development**: Added a watchdog for easier GUI development
- - **Analyzer**: Added `labeling.nii.gz` as an option for voxel analysis w/o need for recon-all

#### Fixes

- - **General**: Removed env limits for flex-search, cleaned up GUI tabs, fixed Gmsh GUI lauchner with analysis visuals, fixed example data (ernie, MNI152) mounting in executable mode, clean up of executable console output.
- - **Critical**: Batch processing of sub-cortical targets in flex-search mode. Previous, `labeling.nii.gz` was no updating between subjects, causing incorrect optimization targeting.

#### Download Links

- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.3/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.3/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.3/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.1.2 — September 8, 2025

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v2.1.2/">Release notes →</a>

**Release Date**: September 08, 2025

#### Additions

- Example Dataset: Toolbox now ships with Ernie & MNI152 MRI scans for quick start & learning purposes.
- Tissue Analyzer: Added skin thickness and volume analysis

#### Fixes

- Various bug fixes: charm, ex-search, flex-search

#### Download Links

- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.2/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.2/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.2/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.1.1 — August 28, 2025

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v2.1.1/">Release notes →</a>

**Release Date**: August 28, 2025

#### Additions

- N/A

#### Fixes

- **ex-search**: fixed final.csv output
- **flex-search**: fixed cleanup of directory if users choose a single start

#### Download Links

- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.1/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.1/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.1/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.1.0 — August 25, 2025

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v2.1.0/">Release notes →</a>

**Release Date**: August 25, 2025

#### Additions

- **Improved BIDS formatting:** Enhanced Brain Imaging Data Structure (BIDS) compliance and formatting for better data - organization and compatibility
- **Debug mode for console output:** Introduced comprehensive debug mode with detailed console logging for troubleshooting and development
- **Inter-individual variability assessment:** New bone analyzer tool integrated into pre-processing pipeline for assessing anatomical variations between subjects
- **Multi-start approach for flex-search optimization:** Implemented multi-start optimization strategy to counter local maxima issues in electrode placement optimization

#### Fixes

- **Removed MATLAB runtime dependency:** Eliminated MATLAB runtime requirement, making the toolbox fully independent and easier to deploy
- **mTI bug fixes and upstream integration:** Resolved critical bugs in mTI (multi-channel Temporal Interference) functionality and improved integration with upstream SimNIBS components
- **Enhanced X11 handling for macOS:** Improved X11 server integration and display management for better GUI - functionality on macOS systems
- **Official rebranding:** Complete renaming from TI-CSC to TI-Toolbox across all components, documentation, and user interfaces

#### Download Links

- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.0/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.0/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.1.0/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.0.5 — July 10, 2025

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v2.0.5/">Release notes →</a>

**Release Date**: July 10, 2025

#### Additions

- **Group Analysis Features**: Group analysis system with GUI interface, comparison capabilities, and logging
- **Focality Measurement**: New focality analysis tools with histogram generation for cortical analysis
- **Normal Component Analysis**: Added normal component matrics and visualization
- **Enhanced Workflow**: Multiple subject selection for flex-search, new naming conventions

#### Fixes

- **GUI Stability**: Multiple bug fixes for group analysis GUI, element resizing, console widget consistency, and special character handling
- **Analysis Accuracy**: Improved histogram generation, ROI comparison plots
- **Visualization**: Fixed mesh visualization and updated mesh visualizer functionality

#### Download Links

- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.5/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.5/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.5/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.0.4 — June 26, 2025

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v2.0.4/">Release notes →</a>

**Release Date**: June 26, 2025

#### Additions

- flex-search -> simulator integration. Simulator now recognizes previous flex-searches and allows for simulation of both optimized and mapped electrodes.
- system monitor -> added a GUI tab that allows users monitor the activity of processes hapenning within the toolbox

#### Fixes

- pre-process -> added missing shell for recon-all step
- pre-process -> fixed parallalization problem
- ex-search redesign -> now is not dependent on MATLAB Runtime, but is fully Python implemented
- ex-search -> users can now creat multiple leadfields for the same subject
- flex-search -> post processing method for TI envelope direction is implemented

#### Download Links

- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.4/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.4/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.4/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.0.3 — June 20, 2025

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v2.0.3/">Release notes →</a>

**Release Date**: June 20, 2025

#### Additions

- Modified tes_flex_optimization.py to include eeg_net field in the .json
- toggle between "Montage Simulation" (traditional) and "Flex-Search Simulation" with automatic discovery of optimization results and electrode type selection (mapped/optimized/both)
- Modified TI.py and pipeline scripts to handle direct XYZ electrode coordinates instead of just electrode names, enabling optimized electrode positioning from flex-search results

#### Fixes

- N/A

#### Download Links

- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.3/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.3/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.3/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.0.2 — June 19, 2025

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v2.0.2/">Release notes →</a>

**Release Date**: June 19, 2025

#### Additions

- Enhanced X11 support for Windows with automatic host IP detection and VcXsrv/Xming configuration guidance
- Created `windows_x11_setup.sh` helper script for simplified Windows X server setup
- Added comprehensive Windows BIDS path guide (`WINDOWS_BIDS_PATH_GUIDE.md`) with troubleshooting tips
- Improved cross-platform X11 configuration with better error handling and user guidance
- Added OpenGL software rendering flags for better GUI compatibility across all platforms

#### Fixes

- Fixed volume mounting in docker-compose.yml - all required volumes now properly mounted to simnibs container
- Fixed Windows path handling - automatic conversion of backslashes to forward slashes for Docker compatibility
- Fixed paths with spaces on Windows - automatic quoting of paths containing spaces
- Fixed X11 socket mounting for macOS XQuartz and Linux compatibility
- Fixed DISPLAY environment variable configuration for Windows, macOS, and Linux
- Fixed MATLAB Runtime library paths in container environment
- Updated XQuartz version warning to reference memory about v2.7.7 compatibility requirement

#### Download Links

- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.2/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.2/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.2/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.0.1 — June 11, 2025

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v2.0.1/">Release notes →</a>

**Release Date**: June 11, 2025

#### Additions

- new logger and report generators under 'projectDIR/derivatives/'
- sub-cortical atlas based targeting for flex-search (example: thalamus targeting)

#### Fixes

- 2 decimal spherical ROIs
- 'TI.py' overwrite protection removed
- intenral 185 EGI net (removed 2 missed electrodes)
- added imagemagick for montage visualizer

#### Download Links

- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.1/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.1/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.1/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

### v2.0.0 — May 28, 2025

<a class="release-notes-link" href="{{ site.baseurl }}/releases/v2.0.0/">Release notes →</a>

**Release Date**: May 28, 2025

#### Major Changes

- Complete rewrite of the Temporal Interference Toolbox with major enhancements: Cross-platform support for Windows, macOS, and Linux
- Docker-based containerization for consistent environment and reproducibility
- Dual interface with both GUI and CLI support, enabling local and remote server usage
- Key functionalities include DICOM to NIfTI conversion, FreeSurfer segmentation, SimNIBS head modeling, flexible and exhaustive electrode optimization algorithms, FEM-based temporal interference field calculations, and comprehensive analysis tools with atlas-based ROI evaluation

#### Installation

- [Windows Installer](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.0/TI-Toolbox-Windows.exe)
- [macOS Universal](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.0/TemporalInterferenceToolbox-macOS-universal.zip)
- [Linux AppImage](https://github.com/idossha/TI-Toolbox/releases/download/v2.0.0/TemporalInterferenceToolbox-Linux-x86_64.AppImage)

---

## Version Support

We actively support and maintain versions 2.x.x and newer of the Temporal Interference Toolbox. Versions 1.x.x are no longer supported.

## Getting Help

If you encounter issues with any release:

1. Check the [Installation Guide]({{ site.baseurl }}/installation/) for setup instructions
2. Review the [Troubleshooting]({{ site.baseurl }}/wiki/troubleshooting/) section
3. Search [existing issues](https://github.com/idossha/TI-Toolbox/issues)
4. Ask in [GitHub Discussions](https://github.com/idossha/TI-Toolbox/discussions)
