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
mkdir -p derivatives/ti-toolbox/tissue_analysis
mkdir -p derivatives/ti-toolbox/logs
mkdir -p derivatives/ti-toolbox/reports
mkdir -p derivatives/ti-toolbox/.ti-toolbox-info
mkdir -p derivatives/SimNIBS
mkdir -p derivatives/SimNIBS/sub-ernie
mkdir -p derivatives/freesurfer
mkdir -p code
mkdir -p code/ti-toolbox
mkdir -p code/ti-toolbox/config

# Copy example data (m2m_ernie directory)
if [ -d "/development/example_data/ernie/m2m_ernie/" ]; then
    echo -e "${CYAN}Copying example data...${NC}"
    cp -r /development/example_data/ernie/m2m_ernie/ derivatives/SimNIBS/sub-ernie/
else
    echo -e "${YELLOW}Warning: Example data not found at /development/example_data/ernie/m2m_ernie/${NC}"
    # Create minimal m2m structure
    mkdir -p derivatives/SimNIBS/sub-ernie/eeg_positions
    mkdir -p derivatives/SimNIBS/sub-ernie/surfaces
fi

# Create BIDS dataset_description.json in project root
echo -e "${CYAN}Creating BIDS dataset_description.json...${NC}"
cat > dataset_description.json << 'EOF'
{
    "Name": "test_projectdir",
    "BIDSVersion": "1.8.0",
    "DatasetType": "raw",
    "License": "CC0",
    "Authors": ["Test User"],
    "Acknowledgements": "Test dataset for TI-Toolbox",
    "HowToAcknowledge": "Please cite this dataset if you use it in your research",
    "Funding": ["Test funding"],
    "EthicsApprovals": ["Test ethics approval"],
    "ReferencesAndLinks": ["Test reference"],
    "DatasetDOI": "10.0000/test"
}
EOF

# Create ti-toolbox derivative dataset_description.json
echo -e "${CYAN}Creating ti-toolbox derivative dataset_description.json...${NC}"
mkdir -p derivatives/ti-toolbox
cat > derivatives/ti-toolbox/dataset_description.json << 'EOF'
{
    "Name": "ti-toolbox",
    "BIDSVersion": "1.8.0",
    "DatasetType": "derivative",
    "GeneratedBy": [
        {
            "Name": "TI-Toolbox",
            "Version": "2.0",
            "Description": "Temporal Interference simulation toolbox"
        }
    ],
    "SourceDatasets": [
        {
            "URI": "bids:test_projectdir@2024-01-01",
            "DOI": "10.0000/test"
        }
    ],
    "PipelineDescription": {
        "Name": "TI-Toolbox",
        "Version": "2.0",
        "CodeURL": "https://github.com/example/ti-toolbox"
    }
}
EOF

# Create SimNIBS derivative dataset_description.json
echo -e "${CYAN}Creating SimNIBS derivative dataset_description.json...${NC}"
mkdir -p derivatives/SimNIBS
cat > derivatives/SimNIBS/dataset_description.json << 'EOF'
{
    "Name": "SimNIBS",
    "BIDSVersion": "1.8.0",
    "DatasetType": "derivative",
    "GeneratedBy": [
        {
            "Name": "SimNIBS",
            "Version": "4.0",
            "Description": "Simulation of Non-Invasive Brain Stimulation"
        }
    ],
    "SourceDatasets": [
        {
            "URI": "bids:test_projectdir@2024-01-01",
            "DOI": "10.0000/test"
        }
    ]
}
EOF

# Create FreeSurfer derivative dataset_description.json
echo -e "${CYAN}Creating FreeSurfer derivative dataset_description.json...${NC}"
mkdir -p derivatives/freesurfer
cat > derivatives/freesurfer/dataset_description.json << 'EOF'
{
    "Name": "freesurfer",
    "BIDSVersion": "1.8.0",
    "DatasetType": "derivative",
    "GeneratedBy": [
        {
            "Name": "FreeSurfer",
            "Version": "7.4",
            "Description": "FreeSurfer cortical surface reconstruction"
        }
    ],
    "SourceDatasets": [
        {
            "URI": "bids:test_projectdir@2024-01-01",
            "DOI": "10.0000/test"
        }
    ]
}
EOF

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

# Create EEG position files for testing
echo -e "${CYAN}Creating EEG position files...${NC}"
mkdir -p derivatives/SimNIBS/sub-ernie/eeg_positions

# Copy actual EEG position files from example data if available
if [ -d "/development/example_data/ernie/m2m_ernie/eeg_positions/" ]; then
    echo -e "${CYAN}Copying EEG position files from example data...${NC}"
    cp /development/example_data/ernie/m2m_ernie/eeg_positions/*.csv derivatives/SimNIBS/sub-ernie/eeg_positions/
else
    echo -e "${YELLOW}Warning: Example EEG position files not found, creating minimal files...${NC}"
    
    # Create EGI template CSV
    cat > derivatives/SimNIBS/sub-ernie/eeg_positions/EGI_template.csv << 'EOF'
Fp1,0,0,0
Fp2,1,1,1
Fz,2,2,2
Cz,3,3,3
C3,4,4,4
C4,5,5,5
Pz,6,6,6
Oz,7,7,7
E1,8,8,8
E2,9,9,9
E3,10,10,10
E4,11,11,11
EOF

    # Create easycap template CSV
    cat > derivatives/SimNIBS/sub-ernie/eeg_positions/easycap_BC_TMS64_X21.csv << 'EOF'
1,0,0,0
2,1,1,1
3,2,2,2
4,3,3,3
5,4,4,4
6,5,5,5
EOF

    # Create EEG10-20_extended_SPM12 CSV
    cat > derivatives/SimNIBS/sub-ernie/eeg_positions/EEG10-20_extended_SPM12.csv << 'EOF'
Fp1,-25.54850942295779,111.13115953748702,26.339920653883464
Fpz,3.346674460645326,115.9919235507693,31.258556501955386
Fp2,32.56836574272711,112.61800559873073,23.5995665387631
AF9,-44.19674336154764,99.41174454761736,-15.058983609856956
AF7,-49.825685808732075,96.8629289120403,20.843106428132746
AF5,-40.986733952830555,98.4620543097189,36.804065301026924
AF3,-29.22706332787313,99.72249184078842,51.76081311690678
AF1,-13.427475995149251,99.06891300240311,61.835623155394174
AFz,4.757195374131389,100.118841997895,63.82552211291642
AF2,23.887216786868663,99.91248606156294,60.51147477714294
AF4,39.721344814579474,100.66092997620242,49.85514691743633
AF6,49.29819014051411,99.43590308984857,32.73139764091498
AF8,56.55609795454048,97.46823642790696,14.803514955913451
AF10,47.52359640020488,96.79627832931786,-21.03047167469089
F9,-65.03115968841914,77.60571643058061,-23.698182833054496
F7,-64.80557007090417,72.24848930414088,12.849586958611194
F5,-44.43723021179237,80.91966474976905,57.294946263009884
F3,-44.43723021179237,80.91966474976905,57.294946263009884
F1,-13.427475995149251,99.06891300240311,61.835623155394174
Fz,3.251521571664626,82.61807498582378,79.9351872818211
F2,23.887216786868663,99.91248606156294,60.51147477714294
F4,51.056380889746386,81.32180263703862,57.886553647208885
F6,51.056380889746386,81.32180263703862,57.886553647208885
F8,71.11941894980622,73.58139545760777,10.895362141959795
F10,65.03115968841914,77.60571643058061,-23.698182833054496
FC9,-65.03115968841914,77.60571643058061,-23.698182833054496
FC7,-64.80557007090417,72.24848930414088,12.849586958611194
FC5,-44.43723021179237,80.91966474976905,57.294946263009884
FC3,-44.43723021179237,80.91966474976905,57.294946263009884
FC1,-13.427475995149251,99.06891300240311,61.835623155394174
FCz,3.251521571664626,82.61807498582378,79.9351872818211
FC2,23.887216786868663,99.91248606156294,60.51147477714294
FC4,51.056380889746386,81.32180263703862,57.886553647208885
FC6,51.056380889746386,81.32180263703862,57.886553647208885
FC8,71.11941894980622,73.58139545760777,10.895362141959795
FC10,65.03115968841914,77.60571643058061,-23.698182833054496
C9,-65.03115968841914,77.60571643058061,-23.698182833054496
C7,-64.80557007090417,72.24848930414088,12.849586958611194
C5,-44.43723021179237,80.91966474976905,57.294946263009884
C3,-60.61955512549808,13.244359262576861,69.8167048168236
C1,-13.427475995149251,99.06891300240311,61.835623155394174
Cz,2.007021915204973,12.242965946667663,99.17761363972069
C2,23.887216786868663,99.91248606156294,60.51147477714294
C4,66.58579917768242,12.764709168116378,67.2895249258904
C6,51.056380889746386,81.32180263703862,57.886553647208885
C8,71.11941894980622,73.58139545760777,10.895362141959795
C10,65.03115968841914,77.60571643058061,-23.698182833054496
CP9,-65.03115968841914,77.60571643058061,-23.698182833054496
CP7,-64.80557007090417,72.24848930414088,12.849586958611194
CP5,-44.43723021179237,80.91966474976905,57.294946263009884
CP3,-60.61955512549808,13.244359262576861,69.8167048168236
CP1,-13.427475995149251,99.06891300240311,61.835623155394174
CPz,2.007021915204973,12.242965946667663,99.17761363972069
CP2,23.887216786868663,99.91248606156294,60.51147477714294
CP4,66.58579917768242,12.764709168116378,67.2895249258904
CP6,51.056380889746386,81.32180263703862,57.886553647208885
CP8,71.11941894980622,73.58139545760777,10.895362141959795
CP10,65.03115968841914,77.60571643058061,-23.698182833054496
P9,-65.03115968841914,77.60571643058061,-23.698182833054496
P7,-64.80557007090417,72.24848930414088,12.849586958611194
P5,-44.43723021179237,80.91966474976905,57.294946263009884
P3,-49.770033949194314,-55.866832348567286,54.5611421483596
P1,-13.427475995149251,99.06891300240311,61.835623155394174
Pz,0.5780916823187474,-63.39441912483082,76.99972918779469
P2,23.887216786868663,99.91248606156294,60.51147477714294
P4,51.88329964505225,-55.743976768532264,52.90617889294789
P6,51.056380889746386,81.32180263703862,57.886553647208885
P8,71.11941894980622,73.58139545760777,10.895362141959795
P10,65.03115968841914,77.60571643058061,-23.698182833054496
PO9,-65.03115968841914,77.60571643058061,-23.698182833054496
PO7,-64.80557007090417,72.24848930414088,12.849586958611194
PO5,-44.43723021179237,80.91966474976905,57.294946263009884
PO3,-49.770033949194314,-55.866832348567286,54.5611421483596
PO1,-13.427475995149251,99.06891300240311,61.835623155394174
POz,0.5780916823187474,-63.39441912483082,76.99972918779469
PO2,23.887216786868663,99.91248606156294,60.51147477714294
PO4,51.88329964505225,-55.743976768532264,52.90617889294789
PO6,51.056380889746386,81.32180263703862,57.886553647208885
PO8,71.11941894980622,73.58139545760777,10.895362141959795
PO10,65.03115968841914,77.60571643058061,-23.698182833054496
O9,-65.03115968841914,77.60571643058061,-23.698182833054496
O7,-64.80557007090417,72.24848930414088,12.849586958611194
O5,-44.43723021179237,80.91966474976905,57.294946263009884
O3,-49.770033949194314,-55.866832348567286,54.5611421483596
O1,-13.427475995149251,99.06891300240311,61.835623155394174
Oz,0.5780916823187474,-63.39441912483082,76.99972918779469
O2,23.887216786868663,99.91248606156294,60.51147477714294
O4,51.88329964505225,-55.743976768532264,52.90617889294789
O6,51.056380889746386,81.32180263703862,57.886553647208885
O8,71.11941894980622,73.58139545760777,10.895362141959795
O10,65.03115968841914,77.60571643058061,-23.698182833054496
EOF
fi

# Copy EEG files to m2m directory if it exists
if [ -d "derivatives/SimNIBS/sub-ernie/m2m_ernie" ]; then
    mkdir -p derivatives/SimNIBS/sub-ernie/m2m_ernie/eeg_positions
    cp derivatives/SimNIBS/sub-ernie/eeg_positions/* derivatives/SimNIBS/sub-ernie/m2m_ernie/eeg_positions/
fi

# Create project status file
echo -e "${CYAN}Creating project status file...${NC}"
cat > derivatives/ti-toolbox/.ti-toolbox-info/project_status.json << 'EOF'
{
    "project_created": "2024-01-01T00:00:00.000000",
    "last_updated": "2024-01-01T00:00:00.000000",
    "config_created": true,
    "user_preferences": {
        "show_welcome": true
    },
    "project_metadata": {
        "name": "test_projectdir",
        "path": "/mnt/test_projectdir",
        "version": "2.0"
    }
}
EOF

# Set proper permissions
echo -e "${CYAN}Setting permissions...${NC}"
chmod -R 755 /mnt/test_projectdir
chmod 777 code/ti-toolbox
chmod 777 code/ti-toolbox/config
chmod 777 code/ti-toolbox/config/montage_list.json
chmod 777 derivatives/ti-toolbox
chmod 777 derivatives/ti-toolbox/.ti-toolbox-info
chmod 777 derivatives/ti-toolbox/.ti-toolbox-info/project_status.json

# Export environment variable
export PROJECT_DIR_NAME=test_projectdir

echo -e "${GREEN}Test project directory setup completed successfully!${NC}"
echo -e "${CYAN}Project structure:${NC}"
echo "  - BIDS dataset_description.json files created"
echo "  - montage_list.json created with test montages"
echo "  - EEG position files created"
echo "  - Project status initialized"
echo "  - Proper permissions set"
echo ""
echo -e "${CYAN}The test project is now ready for simulator testing.${NC}"