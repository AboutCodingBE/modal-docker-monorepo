Two changes to the agent:

## 1. Linux folder picker — force foreground
Update the Linux branch of the folder picker to force the
zenity dialog to the foreground, similar to the Windows fix:

result = subprocess.run(
["zenity", "--file-selection", "--directory",
"--title=Select Archive Folder",
"--modal"],
capture_output=True, text=True
)

Also add error handling: if zenity is not installed, return
a clear error message to the frontend like
{"error": "zenity is not installed. Please install it with: sudo apt install zenity"}
instead of a generic 500 error.

## 2. Browser loading page during startup
The user double-clicks the agent and sees nothing — no
feedback until all Docker services are ready. Fix this by
serving a loading page from the agent itself.

Changes needed:

a) Add a new endpoint GET /loading on the agent that serves
a simple, self-contained HTML page (inline CSS, no external
dependencies). The page should show:
- The app name/logo
- A spinner or progress animation
- Status message: "Starting Archive App..."
- The page polls GET http://localhost:4200/api/health
  every 3 seconds using fetch()
- When the health endpoint responds with 200, the page
  redirects to http://localhost:4200
- While waiting, cycle through friendly status messages:
  "Starting database..."
  "Starting analysis services..."
  "Starting backend..."
  "Almost ready..."

b) Change the agent's startup sequence:
- Start the Flask API first (so /loading is available)
- Immediately open the browser to http://localhost:9090/loading
- THEN start Docker services (docker compose up)
- The loading page automatically detects when services are
  ready and redirects

c) The Flask server needs to run in a background thread so
the main thread can proceed with starting Docker services.
Or use the existing threading setup but make sure Flask
is accepting requests before opening the browser.

d) The loading page should look professional — centered card
with a subtle animation, clean typography. Use a neutral
color scheme that matches the app. All styles inline in
the HTML, no external resources needed.

e) If Docker services fail to start, the agent should update
an endpoint GET /startup-status that the loading page can
check. If startup fails, show an error message on the
loading page instead of spinning forever:
"Failed to start services. Check the logs at ~/.archive-app/agent.log"