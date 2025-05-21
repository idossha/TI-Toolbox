#!/bin/bash

# Only source FreeSurfer if it exists
if [ -f "$FREESURFER_HOME/SetUpFreeSurfer.sh" ]; then
  echo "Sourcing FreeSurfer setup..."
  source "$FREESURFER_HOME/SetUpFreeSurfer.sh"
fi

# Only source FSL if it exists
if [ -f "$FSLDIR/etc/fslconf/fsl.sh" ]; then
  echo "Sourcing FSL setup..."
  source "$FSLDIR/etc/fslconf/fsl.sh"
fi

# Avoid exporting a non-existent preload
if [ -f "/usr/local/fsl/lib/libstdc++.so.6" ]; then
  export LD_PRELOAD=/usr/local/fsl/lib/libstdc++.so.6
  echo 'export LD_PRELOAD=/usr/local/fsl/lib/libstdc++.so.6' >> ~/.bashrc
fi

# Add CLI tools if present
if [ -d /ti-csc/CLI ]; then
  chmod +x /ti-csc/CLI/*.sh
  export PATH="$PATH:/ti-csc/CLI"
  echo 'export PATH="$PATH:/ti-csc/CLI"' >> ~/.bashrc
  echo 'alias GUI="/ti-csc/CLI/GUI.sh"' >> ~/.bashrc
  echo 'alias simulator="/ti-csc/CLI/simulator.sh"' >> ~/.bashrc
  echo 'alias pre-process="/ti-csc/CLI/pre-process.sh"' >> ~/.bashrc
  echo 'alias flex-search="/ti-csc/CLI/flex-search.sh"' >> ~/.bashrc
  echo 'alias ex-search="/ti-csc/CLI/ex-search.sh"' >> ~/.bashrc
fi

# Runtime directory for GUI
export XDG_RUNTIME_DIR=/tmp/runtime-root
mkdir -p $XDG_RUNTIME_DIR
chmod 700 $XDG_RUNTIME_DIR

exec "$@"
