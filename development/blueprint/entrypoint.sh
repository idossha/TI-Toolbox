#!/bin/bash

# Source FreeSurfer setup script if available
if [ -f $FREESURFER_HOME/SetUpFreeSurfer.sh ]; then
  source $FREESURFER_HOME/SetUpFreeSurfer.sh
fi

# Source FSL setup script if available
if [ -f $FSLDIR/etc/fslconf/fsl.sh ]; then
  source $FSLDIR/etc/fslconf/fsl.sh
fi

# Add FSL and FreeSurfer sourcing to .bashrc
echo "source \$FSLDIR/etc/fslconf/fsl.sh" >>~/.bashrc
echo "source \$FREESURFER_HOME/SetUpFreeSurfer.sh" >>~/.bashrc

# Make CLI scripts executable and add to PATH
if [ -d /ti-csc/CLI ]; then
  chmod +x /ti-csc/CLI/*.sh
  
  # Add to PATH for current session
  export PATH="$PATH:/ti-csc/CLI"
  
  # Add to .bashrc for future sessions
  echo 'export PATH="$PATH:/ti-csc/CLI"' >>~/.bashrc
  
  # Add aliases to .bashrc only
  echo 'alias GUI="/ti-csc/CLI/GUI.sh"' >>~/.bashrc
  echo 'alias simulator="/ti-csc/CLI/simulator.sh"' >>~/.bashrc
  echo 'alias pre-process="/ti-csc/CLI/pre-process.sh"' >>~/.bashrc
  echo 'alias flex-search="/ti-csc/CLI/flex-search.sh"' >>~/.bashrc
  echo 'alias ex-search="/ti-csc/CLI/ex-search.sh"' >>~/.bashrc
  echo 'alias simulator="/ti-csc/CLI/simulator.sh"' >>~/.bashrc
  
  echo "CLI tools added to PATH and aliases created in .bashrc"
fi

# Ensure XDG_RUNTIME_DIR exists for GUI applications
export XDG_RUNTIME_DIR=/tmp/runtime-root
mkdir -p $XDG_RUNTIME_DIR
chmod 700 $XDG_RUNTIME_DIR

exec "$@"
