TI-Toolbox API Reference
========================

Welcome to the TI-Toolbox API documentation. This reference covers the Python API for programmatic use of TI-Toolbox components.

.. note::
   For user guides and tutorials, see the main `TI-Toolbox Documentation <../index.html>`_.

Quick Start
-----------

The TI-Toolbox Python API provides programmatic access to simulation, analysis, and optimization tools:

.. code-block:: python

   from tit.sim import simulator, config
   from tit.analyzer import mesh_analyzer
   from tit.core import get_path_manager

   # Configure simulation
   sim_config = config.SimulationConfig(
       subject_id="001",
       project_dir="/path/to/project",
       conductivity_type=config.ConductivityType.SCALAR,
       intensities=config.IntensityConfig(pair1=2.0, pair2=2.0),
       electrode=config.ElectrodeConfig(),
       eeg_net="EGI_template.csv"
   )

   # Run simulation
   results = simulator.run_simulation(sim_config, montages)

   # Analyze results
   analyzer = mesh_analyzer.MeshAnalyzer(
       field_mesh_path="/path/to/mesh.msh",
       field_name="TI_max",
       subject_dir="/path/to/m2m",
       output_dir="/path/to/output"
   )
   results = analyzer.analyze_sphere([0, 0, 0], radius=10)

API Modules
-----------

.. toctree::
   :maxdepth: 2
   :caption: Core Modules

   core/index

.. toctree::
   :maxdepth: 2
   :caption: Simulation

   sim/index

.. toctree::
   :maxdepth: 2
   :caption: Analysis

   analyzer/index

.. toctree::
   :maxdepth: 2
   :caption: Optimization

   opt/index

.. toctree::
   :maxdepth: 2
   :caption: Statistics

   stats/index

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
