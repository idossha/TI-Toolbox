#!/bin/bash

# Setup test project directory - DEPRECATED
# This script is kept for backward compatibility but is no longer needed.
# Test data is now pre-baked into the Docker image during build (see Dockerfile.test).
# The entrypoint_test.sh script handles copying pre-baked data to the mount point.

set -e

# Colors for output
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}⚠ Warning: setup_test_projectdir.sh is deprecated.${NC}"
echo -e "${YELLOW}⚠ Test data should be pre-baked in the Docker image.${NC}"
echo -e "${YELLOW}⚠ If you see this message, the entrypoint may not have run correctly.${NC}"
echo ""

# Exit successfully (don't fail tests that might still call this)
exit 0
