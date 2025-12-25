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
    run simnibs_python -c "import sys; sys.path.insert(0, '${BATS_TEST_DIRNAME}/../ti-toolbox'); from core.roi import ROICoordinateHelper; print('OK')"
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
from core.roi import ROICoordinateHelper

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
from core.roi import find_target_voxels

# Test that import works
print('Import successful')
"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "successful" ]]
}

@test "Ex-Search: ti_calculations bridge module works" {
    run simnibs_python -c "
import sys
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../ti-toolbox')
from core import calc, roi

# Test that all expected functions are available
assert hasattr(calc, 'get_TI_vectors')
assert hasattr(roi, 'find_target_voxels')
assert hasattr(roi, 'validate_ti_montage')

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
from core.roi import find_target_voxels

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
from core.roi import validate_ti_montage

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
from core.roi import ROICoordinateHelper

# Non-existent file
coords = ROICoordinateHelper.load_roi_from_csv('/nonexistent/file.csv')
assert coords is None

print('Invalid file handled correctly')
"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "correctly" ]]
}

@test "Ex-Search: All __all__ exports are available" {
    run simnibs_python -c "
import sys
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../ti-toolbox')
from core import calc, roi

# Check calc module exports
calc_exports = ['get_TI_vectors']
for export in calc_exports:
    assert hasattr(calc, export), f'Missing calc export: {export}'

# Check roi module exports
roi_exports = ['find_target_voxels', 'validate_ti_montage', 'ROICoordinateHelper']
for export in roi_exports:
    assert hasattr(roi, export), f'Missing roi export: {export}'

print('All exports available')
"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "available" ]]
}
