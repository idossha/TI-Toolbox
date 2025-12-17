---
layout: wiki
title: MOVEA Optimization
permalink: /wiki/movea-opt/
---

**THis is an experimental feature and may not work as expected, please report any issues**

MOVEA (Multi-Objective Optimization via Evolutionary Algorithm) is an advanced optimization method for finding optimal electrode montages for Temporal Interference (TI) stimulation. This implementation is based on the original MOVEA algorithm developed by the Neural Control and Computation Lab at SUSTech.

**Original Project**: [MOVEA on GitHub](https://github.com/ncclab-sustech/MOVEA)  
**Original Paper**: [Zhu et al., 2023](https://doi.org/10.1016/j.neuroimage.2023.120331) - "MOVEA: Multi-objective optimization via evolutionary algorithm for high-definition transcranial electrical stimulation of the human brain"


### TI-Toolbox Implementation of MOVEA
- **NSGA-II style evolutionary algorithm** for true multi-objective optimization
- **Parallel evaluation** using threading for faster computation
- **Smart genetic operators** ensuring valid electrode configurations
- **Elitism** to preserve best solutions across generations

## GUI Usage

<img src="{{ site.baseurl }}/assets/imgs/wiki/movea-opt/mova_UI.png" alt="MOVEA Optimization Interface" style="width: 80%; max-width: 700px;">

*Figure: MOVEA optimization GUI showing the main interface with target selection, parameter configuration, and optimization controls*

### Basic Workflow
1. **Generate or Load Leadfield**: Create the leadfield matrix for your subject
2. **Set Target**: Choose a preset ROI or enter custom MNI coordinates
3. **Configure Parameters**: Adjust optimization settings as needed
4. **Run Optimization**: Single-objective for fast results or multi-objective for detailed analysis
5. **Analyze Results**: Review the optimal montage and optionally the Pareto front

### Parameter Guidelines

Have not expereimented with it enough, TBD.

### Output Files

The optimization generates several output files in the derivatives folder:

1. **movea_montage.csv**: Main result file with electrode configuration
2. **pareto_front.png**: Visualization of intensity vs focality trade-off (multi-objective only)
3. **pareto_solutions.csv**: Detailed data for all Pareto-optimal solutions (multi-objective only)
4. **convergence.png**: Optimization progress plot showing field strength and cost convergence (when multiple runs)
5. **montage_summary.png**: Comprehensive summary plot of single-objective optimization results

## Visualization Examples

### Single-Objective Optimization Results

<img src="{{ site.baseurl }}/assets/imgs/wiki/movea-opt/movea_single.png" alt="MOVEA Single-Objective Results" style="width: 80%; max-width: 700px;">
*Figure: Single-objective optimization summary showing optimal electrode montage and field distribution*

### Multi-Objective Optimization Results

<img src="{{ site.baseurl }}/assets/imgs/wiki/movea-opt/movea_multi.png" alt="MOVEA Single-Objective Results" style="width: 80%; max-width: 600px;">

*Figure: Multi-objective optimization Pareto front showing trade-off between intensity and focality*


#### Optimization Algorithms

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
