#!/bin/bash
# Automated documentation build script
# Builds both Sphinx API docs and Jekyll site

set -e  # Exit on error

echo "========================================="
echo "TI-Toolbox Documentation Build"
echo "========================================="

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in the docs directory
if [ ! -f "_config.yml" ]; then
    echo "Error: Must run from docs/ directory"
    exit 1
fi

# Step 1: Build Sphinx API Documentation
echo -e "\n${BLUE}[1/3] Building Sphinx API Documentation...${NC}"
cd api

# Check if Sphinx is installed
if ! command -v sphinx-build &> /dev/null; then
    echo -e "${YELLOW}Warning: sphinx-build not found. Installing requirements...${NC}"
    pip install -r requirements.txt
fi

# Build HTML documentation
echo "Running: make html"
make html

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Sphinx build successful${NC}"
    echo "  Output: api/_build/html/"
else
    echo "Error: Sphinx build failed"
    exit 1
fi

cd ..

# Step 2: Build Jekyll Site (optional - only if Jekyll is installed)
echo -e "\n${BLUE}[2/3] Checking Jekyll...${NC}"
if command -v bundle &> /dev/null && [ -f "Gemfile" ]; then
    echo "Building Jekyll site..."
    bundle exec jekyll build
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Jekyll build successful${NC}"
        echo "  Output: _site/"

        # Copy the built Sphinx HTML into the built Jekyll site so it can be
        # served without Jekyll trying to process Sphinx's `_static/` folders.
        echo -e "\n${BLUE}[2.5/3] Copying Sphinx HTML into Jekyll site...${NC}"
        rm -rf "_site/api"
        mkdir -p "_site/api"
        cp -a "api/_build/html/." "_site/api/"
        echo -e "${GREEN}✓ API docs copied to _site/api/${NC}"
    else
        echo -e "${YELLOW}Warning: Jekyll build failed (continuing anyway)${NC}"
    fi
else
    echo -e "${YELLOW}Jekyll not found (skipping - GitHub Pages will build automatically)${NC}"
fi

# Step 3: Create timestamp file
echo -e "\n${BLUE}[3/3] Creating build timestamp...${NC}"
echo "Last built: $(date)" > api/_build/html/.buildinfo
echo -e "${GREEN}✓ Build timestamp created${NC}"

# Summary
echo -e "\n${GREEN}=========================================${NC}"
echo -e "${GREEN}Documentation build complete!${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo "Next steps:"
echo "  1. View API docs: open api/_build/html/index.html"
echo "  2. Commit changes: git add docs/"
echo "  3. Push to GitHub: git push"
echo ""
echo "The API documentation will be accessible at:"
echo "  https://idossha.github.io/TI-Toolbox/api/_build/html/index.html"
echo ""
