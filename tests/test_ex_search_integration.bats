#!/usr/bin/env bats
# Integration tests for ex-search system

setup() {
    # Setup test environment
    export TEST_DIR="${BATS_TEST_DIRNAME}/../test_data/ex_search_integration"
    export EX_MAIN="${BATS_TEST_DIRNAME}/../tit/opt/ex/main.py"

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

@test "Ex-Search: Main script exists" {
    [ -f "${EX_MAIN}" ]
}

@test "Ex-Search: Main module can be imported" {
    run simnibs_python -c "import sys; sys.path.insert(0, '${BATS_TEST_DIRNAME}/../tit'); from tit.opt.ex import main; print('OK')"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "OK" ]]
}

@test "Ex-Search: ROICoordinateHelper can be imported" {
    run simnibs_python -c "import sys; sys.path.insert(0, '${BATS_TEST_DIRNAME}/../tit'); from core.roi import ROICoordinateHelper; print('OK')"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "OK" ]]
}

@test "Ex-Search: Config module can be imported" {
    run simnibs_python -c "import sys; sys.path.insert(0, '${BATS_TEST_DIRNAME}/../tit'); from tit.opt.ex import config; print('OK')"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "OK" ]]
}

@test "Ex-Search: Logic module can be imported" {
    run simnibs_python -c "import sys; sys.path.insert(0, '${BATS_TEST_DIRNAME}/../tit'); from tit.opt.ex import logic; print('OK')"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "OK" ]]
}

@test "Ex-Search: Runner module can be imported" {
    run simnibs_python -c "import sys; sys.path.insert(0, '${BATS_TEST_DIRNAME}/../tit'); from tit.opt.ex import runner; print('OK')"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "OK" ]]
}

@test "Ex-Search: Results module can be imported" {
    run simnibs_python -c "import sys; sys.path.insert(0, '${BATS_TEST_DIRNAME}/../tit'); from opt.ex import results; print('OK')"
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
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../tit')
from core.roi import ROICoordinateHelper

coords = ROICoordinateHelper.load_roi_from_csv('${TEST_DIR}/roi/test_roi.csv')
assert coords is not None
assert len(coords) == 3
print(f'Loaded coordinates: {coords}')
"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "Loaded coordinates" ]]
}

@test "Ex-Search: Logic functions work correctly" {
    run simnibs_python -c "
import sys
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../tit')
from opt.ex.logic import generate_current_ratios, calculate_total_combinations, generate_montage_combinations

# Test current ratio generation
ratios, exceeded = generate_current_ratios(1.0, 0.1, 0.6)
print(f'Generated {len(ratios)} current ratios')

# Test combination calculation
total = calculate_total_combinations(['E1', 'E2'], ['E3', 'E4'], ['E5', 'E6'], ['E7', 'E8'], ratios, False)
print(f'Calculated {total} combinations')

print('Logic functions work')
"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "Logic functions work" ]]
}

@test "Ex-Search: Config validation works" {
    run simnibs_python -c "
import sys
import os
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../tit')
from opt.ex.config import validate_electrode, validate_current

# Test electrode validation
assert validate_electrode('E1') == True
assert validate_electrode('e1') == True
assert validate_electrode('1E') == False

# Test current validation
assert validate_current(1.0) == True
assert validate_current(0.5, 0.1) == True
assert validate_current(-0.1) == False

print('Config validation works')
"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "Config validation works" ]]
}

@test "Ex-Search: ROI utility functions work correctly" {
    run simnibs_python -c "
import sys
import numpy as np
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../tit')
from core.roi import ROICoordinateHelper

# Test that import works
print('Import successful')
"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "successful" ]]
}

@test "Ex-Search: ti_calculations bridge module works" {
    run simnibs_python -c "
import sys
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../tit')
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
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../tit')
from core.roi import ROICoordinateHelper

# Create test voxel positions
positions = np.array([
    [0, 0, 0],
    [5, 0, 0],
    [10, 0, 0],
    [0, 5, 0],
    [0, 0, 5]
])

# Find voxels within 6mm of origin
indices = ROICoordinateHelper.find_voxels_in_sphere(positions, [0, 0, 0], 6.0)

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
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../tit')
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
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../tit')
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
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../tit')
from core import calc, roi
from opt.ex import logic, config

# Check calc module exports
calc_exports = ['get_TI_vectors']
for export in calc_exports:
    assert hasattr(calc, export), f'Missing calc export: {export}'

# Check roi module exports
roi_exports = ['find_target_voxels', 'validate_ti_montage', 'ROICoordinateHelper']
for export in roi_exports:
    assert hasattr(roi, export), f'Missing roi export: {export}'

# Check ex-search logic exports
logic_exports = ['generate_current_ratios', 'calculate_total_combinations', 'generate_montage_combinations']
for export in logic_exports:
    assert hasattr(logic, export), f'Missing logic export: {export}'

# Check ex-search config exports
config_exports = ['validate_electrode', 'validate_current', 'get_full_config']
for export in config_exports:
    assert hasattr(config, export), f'Missing config export: {export}'

print('All exports available')
"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "available" ]]
}
