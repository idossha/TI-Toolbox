# TI-Toolbox Command Line Interface Scripts

This directory contains command-line interface scripts.
## Scripts

- **GUI.sh** - Launches the GUI application
- **pre-process.sh**     - CLI for preprocessing operations
- **flex-search.sh**     - CLI for flexible electrode position search
- **ex-search.sh**       - CLI for exhaustive search optimization for electrode position.
- **simulator.sh**       - CLI for running simulations
- **analyzer.sh**        - CLI for running analysis on simulation output
- **group_analyzer.sh**  - CLI for running group analysis on simualtion output 

## Usage

These scripts can be executed directly from the command line. For example: `GUI` to launch the GUI or `simulator` to start the simulator CLI. 


## Dependencies

The execuatble nature depends on the content of the .bashrc that is configured in the `Dockerfile.simnibs` and `entrypoint.sh`
