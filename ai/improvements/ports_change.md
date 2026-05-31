# Update ports

Change the host-facing ports for all Docker services to avoid
conflicts with common development tools. Only the left side
of the port mapping changes — the container-internal ports
stay the same.

New port mappings:
- Frontend: 4210:80 (was 4200:80)
- Backend: 8010:8000 (was 8000:8000)
- Tika: 7777:9998 (was 9998:9998)
- Postgres: 5442:5432 (was 5432:5432)
- Ollama: 11434 stays (unlikely to conflict, keep as-is)
- Agent: 9090 stays (not in Docker)

Update ALL references to these ports across the entire
codebase:

1. docker-compose.yml — update port mappings
2. docker-compose.prod.yml — update port mappings
3. .env — update DATABASE_URL to use port 5442
4. agent/config.json — update frontend_url to
   http://localhost:4210
5. agent/agent.py — update any hardcoded references to
   localhost:4200 (the loading page health check, the
   browser redirect URL, CORS origins)
6. frontend/src/environments/environment.ts — update
   apiUrl if it references a port directly
7. frontend/src/environments/environment.prod.ts — same
8. frontend/nginx.conf — the internal proxy_pass to
   backend:8000 stays the same (container-internal)
9. diagnostic.sh and diagnostic.ps1 — update port checks
   to match new ports
   10 .env — update TIKA_URL to use port 7777
   (http://localhost:7777)

Important: the nginx proxy_pass and backend-to-tika/ollama
URLs use container-internal ports and Docker service names
— those do NOT change. Only host-facing ports change.

Also update the README and any documentation that mentions
these ports.