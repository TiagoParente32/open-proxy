#!/bin/bash
set -e

echo "Building UI..."
cd ui && npm run build && cd ..

echo "Starting app..."
python main.py