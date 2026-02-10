# Container Blueprints

Always build images from within the `blueprint` directory.

## Docker

```bash
docker build -f <file> -t <image_name> .
```

Where `<file>` is `Dockerfile.simnibs`, `Dockerfile.freesurfer`, etc. and `<image_name>` is `idossha/simnibs:vX.X.X` or `idossha/freesurfer:vX.X.X`.

Use `--no-cache` to ensure no previous build layers are reused:

```bash
docker build --no-cache -f Dockerfile.simnibs -t idossha/simnibs:vX.X.X .
```

Then push:

```bash
docker push <image_name>
```

On ARM processors (Apple Silicon), add `--platform linux/amd64`:

```bash
docker build --no-cache --platform linux/amd64 \
  -f Dockerfile.simnibs \
  -t idossha/simnibs:vX.X.X .
```

---

## Apptainer (HPC)

The `apptainer.def` file builds a combined image with SimNIBS 4.5 + FreeSurfer 7.4.1 + TI-Toolbox for HPC clusters.

### Build from definition file

```bash
apptainer build ti-toolbox.sif apptainer.def
```

This requires `fakeroot` capability or root access. Build time is ~30-60 minutes. The resulting `.sif` file is ~8-12 GB.

Set a custom temp directory if `/tmp` is too small:

```bash
export APPTAINER_TMPDIR=/scratch/tmp
apptainer build ti-toolbox.sif apptainer.def
```

### Convert from Docker Hub

```bash
apptainer build ti-toolbox.sif docker://idossha/simnibs:v2.2.4
```

### Run with the wrapper script

```bash
./apptainer_run.sh --sif ti-toolbox.sif --project-dir /data/my_study
./apptainer_run.sh --sif ti-toolbox.sif --mode slurm-template > submit.sh
```

See `./apptainer_run.sh --help` for all options.

Full documentation: [HPC Deployment Guide](../../docs/wiki/installation/hpc-apptainer.md)
