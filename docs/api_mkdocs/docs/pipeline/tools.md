# Utility Tools

The `tit.tools` module provides standalone utilities for mesh and field manipulation, format conversion, electrode mapping, and visualization. These tools are typically called from scripts, the CLI, or other pipeline stages rather than forming a pipeline of their own.

## Mesh / NIfTI Conversion

### Mesh to NIfTI

Convert SimNIBS `.msh` mesh files to NIfTI volumes in subject or MNI space:

```python
from tit.tools.mesh2nii import msh_to_nifti, msh_to_mni, convert_mesh_dir

# Single mesh to subject-space NIfTI
msh_to_nifti(
    mesh_path="TI_max.msh",
    m2m_dir="/data/project/derivatives/SimNIBS/sub-001/m2m_001",
    output_path="/data/output/TI_max_subject",
    fields=["TI_max"],  # optional: convert only specific fields
)

# Single mesh to MNI-space NIfTI
msh_to_mni(
    mesh_path="TI_max.msh",
    m2m_dir="/data/project/derivatives/SimNIBS/sub-001/m2m_001",
    output_path="/data/output/TI_max_MNI",
)

# Batch-convert all meshes in a directory (both subject and MNI space)
convert_mesh_dir(
    mesh_dir="/data/project/derivatives/SimNIBS/sub-001/Simulations/motor/TI/mesh",
    output_dir="/data/output/niftis",
    m2m_dir="/data/project/derivatives/SimNIBS/sub-001/m2m_001",
    fields=["TI_max"],
    skip_patterns=["normal"],  # skip surface-only meshes (default)
)
```

### NIfTI to Mesh

Convert a NIfTI segmentation or mask to a surface mesh (`.stl` or `.msh`) using marching cubes:

```python
from tit.tools.nifti_to_mesh import nifti_to_mesh

result = nifti_to_mesh(
    input_file="segmentation.nii.gz",
    output_file="thalamus.stl",       # .stl or .msh; defaults to .stl
    clean_components=True,             # remove small disconnected pieces
    clean_threshold=0.1,              # keep components >= 10% of largest
)

print(result)
# {'vertices': 12345, 'faces': 24680, 'output_file': 'thalamus.stl', 'removed_components': 3}
```

### Field Extraction

Extract grey-matter and white-matter sub-meshes from a full SimNIBS head mesh:

```python
from tit.tools.field_extract import main as extract_fields

extract_fields(
    input_file="/data/sims/TI_max.msh",
    project_dir="/data/my_project",
    subject_id="001",
    # gm_output_file and wm_output_file default to BIDS-compliant paths
)
```

## Visualization

### Montage Visualizer

Render a PNG showing electrode positions and connection arcs on the EEG cap template:

```python
from tit.tools.montage_visualizer import visualize_montage

visualize_montage(
    montage_name="motor_cortex",
    electrode_pairs=[["E030", "E020"], ["E095", "E070"]],
    eeg_net="GSN-HydroCel-185.csv",
    output_dir="/data/output/montage_imgs",
    sim_mode="U",  # "U" = one image per montage, "M" = combined image
)
```

### Gmsh Option Files

Generate `.opt` files for Gmsh visualization of mesh fields:

```python
from tit.tools.gmsh_opt import create_mesh_opt_file

opt_path = create_mesh_opt_file(
    mesh_path="/data/sims/TI_max.msh",
    field_info={
        "fields": ["TI_max", "magnE"],
        "max_values": {"TI_max": 0.25, "magnE": 0.5},
    },
)
# writes /data/sims/TI_max.msh.opt
```

## Atlas and Labels

### Label Extraction

Extract specific label values from a NIfTI segmentation file:

```python
from tit.tools.extract_labels import extract_labels

output = extract_labels(
    input_file="atlas_parcellation.nii.gz",
    labels=[10, 11, 12],              # label integers to keep
    output_file="extracted.nii.gz",   # optional; defaults to *_extracted suffix
)
```

### FreeSurfer Annotation Reading

Read and inspect FreeSurfer `.annot` annotation files:

```python
from tit.tools.read_annot import read_annot_file

# Print all regions and optionally look up a specific vertex
read_annot_file(
    annot_path="/data/freesurfer/sub-001/label/lh.aparc.annot",
    vertex_id=1024,  # optional
)
```

## Electrode Mapping

Map optimized electrode positions to the nearest positions in a physical EEG net using the Hungarian algorithm:

```python
from tit.tools.map_electrodes import (
    read_csv_positions,
    load_electrode_positions_json,
    map_electrodes_to_net,
    save_mapping_result,
    log_mapping_summary,
)

# Load net positions from SimNIBS CSV
net_positions, net_labels = read_csv_positions("GSN-HydroCel-256.csv")

# Load optimized positions from flex-search output
opt_positions, channel_indices = load_electrode_positions_json(
    "electrode_positions.json"
)

# Compute optimal assignment
mapping = map_electrodes_to_net(
    opt_positions, net_positions, net_labels, channel_indices
)

# Save and log
save_mapping_result(mapping, "mapping_result.json", eeg_net_name="GSN-HydroCel-256")
log_mapping_summary(mapping)
```

## Other Utilities

### Version Checking

Check GitHub for newer TI-Toolbox releases:

```python
from tit.tools.check_for_update import check_for_new_version

newer = check_for_new_version(
    current_version="2.2.0",
    repo="idossha/TI-Toolbox",  # default
    timeout=2.0,                # seconds, default
)
if newer:
    print(f"New version available: {newer}")
```

## API Reference

### Mesh to NIfTI

::: tit.tools.mesh2nii.msh_to_nifti
    options:
      show_root_heading: true

::: tit.tools.mesh2nii.msh_to_mni
    options:
      show_root_heading: true

::: tit.tools.mesh2nii.convert_mesh_dir
    options:
      show_root_heading: true

### NIfTI to Mesh

::: tit.tools.nifti_to_mesh.nifti_to_mesh
    options:
      show_root_heading: true

::: tit.tools.nifti_to_mesh.remove_small_components
    options:
      show_root_heading: true

::: tit.tools.nifti_to_mesh.save_stl
    options:
      show_root_heading: true

::: tit.tools.nifti_to_mesh.save_gmsh
    options:
      show_root_heading: true

### Field Extraction

::: tit.tools.field_extract.main
    options:
      show_root_heading: true

### Montage Visualizer

::: tit.tools.montage_visualizer.visualize_montage
    options:
      show_root_heading: true

### Gmsh Options

::: tit.tools.gmsh_opt.create_mesh_opt_file
    options:
      show_root_heading: true

### Label Extraction

::: tit.tools.extract_labels.extract_labels
    options:
      show_root_heading: true

### FreeSurfer Annotations

::: tit.tools.read_annot.read_annot_file
    options:
      show_root_heading: true

### Electrode Mapping

::: tit.tools.map_electrodes.read_csv_positions
    options:
      show_root_heading: true

::: tit.tools.map_electrodes.load_electrode_positions_json
    options:
      show_root_heading: true

::: tit.tools.map_electrodes.map_electrodes_to_net
    options:
      show_root_heading: true

::: tit.tools.map_electrodes.save_mapping_result
    options:
      show_root_heading: true

::: tit.tools.map_electrodes.log_mapping_summary
    options:
      show_root_heading: true

### Version Checking

::: tit.tools.check_for_update.check_for_new_version
    options:
      show_root_heading: true

::: tit.tools.check_for_update.parse_version
    options:
      show_root_heading: true
