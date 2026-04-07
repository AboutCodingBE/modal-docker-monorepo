Create a GitHub Actions release workflow that builds the agent
for all platforms and creates a downloadable GitHub Release.

## File: .github/workflows/release.yml

Trigger: when a version tag is pushed (pattern: v*)

The workflow should:

1. Build the agent binary on all three platforms using a matrix
   strategy (ubuntu-latest, macos-latest, windows-latest).

2. Each matrix job:
    - Checks out the repo
    - Sets up Python 3.12
    - Installs agent dependencies: pip install -r agent/requirements.txt
    - Installs PyInstaller: pip install pyinstaller
    - Builds the binary: cd agent && pyinstaller --onefile --name archive-agent --add-data "config.json:." agent.py
    - On Windows the --add-data separator is ";" not ":"
    - Creates a zip containing:
        - The agent binary (dist/archive-agent or dist/archive-agent.exe)
        - docker-compose.prod.yml (from project root)
        - agent/config.json
    - Name the zips:
        - archive-app-macos.zip
        - archive-app-linux.zip
        - archive-app-windows.zip
    - Upload the zip as a build artifact

3. After all three matrix jobs complete, a separate job
   (needs: [build]) that:
    - Downloads all three zip artifacts
    - Creates a GitHub Release using softprops/action-gh-release@v2
    - Attaches all three zips to the release
    - Uses the tag name as the release title
    - Auto-generates release notes from commits

## Also create: a simple README-RELEASE.md that goes inside
each zip. Contents:

# Archive App - Quick Start

## Prerequisites
- Docker Desktop must be installed and running

## Installation
1. Unzip this archive to a folder of your choice
2. Double-click archive-agent (or archive-agent.exe on Windows)
3. The app will start all services and open your browser
4. To stop: press Ctrl+C in the agent terminal or close it

## Files
- archive-agent: the application launcher
- docker-compose.prod.yml: service configuration
- config.json: agent settings (ports, URLs)

Include this README-RELEASE.md in each zip alongside the
binary, compose file, and config.

## Important notes
- The docker-compose.prod.yml must use image: references
  (ghcr.io/OWNER/...) not build: contexts
- The config.json compose_file field should point to
  docker-compose.prod.yml
- Make sure the agent binary is executable in the zip
  (chmod +x on Linux/macOS builds before zipping)