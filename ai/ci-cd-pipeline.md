Set up GitHub Container Registry publishing for the frontend
and backend Docker images. Here is what needs to happen:

1. Update .github/workflows/backend.yml:
    - Add permissions: contents read, packages write
    - Add step to log in to ghcr.io using docker/login-action@v3
      with registry ghcr.io, username github.actor, password
      secrets.GITHUB_TOKEN
    - Add step to build and push using docker/build-push-action@v5
      with context ./backend, push true, and two tags:
      ghcr.io/${{ github.repository_owner }}/archive-app-backend:latest
      ghcr.io/${{ github.repository_owner }}/archive-app-backend:${{ github.sha }}
    - Remove the old "Build Docker image" step if present

2. Do the same for .github/workflows/frontend.yml, using
   archive-app-frontend as the image name and ./frontend as
   the context.

3. Create a docker-compose.prod.yml at the project root.
   This is a copy of docker-compose.yml but with two changes:
    - frontend service uses image: ghcr.io/OWNER/archive-app-frontend:latest
      instead of build: ./frontend
    - backend service uses image: ghcr.io/OWNER/archive-app-backend:latest
      instead of build: ./backend
    - Use OWNER as a placeholder, we will replace it later
    - Tika and db services stay the same (they already use
      public images)

4. Update agent/config.json to add a compose_file field
   pointing to docker-compose.prod.yml. The existing
   docker-compose.yml remains for local development.

Do not modify the agent.yml workflow or the docker-compose.yml
(that one stays for development with build: context).