---
layout: wiki
title: Pre-processing
permalink: /wiki/pre-processing/
---

Pre-processing prepares subject data for simulation and analysis. Select subjects and the stages
you need; the plan shows their dependencies and existing outputs before you run them.

<div class="split split--wide">
<div>
<img src="{{ site.baseurl }}/assets/imgs/v3/preprocessing-page.png" alt="The Pre-processing page: a subject table showing which outputs each subject has, then the structural and DWI stages to run">
</div>
<div>
<div class="flow" role="group" aria-label="Pre-processing stages and what each produces">
<figure class="flow-node"><img src="{{ site.baseurl }}/assets/imgs/v3/preprocess-workflow/nifti.webp" alt="Sagittal slice of the converted T1-weighted NIfTI" width="96" height="96" loading="lazy"><figcaption>DICOM conversion or existing NIfTI</figcaption></figure>
<span class="flow-arrow" aria-hidden="true">&darr;</span>
<div class="flow-branch">
<div class="flow-lane"><figure class="flow-node"><img src="{{ site.baseurl }}/assets/imgs/v3/preprocess-workflow/charm.webp" alt="CHARM head mesh with translucent scalp and skull" width="96" height="96" loading="lazy"><figcaption>SimNIBS CHARM</figcaption></figure><span class="flow-arrow" aria-hidden="true">&darr;</span><figure class="flow-node"><img src="{{ site.baseurl }}/assets/imgs/v3/preprocess-workflow/atlas.webp" alt="Subject atlas outlined on an axial T1 slice" width="96" height="96" loading="lazy"><figcaption>Subject atlas and tissue analysis</figcaption></figure></div>
<div class="flow-lane"><figure class="flow-node"><img src="{{ site.baseurl }}/assets/imgs/v3/preprocess-workflow/fastsurfer.webp" alt="FastSurfer DKT parcellation over a coronal T1 slice" width="96" height="96" loading="lazy"><figcaption>FastSurfer / FreeSurfer</figcaption></figure></div>
<div class="flow-lane"><figure class="flow-node"><img src="{{ site.baseurl }}/assets/imgs/v3/preprocess-workflow/qsiprep.webp" alt="QSIPrep preprocessed DWI reference (b0) slice" width="96" height="96" loading="lazy"><figcaption>QSIPrep</figcaption></figure><span class="flow-arrow" aria-hidden="true">&darr;</span><figure class="flow-node"><img src="{{ site.baseurl }}/assets/imgs/v3/preprocess-workflow/dti.webp" alt="Fractional anisotropy of the DTI tensor in T1 space" width="96" height="96" loading="lazy"><figcaption>DTI tensor<small>also uses the CHARM head model</small></figcaption></figure><span class="flow-arrow flow-arrow--opt" aria-hidden="true">&darr;</span><figure class="flow-node"><img src="{{ site.baseurl }}/assets/imgs/v3/preprocess-workflow/qsirecon.webp" alt="QSIRecon generalized FA map" width="96" height="96" loading="lazy"><figcaption>QSIRecon, optional<small>from QSIPrep</small></figcaption></figure></div>
</div>
</div>
</div>
</div>

CHARM creates the head model required for simulations. Reconstruction, segmentation and diffusion
processing are optional, depending on the outputs your workflow needs. Independent stages can
run when their dependencies and the job scheduler's resource budget allow.

## Required Input Data Structure

### BIDS Format Requirements

The toolbox expects data to be organized following the BIDS (Brain Imaging Data Structure) standard:

```
project_root/
└── sourcedata/
    └── sub-{subject_id}/
        ├── T1w/
        │   ├── dicom/          # Raw T1w .dcm/.dicom files (searched recursively)
        │   └── *.zip|*.tar|*.tar.gz|*.tgz  # Optional T1w DICOM archives (extracted to extracted_archives/)
        ├── T2w/                # Optional, same layout
        ├── ct/                 # Optional CT (→ anat/sub-{id}_ct.nii.gz, a local non-BIDS extension)
        ├── dwi/                # Optional diffusion DICOMs (→ dwi/sub-{id}_dwi.nii.gz + .bval/.bvec/.json)
        └── fmap/               # Optional short reverse phase-encoding scan for the DWI, e.g. PA
                                #   (→ fmap/sub-{id}_dir-PA_epi.nii.gz + .json, + .bval/.bvec if written)
```

Each modality folder is searched recursively, so DICOM files placed directly in `T1w/` also work; the `dicom/` subfolder is the recommended layout. Converted files are named `sub-{id}_T1w.nii.gz`, `sub-{id}_T2w.nii.gz`, etc., and land in the project's `sub-{id}/anat/`, `dwi/` and `fmap/` folders (outside `sourcedata/`).

**Diffusion with a reverse phase-encoding scan.** Put the main DWI series (e.g. AP) in `dwi/dicom/` and the short reverse phase-encoding scan (b=0 volumes, or a few b=0 and b>0 volumes; e.g. PA) in `fmap/dicom/`. Conversion writes it as the BIDS "pepolar" fieldmap `fmap/sub-{id}_dir-PA_epi.nii.gz` that [QSIPrep documents](https://qsiprep.readthedocs.io/en/latest/usage.html#siemens-reverse-phase-encoded-field-maps) for this case, with its JSON sidecar and an `IntendedFor` naming the DWI (`"dwi/sub-{id}_dwi.nii.gz"`, relative to the subject folder, because QSIPrep does not read BIDS URIs there). The `dir-` label is the direction the phase encoding travels in the image (`AP`, `PA`, `LR`, `RL`, `SI` or `IS`), worked out from the sidecar's `PhaseEncodingDirection` and the image orientation; if either is missing, the file is left unnamed and the log says what to add. A fieldmap series that holds both polarities, such as GE's `epi_pepolar` sequence, is split by dcm2niix and each half is named by its own direction (`dir-AP` and `dir-PA`).

If instead you acquired the full diffusion series twice with opposite phase encoding, put both in `dwi/dicom/`: they are written as `dwi/sub-{id}_dir-AP_dwi.nii.gz` and `dwi/sub-{id}_dir-PA_dwi.nii.gz`, which QSIPrep pairs for TOPUP. A short reverse phase-encoding scan does not belong in `dwi/`: QSIPrep would preprocess it as a diffusion run and combine it with the main one.

### Supported Input Formats

A T1-weighted scan (typically MPRAGE) is required; a T2-weighted scan (typically CUBE/SPACE) is recommended.

- **DICOM files** (`.dcm`, `.dicom`) under `sourcedata/sub-{subject_id}/{T1w,T2w}/dicom/`; nested folders are searched recursively
- **Compressed DICOM archives** (`.zip`, `.tar`, `.tar.gz`, `.tgz`) placed directly in a modality folder or its `dicom/` folder
- **NIfTI files** (`.nii`, `.nii.gz`) - if already converted

DICOMs are recognised only by a `.dcm` or `.dicom` extension. An extensionless export, including
one inside an archive, is skipped and the log says "No DICOM (.dcm/.dicom) or NIfTI … files found";
add the extension first.

**Starting from a NIfTI you already have.** Either put it in `sourcedata/sub-{id}/T1w/`, where
conversion copies it (and gzips a `.nii`) to `sub-{id}/anat/sub-{id}_T1w.nii.gz`, or place
`sub-{id}_T1w.nii[.gz]` directly in `sub-{id}/anat/` to skip conversion. If a modality folder holds
both DICOMs and a NIfTI, the DICOMs are converted and the NIfTI is ignored.

**How a subject appears.** There is no "Add subject" button. Create `sourcedata/sub-{id}/T1w/dicom/`
(or put a NIfTI in `T1w/`) and the subject shows up in the table as *not converted*.

## Head models and atlas alignment

CHARM accepts T1w alone or T1w with T2w. The pipeline runs `subject_atlas` after CHARM to generate
atlas annotations. Head models are stored in `derivatives/SimNIBS/sub-<id>/m2m_<id>/`.

MNI/template and volume-atlas targets depend on the head model's transforms and registration
quality. If CHARM reports cropped anatomy or poor registration, inspect the input coverage before
using those targets. CHARM supplies whole-thalamus, whole-hippocampus and whole-amygdala labels;
the surfer guide explains the separate reconstruction and finer subregion options.

## Run and monitor

Review the plan, then start the selected stages. When outputs already exist, choose whether to
skip them or replace and rerun. Use [Jobs]({{ site.baseurl }}/wiki/jobs/) for live progress, logs,
cancellation and failures; the Overview shows which outputs are present for each subject.

For programmatic execution, use the [scripting guide]({{ site.baseurl }}/wiki/notebooks/#example-workflow).
Tool-specific inputs and output layouts live in the two subguides above.

## Pre-processing settings

Open **Settings ▸ Pre-processing** for user-wide defaults. Changes apply to new jobs across
projects, not work already running. Edits to the thread, memory, FreeSurfer and CHARM controls are
a draft until you press **Save pre-processing preferences**. Automatic thread allocation follows
the CPU limit set under **Settings ▸ Project ▸ Execution** (70 % of the effective CPUs by default,
and at least one). Each control shows the available capacity; container limits and the job
scheduler still constrain execution.

<div class="split split--wide">
<div>
<img src="{{ site.baseurl }}/assets/imgs/v3/settings-preprocessing.png" alt="Settings, Pre-processing tab: FastSurfer, FreeSurfer, SimNIBS CHARM and QSIPrep sections with thread controls">
<em>Settings &#9656; Pre-processing. Each tool has its own thread controls; leave them on Auto to follow the CPU limit.</em>
</div>
<div markdown="1">

- **FastSurfer / FreeSurfer:** thread controls, Apple GPU enablement and FreeSurfer operations.
  TI-Toolbox supplies the FreeSurfer license automatically; no personal license setup is required.
  See the [surfer guide]({{ site.baseurl }}/wiki/fastsurfer/) for setup and permissions.
- **QSIPrep / QSIRecon:** CPU threads, OpenMP threads and memory limits. **Configure QSIPrep**
  and **Configure QSIRecon** open the same saved processing choices as the run page; saving either
  dialog remembers them across projects. The QSIPrep defaults (native resolution, automatic
  unringing, mandatory distortion correction, no MNI normalization) suit most data; see the
  [diffusion guide]({{ site.baseurl }}/wiki/diffusion-processing/) for what each choice does.
- **SimNIBS CHARM:** threads and an Advanced section for anatomical denoising, final segmentation
  resolution and scalp triangle size. Default values follow the installed settings. Scalp triangle
  size controls the scalp surface, not every volume element. Resolution changes affect the head
  model and computation time; configure them before generating a new model.

</div>
</div>

See the [CHARM configuration reference](https://simnibs.github.io/simnibs/build/html/documentation/command_line/charm.html)
for the upstream options.
