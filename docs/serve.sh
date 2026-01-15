#!/bin/bash

# Temporal Interference Toolbox Documentation Local Server
# This script helps you run the documentation website locally

echo "🚀 Starting Temporal Interference Toolbox Documentation Server..."
echo ""

# Use Homebrew Ruby 3.3 (installed for compatibility with macOS 15)
export PATH="/opt/homebrew/opt/ruby@3.3/bin:$PATH"

# Check if Ruby is installed
if ! command -v ruby &> /dev/null; then
    echo "❌ Ruby is not installed. Please run: brew install ruby@3.3"
    exit 1
fi

echo "📍 Using Ruby: $(ruby --version)"
echo "📍 Using Ruby path: $(which ruby)"

# Kill any existing Jekyll processes to avoid port conflicts
echo "🔧 Checking for existing Jekyll processes..."
if pgrep -f "jekyll serve" > /dev/null; then
    echo "🛑 Killing existing Jekyll processes..."
    pkill -f "jekyll serve"
    sleep 2
fi

# Check if Bundler is installed
if ! command -v bundle &> /dev/null; then
    echo "📦 Installing Bundler..."
    gem install bundler
fi

# Install dependencies if needed
if [ ! -f "Gemfile.lock" ]; then
    echo "📦 Installing dependencies..."
    bundle install
else
    echo "✅ Dependencies already installed"
fi

# Start the server
echo ""
echo "🌐 Starting Jekyll server..."
echo "   Local URL: http://localhost:4000/TI-Toolbox/"
echo "   Press Ctrl+C to stop"
echo ""
echo "💡 Tip: Google Analytics is enabled by default. To disable, run:"
echo "   ENABLE_ANALYTICS=false bash serve.sh"
echo "   To enable live reload: bundle exec jekyll serve --livereload"
echo ""

# Check if analytics should be disabled
if [ "$ENABLE_ANALYTICS" = "false" ]; then
  echo "📊 Google Analytics disabled"
  ENABLE_ANALYTICS=false bundle exec jekyll serve
else
  echo "📊 Google Analytics enabled (default)"
  bundle exec jekyll serve
fi