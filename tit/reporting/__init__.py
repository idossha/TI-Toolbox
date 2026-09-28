"""TI-Toolbox reports: self-contained HTML records of a pipeline run (ARCHITECTURE.md §14).

``html/`` is the one report layer (page shell, components, SVG charts, stylesheet, fonts);
``qc_rules`` holds every rule with its role and citation; ``references`` the cited papers;
``generators/`` one module per report — ``dti_qc``, ``simulation``, ``flex_search`` and
``ex_search`` — each with ``python -m tit.reporting.generators.<name>`` to rebuild a report from a
run's outputs. SimNIBS's charm report is copied, not generated (``tit.pre.charm``).
"""
