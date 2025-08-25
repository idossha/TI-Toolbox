#!/bin/bash
# TI-Toolbox Analysis Setup Script
# This script helps set up the streamlined analysis system

set -e  # Exit on any error

echo "🚀 Setting up TI-Toolbox Streamlined Analysis System"
echo "=================================================="

# Check if we're in the right directory
if [ ! -f "settings.yaml" ]; then
    echo "❌ Error: settings.yaml not found. Please run this script from the analysis directory."
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "../../venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv ../../venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source ../../venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r ../../requirements.txt

# Validate setup
echo "✅ Validating setup..."
python main.py --validate-only

echo ""
echo "🎉 Setup completed successfully!"
echo ""
echo "Next steps:"
echo "1. Run default analysis: python main.py"
echo "2. Run all regions: python main.py --all-regions"
echo "3. Run specific analysis: python main.py --region Left_Insula --optimization max"
echo "4. See help: python main.py --help"
echo ""
echo "Remember to activate the virtual environment:"
echo "source ../../venv/bin/activate" 