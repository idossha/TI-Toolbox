---
layout: installation
title: HPC Deployment (Apptainer/Singularity)
permalink: /installation/hpc-apptainer/
---

**This feature is still in testing period**.

Deploy TI-Toolbox on HPC clusters using Apptainer. Unlike Docker images, the `.sif` must be built from the definition file.

## Prerequisites

| Requirement | Details |
|-------------|---------|
| **Apptainer** | Version 1.1+ (or Singularity 3.8+) |
| **FreeSurfer License** | Free from [surfer.nmr.mgh.harvard.edu/registration.html](https://surfer.nmr.mgh.harvard.edu/registration.html) |

## Quick Start

### 1. Download Files

```bash
# Get the definition and launcher
curl -O https://raw.githubusercontent.com/idossha/TI-toolbox/main/container/blueprint/apptainer.def
curl -O https://raw.githubusercontent.com/idossha/TI-toolbox/main/container/blueprint/apptainer_run.sh
chmod +x apptainer_run.sh
```

### 2. Build the Image

```bash
# Build takes 30-60 minutes, produces ~8-12 GB SIF
apptainer build ti-toolbox.sif apptainer.def
```

If your cluster lacks `fakeroot`, build on a machine with root and transfer the `.sif`.

### 3. Set Up FreeSurfer License

```bash
mkdir -p ~/.freesurfer
cp /path/to/license.txt ~/.freesurfer/license.txt
```

### 4. Run

```bash
# Interactive session
./apptainer_run.sh --sif ti-toolbox.sif --project-dir /scratch/my_study

# Execute command
./apptainer_run.sh --sif ti-toolbox.sif --project-dir /scratch/my_study \
    --mode exec --cmd "simnibs_python -m tit.cli.simulator --help"

# Generate SLURM template
./apptainer_run.sh --sif ti-toolbox.sif --project-dir /scratch/my_study \
    --mode slurm-template > submit.sh
```

## SLURM Batch Job

```bash
#!/bin/bash
#SBATCH --job-name=ti-sim
#SBATCH --output=ti-sim_%j.out
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=04:00:00

module load apptainer

SIF="/path/to/ti-toolbox.sif"
PROJECT="/scratch/my_study"
FS_LICENSE="$HOME/.freesurfer/license.txt"

apptainer exec \
    --bind "${PROJECT}:/mnt/my_study" \
    --bind "${FS_LICENSE}:/usr/local/freesurfer/license.txt:ro" \
    "${SIF}" \
    simnibs_python -m tit.cli.simulator \
        --project /mnt/my_study \
        --subject sub-001
```


## Direct Apptainer Commands

Without the wrapper script:

```bash
# Interactive
apptainer run \
    --bind /scratch/my_study:/mnt/my_study \
    --bind ~/.freesurfer/license.txt:/usr/local/freesurfer/license.txt:ro \
    ti-toolbox.sif

# Command execution
apptainer exec \
    --bind /scratch/my_study:/mnt/my_study \
    --bind ~/.freesurfer/license.txt:/usr/local/freesurfer/license.txt:ro \
    ti-toolbox.sif \
    simnibs_python -m tit.cli.simulator --project /mnt/my_study --subject sub-001
```

## CLI Aliases Inside Container

Interactive sessions have these aliases pre-defined:

| Alias | Command |
|-------|---------|
| `analyzer` | `simnibs_python -m tit.cli.analyzer` |
| `simulator` | `simnibs_python -m tit.cli.simulator` |
| `ex_search` | `simnibs_python -m tit.cli.ex_search` |
| `flex_search` | `simnibs_python -m tit.cli.flex_search` |
| `pre_process` | `simnibs_python -m tit.cli.pre_process` |
| `group_analyzer` | `simnibs_python -m tit.cli.group_analyzer` |
| `GUI` | `simnibs_python -m tit.cli.gui` |

## GPU Support

Add `--gpus` flag to the launcher or `--nv` to direct commands:

```bash
./apptainer_run.sh --sif ti-toolbox.sif --project-dir /data/study --gpus
```

## Troubleshooting

### FreeSurfer license not found

Verify license is accessible from compute nodes:
```bash
srun --ntasks=1 cat ~/.freesurfer/license.txt
```

## Diffusion Processing

For QSIPrep/QSIRecon (not included in TI-Toolbox image):

```bash
apptainer build qsiprep.sif docker://pennbbl/qsiprep:latest
apptainer run --bind /data:/data qsiprep.sif /data/input /data/output participant
```
