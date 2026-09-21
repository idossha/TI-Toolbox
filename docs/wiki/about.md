---
layout: about
title: About
permalink: /about/
---

TI-Toolbox is an open-source platform for temporal interference (TI) brain-stimulation research. It helps researchers explore how electrode placement and stimulation settings shape electric fields in the brain, bringing study planning, simulation, and analysis into one workflow.

Started as a side project in 2024, the toolbox supports both researchers new to TI modeling and experienced users working with larger studies. You can explore stimulation using standard head models or personalize a study with a participant's MRI.

## From a research question to results

- **Prepare your study** — organize imaging data and build head models that represent the anatomy you want to study.
- **Explore stimulation** — simulate electrode arrangements and visualize the resulting electric fields.
- **Find promising settings** — search for electrode placements and currents that focus stimulation on your region of interest.
- **Compare and communicate** — analyze target regions, compare results across participants, and create figures and reports.

Use the desktop interface to work through a study, or build on the same tools in scripts and notebooks when you need a custom workflow.

## Built for research

TI-Toolbox brings related modeling tasks together so you can spend more time on your research questions. Organized projects, reusable settings, and saved results help you revisit analyses and share your work with collaborators.

The project is developed openly on [GitHub](https://github.com/idossha/TI-toolbox), with contributions from the research community. Feedback, questions, and ideas help shape its development.

[Get started]({{ site.baseurl }}/installation/) · [Explore the user guide]({{ site.baseurl }}/wiki/) · [Report an issue](https://github.com/idossha/TI-toolbox/issues)

## Contributors

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
          Developed the idea and architecture for the TI-Toolbox.
        </p>
        <ul class="contributor-list">
          <li>Project direction and software development</li>
          <li>Research workflows, user experience, and documentation</li>
        </ul>
        <div class="contributor-links">
          <a href="mailto:ihaber@wisc.edu" target="_blank">📧 Email</a>
          <a href="https://github.com/idossha" target="_blank">🔗 GitHub</a>
        </div>
      </div>
    </div>

    <!-- Larissa Albantakis Profile -->
    <div class="contributor-card">
      <div class="contributor-avatar">
        <img src="{{ site.baseurl }}/assets/imgs/about/larissa_profile.jpg" alt="Larissa Albantakis"
             onerror="this.src='{{ site.baseurl }}/assets/imgs/default-avatar.png'">
      </div>
      <div class="contributor-info">
        <h3>Larissa Albantakis</h3>
        <p class="contributor-role">Core Contributor</p>
        <p class="contributor-description">
          Larissa Albantakis, PhD is a computational neuroscientist and Assistant Professor of Computational Psychiatry at University of Wisconsin - Madison.
        </p>
        <ul class="contributor-list">
          <li>Methods for modeling stimulation with multiple electrode pairs</li>
          <li>Electrode search and visualization of candidate arrangements</li>
        </ul>
        <div class="contributor-links">
          <a href="mailto:albantakis@wisc.edu" target="_blank">📧 Email</a>
          <a href="https://github.com/Albantakis" target="_blank">🔗 GitHub</a>
        </div>
      </div>
    </div>

  </div>
</div>

## Past contributors

<div class="contributors-section">
  <div class="contributor-grid">

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
          Undergraduate Research Assistant and software developer focused on computational modeling, visualization, and analysis of electric field distributions.
        </p>
        <ul class="contributor-list">
          <li>Visualizing and analyzing electric fields</li>
          <li>Project organization and software reliability</li>
        </ul>
        <div class="contributor-links">
          <a href="mailto:awjackson2@wisc.edu" target="_blank">📧 Email</a>
          <a href="https://github.com/awjackson2" target="_blank">🔗 GitHub</a>
        </div>
      </div>
    </div>

  </div>
</div>

## Acknowledgments

TI-Toolbox builds on the work of the open-source neuroimaging community, including [SimNIBS](https://simnibs.github.io/simnibs/build/html/index.html), [FreeSurfer](https://surfer.nmr.mgh.harvard.edu/), [FastSurfer](https://github.com/Deep-MI/FastSurfer), [FSL](https://fsl.fmrib.ox.ac.uk/fsl/), [QSIPrep](https://qsiprep.readthedocs.io/), and [QSIRecon](https://qsirecon.readthedocs.io/). We thank their developers, the [BIDS](https://bids.neuroimaging.io/) community, and the contributors to the many scientific and visualization tools that support this work.

If you use TI-Toolbox in a publication, please [cite the software and its associated paper](https://github.com/idossha/TI-toolbox#how-to-cite), along with the underlying tools used in your study.

<style>
.contributors-section {
  margin: 1rem 0 2rem;
}

.contributor-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 420px));
  gap: 1.5rem;
  margin-top: 1rem;
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

.contributor-list {
  color: #495057;
  line-height: 1.5;
  font-size: 0.95rem;
  text-align: left;
  margin: 0.5rem 0 1rem;
  padding-left: 1.1rem;
}

.contributor-list li {
  margin-bottom: 0.35rem;
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
