---
layout: home
---

<div class="hero" style="display: flex; align-items: center; gap: 2rem;">
  <img src="{{ site.baseurl }}/assets/imgs/icon.png" alt="TI Toolbox Icon" style="width:80px;height:80px;flex-shrink:0;">
  <div>
    <h1>Temporal Interference Toolbox</h1>
    <p>A comprehensive toolbox for temporal interference stimulation research, providing end-to-end neuroimaging and simulation capabilities.</p>
  </div>
</div>

<div class="features">
  <!-- ... existing code ... -->
</div>

## Quick Start Workflow

1. **Set up your BIDS project directory**
   - Organize your data in BIDS format. Place DICOM files in `sourcedata/sub-<subject>/T1w/dicom/` (and optionally T2w).
2. **Install Docker Desktop**
   - Required for running the toolbox environment.
3. **Get the Latest Release**
   - Download the latest version (2.x.x or newer) from the <a href="{{ site.baseurl }}/releases/">Releases page</a>. See the <a href="{{ site.baseurl }}/installation/">Installation</a> for platform-specific instructions. Note: Versions 1.x.x are no longer supported.
4. **Pre-process your data**
   - Convert DICOM to NIfTI, run FreeSurfer, and create SimNIBS head models using the pre-processing pipeline.
5. **Optimize electrode placement**
   - Use <b>flex-search</b> (evolutionary) or <b>ex-search</b> (exhaustive) tools to find optimal stimulation parameters.
6. **Simulate TI fields**
   - Run FEM-based simulations for your selected montages and parameters.
7. **Analyze and visualize results**
   - Use the analyzer and visualization tools for ROI-based and atlas-based analysis, and to generate figures and reports.

<div style="display: flex; justify-content: center; margin: 2rem 0;">
  <svg width="650" height="110" viewBox="0 0 650 110" xmlns="http://www.w3.org/2000/svg">
    <!-- Pre-processing Box -->
    <rect x="10" y="30" width="130" height="50" rx="12" fill="#f5f5f5" stroke="#0074D9" stroke-width="2"/>
    <text x="75" y="60" text-anchor="middle" alignment-baseline="middle" font-size="16" fill="#0074D9">Pre-processing</text>
    <!-- Arrow 1 -->
    <line x1="140" y1="55" x2="180" y2="55" stroke="#888" stroke-width="3" marker-end="url(#arrowhead)"/>
    <!-- Optimization Box -->
    <rect x="180" y="30" width="130" height="50" rx="12" fill="#f5f5f5" stroke="#2ECC40" stroke-width="2"/>
    <text x="245" y="60" text-anchor="middle" alignment-baseline="middle" font-size="16" fill="#2ECC40">Optimization</text>
    <!-- Arrow 2 -->
    <line x1="310" y1="55" x2="350" y2="55" stroke="#888" stroke-width="3" marker-end="url(#arrowhead)"/>
    <!-- Simulation Box -->
    <rect x="350" y="30" width="130" height="50" rx="12" fill="#f5f5f5" stroke="#FF851B" stroke-width="2"/>
    <text x="415" y="60" text-anchor="middle" alignment-baseline="middle" font-size="16" fill="#FF851B">Simulation</text>
    <!-- Arrow 3 -->
    <line x1="480" y1="55" x2="520" y2="55" stroke="#888" stroke-width="3" marker-end="url(#arrowhead)"/>
    <!-- Analysis & Visualization Box -->
    <rect x="520" y="30" width="120" height="50" rx="12" fill="#f5f5f5" stroke="#B10DC9" stroke-width="2"/>
    <text x="580" y="53" text-anchor="middle" font-size="15" fill="#B10DC9">Analysis &</text>
    <text x="580" y="73" text-anchor="middle" font-size="15" fill="#B10DC9">Visualization</text>
    <!-- Arrowhead marker definition -->
    <defs>
      <marker id="arrowhead" markerWidth="6" markerHeight="4" refX="6" refY="2" orient="auto" markerUnits="strokeWidth">
        <polygon points="0 0, 6 2, 0 4" fill="#888" />
      </marker>
    </defs>
  </svg>
</div>