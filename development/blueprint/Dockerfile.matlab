# Dockerfile.matlab
FROM ubuntu:20.04

# Set noninteractive mode for apt-get
ENV DEBIAN_FRONTEND=noninteractive

# Install necessary packages
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Set MATLAB Runtime version and installation directory
ENV MATLAB_RUNTIME_INSTALL_DIR=/usr/local/MATLAB/MATLAB_Runtime

# Download and install MATLAB Runtime R2024a
RUN wget https://ssd.mathworks.com/supportfiles/downloads/R2024a/Release/1/deployment_files/installer/complete/glnxa64/MATLAB_Runtime_R2024a_Update_1_glnxa64.zip -P /tmp \
    && unzip -q /tmp/MATLAB_Runtime_R2024a_Update_1_glnxa64.zip -d /tmp/matlab_runtime_installer \
    && /tmp/matlab_runtime_installer/install -destinationFolder ${MATLAB_RUNTIME_INSTALL_DIR} -agreeToLicense yes -mode silent \
    && rm -rf /tmp/MATLAB_Runtime_R2024a_Update_1_glnxa64.zip /tmp/matlab_runtime_installer

# Set environment variables
ENV LD_LIBRARY_PATH=${MATLAB_RUNTIME_INSTALL_DIR}/v124/runtime/glnxa64:${MATLAB_RUNTIME_INSTALL_DIR}/v124/bin/glnxa64:${MATLAB_RUNTIME_INSTALL_DIR}/v124/sys/os/glnxa64:${LD_LIBRARY_PATH}
ENV XAPPLRESDIR=${MATLAB_RUNTIME_INSTALL_DIR}/v124/X11/app-defaults 