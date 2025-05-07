# ROI/non-ROI Parameter Options for TesFlexOptimization

This section summarizes the main options for defining ROIs (Regions of Interest) and non-ROIs in SimNIBS `TesFlexOptimization` workflows.

---

## 1. `method` (How the ROI is defined)
- `"surface"`: Use a surface mesh (e.g., cortex/GM surface)
- `"volume"`: Use a volume mesh (e.g., brain volume)
- `"custom"`: Provide a custom list of node coordinates
- `"manual"`: Manual setup (rarely used)
- `"volume_from_surface"`: Define a volume ROI based on distance from a surface ROI
- `"mesh+mask"`: Use a boolean mask on mesh nodes or elements

---

## 2. `surface_type` (For surface ROIs)
- `"central"`: Central cortical surface (default)
- `"custom"`: User-provided surface

---

## 3. `roi_sphere_operator` / `mask_operator` (How to combine regions/masks)
- `"union"`: Add/combine regions (default)
- `"intersection"`: Use only the overlapping region
- `"difference"`: Subtract the mask/sphere from the current ROI

You can use a single string or a list of these if you have multiple spheres/masks.

---

## 4. Other Useful Parameters
- **`roi_sphere_center` / `roi_sphere_radius`**: Center and radius for spherical ROIs
- **`mask_space`**: Space for mask (e.g., `"subject"`, `"mni"`, `"subject_lh"`)
- **`mask_path`**: Path to mask file (e.g., atlas, annotation, NIfTI)
- **`mask_value`**: Value(s) in mask file to use
- **`tissues`**: For volume ROIs, which tissue types to include

---

## Example Usage
```python
roi.method = "surface"
roi.surface_type = "central"
roi.roi_sphere_center = [x, y, z]
roi.roi_sphere_radius = r
roi.roi_sphere_operator = ["difference"]  # or "union", "intersection"
```

---

**Summary:**
- Choose `method` to define how your ROI/non-ROI is created.
- Use `surface_type` for surface ROIs.
- Use `roi_sphere_operator`/`mask_operator` to combine regions as needed (`"union"`, `"intersection"`, `"difference"`).
