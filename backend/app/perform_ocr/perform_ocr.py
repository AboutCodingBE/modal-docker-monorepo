import asyncio
import logging
import uuid

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.analysis import task_tracker
from app.config import settings
from app.perform_ocr.file_repository import OcrFileRepository
from app.perform_ocr.ocr_repository import OcrRepository
from app.perform_tika_analysis.text_functions import get_word_count, normalize_newlines
from app.perform_tika_analysis.tika_extractor import TIKA_text_extract
from app.shared.logging_config import log_context

_logger = logging.getLogger("app.ocr")

_DRIVE_GONE_THRESHOLD = 5
_OCR_LANGUAGE = "nld+eng"


class PerformOcr:
    """Flow controller for running OCR on all candidate files in an archive."""

    def __init__(self, session_factory: async_sessionmaker):
        self._session_factory = session_factory

    async def execute(self, archive_id: uuid.UUID, task_id: uuid.UUID) -> None:
        # Phase 0: start task and fetch candidate list
        async with self._session_factory() as session:
            await task_tracker.start_task(session, task_id)
            candidates = await OcrFileRepository(session).get_candidates(archive_id)
            await task_tracker.update_total_files(session, task_id, len(candidates))
            await session.commit()

        processed = 0
        failed_count = 0
        skipped: list[dict] = []
        consecutive_failures = 0
        stop_reason: str | None = None
        outcome_status = "completed"

        try:
            for file in candidates:
                file_id = file["id"]
                relative_path = file["relative_path"]
                size_bytes = file["size_bytes"]
                file_name = file["name"]

                async with self._session_factory() as session:
                    await task_tracker.update_progress(
                        session, task_id, processed, failed_count, relative_path
                    )
                    await session.commit()

                # Fetch file bytes from agent's OCR endpoint
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(
                            f"{settings.agent_url}/ocr/file-content",
                            params={
                                "archive_id": str(archive_id),
                                "relative_path": relative_path,
                            },
                            timeout=300.0,
                        )
                        if resp.status_code == 410:
                            stop_reason = "stopped_verification_lost"
                            _logger.error(
                                f"{log_context(archive_id, file_name)}"
                                "Agent returned 410: verification lost, stopping OCR run."
                            )
                            break
                        resp.raise_for_status()
                        file_content = resp.content
                except Exception as e:
                    _logger.error(
                        f"{log_context(archive_id, file_name)}Failed to fetch from agent: {e}"
                    )
                    failed_count += 1
                    consecutive_failures += 1
                    skipped.append({"relative_path": relative_path, "reason": "fetch_failed"})
                    if consecutive_failures >= _DRIVE_GONE_THRESHOLD:
                        stop_reason = "stopped_drive_gone"
                        break
                    continue

                # Per-file size verification (catches wrong-drive mid-run)
                if size_bytes is not None and len(file_content) != size_bytes:
                    _logger.warning(
                        f"{log_context(archive_id, file_name)}"
                        f"Size mismatch: expected {size_bytes}, got {len(file_content)}"
                    )
                    failed_count += 1
                    consecutive_failures += 1
                    skipped.append({"relative_path": relative_path, "reason": "size_mismatch"})
                    if consecutive_failures >= _DRIVE_GONE_THRESHOLD:
                        stop_reason = "stopped_drive_gone"
                        break
                    continue

                consecutive_failures = 0

                # Run Tika with OCR enabled
                tika = await asyncio.to_thread(
                    TIKA_text_extract, file_content, True, _OCR_LANGUAGE
                )

                if not isinstance(tika, (tuple, list)) or len(tika) < 7:
                    _logger.warning(
                        f"{log_context(archive_id, file_name)}Invalid Tika OCR output, skipping."
                    )
                    failed_count += 1
                    skipped.append({"relative_path": relative_path, "reason": "tika_failed"})
                    continue

                content = tika[1]
                lang = tika[3]
                if isinstance(lang, list):
                    lang = lang[0] if lang else None
                elif lang == "":
                    lang = None

                if content and len(str(content).strip()) > 0:
                    clean_content = normalize_newlines(content)
                    word_count = get_word_count(clean_content)
                else:
                    clean_content = None
                    word_count = 0

                try:
                    async with self._session_factory() as session:
                        await OcrRepository(session).update_tika_content(
                            file_id, clean_content, word_count, lang
                        )
                        await session.commit()
                    processed += 1
                    _logger.info(f"{log_context(archive_id, file_name)}OCR content saved.")
                except Exception as e:
                    _logger.error(
                        f"{log_context(archive_id, file_name)}Failed to persist OCR result: {e}"
                    )
                    failed_count += 1
                    skipped.append({"relative_path": relative_path, "reason": "persist_failed"})
                    continue

            # Determine final outcome
            if stop_reason:
                outcome_status = stop_reason
                outcome = {
                    "status": outcome_status,
                    "processed": processed,
                    "skipped": len(skipped),
                    "skipped_files": skipped[:50],
                }
                async with self._session_factory() as session:
                    await task_tracker.update_progress(session, task_id, processed, failed_count, None)
                    await task_tracker.fail_task_with_outcome(session, task_id, outcome)
                    await session.commit()
            else:
                outcome_status = "completed_with_skips" if skipped else "completed"
                outcome = {
                    "status": outcome_status,
                    "processed": processed,
                    "skipped": len(skipped),
                    "skipped_files": skipped[:50],
                }
                async with self._session_factory() as session:
                    await OcrRepository(session).set_ocr_enabled(archive_id, True)
                    await task_tracker.update_progress(session, task_id, processed, failed_count, None)
                    await task_tracker.complete_task_with_outcome(session, task_id, outcome)
                    await session.commit()

            _logger.info(
                f"{log_context(archive_id)}OCR complete. "
                f"Status: {outcome_status}, processed: {processed}, skipped: {len(skipped)}"
            )

        except Exception as e:
            _logger.error(f"{log_context(archive_id)}OCR failed unexpectedly: {e}")
            try:
                async with self._session_factory() as session:
                    await task_tracker.fail_task(session, task_id)
                    await session.commit()
            except Exception:
                pass
        finally:
            # Clear the agent's held root (best-effort)
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{settings.agent_url}/ocr/clear",
                        params={"archive_id": str(archive_id)},
                        timeout=5.0,
                    )
            except Exception as e:
                _logger.warning(f"{log_context(archive_id)}Could not clear agent OCR root: {e}")
