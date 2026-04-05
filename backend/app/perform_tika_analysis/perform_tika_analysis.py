import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.perform_tika_analysis.file_repository import FileRepository
from app.perform_tika_analysis.tika_extractor import TIKA_text_extract
from app.perform_tika_analysis.tika_repository import TikaRepository
from app.perform_tika_analysis.text_functions import normalize_newlines, get_word_count, file_filter, path_filter


class PerformTikaAnalysis:
    """Flow controller for running Tika analysis on all files in an archive."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._file_repo = FileRepository(session)
        self._tika_repo = TikaRepository(session)

    def _ensure_single_value(self, value):
        """Reduces lists to their first element; converts empty strings to None."""
        if isinstance(value, list):
            value = value[0] if value else None
        if value == "" or value is None:
            return None
        return str(value).strip()

    async def execute(self, archive_id: uuid.UUID) -> None | str:
        files = await self._file_repo.get_by_archive(archive_id)
        num_tot_files = num_processed_files = num_extracted_texts = 0

        for file in files:
            file_path = file["path"]
            file_name = file["name"]
            file_id = file["id"]
            num_tot_files += 1
            print(f"Processing file {num_tot_files}: {file_path}")

            if not (file_filter(file_name) and path_filter(file_path)):
                print(f"{file_name} is ignored.")
                continue

            num_processed_files += 1

            # Run the blocking tika call in a thread so the event loop stays free.
            tika = await asyncio.to_thread(TIKA_text_extract, file_path)

            if not isinstance(tika, (tuple, list)) or len(tika) < 6:
                print(f"{file_name}: invalid Tika output, skipping.")
                continue

            mime_type = self._ensure_single_value(tika[0])
            content = tika[1]
            parsers = tika[2]
            tika_parser = ", ".join(parsers) if isinstance(parsers, list) else str(parsers)
            lang = self._ensure_single_value(tika[3])
            creation_date = self._ensure_single_value(tika[4])
            creator = self._ensure_single_value(tika[5])

            if content and len(str(content).strip()) > 0:
                num_extracted_texts += 1
                clean_content = normalize_newlines(content)
                word_count = get_word_count(clean_content)
            else:
                clean_content = None
                word_count = 0

            try:
                await self._tika_repo.persist(
                    file_id,
                    mime_type,
                    tika_parser,
                    clean_content,
                    lang,
                    word_count,
                    creator,
                    creation_date,
                )
                print(f"{file_name} written to {file_id}")
            except Exception as e:
                print(f"Fout bij opslaan van {file_name}: {e}")
                continue

        print(f"Done. Total: {num_tot_files}, processed: {num_processed_files}, texts extracted: {num_extracted_texts}")
        return None
