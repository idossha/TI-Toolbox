---
layout: page
title: About
permalink: /about/
---

The Temporal Interference Toolbox started as a side project in early 2024 and matured to be a toolbox that allows both inexperience and experience users simulate TI fields from standardized and personalized imaging data.

### Contributors

<div class="contributors-section">
  <div class="contributor-grid">
    
    <!-- Ido Haber Profile -->
    <div class="contributor-card">
      <div class="contributor-avatar">
        <img src="{{ site.baseurl }}/assets/imgs/about/ido_profile.png" alt="Ido Haber" 
             onerror="this.src='{{ site.baseurl }}/assets/imgs/default-avatar.png'">
      </div>
      <div class="contributor-info">
        <h3>Ido Haber</h3>
        <p class="contributor-role">Lead Developer & Project Founder</p>
        <p class="contributor-description">
          PhD Research Assistant and software developer specializing in computational neurostimulation. 
          Developed the idea and architecture for the TI-Toolbox.<br>
        </p>
        <div class="contributor-links">
          <a href="mailto:ihaber@wisc.edu" target="_blank">📧 Email</a>
          <a href="https://github.com/idossha" target="_blank">🔗 GitHub</a>
        </div>
      </div>
    </div>

    <!-- Aksel Profile -->
    <div class="contributor-card">
      <div class="contributor-avatar">
        <img src="{{ site.baseurl }}/assets/imgs/about/aksel_profile.png" alt="Aksel" 
             onerror="this.src='{{ site.baseurl }}/assets/imgs/default-avatar.png'">
      </div>
      <div class="contributor-info">
        <h3>Aksel Jackson</h3>
        <p class="contributor-role">Core Contributor</p>
        <p class="contributor-description">
          Undergraduate Research Assistant and software developer focused on computational modeling, visualization, and analysis of electric field distribution. <br>
        </p>
        <div class="contributor-links">
          <a href="mailto:awjackson2@wisc.edu" target="_blank">📧 Email</a>
          <a href="https://github.com/awjackson2" target="_blank">🔗 GitHub</a>
        </div>
      </div>
    </div>

  </div>
</div>

## Acknowledgments

We extend our gratitude to the developers and contributors of the tools integrated into the TI-Toolbox. 

- [**Docker**](https://www.docker.com): A containerization platform for developing, shipping, and running distributed applications.
- [**SimNIBS**:](https://simnibs.github.io/simnibs/build/html/index.html) A simulation environment for transcranial brain stimulation, enabling electric field modeling.
- [**FreeSurfer**:](https://surfer.nmr.mgh.harvard.edu/) A software suite for the analysis and visualization of structural and functional neuroimaging data.
- [**Gmsh**:](http://gmsh.info/) A three-dimensional finite element mesh generator with a built-in CAD engine and post-processor.  
- [**FSL**:](https://fsl.fmrib.ox.ac.uk/fsl/) A comprehensive library of tools for analysis of functional and structural brain imaging data.
- [**dcm2niix**](https://github.com/rordenlab/dcm2niix): A tool for converting DICOM images to NIfTI format
- [**BIDS**](https://bids.neuroimaging.io/): A standardized way to organize and describe neuroimaging data.



<style>
.contributors-section {
  margin: 2rem 0;
}

.contributor-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
  gap: 2rem;
  margin-top: 1.5rem;
}

.contributor-card {
  background: #f8f9fa;
  border-radius: 12px;
  padding: 1.5rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.contributor-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

.contributor-avatar {
  width: 80px;
  height: 80px;
  margin: 0 auto 1rem;
  border-radius: 50%;
  overflow: hidden;
  background-color: #e9ecef;
}

.contributor-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.contributor-info {
  text-align: center;
}

.contributor-info h3 {
  margin: 0 0 0.25rem;
  font-size: 1.25rem;
}

.contributor-role {
  color: #6c757d;
  font-weight: 600;
  margin: 0 0 0.75rem;
  font-size: 0.9rem;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.contributor-description {
  color: #495057;
  line-height: 1.5;
  margin-bottom: 1rem;
  font-size: 0.95rem;
  text-align: Left;
}

.contributor-links {
  display: flex;
  justify-content: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.contributor-links a {
  background: grey;
  color: white;
  padding: 0.4rem 0.8rem;
  border-radius: 20px;
  text-decoration: none;
  font-size: 0.85rem;
  transition: background-color 0.2s ease;
}

.contributor-links a:hover {
  background: #0056b3;
}

@media (max-width: 768px) {
  .contributor-grid {
    grid-template-columns: 1fr;
    gap: 1.5rem;
  }
  
  .contributor-card {
    padding: 1rem;
  }
  
  .contributor-avatar {
    width: 60px;
    height: 60px;
  }
}
</style> 
