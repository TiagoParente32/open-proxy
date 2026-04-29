#!/bin/bash
set -e

cd "$(dirname "$0")"

# Electron handles the UI build and Python backend startup automatically
echo "Launching Electron..."
npm start
