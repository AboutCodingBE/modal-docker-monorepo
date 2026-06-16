import asyncio
import logging
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.analysis import task_tracker
from app.create_topic_detection_for_archive.archive_analysis_repository import ArchiveAnalysisRepository
from app.create_topic_detection_for_archive.file_repository import FileRepository
from app.create_topic_detection_for_archive.topic_detection_repository import TopicDetectionRepository
from app.shared.logging_config import log_context

from datetime import datetime
from bertopic import BERTopic
from bertopic.representation import KeyBERTInspired
import numpy as np
from app.create_topic_detection_for_archive.text_functions import remove_stopwords, remove_numbers
from topic_representation2subject import topic_representation2subject_openai
import os

_logger = logging.getLogger("app")

_MAX_CONSECUTIVE_FAILURES = 5

# Disable GPU usage
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"


class CreateTopicDetectionForArchive:
    """Flow controller for spaCy NER analysis of all files in an archive.

    Accepts a session_factory rather than a single session so that each unit of
    DB work gets its own short-lived connection. The connection is released
    before every run_ner call, preventing pool exhaustion during long analyses.
    """

    def __init__(self, session_factory: async_sessionmaker):
        self._session_factory = session_factory

    async def execute(
        self,
        archive_id: uuid.UUID,
        archive_analysis_id: uuid.UUID,
        task_id: uuid.UUID,
        model: str,
    ) -> None:
        try:
            # ── Phase 0: start task and fetch file list ───────────────────────
            async with self._session_factory() as session:
                await task_tracker.start_task(session, task_id)
                files = await FileRepository(session).get_files_with_tika_content(archive_id)
                await task_tracker.update_total_files(session, task_id, len(files))
                await session.commit()

            processed = 0
            failed_count = 0
            consecutive_failures = 0

            # Select text documents with enough words to be considered for topic detection:
            documents = files.find(
                {
                    "$and": [
                        {"$or": [{"mime_type": "application/msword"},
                                {"mime_type": "application/vnd.wordperfect; version=5.1"},
                                {"mime_type": "application/vnd.wordperfect; version=5.0"},
                                {"mime_type": "application/rtf"},
                                {"mime_type": "text/html"},
                                {"mime_type": "application/pdf"},
                                {"mime_type": "application/vnd.ms-works"},
                                {"mime_type": "application/x-tika-msoffice"},
                                {"mime_type": "application/vnd.oasis.opendocument.tika.flat.document"},
                                {"mime_type": "application/vnd.ms-word.document.macroenabled.12"},
                                {"mime_type": "application/msword2"},
                                {"mime_type": "application/vnd.wordperfect"},
                                {"mime_type": "application/x-mspublisher"},
                                {"mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation"},
                                {"mime_type": "application/vnd.openxmlformats-officedocument.presentationml.slideshow"},
                                {"mime_type": "application/vnd.oasis.opendocument.text"},
                                {"mime_type": "application/vnd.oasis.opendocument.presentation"},
                                {"mime_type": "message/rfc822"},
                                {"mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
                                {"mime_type": "message/x-emlx"},
                                {"mime_type": "application/vnd.ms-powerpoint"},
                                {"mime_type": "application/vnd.ms-outlook"},
                                {"mime_type": "text/plain"},
                                {"mime_type": "application/vnd.wordperfect; version=6.x"}, ]},
                        {"word_count": {"$gte": 100}}
                    ]
                },
                {"_id": 1, "content": 1, "language": 1}
            )

            # Extract text and IDs correctly and remove stopwords
            docs = []
            doc_ids = []
            for doc in documents:
                if "content" in doc:
                    cleaned_text = remove_stopwords(doc["content"], doc["language"])  # remove stopwords
                    cleaned_text = remove_numbers(cleaned_text)
                    cleaned_text = cleaned_text[:min(10000, len(cleaned_text))]
                    docs.append(cleaned_text)
                    doc_id = str(doc["_id"])  # Ensure ID is a string
                    doc_ids.append(doc_id)

            num_docs = len(docs)
            num_enrichments = 0
            num_no_topic_found = 0
            print(f"Number of documents: {num_docs}")
            # Set the number of topics, between 10 and 100
            min_topic_size = int(num_docs / 500)
            if min_topic_size < 10:
                min_topic_size = 10
                print(f"Minimum topic size set to {min_topic_size} because the number of documents is too small.")
            if min_topic_size > 100:
                min_topic_size = 100
                print(f"Minimum topic size set to {min_topic_size} because the number of documents is too large.")

            if not docs:
                raise ValueError("No documents found in the database.")

            # Initialize BERTopic
            print("loading model...")
            # Force the SentenceTransformer embedding model to run on the CPU
            embedding_model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", device="cpu")
            representation_model = KeyBERTInspired()
            topic_model = BERTopic(embedding_model=embedding_model,
                                representation_model=representation_model,
                                language="multilingual",
                                calculate_probabilities=True,
                                verbose=True,
                                min_topic_size=min_topic_size)

            print("detecting topics...")
            topics, probs = topic_model.fit_transform(docs)

            # Ensure probs is not None
            if probs is None:
                print("Warning: No probabilities were calculated. Proceeding without them.")
                probs = [None] * len(topics)

            #get topics and write to CSV file:
            info = topic_model.get_topic_info()

            # Get topics for each document and write to database
            print("creating subjects...")
            if 'subject' not in info.columns:
                info['subject'] = None

            for index, row in info.iterrows():
                topic_representation = row['Representation']
                print(topic_representation)
                keywords = "'" + ", ".join(item for item in topic_representation) + "'"
                print(keywords)
                subject = topic_representation2subject_openai(keywords) # create label
                print(subject)
                info.at[index, 'subject'] = subject

            print(info)

            current_date = datetime.now().isoformat()


            # Helper to handle doc_prob
            def extract_scalar_probability(doc_prob):
                if isinstance(doc_prob, np.ndarray):
                    if doc_prob.size == 1:
                        return float(doc_prob[0])
                    else:
                        average = np.mean(doc_prob)
                        print(f"Warning: doc_prob is a multi-element array: {doc_prob}. Using the average: {average}")
                        return float(average)
                elif isinstance(doc_prob, (float, int)):
                    return float(doc_prob)
                return None

            topic_labels_dict = dict(zip(info["Topic"], topic_model.generate_topic_labels()))

            for doc_id, doc_topic, doc_prob in zip(doc_ids, topics, probs):
                if doc_topic != -1:
                    num_enrichments += 1
                    topic_representation = topic_model.get_topic(doc_topic) or []
                    topic_name = topic_labels_dict.get(doc_topic, f"Topic {doc_topic}")
                    topic_keywords = [word for word, _ in topic_representation]
                    subject = info.loc[info['Topic'] == doc_topic, 'subject'].values[0] if not info.loc[
                        info['Topic'] == doc_topic, 'subject'].empty else None
                    if subject is None:
                        subject = f"no subject"
                    topic_probability = float(doc_prob[doc_topic]) if doc_prob is not None and doc_topic != -1 else None  #FIX 1

                else:
                    num_no_topic_found += 1
                    topic_representation = topic_model.get_topic(doc_topic) or []
                    topic_keywords = [word for word, _ in topic_representation]
                    topic_name = "No Topic Found"
                    topic_probability = None
                    subject = info.loc[info['Topic'] == doc_topic, 'subject'].values[0] if not info.loc[
                        info['Topic'] == doc_topic, 'subject'].empty else None
                    if subject is None:
                        subject = f"no subject"

                enrichment_data = {
                    "model_used": "BERTopic",
                    "enrichment_date": current_date,
                    "Topic_representation": topic_keywords,
                    "Topic_label": subject,
                    "Topic_name": topic_name,
                    "Topic_probability": topic_probability
                }

                return {
                    "topics":             topic_name,
                    "topics_count":       len(topic_name),
                }


            print(f'Documents with topics found: {num_enrichments}, documents without topics found: {num_no_topic_found}')
            print("Topics with probabilities have been written back to the database.")
            # ── File NER loop ─────────────────────────────────────────────────
            for file in files:
                file_id: uuid.UUID = file["id"]

                # Check if already processed and update progress — short session,
                # released before the NER call below.
                async with self._session_factory() as session:
                    if await TopicDetectionRepository(session).exists(archive_analysis_id, file_id):
                        processed += 1
                        continue
                    await task_tracker.update_progress(
                        session, task_id, processed, failed_count, file["relative_path"]
                    )
                    await session.commit()

                # No DB connection held during the spaCy call.
                try:
                    text = file["content"] or ""
                    topic_result = await asyncio.to_thread(run_topic_detection, text, model)
                except Exception as e:
                    _logger.error(f"{log_context(archive_id, file['name'])}Failed to run topic detection: {e}")
                    failed_count += 1
                    consecutive_failures += 1
                    if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                        _logger.error(f"{log_context(archive_id)}Repeated failures — topic detection processing stopped")
                        await self._fail(task_id, archive_analysis_id)
                        return
                    continue

                async with self._session_factory() as session:
                    await TopicDetectionRepository(session).persist(
                        archive_analysis_id, archive_id, file["parent_id"], file_id, topic_result
                    )
                    await session.commit()

                processed += 1
                consecutive_failures = 0

            # ── Completion ────────────────────────────────────────────────────
            async with self._session_factory() as session:
                await task_tracker.update_progress(session, task_id, processed, failed_count, None)
                await task_tracker.complete_task(session, task_id)
                await ArchiveAnalysisRepository(session).update_status(archive_analysis_id, "COMPLETED")
                await session.commit()

            _logger.info(f"{log_context(archive_id)}NER complete. Processed: {processed}, failed: {failed_count}")

        except Exception as e:
            _logger.error(f"{log_context(archive_id)}Topic detection task failed unexpectedly: {e}")
            await self._fail(task_id, archive_analysis_id)

    async def _fail(self, task_id: uuid.UUID, archive_analysis_i d: uuid.UUID) -> None:
        async with self._session_factory() as session:
            await task_tracker.fail_task(session, task_id)
            await ArchiveAnalysisRepository(session).update_status(archive_analysis_id, "FAILED")
            await session.commit()
