#!/usr/bin/env bats
# Integration tests for ex-search analyzer

setup() {
    # Setup test environment
    export TEST_DIR="${BATS_TEST_DIRNAME}/../test_data/ex_search_integration"
    export EX_ANALYZER="${BATS_TEST_DIRNAME}/../ti-toolbox/opt/ex/ex_analyzer.py"

    # Create test directories
    mkdir -p "${TEST_DIR}/opt"
    mkdir -p "${TEST_DIR}/roi"
}

teardown() {
    # Cleanup test directories
    if [ -d "${TEST_DIR}" ]; then
        rm -rf "${TEST_DIR}"
    fi
}

@test "Ex-Search: Analyzer script exists" {
    [ -f "${EX_ANALYZER}" ]
}

@test "Ex-Search: Analyzer module can be imported" {
    run simnibs_python -c "import sys; sys.path.insert(0, '${BATS_TEST_DIRNAME}/../ti-toolbox'); from opt.ex.ex_analyzer import analyze_ex_search; print('OK')"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "OK" ]]
}

@test "Ex-Search: ROICoordinateHelper can be imported" {
    run simnibs_python -c "import sys; sys.path.insert(0, '${BATS_TEST_DIRNAME}/../ti-toolbox'); from opt.roi import ROICoordinateHelper; print('OK')"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "OK" ]]
}

@test "Ex-Search: Can create and load ROI CSV file" {
    # Create ROI CSV
    cat > "${TEST_DIR}/roi/test_roi.csv" <<EOF
x,y,z
10.5,20.5,30.5
EOF

    run simnibs_python -c "
import sys
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../ti-toolbox')
from opt.roi import ROICoordinateHelper

coords = ROICoordinateHelper.load_roi_from_csv('${TEST_DIR}/roi/test_roi.csv')
assert coords is not None
assert len(coords) == 3
print(f'Loaded coordinates: {coords}')
"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "Loaded coordinates" ]]
}

@test "Ex-Search: analyze_ex_search handles empty directory" {
    run simnibs_python -c "
import sys
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../ti-toolbox')
from opt.ex.ex_analyzer import analyze_ex_search
from unittest.mock import MagicMock

logger = MagicMock()
result = analyze_ex_search(
    '${TEST_DIR}/opt',
    '${TEST_DIR}/roi',
    [],
    '/fake/m2m',
    logger
)
print('Analysis completed')
"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "completed" ]]
}

@test "Ex-Search: Creates analysis directory" {
    run simnibs_python -c "
import sys
import os
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../ti-toolbox')
from opt.ex.ex_analyzer import analyze_ex_search
from unittest.mock import MagicMock

logger = MagicMock()
analyze_ex_search(
    '${TEST_DIR}/opt',
    '${TEST_DIR}/roi',
    [],
    '/fake/m2m',
    logger
)

analysis_dir = os.path.join('${TEST_DIR}/opt', 'analysis')
assert os.path.exists(analysis_dir), 'Analysis directory should be created'
print('Analysis directory created')
"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "created" ]]
    [ -d "${TEST_DIR}/opt/analysis" ]
}

@test "Ex-Search: ROI utility functions work correctly" {
    run simnibs_python -c "
import sys
import numpy as np
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../ti-toolbox')
from opt.ti_calculations import find_roi_element_indices

# This function is imported from core.utils
# Test that import chain works
print('Import successful')
"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "successful" ]]
}

@test "Ex-Search: ti_calculations bridge module works" {
    run simnibs_python -c "
import sys
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../ti-toolbox')
from opt import ti_calculations

# Test that all expected functions are available
assert hasattr(ti_calculations, 'get_TI_vectors')
assert hasattr(ti_calculations, 'envelope')
assert hasattr(ti_calculations, 'calculate_ti_field_from_leadfield')
assert hasattr(ti_calculations, 'find_target_voxels')
assert hasattr(ti_calculations, 'validate_ti_montage')

print('All functions available')
"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "available" ]]
}

@test "Ex-Search: find_target_voxels works correctly" {
    run simnibs_python -c "
import sys
import numpy as np
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../ti-toolbox')
from opt.ti_calculations import find_target_voxels

# Create test voxel positions
positions = np.array([
    [0, 0, 0],
    [5, 0, 0],
    [10, 0, 0],
    [0, 5, 0],
    [0, 0, 5]
])

# Find voxels within 6mm of origin
indices = find_target_voxels(positions, [0, 0, 0], 6.0)

# Should find (0,0,0), (5,0,0), (0,5,0), (0,0,5)
assert len(indices) == 4
print(f'Found {len(indices)} voxels')
"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "Found 4 voxels" ]]
}

@test "Ex-Search: validate_ti_montage validates correctly" {
    run simnibs_python -c "
import sys
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../ti-toolbox')
from opt.ti_calculations import validate_ti_montage

# Valid montage
assert validate_ti_montage([0, 1, 2, 3], 75) == True

# Invalid - wrong number of electrodes
assert validate_ti_montage([0, 1, 2], 75) == False
assert validate_ti_montage([0, 1, 2, 3, 4], 75) == False

# Invalid - duplicates
assert validate_ti_montage([0, 0, 1, 2], 75) == False

# Invalid - out of range
assert validate_ti_montage([0, 1, 2, 100], 75) == False

# Invalid - negative
assert validate_ti_montage([-1, 0, 1, 2], 75) == False

print('All validation tests passed')
"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "passed" ]]
}

@test "Ex-Search: ROI coordinate helper handles invalid files" {
    run simnibs_python -c "
import sys
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../ti-toolbox')
from opt.roi import ROICoordinateHelper

# Non-existent file
coords = ROICoordinateHelper.load_roi_from_csv('/nonexistent/file.csv')
assert coords is None

print('Invalid file handled correctly')
"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "correctly" ]]
}

@test "Ex-Search: Backward compatibility aliases work" {
    run simnibs_python -c "
import sys
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../ti-toolbox')
from opt.ti_calculations import calculate_ti_field, calculate_ti_field_from_leadfield

# Should be the same function
assert calculate_ti_field is calculate_ti_field_from_leadfield

print('Backward compatibility maintained')
"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "maintained" ]]
}

@test "Ex-Search: All __all__ exports are available" {
    run simnibs_python -c "
import sys
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../ti-toolbox')
import opt.ti_calculations as tc

expected_exports = [
    'get_TI_vectors',
    'envelope',
    'calculate_ti_field_from_leadfield',
    'calculate_ti_field',
    'create_stim_patterns',
    'find_roi_element_indices',
    'find_grey_matter_indices',
    'calculate_roi_metrics',
    'find_target_voxels',
    'validate_ti_montage'
]

for export in expected_exports:
    assert hasattr(tc, export), f'Missing export: {export}'

print('All exports available')
"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "available" ]]
}
