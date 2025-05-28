---
layout: page
title: Wiki
permalink: /wiki/
---

# Temporal Interference Toolbox Wiki

Welcome to the Temporal Interference Toolbox Wiki. Here you'll find detailed guides, advanced usage, and troubleshooting tips for the toolbox.

## Workflow Overview

1. **Set up your BIDS project directory**
2. **Install Docker Desktop**
3. **Download the latest release from the [releases page](/releases)**
4. **Pre-process your data** (DICOM to NIfTI, FreeSurfer, SimNIBS)
5. **Optimize electrode placement** (flex-search or ex-search)
6. **Simulate TI fields**
7. **Analyze and visualize results**

## Key Topics

- [Project Structure](#project-structure)
- [Pre-processing Pipeline](#pre-processing-pipeline)
- [Optimization](#optimization)
- [Simulation](#simulation)
- [Analysis & Visualization](#analysis--visualization)
- [Troubleshooting](#troubleshooting)

## Project Structure

The toolbox expects a BIDS-compliant directory structure. See the [documentation](/documentation) for details.

## Pre-processing Pipeline

- DICOM to NIfTI conversion
- FreeSurfer cortical reconstruction
- SimNIBS head modeling

## Optimization

- flex-search: Evolutionary optimization
- ex-search: Exhaustive search

## Simulation

- FEM-based TI/mTI field calculations
- Custom montages and parameters

## Analysis & Visualization

- ROI and atlas-based analysis
- NIfTI/mesh viewers, report generator

## Troubleshooting

See the [issue tracker](https://github.com/idossha/TI-Toolbox/issues) or [discussions](https://github.com/idossha/TI-Toolbox/discussions) for help.

## More Resources

- [Releases](/releases)
- [Documentation](/documentation)
- [About](/about)

<div class="wiki-layout">
  <div class="wiki-sidebar">
    <div class="wiki-nav">
      <h3>Getting Started</h3>
      <ul>
        <li><a href="/wiki/installation-guide">Installation Guide</a></li>
        <li><a href="/wiki/first-project">Your First Project</a></li>
        <li><a href="/wiki/bids-format">BIDS Data Format</a></li>
        <li><a href="/wiki/docker-basics">Docker Basics</a></li>
      </ul>
      
      <h3>Tutorials</h3>
      <ul>
        <li><a href="/wiki/preprocessing-tutorial">Pre-processing Tutorial</a></li>
        <li><a href="/wiki/simulation-tutorial">Running Simulations</a></li>
        <li><a href="/wiki/optimization-guide">Optimization Guide</a></li>
        <li><a href="/wiki/visualization-tutorial">Visualization Tutorial</a></li>
      </ul>
      
      <h3>Advanced Topics</h3>
      <ul>
        <li><a href="/wiki/custom-electrodes">Custom Electrode Models</a></li>
        <li><a href="/wiki/batch-processing">Batch Processing</a></li>
        <li><a href="/wiki/gpu-acceleration">GPU Acceleration</a></li>
        <li><a href="/wiki/scripting">Scripting & Automation</a></li>
      </ul>
      
      <h3>Theory</h3>
      <ul>
        <li><a href="/wiki/ti-theory">TI Theory & Physics</a></li>
        <li><a href="/wiki/fem-basics">FEM Fundamentals</a></li>
        <li><a href="/wiki/optimization-algorithms">Optimization Algorithms</a></li>
        <li><a href="/wiki/safety-guidelines">Safety Guidelines</a></li>
      </ul>
      
      <h3>Development</h3>
      <ul>
        <li><a href="/wiki/architecture">System Architecture</a></li>
        <li><a href="/wiki/api-reference">API Reference</a></li>
        <li><a href="/wiki/contributing">Contributing Guide</a></li>
        <li><a href="/wiki/plugin-development">Plugin Development</a></li>
      </ul>
      
      <h3>Troubleshooting</h3>
      <ul>
        <li><a href="/wiki/common-errors">Common Errors</a></li>
        <li><a href="/wiki/performance-tuning">Performance Tuning</a></li>
        <li><a href="/wiki/debugging">Debugging Guide</a></li>
        <li><a href="/wiki/faq">FAQ</a></li>
      </ul>
    </div>
  </div>
  
  <div class="wiki-content">
    <h2>Popular Articles</h2>
    
    <h3>📚 Getting Started with Temporal Interference Toolbox</h3>
    <p>New to Temporal Interference Toolbox? Start with our <a href="/wiki/installation-guide">Installation Guide</a> and then follow the <a href="/wiki/first-project">Your First Project</a> tutorial to get up and running quickly.</p>
    
    <h3>🧠 Understanding Temporal Interference</h3>
    <p>Learn about the physics and theory behind temporal interference stimulation in our comprehensive <a href="/wiki/ti-theory">TI Theory & Physics</a> guide.</p>
    
    <h3>⚡ Running Your First Simulation</h3>
    <p>Follow our step-by-step <a href="/wiki/simulation-tutorial">Simulation Tutorial</a> to run your first TI simulation and understand the results.</p>
    
    <h3>🎯 Optimizing Electrode Placement</h3>
    <p>Discover how to find optimal electrode configurations using our <a href="/wiki/optimization-guide">Optimization Guide</a>.</p>
    
    <h2>Recent Updates</h2>
    
    <ul>
      <li><strong>NEW:</strong> GPU Acceleration guide for NVIDIA cards</li>
      <li><strong>UPDATED:</strong> Docker troubleshooting for Apple Silicon</li>
      <li><strong>NEW:</strong> Batch processing tutorial for multiple subjects</li>
      <li><strong>UPDATED:</strong> XQuartz configuration for macOS</li>
    </ul>
    
    <h2>Contributing to the Wiki</h2>
    
    <p>The Temporal Interference Toolbox Wiki is maintained by the community. If you'd like to contribute:</p>
    
    <ol>
      <li>Fork the repository on GitHub</li>
      <li>Add or edit wiki pages in the <code>docs/_wiki</code> directory</li>
      <li>Submit a pull request with your changes</li>
    </ol>
    
    <p>See our <a href="/wiki/contributing">Contributing Guide</a> for detailed instructions.</p>
    
    <h2>Video Tutorials</h2>
    
    <p>Looking for video content? Check out our <a href="https://youtube.com/ti-csc">YouTube channel</a> for video tutorials and webinars.</p>
    
    <h2>Need Help?</h2>
    
    <p>Can't find what you're looking for? Try:</p>
    <ul>
      <li>Searching the wiki using the search box above</li>
      <li>Checking the <a href="/wiki/faq">Frequently Asked Questions</a></li>
      <li>Asking in our <a href="https://github.com/idossha/TI-Toolbox/discussions">GitHub Discussions</a></li>
      <li>Opening an <a href="https://github.com/idossha/TI-Toolbox/issues">issue</a> if you've found a bug</li>
    </ul>
  </div>
</div> 