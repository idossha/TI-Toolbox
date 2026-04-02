"""GUI package for TI-Toolbox.

Provides the PyQt5-based desktop interface that runs inside the Docker
container with X11 forwarding.  The package is organised into three layers:

* **Tabs** -- top-level views (``simulator_tab``, ``analyzer_tab``, etc.)
* **Components** -- reusable widgets shared across tabs (``components/``)
* **Extensions** -- optional plug-in panels (``extensions/``)

See Also
--------
tit.gui.main : Application entry point and ``MainWindow``.
tit.gui.components : Shared widget library.
tit.gui.extensions : Plug-in extension panels.
"""
