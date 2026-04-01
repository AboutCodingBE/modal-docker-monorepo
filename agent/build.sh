#!/bin/bash
# Build the agent into a single executable using PyInstaller.
# Run from the /agent directory.
#
# Prerequisites:
#   pip install pyinstaller
#
# The resulting binary will be in dist/archive-agent

set -e

echo "Building agent binary..."
pyinstaller \
    --onefile \
    --name archive-agent \
    --add-data "config.json:." \
    agent.py

echo ""
echo "Done! Binary at: dist/archive-agent"
echo "To distribute, ship the binary alongside docker-compose.yml and config.json"
