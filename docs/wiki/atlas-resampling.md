---
layout: wiki
title: Atlas Resampling in Cortical Region Analysis
permalink: /wiki/atlas-resampling/
---

## Overview

When analyzing field data within cortical regions, the toolbox requires that the atlas and field files have matching dimensions and spatial orientation. This document explains how the toolbox handles dimension mismatches and the resampling process.

## Visual Example

Below are two images showing the effect of atlas resampling:

| Original Atlas (Not Aligned) | Resampled Atlas (Aligned) |
|-----------------------------|---------------------------|
| ![Original Atlas]({{ site.baseurl }}/wiki/assets/atlas_resample/atlas_under_field.png) | ![Resampled Atlas]({{ site.baseurl }}/wiki/assets/atlas_resample/aligned_atlas_under_field.png) |

**Left:** The blue outline shows the original atlas, which does not perfectly align with the heat map of the cortical region (field data).

**Right:** The blue outline shows the resampled (aligned) atlas, which now matches the field data.

**Explanation:**  
In the left image, the blue atlas outline does not match the underlying heat map, indicating a dimension or alignment mismatch. In the right image, after resampling, the blue outline of the atlas is perfectly aligned with the heat map, ensuring accurate region analysis.

## Automatic Resampling Process

When a dimension mismatch is detected between your atlas and field data, the toolbox automatically:

1. Detects the mismatch by comparing spatial dimensions
2. Creates a resampled version of your atlas using FreeSurfer's `mri_convert`
3. Saves the resampled atlas for future use
4. Proceeds with analysis using the resampled atlas

### Example Log Output

```
[2025-06-05 23:10:26] [analyzer.mesh_analyzer] [INFO] Atlas and field dimensions don't match, attempting to resample...
[2025-06-05 23:10:26] [analyzer.mesh_analyzer] [DEBUG] Atlas shape: (256, 256, 256)
[2025-06-05 23:10:26] [analyzer.mesh_analyzer] [DEBUG] Field shape: (512, 512, 512)
[2025-06-05 23:10:26] [analyzer.mesh_analyzer] [INFO] Running: mri_convert --reslice_like template.nii.gz atlas.mgz resampled_atlas.nii.gz
```

## Resampled Atlas Storage

The resampled atlas is stored with a filename that includes the target dimensions:

```
{original_atlas_name}_resampled_{width}x{height}x{depth}.{extension}
```

For example:
```
subject_dk40_resampled_512x512x512.nii.gz
```

This naming convention allows the toolbox to:
- Quickly identify existing resampled versions
- Avoid unnecessary re-resampling
- Maintain consistency across multiple analyses

## Supported Atlas Formats

The toolbox supports various atlas formats:
- `.nii` or `.nii.gz` (NIfTI format)
- `.mgz` (FreeSurfer format)

For `.mgz` files, the toolbox automatically converts them to NIfTI format during the resampling process.

## Common Scenarios

### 1. Different Resolution Field Data

If your field data has a different resolution than your atlas:
```
Field data: 512x512x512 voxels
Atlas: 256x256x256 voxels
```
The toolbox will automatically resample the atlas to match the field data's resolution.

### 2. Different Field of View

If your field data covers a different spatial extent:
```
Field data: 240x240x180 mm
Atlas: 256x256x256 mm
```
The resampling process will adjust the atlas to match the field data's spatial coverage.

## Best Practices

1. **Use Subject-Specific Atlases**: Generate atlases using the same preprocessing pipeline as your field data
2. **Check Dimensions**: Verify atlas and field dimensions before analysis
3. **Monitor Logs**: Watch for resampling messages in the log files
4. **Preserve Originals**: Keep your original atlas files; resampled versions are automatically managed

## Technical Details

The resampling process uses FreeSurfer's `mri_convert` with the following steps:

1. Creates a template image with target dimensions
2. Uses `--reslice_like` to resample the atlas
3. Preserves the anatomical validity of the atlas
4. Maintains the original atlas's region labels

## Troubleshooting

If you encounter issues with resampling:

1. Check the log files for detailed error messages
2. Verify that FreeSurfer is properly installed
3. Ensure both atlas and field files are readable

## See Also

- [Logging Documentation]({{ site.baseurl }}/wiki/logging/) - Learn how to monitor the resampling process
- [Installation Guide]({{ site.baseurl }}/installation/) - Ensure FreeSurfer is properly installed
- Return to [Wiki]({{ site.baseurl }}/wiki/)
