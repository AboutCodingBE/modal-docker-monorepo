Create a diagnostic/cleanup shell script at the project root
called diagnostic.sh (for Linux/macOS) that helps users
troubleshoot and clean up the Archive App.

The script should:

1. Print a header: "Archive App Diagnostic Tool"

2. Check all ports used by the app (9090 agent, 4200 frontend,
   8000 backend, 9998 tika, 5432 postgres). For each port:
    - Show if it's in use or free
    - If in use, identify the process name and PID
    - Example output:
      "Port 9090 (Agent):    IN USE by archive-agent (PID 12345)"
      "Port 4200 (Frontend): FREE"

3. Check if Docker is running. Show "Docker: Running" or
   "Docker: Not running"

4. Check if any docker compose containers are running for the
   app. List them with their status (running, exited, unhealthy).

5. After showing the diagnostic info, offer a menu:
   a) "Stop everything" — kills any process on the app ports
   AND runs docker compose down
   b) "Stop Docker services only" — runs docker compose down
   but leaves the agent
   c) "Stop agent only" — kills the process on port 9090
   d) "Exit without changes"

6. Before killing any process, show what will be stopped and
   ask for confirmation: "This will stop: archive-agent (PID 12345)
   on port 9090. Continue? (y/n)"

7. The script should detect the docker-compose file automatically
   — look for docker-compose.prod.yml or docker-compose.yml in
   the same directory as the script.

Make the script executable (chmod +x). Use only standard
Linux/macOS tools (lsof, grep, awk, kill). No dependencies.

Also create a diagnostic.bat or diagnostic.ps1 for Windows
that does the same thing using netstat and taskkill.

Include both scripts in the release zip alongside the agent
binary and docker-compose file.