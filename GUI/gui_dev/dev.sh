#!/bin/bash
# Development mode launcher for TI-Toolbox GUI
# Enables auto-reload on file changes

cd "$(dirname "$0")"

echo "=================================================="
echo "  TI-Toolbox GUI - Development Mode"
echo "=================================================="
echo ""
echo "This mode will automatically restart the GUI when"
echo "you save changes to any Python file."
echo ""

# Ensure watchdog is installed
python3 -c "import watchdog" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "📦 Installing development dependencies..."
    pip install watchdog
    echo ""
fi

# Run the development server
python3 dev_runner.py
