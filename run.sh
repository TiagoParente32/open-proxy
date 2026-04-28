#!/bin/bash
set -e

cd "$(dirname "$0")"

# Activate venv if present
if [ -f "venv/bin/activate" ]; then
  source venv/bin/activate
fi

# Build UI if dist is missing or source is newer
if [ ! -d "ui/dist" ] || [ "$(find ui/src -newer ui/dist/index.html 2>/dev/null | head -1)" ]; then
  echo "Building UI..."
  cd ui && npm install --silent && npm run build && cd ..
fi

# Start Python backend in background
echo "Starting Python backend..."
python main.py &
PYTHON_PID=$!

# Give Python a moment to bind its ports
sleep 1

# Launch Electron (blocks until window is closed)
echo "Launching Electron..."
npm start

# Kill Python when Electron exits
kill $PYTHON_PID 2>/dev/null || true
