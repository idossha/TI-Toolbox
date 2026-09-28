# tit.reporting

Self-contained HTML reports, one per pipeline run. The contract is
[ARCHITECTURE.md §14](../../docs/dev/ARCHITECTURE.md); this file only maps the package.

```
tit/reporting/
├── qc_rules.py        # every rule: value, role (gate/internal/advisory/report), citation, plain text
├── references.py      # the cited papers, as data (key, label, citation, DOI)
├── html/
│   ├── components.py  # page shell, components, SVG charts, Check rows, Cites
│   ├── report.css     # tokens (light/dark), layout
│   └── fonts/         # IBM Plex woff2 (OFL), embedded once
└── generators/
    ├── dti_qc.py      # DTI QC           <- tit.pre.qsi.dti_extractor
    ├── simulation.py  # simulator        <- tit.sim.base.BaseSimulation.run, per montage
    ├── flex_search.py # flex-search      <- tit.opt.flex.flex (after flex_meta.json)
    ├── ex_search.py   # ex-search        <- tit.opt.ex.ex (after final_output.csv)
    └── common.py      # what the last three share: current check, cap figure, ROI name, writer
```

TI-Toolbox keeps five report kinds: SimNIBS's own charm report (copied by `tit.pre.charm`), DTI
QC, simulator, flex-search and ex-search. There is no PDF export or print layout, no sidecar file,
no cross-link and no index page.

Every generator reads only what its run wrote and rebuilds from the command line:

```
simnibs_python -m tit.reporting.generators.dti_qc      <project> <subject>              [--out DIR]
simnibs_python -m tit.reporting.generators.simulation  <project> <subject> <simulation> [--out DIR]
simnibs_python -m tit.reporting.generators.flex_search <project> <subject> <run folder> [--out DIR]
simnibs_python -m tit.reporting.generators.ex_search   <project> <subject> <run name>   [--out DIR]
```

Reports are written to `derivatives/ti-toolbox/reports/sub-<id>/<kind>_<YYYYMMDD>_<HHMMSS>.html`
and recorded as a `report` artifact of the running job. The montage figures are the app's own
EEG-cap overlay (`tit.tools.montage_visualizer`), converted to WebP.
