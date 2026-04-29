#!/bin/bash
set -e

cd "$(dirname "$0")"

# Build UI if dist is missing or source is newer
if [ ! -d "ui/dist" ] || [ "$(find ui/src -newer ui/dist/index.html 2>/dev/null | head -1)" ]; then
  echo "Building UI..."
  cd ui && npm install --silent && npm run build && cd ..
fi

# Electron spawns and manages the Python backend itself
echo "Launching Electron..."
npm start
