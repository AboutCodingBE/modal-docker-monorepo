import httpx

from app.config import settings


class AgentExportError(Exception):
    """Raised for any failure talking to the agent's export endpoints —
    covers both writing files and computing the default export path."""


async def write_export_files(base_path: str, subfolder_name: str, files: list[dict]) -> str:
    """files: [{"filename": str, "content": str}, ...]. Returns the final written path.

    base_path and subfolder_name are sent separately, never pre-joined here —
    the backend doesn't know the host OS, so path joining happens agent-side
    via pathlib.Path(base_path) / subfolder_name.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.agent_url}/export/write",
                json={"base_path": base_path, "subfolder_name": subfolder_name, "files": files},
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()["path"]
    except httpx.HTTPError as e:
        raise AgentExportError(f"Agent failed to write export: {e}") from e


async def get_default_export_path() -> str:
    """Asks the agent for the OS-appropriate default export folder
    (Documents-based, cross-platform). Pure read, no filesystem side effects
    on the agent side — the folder is created later, on first write.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.agent_url}/export/default-path", timeout=10.0)
            resp.raise_for_status()
            return resp.json()["path"]
    except httpx.HTTPError as e:
        raise AgentExportError(f"Agent failed to compute default export path: {e}") from e
