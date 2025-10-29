#!/bin/bash

# Initialize .bashrc if it doesn't exist
touch ~/.bashrc

# Source environment setup scripts
[ -f "$FREESURFER_HOME/SetUpFreeSurfer.sh" ] && source "$FREESURFER_HOME/SetUpFreeSurfer.sh"
[ -f "$FSLDIR/etc/fslconf/fsl.sh" ] && source "$FSLDIR/etc/fslconf/fsl.sh"

# Add environment setup to .bashrc
{
    echo "source \"\$FSLDIR/etc/fslconf/fsl.sh\""
    echo "source \"\$FREESURFER_HOME/SetUpFreeSurfer.sh\""
    [ -f "/usr/local/fsl/lib/libstdc++.so.6" ] && echo 'export LD_PRELOAD=/usr/local/fsl/lib/libstdc++.so.6'
} >> ~/.bashrc

# Setup CLI tools if present
if [ -d /ti-toolbox/cli ]; then
    chmod +x /ti-toolbox/cli/*.sh
    export PATH="$PATH:/ti-toolbox/cli"
    {
        echo 'export PATH="$PATH:/ti-toolbox/cli"'
        echo 'alias GUI="/ti-toolbox/cli/GUI.sh"'
        echo 'alias simulator="/ti-toolbox/cli/simulator.sh"'
        echo 'alias pre-process="/ti-toolbox/cli/pre-process.sh"'
        echo 'alias flex-search="/ti-toolbox/cli/flex-search.sh"'
        echo 'alias ex-search="/ti-toolbox/cli/ex-search.sh"'
    } >> ~/.bashrc
fi

# Setup XDG runtime directory
export XDG_RUNTIME_DIR=/tmp/runtime-root
mkdir -p $XDG_RUNTIME_DIR
chmod 700 $XDG_RUNTIME_DIR

# Start interactive shell if no command provided
if [ $# -eq 0 ]; then
    exec /bin/bash
else
    exec "$@"
fi
