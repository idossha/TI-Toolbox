#!/bin/bash

# Setup test project directory with proper BIDS structure and TI-Toolbox configuration
# This script creates a complete test project that can be used with the simulator

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}Setting up test project directory at /mnt/test_projectdir...${NC}"

# Create main project directory structure
mkdir -p /mnt/test_projectdir
cd /mnt/test_projectdir

# Create BIDS structure
mkdir -p sourcedata
mkdir -p derivatives
mkdir -p derivatives/ti-toolbox
mkdir -p derivatives/ti-toolbox/
mkdir -p derivatives/SimNIBS
mkdir -p derivatives/freesurfer
mkdir -p code
mkdir -p code/ti-toolbox
mkdir -p code/ti-toolbox/config

# Create montage_list.json with proper structure
echo -e "${CYAN}Creating montage_list.json...${NC}"
cat > code/ti-toolbox/config/montage_list.json << 'EOF'
{
    "nets": {
        "GSN-HydroCel-256.csv": {
            "uni_polar_montages": {
                "test_montage": [["Fp1", "Fp2"], ["C3", "C4"]],
                "default_montage": [["Fz", "Cz"], ["Pz", "Oz"]]
            },
            "multi_polar_montages": {
                "test_multipolar": [["Fp1", "Fp2", "C3", "C4"]],
                "default_multipolar": [["Fz", "Cz", "Pz", "Oz"]]
            }
        },
        "easycap_BC_TMS64_X21.csv": {
            "uni_polar_montages": {
                "test_montage": [["1", "2"], ["3", "4"]]
            },
            "multi_polar_montages": {
                "test_multipolar": [["1", "2", "3", "4"]]
            }
        },
        "EEG10-20_extended_SPM12.csv": {
            "uni_polar_montages": {
                "test_montage": [["Fp1", "Fp2"], ["C3", "C4"]],
                "default_montage": [["Fz", "Cz"], ["Pz", "Oz"]],
                "frontal_montage": [["Fp1", "Fp2"], ["F3", "F4"]],
                "central_montage": [["C3", "C4"], ["Cz", "Cz"]]
            },
            "multi_polar_montages": {
                "test_multipolar": [["Fp1", "Fp2", "C3", "C4"]],
                "default_multipolar": [["Fz", "Cz", "Pz", "Oz"]],
                "frontal_multipolar": [["Fp1", "Fp2", "F3", "F4"]],
                "central_multipolar": [["C3", "C4", "Cz", "Cz"]]
            }
        },
        "EEG10-10_Cutini_2011.csv": {
            "uni_polar_montages": {
                "test_montage": [["Fp1", "Fp2"], ["C3", "C4"]],
                "default_montage": [["Fz", "Cz"], ["Pz", "Oz"]]
            },
            "multi_polar_montages": {
                "test_multipolar": [["Fp1", "Fp2", "C3", "C4"]],
                "default_multipolar": [["Fz", "Cz", "Pz", "Oz"]]
            }
        },
        "EEG10-10_Neuroelectrics.csv": {
            "uni_polar_montages": {
                "test_montage": [["Fp1", "Fp2"], ["C3", "C4"]],
                "default_montage": [["Fz", "Cz"], ["Pz", "Oz"]]
            },
            "multi_polar_montages": {
                "test_multipolar": [["Fp1", "Fp2", "C3", "C4"]],
                "default_multipolar": [["Fz", "Cz", "Pz", "Oz"]]
            }
        },
        "EEG10-10_UI_Jurak_2007.csv": {
            "uni_polar_montages": {
                "test_montage": [["Fp1", "Fp2"], ["C3", "C4"]],
                "default_montage": [["Fz", "Cz"], ["Pz", "Oz"]]
            },
            "multi_polar_montages": {
                "test_multipolar": [["Fp1", "Fp2", "C3", "C4"]],
                "default_multipolar": [["Fz", "Cz", "Pz", "Oz"]]
            }
        },
        "EEG10-20_Okamoto_2004.csv": {
            "uni_polar_montages": {
                "test_montage": [["Fp1", "Fp2"], ["C3", "C4"]],
                "default_montage": [["Fz", "Cz"], ["Pz", "Oz"]]
            },
            "multi_polar_montages": {
                "test_multipolar": [["Fp1", "Fp2", "C3", "C4"]],
                "default_multipolar": [["Fz", "Cz", "Pz", "Oz"]]
            }
        }
    }
}
EOF

# Create base directory structure
echo -e "${CYAN}Creating directory structure...${NC}"
mkdir -p /mnt/test_projectdir/derivatives/SimNIBS/sub-ernie_extended/m2m_ernie_extended
mkdir -p /mnt/test_projectdir/derivatives/SimNIBS/sub-ernie_extended/Simulations

# Download and setup ErnieExtended data
echo -e "${CYAN}Downloading ErnieExtended data from OSF...${NC}"

# Try downloading with proper OSF URL format
if ! curl -L -f -o /tmp/ErnieExtended.zip "https://osf.io/download/6qv2z/"; then
    echo -e "${YELLOW}First download attempt failed, trying alternative URL...${NC}"
    curl -L -f -o /tmp/ErnieExtended.zip "https://files.osf.io/v1/resources/6qv2z/providers/osfstorage/?zip="
fi

# Verify the download is actually a zip file
if ! file /tmp/ErnieExtended.zip | grep -q "Zip archive"; then
    echo -e "${RED}Downloaded file is not a valid zip archive. Contents:${NC}"
    head -20 /tmp/ErnieExtended.zip
    exit 1
fi

echo -e "${CYAN}Extracting ErnieExtended data...${NC}"
unzip -q /tmp/ErnieExtended.zip -d /tmp/ernie

# Move the contents of m2m_ernie_extended into m2m_ernie
if [ -d "/tmp/ernie/ErnieExtended/m2m_ernie_extended" ]; then
    cp -r /tmp/ernie/ErnieExtended/m2m_ernie_extended/* /mnt/test_projectdir/derivatives/SimNIBS/sub-ernie_extended/m2m_ernie_extended/
else
    find /tmp/ernie -maxdepth 3 -type d -print
    exit 1
fi

# Download and setup "test_montage", this a example of simulation data that will be used for the analyzer testing
echo -e "${CYAN}Downloading test_montage simulation data...${NC}"
curl -L -o /tmp/test_montage.zip "https://archive.org/download/test_montage/test_montage.zip"

echo -e "${CYAN}Extracting test_montage simulation data...${NC}"
unzip -q /tmp/test_montage.zip -d /tmp/ernie_simulation

# Move the contents of test_montage into ernie_extend's simulations
if [ -d "/tmp/ernie_simulation/test_montage" ]; then
    cp -r /tmp/ernie_simulation/test_montage* /mnt/test_projectdir/derivatives/SimNIBS/sub-ernie_extended/Simulations/
    echo -e "${GREEN}✓ Simulation data copied${NC}"
else
    echo -e "${RED}Error: test_montage directory not found${NC}"
    find /tmp/ernie_simulation -maxdepth 3 -type d -print
    exit 1
fi

# Clean up temporary files
rm -rf /tmp/ernie /tmp/ErnieExtended.zip
rm -rf /tmp/ernie_simulation /tmp/test_montage.zip

# Set proper permissions
chmod -R 777 /mnt/test_projectdir