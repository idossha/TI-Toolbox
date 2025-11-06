---
layout: wiki
title: 3D Visual Exporter
permalink: /wiki/visual-exporter/
---

The 3D Visual Exporter extension was built to enable better visualization and presentation of simulation results using other 3D modeling software. It bundles the mesh export scripts that ship with TI-Toolbox and provides a single interface for exporting cortical surfaces and field vectors in formats compatible with Blender, CAD software, and other 3D visualization tools. Use it when you want a guided workflow from the GUI, or call the underlying Python scripts directly for batch jobs and automation.

## Overview

- **Location**: `ti-toolbox/gui/extensions/visual_exporter.py`
- **Purpose**: Export 3D assets in formats compatible with Blender, CAD software, and other 3D modeling tools to enable better visualization and presentation of simulation results.
- **Back-end scripts**:
  - `3d_exporter/cortical_regions_to_ply.py`
  - `3d_exporter/cortical_regions_to_stl.py`
  - `3d_exporter/vector_ply.py`
- **Outputs**: PLY surface meshes, STL geometry, and PLY vector clouds stored under the TI-Toolbox derivatives tree.

## Supported Modes

### Cortical Regions

This mode exports cortical surface regions defined by anatomical atlases as 3D mesh files. The exporter uses the central cortical surface mesh generated from your simulation and segments it according to the selected atlas labels.

<div class="carousel-container">
  <div class="carousel-wrapper">
    <div class="carousel-images">
      <div class="carousel-slide active">
        <img src="{{ site.baseurl }}/assets/imgs/wiki_visual_exporter_stl_sample.png" alt="STL Export Sample">
        <p>STL format export showing cortical surface geometry</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/wiki_visual_exporter_ply_sample.png" alt="PLY Export Sample">
        <p>PLY format export with color-mapped field data</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/wiki_visual_exporter_ply_sample_2.png" alt="PLY Export Sample 2">
        <p>PLY format export showing detailed cortical regions</p>
      </div>
    </div>
    <button class="carousel-btn prev" onclick="changeSlide(this, -1)">&#10094;</button>
    <button class="carousel-btn next" onclick="changeSlide(this, 1)">&#10095;</button>
    <div class="carousel-dots">
      <span class="dot active" onclick="currentSlide(this, 0)"></span>
      <span class="dot" onclick="currentSlide(this, 1)"></span>
      <span class="dot" onclick="currentSlide(this, 2)"></span>
    </div>
  </div>
</div>

**What is produced:**
- **STL files**: Binary STL format containing only geometry (no color information). These are lightweight files suitable for CAD software, 3D printing, or any workflow that doesn't require color mapping.
- **PLY files**: PLY format with embedded color information. Each region is color-mapped according to the field values (e.g., `TI_max`) from the simulation mesh. These files preserve both geometry and field data for visualization in Blender or other 3D tools.

**Atlas options:**
- Choose from available atlases (DK40, DKTatlas40, HCP_MMP1, aparc.a2009s) based on your analysis needs.
- Select individual cortical regions to export, or export the entire atlas.
- Optionally include the whole gray matter (GM) surface as a single mesh file.

**Output structure:**
- Individual region meshes are stored in `regions/` subdirectories.
- Whole GM surface is exported as a separate file when enabled.
- Optionally keep intermediate `.msh` files for audit trails and debugging.

### Field Vectors

This mode exports electric field vectors from TDCS simulations as arrow clouds in PLY format. The vectors represent the electric field direction and magnitude at sampled points in the brain.

<div class="carousel-container">
  <div class="carousel-wrapper">
    <div class="carousel-images">
      <div class="carousel-slide active">
        <img src="{{ site.baseurl }}/assets/imgs/wiki_visual_exporter_vectors.png" alt="Vector Field Visualization">
        <p>TI vector field visualization showing electric field directions and magnitudes</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/wiki_visual_exporter_vectors_close.png" alt="Close-up Vector Field Visualization">
        <p>Close-up view of the vector field, highlighting individual arrow placement and detail</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/wiki_visual_exporter_rgb_vectors.png" alt="RGB Vector Visualization">
        <p>RGB color-coded vectors showing CH1 (red), CH2 (blue), TI (green), TI_sum (yellow), and TI_normal (cyan) fields</p>
      </div>
    </div>
    <button class="carousel-btn prev" onclick="changeSlide(this, -1)">&#10094;</button>
    <button class="carousel-btn next" onclick="changeSlide(this, 1)">&#10095;</button>
    <div class="carousel-dots">
      <span class="dot active" onclick="currentSlide(this, 0)"></span>
      <span class="dot" onclick="currentSlide(this, 1)"></span>
      <span class="dot" onclick="currentSlide(this, 2)"></span>
    </div>
  </div>
</div>

**What is produced:**
- **CH1 (Channel 1)**: Vector field from the first TDCS electrode configuration. Represents the electric field distribution (E1) when current flows through channel 1. **Color**: Red (RGB: 255, 0, 0) in RGB mode.
- **CH2 (Channel 2)**: Vector field from the second TDCS electrode configuration. Represents the electric field distribution (E2) when current flows through channel 2. **Color**: Blue (RGB: 0, 0, 255) in RGB mode.
- **TI (Temporal Interference)**: Modulation amplitude vectors representing the temporal interference pattern when two electric fields with slightly different frequencies interfere. The TI vector indicates both the spatial direction of maximum envelope modulation and the magnitude of maximum envelope amplitude (2 × effective amplitude). Calculated using the Grossman et al. 2017 algorithm, which computes the modulation amplitude when two sinusoidal fields E1(t) and E2(t) create a beating pattern. **Color**: Green (RGB: 0, 255, 0) in RGB mode.
- **TI_sum**: Optional output representing the vector addition of CH1 and CH2 (E1 + E2). This is the direct vector sum of the two electric field vectors, useful for visualizing the combined field distribution. **Color**: Yellow (RGB: 255, 255, 0) in RGB mode.
- **TI_normal**: Optional output representing the component of the TI vector normal to the cortical surface. This is particularly useful for understanding stimulation perpendicular to the cortex, as it isolates the component of the modulation amplitude that is orthogonal to the gray matter surface. **Color**: Cyan (RGB: 0, 255, 255) in RGB mode.

**Vector properties:**
- Each arrow's direction represents the electric field direction at that point.
- Arrow length is scaled by the field magnitude (configurable via length scale parameter).
- Colors can be mapped using RGB mode (fixed colors per vector type: CH1=red, CH2=blue, TI=green, TI_sum=yellow, TI_normal=cyan) or magnitude-based scaling (magscale) to visualize field intensity across a blue-green-red gradient.
- Vector width and anchor point (tail or head) are customizable for visualization clarity.

**TI vs mTI modes:**
- **TI mode**: Uses 2 TDCS meshes (CH1 and CH2) to compute standard TI vectors.
- **mTI mode**: Uses 4 TDCS meshes (CH1, CH2, CH3, CH4) to compute multi-channel TI vectors, enabling more complex stimulation patterns.

**Sampling options:**
- Configure the number of vectors to sample (default: 100,000) or use all nodes for maximum detail.
- When using the maximum sample count, the script will produce a vector on every node of the given surface mesh. This is an expensive process that requires a large amount of memory and can take multiple hours for all vectors to be produced.
- Random seed controls reproducibility of sampling patterns.
- Vectors can be filtered to show only top percentile regions by magnitude.

## Running from the GUI

1. Launch TI-Toolbox and click the **Extensions** button in the top-right corner of the window.
2. Select **3D Visual Exporter** and click **Launch**.
3. Pick a subject and simulation from the dropdowns. The extension queries the Path Manager for available outputs.
4. Choose **Cortical Regions** or **Field Vectors** mode.
5. Configure atlas, region filters, formats, and output directory options (for regions) or sampling and styling parameters (for vectors).
6. Click **Run Export**. The console panel shows the exact commands executed and live progress.
7. Review artifacts in `derivatives/ti-toolbox/visual_exports/sub-<id>/<simulation>/` once the export completes.

The **Stop** button terminates the active subprocess if you need to cancel a long export.

## Running the scripts individually

You can call the Python scripts directly whenever you need command-line automation or custom batching. From within the TI-Toolbox environment, run:

```bash
# Export atlas-aligned cortical regions to PLY
simnibs_python 3d_exporter/cortical_regions_to_ply.py \
  --mesh <path/to/central.msh> \
  --m2m <path/to/m2m_subject> \
  --output-dir <output_folder>

# Export region geometry to STL
simnibs_python 3d_exporter/cortical_regions_to_stl.py \
  --mesh <path/to/central.msh> \
  --m2m <path/to/m2m_subject> \
  --output-dir <output_folder>

# Export TI or mTI vector arrows
simnibs_python 3d_exporter/vector_ply.py \
  tdcs1.msh tdcs2.msh <output_prefix> --sum --ti-normal
```

Refer to the README files in `ti-toolbox/3d_exporter/` for full command-line options, including support for `--gm-mesh`, `--regions`, `--field-range`, vector sampling, and mTI mode.

## Output structure

Exports triggered from the extension (or using the same base output directory) follow this structure:

```
derivatives/
  ti-toolbox/
    visual_exports/
      sub-<subject>/
        <simulation>/
          stl/                 # Cortical STL exports
          ply/                 # Cortical PLY exports
          vectors/             # Vector PLY exports
```

Vector exports append suffixes such as `_CH1`, `_CH2`, `_TI`, `_TI_sum`, and `_TI_normal`. Cortical exports include `cortical_stls/` and `cortical_plys/` subfolders with `regions/` and `whole_gm` outputs.

## Tips and troubleshooting

- **Environment**: Run the commands from within the TI-Toolbox environment. The scripts handle SimNIBS dependencies automatically.
- **Missing fields**: The cortical exporters expect the requested `--field` (default `TI_max`) to exist on the mesh. Inspect field names with `simnibs_python -c "import simnibs; print(simnibs.read_msh('mesh.msh').field.keys())"`.
- **Large vector clouds**: Start with smaller `--count` values or enable `--top-percent` to reduce file sizes before ramping up density.
- **Atlas updates**: If you add a new atlas, ensure the `m2m_*` directory contains the matching label files before launching the GUI.
- **Error logs**: The extension console mirrors stdout/stderr from the scripts. Copy the failing command and re-run in a terminal to investigate with additional flags (for example `--verbose`).

## Blender Tutorial: Visualizing PLY Files

This tutorial walks you through importing and visualizing PLY files exported from TI-Toolbox in Blender, including how to display the embedded color attributes.

### Step 1: Importing PLY Files

1. Open Blender and start with the default scene (or create a new project).
2. Go to **File** → **Import** → **Stanford (.ply)**.
3. Navigate to your exported PLY file location (typically in `derivatives/ti-toolbox/visual_exports/sub-<id>/<simulation>/ply/`).
4. Select your PLY file and click **Import Stanford (.ply)**.

The mesh will appear in your viewport. If the mesh appears very small or very large, you may need to adjust the view or scale the object.

![Import PLY file]({{ site.baseurl }}/assets/imgs/wiki_visual_exporter_blender_1.png)

### Step 2: Switching to Material Preview

To see materials and colors properly, switch the viewport shading mode:

1. In the 3D viewport, locate the viewport shading buttons in the top-right corner (or press `Z` to open the viewport shading menu).
2. Select **Material Preview** mode (or press `Z` then `2`).

Material Preview mode provides a quick preview of how materials will look with basic lighting, making it ideal for checking color attributes.

![Material Preview mode]({{ site.baseurl }}/assets/imgs/wiki_visual_exporter_blender_2.png)

### Step 3: Adding a Material

To display the color attributes from your PLY file, you need to create and assign a material:

1. Select your imported PLY mesh object in the viewport.
2. In the **Material Properties** panel (right sidebar, indicated by a sphere icon), click **New** to create a new material.
3. The material will be automatically assigned to your selected object.

![Adding a material]({{ site.baseurl }}/assets/imgs/wiki_visual_exporter_blender_3.png)

### Step 4: Setting Color to 'col' Attribute

To use the color data embedded in your PLY file (stored in the `col` attribute), set it as the material's base color:

1. With your object still selected, in the **Material Properties** panel, locate the **Base Color** field (under the **Surface** section).
2. Click on the **Base Color** field.
3. Select **Color Attribute** from the dropdown menu.
4. In the attribute name field that appears, enter `col` (this matches the color attribute name in your PLY file).

Your mesh should now display the color-mapped field data from your simulation. The colors represent the field values (e.g., `TI_max`) that were exported with the mesh.

<div class="carousel-container">
  <div class="carousel-wrapper">
    <div class="carousel-images">
      <div class="carousel-slide active">
        <img src="{{ site.baseurl }}/assets/imgs/wiki_visual_exporter_blender_4.png" alt="Setting color attribute - Attribute node">
        <p>Adding the Attribute node and setting it to 'col'</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/wiki_visual_exporter_blender_5.png" alt="Setting color attribute - Connected shader">
        <p>Final result with color attribute connected to the material</p>
      </div>
    </div>
    <button class="carousel-btn prev" onclick="changeSlide(this, -1)">&#10094;</button>
    <button class="carousel-btn next" onclick="changeSlide(this, 1)">&#10095;</button>
    <div class="carousel-dots">
      <span class="dot active" onclick="currentSlide(this, 0)"></span>
      <span class="dot" onclick="currentSlide(this, 1)"></span>
    </div>
  </div>
</div>

**Note**: If your PLY file uses a different attribute name for colors, replace `col` in step 4 with the appropriate attribute name. You can check available attributes by selecting the mesh and viewing the **Geometry Nodes** or **Mesh Data** properties.

<style>
/* Carousel Styles */
.carousel-container {
  position: relative;
  max-width: 100%;
  margin: 30px auto;
  overflow: hidden;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  background: #f8f9fa;
  padding: 20px;
}

.carousel-wrapper {
  position: relative;
  width: 100%;
}

.carousel-images {
  position: relative;
  width: 100%;
  height: 500px;
  overflow: hidden;
}

.carousel-slide {
  display: none;
  text-align: center;
  width: 100%;
  height: 100%;
}

.carousel-slide.active {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.carousel-slide img {
  max-width: 100%;
  max-height: 450px;
  width: auto;
  height: auto;
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  margin: 0 auto;
}

.carousel-slide p {
  margin-top: 15px;
  color: #666;
  font-style: italic;
  font-size: 0.9em;
  text-align: center;
}

.carousel-btn {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  background-color: rgba(46, 134, 171, 0.8);
  color: white;
  border: none;
  padding: 15px 20px;
  font-size: 24px;
  cursor: pointer;
  border-radius: 4px;
  z-index: 10;
  transition: background-color 0.3s ease;
}

.carousel-btn:hover {
  background-color: rgba(46, 134, 171, 1);
}

.carousel-btn.prev {
  left: 10px;
}

.carousel-btn.next {
  right: 10px;
}

.carousel-dots {
  text-align: center;
  padding: 15px 0;
}

.dot {
  cursor: pointer;
  height: 12px;
  width: 12px;
  margin: 0 5px;
  background-color: #bbb;
  border-radius: 50%;
  display: inline-block;
  transition: background-color 0.3s ease;
}

.dot.active,
.dot:hover {
  background-color: #2E86AB;
}

@media (max-width: 768px) {
  .carousel-images {
    height: 400px;
  }
  
  .carousel-slide img {
    max-height: 350px;
  }
  
  .carousel-btn {
    padding: 10px 15px;
    font-size: 20px;
  }
}
</style>

<script>
function changeSlide(btn, direction) {
  const carousel = btn.closest('.carousel-container');
  const slides = carousel.querySelectorAll('.carousel-slide');
  const dots = carousel.querySelectorAll('.dot');
  let currentIndex = 0;
  
  // Find current active slide
  slides.forEach((slide, index) => {
    if (slide.classList.contains('active')) {
      currentIndex = index;
    }
  });
  
  // Remove active class from current slide
  slides[currentIndex].classList.remove('active');
  dots[currentIndex].classList.remove('active');
  
  // Calculate new index
  let newIndex = currentIndex + direction;
  if (newIndex < 0) {
    newIndex = slides.length - 1;
  } else if (newIndex >= slides.length) {
    newIndex = 0;
  }
  
  // Add active class to new slide
  slides[newIndex].classList.add('active');
  dots[newIndex].classList.add('active');
}

function currentSlide(dot, index) {
  const carousel = dot.closest('.carousel-container');
  const slides = carousel.querySelectorAll('.carousel-slide');
  const dots = carousel.querySelectorAll('.dot');
  
  // Remove active class from all slides and dots
  slides.forEach(slide => slide.classList.remove('active'));
  dots.forEach(d => d.classList.remove('active'));
  
  // Add active class to selected slide and dot
  slides[index].classList.add('active');
  dots[index].classList.add('active');
}

// Auto-advance carousel (optional)
document.addEventListener('DOMContentLoaded', function() {
  const carousels = document.querySelectorAll('.carousel-container');
  carousels.forEach(carousel => {
    let interval = setInterval(() => {
      const nextBtn = carousel.querySelector('.carousel-btn.next');
      if (nextBtn) {
        changeSlide(nextBtn, 1);
      }
    }, 5000); // Change slide every 5 seconds
    
    // Pause on hover
    carousel.addEventListener('mouseenter', () => clearInterval(interval));
    carousel.addEventListener('mouseleave', () => {
      interval = setInterval(() => {
        const nextBtn = carousel.querySelector('.carousel-btn.next');
        if (nextBtn) {
          changeSlide(nextBtn, 1);
        }
      }, 5000);
    });
  });
});
</script>

