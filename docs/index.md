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


<div style="display: flex; justify-content: center; margin: 0.73rem 0 0.2rem 0;">
  <svg width="720" height="180" viewBox="0 0 720 180" xmlns="http://www.w3.org/2000/svg">
    <!-- Pre-processing Box -->
    <rect x="10" y="30" width="130" height="50" rx="12" fill="#f8f8f8" stroke="#666" stroke-width="2"/>
    <text x="75" y="60" text-anchor="middle" alignment-baseline="middle" font-size="16" fill="#333">Pre-processing</text>
    <!-- Arrow 1 -->
    <line x1="140" y1="55" x2="180" y2="55" stroke="#888" stroke-width="3" marker-end="url(#arrowhead)"/>
    <!-- Optimization Box -->
    <rect x="180" y="30" width="130" height="50" rx="12" fill="#f8f8f8" stroke="#666" stroke-width="2"/>
    <text x="245" y="60" text-anchor="middle" alignment-baseline="middle" font-size="16" fill="#333">Optimization</text>
    <!-- Arrow 2 -->
    <line x1="310" y1="55" x2="350" y2="55" stroke="#888" stroke-width="3" marker-end="url(#arrowhead)"/>
    <!-- Simulation Box -->
    <rect x="350" y="30" width="130" height="50" rx="12" fill="#f8f8f8" stroke="#666" stroke-width="2"/>
    <text x="415" y="60" text-anchor="middle" alignment-baseline="middle" font-size="16" fill="#333">Simulation</text>
    
    <!-- Split arrows from simulation -->
    <line x1="480" y1="45" x2="520" y2="35" stroke="#888" stroke-width="3" marker-end="url(#arrowhead)"/>
    <line x1="480" y1="65" x2="520" y2="75" stroke="#888" stroke-width="3" marker-end="url(#arrowhead)"/>
    
    <!-- Mesh Analysis & Visualization Box (upper) -->
    <rect x="520" y="10" width="180" height="50" rx="12" fill="#f8f8f8" stroke="#666" stroke-width="2"/>
    <text x="610" y="30" text-anchor="middle" font-size="14" fill="#333">Mesh Analysis &</text>
    <text x="610" y="46" text-anchor="middle" font-size="14" fill="#333">Visualization</text>
    
    <!-- Voxel Analysis & Visualization Box (lower) -->
    <rect x="520" y="70" width="180" height="50" rx="12" fill="#f8f8f8" stroke="#666" stroke-width="2"/>
    <text x="610" y="90" text-anchor="middle" font-size="14" fill="#333">Voxel Analysis &</text>
    <text x="610" y="106" text-anchor="middle" font-size="14" fill="#333">Visualization</text>
    
    <!-- Highlight overlays (initially hidden) -->
    <rect id="highlight-preproc" x="9" y="29" width="132" height="52" rx="13" fill="none" stroke="#dc3545" stroke-width="2" opacity="0"/>
    <rect id="highlight-optimization" x="179" y="29" width="132" height="52" rx="13" fill="none" stroke="#dc3545" stroke-width="2" opacity="0"/>
    <rect id="highlight-mesh" x="519" y="9" width="182" height="52" rx="13" fill="none" stroke="#dc3545" stroke-width="2" opacity="0"/>
    <rect id="highlight-voxel" x="519" y="69" width="182" height="52" rx="13" fill="none" stroke="#dc3545" stroke-width="2" opacity="0"/>
    
    <!-- Connecting lines (initially hidden) -->
    <g id="connection-lines" opacity="0">
      <line id="line-preproc" x1="75" y1="82" x2="360" y2="160" stroke="#333" stroke-width="2" stroke-dasharray="3,3" opacity="0"/>
      <line id="line-optimization" x1="245" y1="82" x2="360" y2="160" stroke="#333" stroke-width="2" stroke-dasharray="3,3" opacity="0"/>
      <line id="line-mesh" x1="610" y1="62" x2="360" y2="160" stroke="#333" stroke-width="2" stroke-dasharray="3,3" opacity="0"/>
      <line id="line-voxel" x1="610" y1="122" x2="360" y2="160" stroke="#333" stroke-width="2" stroke-dasharray="3,3" opacity="0"/>
      <!-- Connection point -->
      <circle cx="360" cy="160" r="4" fill="#333"/>
    </g>
    
    <!-- Arrowhead marker definition -->
    <defs>
      <marker id="arrowhead" markerWidth="6" markerHeight="4" refX="6" refY="2" orient="auto" markerUnits="strokeWidth">
        <polygon points="0 0, 6 2, 0 4" fill="#888" />
      </marker>
    </defs>
  </svg>
</div>

<!-- Workflow Carousel -->
<div class="workflow-carousel" style="margin: 0.2rem 0 0.73rem 0; text-align: center; position: relative;">
  
  <div class="carousel-container" style="position: relative; max-width: 600px; margin: 0 auto; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
    <div class="carousel-slide active" style="display: block;">
      <img src="{{ site.baseurl }}/gallery/assets/carousel/pre-proc.png" alt="Pre-processing" style="width: 100%; height: 300px; object-fit: contain; background-color: #f8f9fa; cursor: pointer;" data-fullscreen="0">
    </div>
    <div class="carousel-slide" style="display: none;">
      <img src="{{ site.baseurl }}/gallery/assets/carousel/search.png" alt="Search & Optimization" style="width: 100%; height: 300px; object-fit: contain; background-color: #f8f9fa; cursor: pointer;" data-fullscreen="1">
    </div>
    <div class="carousel-slide" style="display: none;">
      <img src="{{ site.baseurl }}/gallery/assets/carousel/ana.png" alt="Analysis" style="width: 100%; height: 300px; object-fit: contain; background-color: #f8f9fa; cursor: pointer;" data-fullscreen="2">
    </div>
    <div class="carousel-slide" style="display: none;">
      <img src="{{ site.baseurl }}/gallery/assets/carousel/nifti.png" alt="NIfTI Visualization" style="width: 100%; height: 300px; object-fit: contain; background-color: #f8f9fa; cursor: pointer;" data-fullscreen="3">
    </div>
    
    <!-- Navigation arrows -->
    <button id="carousel-prev" style="position: absolute; left: 10px; top: 50%; transform: translateY(-50%); background: none; border: none; color: #555; font-size: 2.5rem; cursor: pointer; z-index: 100; transition: color 0.3s;" onmouseover="this.style.color='#333'" onmouseout="this.style.color='#555'">‹</button>
    <button id="carousel-next" style="position: absolute; right: 10px; top: 50%; transform: translateY(-50%); background: none; border: none; color: #555; font-size: 2.5rem; cursor: pointer; z-index: 100; transition: color 0.3s;" onmouseover="this.style.color='#333'" onmouseout="this.style.color='#555'">›</button>
  </div>
</div>

<!-- Image Modal -->
<div id="image-modal" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; align-items: center; justify-content: center;">
  <div style="position: relative; max-width: 80%; max-height: 80%; background: white; border-radius: 12px; padding: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.3);">
    <!-- Close button -->
    <button id="close-modal" style="position: absolute; top: 10px; right: 15px; background: none; border: none; color: #666; font-size: 2rem; cursor: pointer; z-index: 1001; font-weight: bold; transition: color 0.3s;" onmouseover="this.style.color='#333'" onmouseout="this.style.color='#666'">&times;</button>
    
    <!-- Title -->
    <div id="modal-title" style="color: #333; font-size: 1.5rem; font-weight: 600; text-align: center; margin-bottom: 15px; padding-right: 50px;"></div>
    
    <div style="position: relative; display: flex; align-items: center; justify-content: center;">
                    <!-- Left arrow -->
        <button id="prev-modal" style="position: absolute; left: -60px; top: 50%; transform: translateY(-50%); background: none; border: none; color: #666; font-size: 2.5rem; cursor: pointer; z-index: 1001; transition: color 0.3s;" onmouseover="this.style.color='#333'" onmouseout="this.style.color='#666'">&#8249;</button>
        
        <!-- Image -->
        <img id="modal-image" style="max-width: 100%; max-height: 60vh; object-fit: contain; border-radius: 8px;">
        
        <!-- Right arrow -->
        <button id="next-modal" style="position: absolute; right: -60px; top: 50%; transform: translateY(-50%); background: none; border: none; color: #666; font-size: 2.5rem; cursor: pointer; z-index: 1001; transition: color 0.3s;" onmouseover="this.style.color='#333'" onmouseout="this.style.color='#666'">&#8250;</button>
    </div>
  </div>
</div>

<script>
(function() {
  let currentSlide = 0;
  let fullscreenSlide = 0;
  const slides = document.querySelectorAll('.carousel-slide');
  const totalSlides = slides.length;
  
  // Image data for modal
  const imageData = [
    { src: '{{ site.baseurl }}/gallery/assets/carousel/pre-proc.png', title: 'Pre-processing' },
    { src: '{{ site.baseurl }}/gallery/assets/carousel/search.png', title: 'Search & Optimization' },
    { src: '{{ site.baseurl }}/gallery/assets/carousel/ana.png', title: 'Mesh Analysis & Visualization' },
    { src: '{{ site.baseurl }}/gallery/assets/carousel/nifti.png', title: 'Voxel Analysis & Visualization' }
  ];
  
  // Mapping slides to flowchart elements
  const slideMapping = [
    'preproc',      // pre-proc → pre-processing
    'optimization', // search → optimization  
    'mesh',         // ana → mesh analysis & visualization
    'voxel'         // nifti → voxel analysis & visualization
  ];
  
  function showSlide(index) {
    // Hide all slides
    slides.forEach(slide => slide.style.display = 'none');
    
    // Show current slide
    slides[index].style.display = 'block';
    
    // Update flowchart highlights
    updateFlowchartHighlight(index);
  }
  
  function updateFlowchartHighlight(index) {
    // Hide all highlights
    document.getElementById('highlight-preproc').style.opacity = '0';
    document.getElementById('highlight-optimization').style.opacity = '0';
    document.getElementById('highlight-mesh').style.opacity = '0';
    document.getElementById('highlight-voxel').style.opacity = '0';
    
    // Hide all connection lines
    document.getElementById('line-preproc').style.opacity = '0';
    document.getElementById('line-optimization').style.opacity = '0';
    document.getElementById('line-mesh').style.opacity = '0';
    document.getElementById('line-voxel').style.opacity = '0';
    
    // Show current highlight and connection
    const targetElement = slideMapping[index];
    document.getElementById('highlight-' + targetElement).style.opacity = '1';
    document.getElementById('connection-lines').style.opacity = '1';
    document.getElementById('line-' + targetElement).style.opacity = '1';
  }
  
  function nextSlide() {
    currentSlide = (currentSlide + 1) % totalSlides;
    showSlide(currentSlide);
  }
  
  function prevSlide() {
    currentSlide = (currentSlide - 1 + totalSlides) % totalSlides;
    showSlide(currentSlide);
  }
  
  // Modal functions
  function openModal(index) {
    fullscreenSlide = index;
    const modal = document.getElementById('image-modal');
    const img = document.getElementById('modal-image');
    const title = document.getElementById('modal-title');
    
    img.src = imageData[index].src;
    title.textContent = imageData[index].title;
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
  }
  
  function closeModal() {
    const modal = document.getElementById('image-modal');
    modal.style.display = 'none';
    document.body.style.overflow = 'auto';
  }
  
  function nextModal() {
    fullscreenSlide = (fullscreenSlide + 1) % totalSlides;
    const img = document.getElementById('modal-image');
    const title = document.getElementById('modal-title');
    img.src = imageData[fullscreenSlide].src;
    title.textContent = imageData[fullscreenSlide].title;
  }
  
  function prevModal() {
    fullscreenSlide = (fullscreenSlide - 1 + totalSlides) % totalSlides;
    const img = document.getElementById('modal-image');
    const title = document.getElementById('modal-title');
    img.src = imageData[fullscreenSlide].src;
    title.textContent = imageData[fullscreenSlide].title;
  }
  
  // Initialize first slide highlight
  updateFlowchartHighlight(0);
  
  // Auto-advance every 5 seconds
  setInterval(nextSlide, 5000);
  
  // Carousel arrow navigation
  document.getElementById('carousel-prev').addEventListener('click', prevSlide);
  document.getElementById('carousel-next').addEventListener('click', nextSlide);
  
  // Add click handlers to images for modal
  document.querySelectorAll('[data-fullscreen]').forEach((img, index) => {
    img.addEventListener('click', () => {
      openModal(index);
    });
  });
  
  // Modal controls
  document.getElementById('close-modal').addEventListener('click', closeModal);
  document.getElementById('next-modal').addEventListener('click', nextModal);
  document.getElementById('prev-modal').addEventListener('click', prevModal);
  
  // Keyboard controls
  document.addEventListener('keydown', (e) => {
    const modal = document.getElementById('image-modal');
    if (modal.style.display === 'flex') {
      if (e.key === 'Escape') closeModal();
      if (e.key === 'ArrowRight') nextModal();
      if (e.key === 'ArrowLeft') prevModal();
    }
  });
  
  // Close on background click
  document.getElementById('image-modal').addEventListener('click', (e) => {
    if (e.target.id === 'image-modal') {
      closeModal();
    }
  });
})();
</script>

