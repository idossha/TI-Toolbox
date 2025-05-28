#!/bin/bash

# Temporal Interference Toolbox Documentation Local Server
# This script helps you run the documentation website locally

echo "🚀 Starting Temporal Interference Toolbox Documentation Server..."
echo ""

# Check if Ruby is installed
if ! command -v ruby &> /dev/null; then
    echo "❌ Ruby is not installed. Please install Ruby first."
    echo "   Visit: https://www.ruby-lang.org/en/documentation/installation/"
    exit 1
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

bundle exec jekyll serve --livereload 