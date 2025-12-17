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


1. **Set up your BIDS project directory**
   - Organize your data in BIDS format. Place DICOM files in `{project-name}/sourcedata/sub-{subjectID}/T1w/dicom/` (and optionally T2w).
2. **Install Docker**
   - Required for running the toolbox environment.
3. **Install TI-Toolbox:**<br>
   **A. Desktop Executable:**
   Download and run the executable version of the latest release [here](https://github.com/idossha/TI-toolbox/releases/latest).<br> 
    **B. CLI Entry:** Download the two files below to a designated directory.
   - **[loader.sh](https://github.com/idossha/TI-toolbox/blob/main/loader.sh)** - Main launch script
   - **[docker-compose.yml](https://github.com/idossha/TI-toolbox/blob/main/docker-compose.yml)** - Docker configuration

   ```bash
   bash loader.sh
   ```

<div class="carousel-container">
  <div class="carousel-wrapper">
    <div class="carousel-images">
      <div class="carousel-slide active">
        <img src="{{ site.baseurl }}/assets/imgs/wiki/visual-exporter/visual_exporter_vectors_close.png" alt="Vector Field Visualization">
        <p>High-resolution electric field vector visualization showing direction and magnitude</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/wiki/testing-pipeline/testing_graphical_abstract_revised.png" alt="TI-Toolbox Tech Stack">
        <p>Complete TI-Toolbox technology stack: BIDS-compatible, Docker-based, end-to-end pipeline</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/gallery/ex-search_ex-search_selection.png" alt="Electrode Selection">
        <p>Exhaustive search for optimal electrode placement across standard EEG montages</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/gallery/flex-search_mapping.png" alt="Flex-Search Mapping">
        <p>Flexible search extension mapping genetic algorithm output to registered EEG positions</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/gallery/UI_sim.png" alt="Simulation GUI">
        <p>User-friendly GUI for configuring and running temporal interference simulations</p>
      </div>
      <div class="carousel-slide">
        <img src="{{ site.baseurl }}/assets/imgs/wiki/cluster-permutation-testing/stats_permutation_null_dist.png" alt="Cluster-Based Permutation Testing">
        <p>Statistical analysis with cluster-based permutation testing for group-level inference</p>
      </div>
    </div>
    <button class="carousel-btn prev" onclick="changeSlide(this, -1)">&#10094;</button>
    <button class="carousel-btn next" onclick="changeSlide(this, 1)">&#10095;</button>
    <div class="carousel-dots">
      <span class="dot active" onclick="currentSlide(this, 0)"></span>
      <span class="dot" onclick="currentSlide(this, 1)"></span>
      <span class="dot" onclick="currentSlide(this, 2)"></span>
      <span class="dot" onclick="currentSlide(this, 3)"></span>
      <span class="dot" onclick="currentSlide(this, 4)"></span>
      <span class="dot" onclick="currentSlide(this, 5)"></span>
    </div>
  </div>
</div>

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

// Auto-advance carousel
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


