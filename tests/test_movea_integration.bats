#!/usr/bin/env bats
# Integration tests for MOVEA optimizer

setup() {
    # Setup test environment
    export TEST_DIR="${BATS_TEST_DIRNAME}/../test_data/movea_integration"
    export MOVEA_SCRIPT="${BATS_TEST_DIRNAME}/../ti-toolbox/cli/movea.sh"

    # Create test directories
    mkdir -p "${TEST_DIR}/leadfield"
    mkdir -p "${TEST_DIR}/results"
}

teardown() {
    # Cleanup test directories
    if [ -d "${TEST_DIR}" ]; then
        rm -rf "${TEST_DIR}"
    fi
}

@test "MOVEA: Script exists and is executable" {
    [ -f "${MOVEA_SCRIPT}" ]
    [ -x "${MOVEA_SCRIPT}" ]
}

@test "MOVEA: Shows help message with -h flag" {
    run bash "${MOVEA_SCRIPT}" -h
    [ "$status" -eq 0 ]
    [[ "$output" =~ "MOVEA" ]] || [[ "$output" =~ "optimizer" ]] || [[ "$output" =~ "help" ]]
}

@test "MOVEA: Fails gracefully with missing required arguments" {
    run bash "${MOVEA_SCRIPT}"
    [ "$status" -ne 0 ]
}

@test "MOVEA: Python optimizer module can be imported" {
    run simnibs_python -c "import sys; sys.path.insert(0, '${BATS_TEST_DIRNAME}/../ti-toolbox'); from opt.movea.optimizer import TIOptimizer; print('OK')"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "OK" ]]
}

@test "MOVEA: TIOptimizer class can be instantiated" {
    run simnibs_python -c "
import sys
import numpy as np
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../ti-toolbox')
from opt.movea.optimizer import TIOptimizer

# Create synthetic leadfield
lfm = np.random.rand(10, 50, 3) * 0.1
positions = np.random.rand(50, 3) * 100 - 50

optimizer = TIOptimizer(lfm, positions, num_electrodes=10)
print('Optimizer created successfully')
"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "successfully" ]]
}

@test "MOVEA: Can set optimization target" {
    run simnibs_python -c "
import sys
import numpy as np
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../ti-toolbox')
from opt.movea.optimizer import TIOptimizer

# Set seed for reproducible test data
np.random.seed(42)

# Create synthetic leadfield
lfm = np.random.rand(10, 50, 3) * 0.1

# Create positions with some near the target [0, 0, 0]
positions = np.random.rand(50, 3) * 100 - 50
# Ensure some positions are near the target
positions[0] = [0, 0, 0]  # Exact target
positions[1:5] = np.random.rand(4, 3) * 2 - 1  # Within 1mm of target

optimizer = TIOptimizer(lfm, positions, num_electrodes=10)
optimizer.set_target([0, 0, 0], 10.0)
print('Target set successfully')
"
    [ "$status" -eq 0 ] || echo "Error output: $output"
    [[ "$output" =~ "successfully" ]]
}

@test "MOVEA: Can evaluate montage" {
    run simnibs_python -c "
import sys
import numpy as np
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../ti-toolbox')
from opt.movea.optimizer import TIOptimizer

# Set seed for reproducible test data
np.random.seed(42)

# Create synthetic leadfield
lfm = np.random.rand(10, 50, 3) * 0.1

# Create positions with some near the target [0, 0, 0]
positions = np.random.rand(50, 3) * 100 - 50
# Ensure some positions are near the target
positions[0] = [0, 0, 0]  # Exact target
positions[1:5] = np.random.rand(4, 3) * 2 - 1  # Within 1mm of target

optimizer = TIOptimizer(lfm, positions, num_electrodes=10)
optimizer.set_target([0, 0, 0], 10.0)

cost = optimizer.evaluate_montage([0, 1, 2, 3], 0.5)
print(f'Cost: {cost}')
print('Evaluation successful')
"
    [ "$status" -eq 0 ] || echo "Error output: $output"
    [[ "$output" =~ "Cost:" ]]
    [[ "$output" =~ "successful" ]]
}

@test "MOVEA: Validates electrode montage correctly" {
    run simnibs_python -c "
import sys
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../ti-toolbox')
from core.roi import validate_ti_montage

# Valid montage
assert validate_ti_montage([0, 1, 2, 3], 10) == True

# Invalid - duplicates
assert validate_ti_montage([0, 0, 1, 2], 10) == False

# Invalid - out of range
assert validate_ti_montage([0, 1, 2, 100], 10) == False

print('Validation tests passed')
"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "passed" ]]
}

@test "MOVEA: find_target_voxels utility works correctly" {
    run simnibs_python -c "
import sys
import numpy as np
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../ti-toolbox')
from core.roi import find_target_voxels

positions = np.array([
    [0, 0, 0],
    [5, 0, 0],
    [10, 0, 0],
    [0, 5, 0]
])

indices = find_target_voxels(positions, [0, 0, 0], 6.0)
assert len(indices) == 3  # Should find (0,0,0), (5,0,0), (0,5,0)

print('find_target_voxels tests passed')
"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "passed" ]]
}

@test "MOVEA: Handles optimization exceptions gracefully" {
    run simnibs_python -c "
import sys
import numpy as np
sys.path.insert(0, '${BATS_TEST_DIRNAME}/../ti-toolbox')
from opt.movea.optimizer import TIOptimizer

# Set seed for reproducible test data
np.random.seed(42)

# Create synthetic leadfield
lfm = np.random.rand(10, 50, 3) * 0.1

# Create positions with some near the target [0, 0, 0]
positions = np.random.rand(50, 3) * 100 - 50
# Ensure some positions are near the target
positions[0] = [0, 0, 0]  # Exact target
positions[1:5] = np.random.rand(4, 3) * 2 - 1  # Within 1mm of target

optimizer = TIOptimizer(lfm, positions, num_electrodes=10)
optimizer.set_target([0, 0, 0], 10.0)

# Invalid montage should return infinity
cost = optimizer.evaluate_montage([0, 0, 1, 2], 0.5)  # Duplicates
assert np.isinf(cost), 'Should return infinity for invalid montage'

print('Exception handling tests passed')
"
    [ "$status" -eq 0 ]
    [[ "$output" =~ "passed" ]]
}
