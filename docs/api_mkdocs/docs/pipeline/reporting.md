# Reporting & Visualization

TI-Toolbox writes one self-contained HTML report per pipeline run. There are five kinds:
SimNIBS's own charm report (copied from `m2m_<id>/charm_report.html` when charm finishes), and
DTI QC, simulator, flex-search and ex-search reports, which the pipelines write themselves when
they finish. There is no report object to build by hand: each generator reads what its run wrote,
and rebuilds a report from the command line (inside the container):

```bash
simnibs_python -m tit.reporting.generators.dti_qc      /mnt/project 001                 [--out DIR]
simnibs_python -m tit.reporting.generators.simulation  /mnt/project 001 motor_cortex    [--out DIR]
simnibs_python -m tit.reporting.generators.flex_search /mnt/project 001 <run folder>    [--out DIR]
simnibs_python -m tit.reporting.generators.ex_search   /mnt/project 001 <run name>      [--out DIR]
```

or from Python:

```python
from tit.reporting.generators.simulation import create_simulation_report

path = create_simulation_report("/mnt/project", "001", "motor_cortex")
```

A simulator report opens with the result and the key numbers, the montage on the EEG cap,
the conductivity model, the TI envelope through the ROI (when the Analyzer has run on the
simulation) against the published range, and the safety advisories; rebuild it after an ROI
analysis to include it. Every check shows its role (gate, software check, advisory, reported)
and citation; the rules are in `tit.reporting.qc_rules.RULES`.

## Plotting Utilities

The `tit.plotting` module provides visualization functions used by the analysis and reporting pipelines:

```python
from tit.analyzer.visualizer import save_histogram
from tit.plotting import (
    plot_permutation_null_distribution,
    plot_cluster_size_mass_correlation,
    plot_montage_distributions,
    plot_intensity_vs_focality,
)
```

!!! note "Plotting Context"
    Most plotting functions are called internally by the `Analyzer` and report generators. You typically do not need to call them directly unless building custom visualizations.

## Output Location

Reports are saved under the BIDS derivatives tree:

```
derivatives/ti-toolbox/reports/sub-001/
├── charm_report.html
├── dti_qc_20250101_120000.html
├── simulation_report_20250101_120000.html
├── flex_search_report_20250101_120000.html
└── ex_search_report_20250101_120000.html
```

## API Reference

::: tit.reporting.generators.simulation.create_simulation_report
    options:
      show_root_heading: true

::: tit.reporting.generators.flex_search.create_flex_search_report
    options:
      show_root_heading: true

::: tit.reporting.generators.ex_search.create_ex_search_report
    options:
      show_root_heading: true

::: tit.reporting.generators.dti_qc.create_dti_qc_report
    options:
      show_root_heading: true
