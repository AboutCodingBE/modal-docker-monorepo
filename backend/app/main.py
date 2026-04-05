from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx

from app.config import settings
from app.get_archive_overview.router import router as archives_router
from app.create_new_archive.router import router as create_archive_router
from app.analysis.router import router as analysis_router

app = FastAPI(title="Archive Analysis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(archives_router)
app.include_router(create_archive_router)
app.include_router(analysis_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/health/tika")
async def tika_health():
    """Check if Tika server is reachable."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{settings.tika_url}/tika")
            return {"status": "ok", "tika_status": resp.status_code}
        except httpx.RequestError as e:
            return {"status": "error", "detail": str(e)}


@app.get("/api/health/agent")
async def agent_health():
    """Check if the local agent is reachable."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{settings.agent_url}/health")
            return {"status": "ok", "agent_status": resp.status_code}
        except httpx.RequestError:
            return {"status": "unavailable", "detail": "Local agent is not running"}
