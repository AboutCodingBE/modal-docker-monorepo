import uuid
from dataclasses import dataclass


@dataclass
class DownloadProgress:
    status: str = "starting"
    completed_bytes: int | None = None
    total_bytes: int | None = None
    done: bool = False
    error: str | None = None


_downloads: dict[uuid.UUID, DownloadProgress] = {}


def create(download_id: uuid.UUID) -> None:
    _downloads[download_id] = DownloadProgress()


def update(download_id: uuid.UUID, **kwargs) -> None:
    progress = _downloads.get(download_id)
    if progress:
        for key, value in kwargs.items():
            setattr(progress, key, value)


def get(download_id: uuid.UUID) -> DownloadProgress | None:
    return _downloads.get(download_id)


def cleanup(download_id: uuid.UUID) -> None:
    _downloads.pop(download_id, None)
