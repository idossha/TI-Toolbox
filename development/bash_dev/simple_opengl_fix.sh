#!/bin/bash

echo "Setting up minimal OpenGL configuration for Linux applications..."

# Create runtime directory
mkdir -p /tmp/runtime-root
chmod 700 /tmp/runtime-root

# Set essential software rendering environment variables
export LIBGL_ALWAYS_SOFTWARE=1
export LIBGL_ALWAYS_INDIRECT=0
export XDG_RUNTIME_DIR=/tmp/runtime-root
export QT_X11_NO_MITSHM=1

# Update environment for current session
cat > ~/.opengl_config << EOF
export LIBGL_ALWAYS_SOFTWARE=1
export LIBGL_ALWAYS_INDIRECT=0
export XDG_RUNTIME_DIR=/tmp/runtime-root
export QT_X11_NO_MITSHM=1
EOF

# Source the config in bashrc if not already present
if ! grep -q "source ~/.opengl_config" ~/.bashrc; then
    echo "source ~/.opengl_config" >> ~/.bashrc
fi

# Source the configuration immediately
source ~/.opengl_config

echo ""
echo "Basic OpenGL configuration complete!"
echo ""
echo "The following applications should now work:"
echo "  freeview"
echo "  fsleyes"
echo "  gmsh"
echo "" 