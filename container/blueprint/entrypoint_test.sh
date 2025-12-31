#!/bin/bash
set -e

echo "Setting up test project directory structure..."

# Create test project directory structure
# Note: SimNIBS sub-directories are created during Docker build for downloads
mkdir -p /opt/test_projectdir/sourcedata \
    && mkdir -p /opt/test_projectdir/derivatives/ti-toolbox \
    && mkdir -p /opt/test_projectdir/derivatives/SimNIBS \
    && mkdir -p /opt/test_projectdir/derivatives/freesurfer \
    && mkdir -p /opt/test_projectdir/code/tit/config

# Copy electrode caps from mounted TI-Toolbox to SimNIBS directory
if [ -d "$SIMNIBSDIR" ] && [ -d "/ti-toolbox/resources/ElectrodeCaps_MNI" ]; then
    echo "Copying electrode caps from TI-Toolbox to SimNIBS..."
    mkdir -p "$SIMNIBSDIR/resources/ElectrodeCaps_MNI/"
    cp -f /ti-toolbox/resources/ElectrodeCaps_MNI/*.csv "$SIMNIBSDIR/resources/ElectrodeCaps_MNI/" 2>/dev/null || true
fi

# Create montage_list.json with proper structure
cat > /opt/test_projectdir/code/ti-toolbox/config/montage_list.json << 'EOF'
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
                "central_multipolar": [["C3", "C4"], ["Cz", "Cz"]]
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

# The test data (ErnieExtended and test_montage) has already been downloaded and placed
# in /opt/test_projectdir during the Docker build process.

# If /mnt/test_projectdir is mounted (tests expect data there), copy the pre-baked data
if [ -d "/mnt/test_projectdir" ]; then
    echo "Copying pre-baked test data to mount point..."
    cp -r /opt/test_projectdir/* /mnt/test_projectdir/ 2>/dev/null || true
    chmod -R 777 /mnt/test_projectdir
else
    # Otherwise, create symlink for backward compatibility
    ln -sf /opt/test_projectdir /mnt/test_projectdir 2>/dev/null || true
    chmod -R 777 /opt/test_projectdir
fi

echo "Test project setup complete."

# Execute the command passed to the container (if any)
if [ $# -gt 0 ]; then
    echo "Executing command: $@"
    exec "$@"
else
    echo "No command specified, exiting."
fi
