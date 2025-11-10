---
layout: wiki
title: MOVEA Optimization
permalink: /wiki/movea-opt/
---

## Overview

MOVEA (Multi-Objective Optimization via Evolutionary Algorithm) is an advanced optimization method for finding optimal electrode montages for Temporal Interference (TI) stimulation. This implementation is based on the original MOVEA algorithm developed by the Neural Control and Computation Lab at SUSTech.

**Original Project**: [MOVEA on GitHub](https://github.com/ncclab-sustech/MOVEA)  
**Original Paper**: [Zhu et al., 2023](https://doi.org/10.1016/j.neuroimage.2023.120331) - "MOVEA: Multi-objective optimization via evolutionary algorithm for high-definition transcranial electrical stimulation of the human brain"

## Key Features

### Multi-Objective Optimization
MOVEA simultaneously optimizes two competing objectives:
1. **Maximize electric field intensity at the target region** - Ensures effective stimulation
2. **Minimize electric field across the whole brain** - Improves focality

This creates a Pareto front showing the trade-off between intensity and focality, allowing researchers to choose the best compromise for their specific application.

### Advanced Algorithm
- **NSGA-II style evolutionary algorithm** for true multi-objective optimization
- **Parallel evaluation** using threading for faster computation
- **Smart genetic operators** ensuring valid electrode configurations
- **Elitism** to preserve best solutions across generations

## GUI Usage

### Basic Workflow
1. **Generate or Load Leadfield**: Create the leadfield matrix for your subject
2. **Set Target**: Choose a preset ROI or enter custom MNI coordinates
3. **Configure Parameters**: Adjust optimization settings as needed
4. **Run Optimization**: Single-objective for fast results or multi-objective for detailed analysis
5. **Analyze Results**: Review the optimal montage and optionally the Pareto front

### Parameter Guidelines

#### Target Settings
- **ROI Radius**: 
  - 10-15 mm: Focal stimulation (recommended for most applications)
  - 20-30 mm: Broader cortical areas
  - Larger radius provides more coverage but less focality

#### Single-Objective Optimization
- **Generations**: 
  - 50-100: Quick optimization (5-10 min)
  - 200-500: Standard quality (15-30 min)
  - 500+: Publication quality (30+ min)
- **Population**: 
  - 30-50: Standard (recommended)
  - 100+: Thorough exploration

#### Multi-Objective Optimization (Pareto Front)
- **Enable by default** for comprehensive analysis
- **Pareto Solutions**: 
  - 20-30: Quick exploration
  - 50-100: Detailed analysis
  - 100+: Research quality
- **Iterations**: 
  - 500-1000: Quick results
  - 1500+: High-quality front

#### Stimulation Parameters
- **Current**: 1-2 mA per channel pair (2 mA recommended)

### Output Files

The optimization generates several output files in the derivatives folder:

1. **movea_montage.csv**: Main result file with electrode configuration
2. **pareto_front.png**: Visualization of intensity vs focality trade-off (multi-objective only)
3. **pareto_solutions.csv**: Detailed data for all Pareto-optimal solutions (multi-objective only)
4. **convergence.png**: Optimization progress plot showing field strength and cost convergence (when multiple runs)
5. **montage_summary.png**: Comprehensive summary plot of single-objective optimization results

## Visualization Examples

### Single-Objective Optimization Results

![MOVEA Single-Objective Results]({{ site.baseurl }}/assets/imgs/movea_single.png)

*Figure: Single-objective optimization summary showing optimal electrode montage and field distribution*

### Multi-Objective Optimization Results

![MOVEA Multi-Objective Results]({{ site.baseurl }}/assets/imgs/movea_multi.png)

*Figure: Multi-objective optimization Pareto front showing trade-off between intensity and focality*

## Algorithm Details

### MOVEA Processing Pipeline

MOVEA follows a comprehensive workflow from leadfield generation to optimized electrode montages:

```
1. Leadfield Generation → 2. Target ROI Selection → 3. Optimization → 4. Result Formatting
```

#### Phase 1: Leadfield Matrix Generation
**Purpose**: Create the foundation for field calculations by modeling how each electrode influences the brain's electric field.

**Steps**:
1. **Subject Setup**: Select subject with M2M (Mesh-to-Mesh) head model from SimNIBS
2. **EEG Cap Selection**: Choose electrode montage file (e.g., 10-10 net with ~256 electrodes)
3. **Leadfield Computation**:
   - SimNIBS computes electric field at each brain voxel for each electrode
   - Generates leadfield matrix: `electrodes × voxels × 3` (electric field components)
   - Saves as NumPy arrays: `{net_name}_leadfield.npy` and `{net_name}_positions.npy`

#### Phase 2: Target ROI Selection
**Purpose**: Define the brain region to optimize stimulation for.

**Steps**:
1. **ROI Definition**: Choose preset target (motor cortex, DLPFC, hippocampus) or custom MNI coordinates
2. **Voxel Identification**: Find all brain voxels within specified radius (typically 10-15mm) of target
3. **Validation**: Ensure sufficient voxels found for meaningful optimization

#### Phase 3: Optimization Algorithms

MOVEA supports two optimization approaches with distinct processing steps:

##### Single-Objective Optimization
**Goal**: Maximize electric field intensity at target ROI only

**Algorithm**: Differential Evolution (with fallback to manual genetic algorithm)

**Processing Steps**:
1. **Initialization**:
   - Create initial population of electrode configurations (4 electrodes each)
   - Each individual: `[electrode1, electrode2, electrode3, electrode4, current_ratio]`

2. **Evaluation**:
   - For each electrode configuration:
     - Create bipolar stimulation pairs: (E1+, E2-) and (E3+, E4-)
     - Calculate TI field using leadfield matrix
     - Compute objective: `cost = 1 / (average_target_field + epsilon)`
     - Lower cost = higher field intensity

3. **Evolution Loop**:
   - **Selection**: Choose best individuals based on fitness
   - **Crossover**: Blend electrode configurations from parents
   - **Mutation**: Randomly modify electrodes to explore new solutions
   - **Replacement**: Update population with improved offspring

4. **Termination**: Stop after specified generations or convergence

##### Multi-Objective Optimization (NSGA-II Style)
**Goal**: Find Pareto-optimal trade-off between intensity and focality

**Algorithm**: Non-dominated Sorting Genetic Algorithm II

**Processing Steps**:
1. **Initialization**:
   - Create diverse population of electrode configurations
   - Same format as single-objective

2. **Dual Evaluation**:
   - For each configuration, compute TWO objectives:
     - **Objective 1 (Intensity)**: Maximize field in target ROI
     - **Objective 2 (Focality)**: Minimize field across whole brain
   - Objectives: `[intensity_cost, focality_cost]`

3. **Pareto Front Evolution**:
   - **Non-dominated Sorting**: Rank solutions by dominance
   - **Crowding Distance**: Maintain diversity in objective space
   - **Tournament Selection**: Prefer non-dominated solutions
   - **Genetic Operators**: Smart crossover ensuring electrode validity
   - **Elitism**: Always preserve best Pareto solutions

4. **Pareto Front Refinement**:
   - Evolve population across generations
   - Track best non-dominated solutions
   - Generate complete trade-off curve

#### Phase 4: Result Processing and Visualization
**Steps**:
1. **Montage Formatting**: Convert electrode indices to TI-Toolbox compatible format
2. **CSV Export**: Save electrode configuration with current values
3. **Visualization**: Generate Pareto front plots (multi-objective only)
4. **Validation**: Ensure montage meets TI stimulation constraints

### Evolutionary Process
1. **Initialization**: Random population of electrode configurations
2. **Evaluation**: Calculate objectives for each individual
3. **Selection**: Tournament selection based on Pareto dominance
4. **Crossover**: Smart recombination preserving electrode validity
5. **Mutation**: Controlled changes to explore new solutions
6. **Iteration**: Repeat until convergence

### Objective Functions
- **Intensity Cost**: 1 / (mean field in ROI) - minimized
- **Focality**: Mean field across whole brain - minimized

### Technical Implementation Details
- **Optimization Variables**: 4 electrode indices + 1 current ratio parameter
- **Constraints**: Electrodes must be unique, within bounds, valid for TI stimulation
- **Parallelization**: Thread-based evaluation for multi-core performance
- **Fallback Strategy**: Automatic switch from differential evolution to genetic algorithm if needed
- **Validation**: Ensures montages meet TI stimulation requirements

### Advantages Over Traditional Methods
- **No local optima**: Evolutionary approach explores globally
- **Multiple solutions**: Pareto front provides options
- **Constraint handling**: Ensures valid electrode configurations
- **Scalable**: Works with any number of electrodes

## Best Practices

### For Quick Results
- Use single-objective optimization with 100 generations
- Set population to 50
- ROI radius of 15 mm

### For Research Quality
- Enable multi-objective optimization
- Use 30-50 Pareto solutions with 1000+ iterations
- Consider multiple ROI radii to understand sensitivity
- Export and analyze the full Pareto front data

### Computational Considerations
- Leadfield generation is the most time-consuming step (10-30 min)
- Once generated, optimizations can be run multiple times
- Multi-objective adds ~50% more computation time but provides valuable insights

## Interpreting Results

### Montage Output
- Shows 4 electrodes: 2 pairs for TI stimulation
- Current values indicate stimulation strength
- Electrode names from your EEG cap configuration

### Pareto Front
- **X-axis**: ROI electric field (higher is better)
- **Y-axis**: Whole-brain field (lower is better)
- **Ideal point**: Top-left corner (high intensity, low whole-brain)
- **Trade-off**: Moving right increases focality but reduces intensity

### Convergence Plot
- **Left panel**: Target field strength improvement over optimization runs
- **Right panel**: Optimization cost reduction over runs
- **Best points**: Annotated with arrows showing optimal solutions
- **Purpose**: Monitor optimization progress and assess algorithm convergence

### Montage Summary Plot
- **Top-left**: Text display of the optimized TI montage configuration with electrode names
- **Top-right**: Bar chart showing achieved field strength with reference threshold
- **Bottom-left**: Electrode configuration visualization with anode/cathode coloring
- **Bottom-right**: Complete optimization summary with all parameters
- **Purpose**: Comprehensive overview of single-objective optimization results

### Choosing a Solution
1. **Maximum intensity**: Leftmost point on Pareto front
2. **Maximum focality**: Look for best focality ratio
3. **Balanced**: Middle solutions offer compromise
4. **Application-specific**: Consider your research needs

## Troubleshooting

### Common Issues
- **"No voxels found"**: Increase ROI radius or check coordinates
- **Poor convergence**: Increase generations or population size
- **Multiprocessing errors**: Algorithm automatically falls back to serial mode

### Performance Tips
- Close other applications during optimization
- Use SSD for faster file I/O
- Consider reducing leadfield resolution for initial tests

## References

1. Zhu, Z., et al. (2023). "Multi-objective optimization via evolutionary algorithm for high-definition transcranial electrical stimulation of the human brain." NeuroImage, 280, 120331. [DOI: 10.1016/j.neuroimage.2023.120331](https://doi.org/10.1016/j.neuroimage.2023.120331)

2. Original MOVEA implementation: [github.com/ncclab-sustech/MOVEA](https://github.com/ncclab-sustech/MOVEA)

## See Also
- [TI Simulator](simulator.md) - For running simulations with optimized montages
- [Flex Search](flex-search.md) - Alternative optimization method
- [Analyzer](analyzer.md) - For detailed field analysis
