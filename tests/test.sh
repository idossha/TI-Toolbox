#!/bin/bash

# Wrapper script to run tests in SimNIBS Docker container
# This script mounts your local TI-Toolbox code into the container
# and runs the test suite

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
SIMNIBS_IMAGE="${SIMNIBS_IMAGE:-idossha/simnibs:v2.1.3}"

# Get the repository root (this script is in tests/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "${SCRIPT_DIR}/.." && pwd )"

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}TI-Toolbox Tests with SimNIBS Docker${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running.${NC}"
    echo "Please start Docker Desktop and try again."
    exit 1
fi

echo -e "${GREEN}✓ Docker is running${NC}"

# Check if SimNIBS image exists
if ! docker image inspect "$SIMNIBS_IMAGE" > /dev/null 2>&1; then
    echo -e "${YELLOW}Warning: SimNIBS image '$SIMNIBS_IMAGE' not found locally.${NC}"
    echo -e "${YELLOW}Pulling from Docker Hub...${NC}"
    docker pull "$SIMNIBS_IMAGE"
fi

echo -e "${GREEN}✓ SimNIBS image available${NC}"
echo -e "${GREEN}✓ Mounting local code from: ${REPO_ROOT}${NC}"
echo ""

# Parse arguments to pass to the test script
TEST_ARGS="$@"

echo -e "${CYAN}Starting tests in SimNIBS container...${NC}"
echo ""

# Run the tests in the container with local code mounted
# Mount the local TI-Toolbox directory to /workspace
# The test script will detect and use it
docker run --rm \
    -v "${REPO_ROOT}:/workspace" \
    -v /tmp/test_projectdir:/mnt/test_projectdir \
    -w /workspace \
    "$SIMNIBS_IMAGE" \
    bash -c "./tests/run_tests.sh $TEST_ARGS"

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}Tests completed successfully!${NC}"
    echo -e "${GREEN}========================================${NC}"
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}Tests failed!${NC}"
    echo -e "${RED}========================================${NC}"
fi

exit $EXIT_CODE

