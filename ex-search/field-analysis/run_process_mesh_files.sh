#!/bin/bash
# Function to find MATLAB Runtime
find_matlab_runtime() {
    local potential_paths=(
        "/usr/local/MATLAB/MATLAB_Runtime/R2024a"
        "/usr/local/MATLAB/MATLAB_Runtime/v951"
        "/opt/MATLAB/MATLAB_Runtime/R2024a"
        "/home/$USER/MATLAB_Runtime/R2024a"
    )

    for path in "${potential_paths[@]}"; do
        if [ -d "$path" ]; then
            echo "$path"
            return 0
        fi
    done
    echo "MATLAB Runtime not found. Please install it or update the script with the correct path."
    exit 1
}

exe_name=$0
exe_dir=$(cd "$(dirname $0)" && pwd) # Get the absolute path of the script directory

echo "--------------------------------------"
echo "Setting up environment variables"
MCROOT=$(find_matlab_runtime)
echo "MATLAB Runtime root: ${MCROOT}"
echo "--------------------------------------"

LD_LIBRARY_PATH=.:${MCROOT}/runtime/glnxa64
LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:${MCROOT}/bin/glnxa64
LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:${MCROOT}/sys/os/glnxa64
LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:${MCROOT}/sys/java/jre/glnxa64/jre/lib/amd64
export LD_LIBRARY_PATH

echo "LD_LIBRARY_PATH is ${LD_LIBRARY_PATH}"
echo "--------------------------------------"

# Create a symlink if the exact version of the library is missing
if [ ! -f "${MCROOT}/runtime/glnxa64/libmwmclmcrrt.so.25.1" ]; then
    echo "libmwmclmcrrt.so.25.1 not found. Attempting to create a symlink to libmwmclmcrrt.so.24.1"
    ln -s ${MCROOT}/runtime/glnxa64/libmwmclmcrrt.so.24.1 ${MCROOT}/runtime/glnxa64/libmwmclmcrrt.so.25.1
fi

mesh_dir=$1
echo "Mesh directory: $mesh_dir"

# Execute the MATLAB compiled script with the provided arguments
eval "\"${exe_dir}/process_mesh_files\"" "$mesh_dir"
exit
