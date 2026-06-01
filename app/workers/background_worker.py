"""
Background worker for ingest jobs.
"""

import threading
import uuid
from queue import Empty, Queue
from typing import Optional

from app.api.repositories.processing_repository import (
    DocumentVersionRepository,
    ProcessingJobRepository,
)
from app.core.database import SessionLocal
from app.pipeline.ingest_pipeline import IngestPipeline


class BackgroundWorker:
    """Worker that processes ingest jobs in a background thread."""

    def __init__(self, max_retries: int = 3):
        self.job_queue: Queue = Queue()
        self.max_retries = max_retries
        self.worker_thread: Optional[threading.Thread] = None
        self.running = False

    def start(self):
        """Start the worker thread."""
        if self.running:
            print("[WORKER] Already running")
            return

        self.running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        print("[WORKER] Started background worker")

    def stop(self):
        """Stop the worker thread."""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        print("[WORKER] Stopped background worker")

    def enqueue_document(self, document_id: uuid.UUID):
        """Backward-compatible enqueue for a document-level job."""
        self.job_queue.put({"document_id": document_id, "version_id": None})
        print(f"[WORKER] Enqueued document {document_id}")

    def enqueue_document_version(self, document_id: uuid.UUID, version_id: uuid.UUID):
        """Enqueue a specific version to ingest."""
        self.job_queue.put({"document_id": document_id, "version_id": version_id})
        print(f"[WORKER] Enqueued version {version_id} for document {document_id}")

    def _worker_loop(self):
        """Main loop that consumes items from the queue."""
        pipeline = IngestPipeline()

        while self.running:
            try:
                queue_item = self.job_queue.get(timeout=1)
            except Empty:
                continue

            try:
                self._process_job(queue_item, pipeline)
            except Exception as e:
                print(f"[WORKER] Unhandled error for queue item {queue_item}: {str(e)}")

    def _process_job(self, queue_item, pipeline: IngestPipeline):
        """Process one ingest job with retry handling."""
        document_id = queue_item.get("document_id")
        version_id = queue_item.get("version_id")

        try:
            with SessionLocal() as db:
                job_repo = ProcessingJobRepository(db)
                pending_jobs = job_repo.get_pending_jobs(
                    document_id=document_id,
                    version_id=version_id,
                    limit=1,
                )
                if not pending_jobs:
                    print(f"[WORKER] No pending job found for queue item {queue_item}")
                    return

                job = pending_jobs[0]
                job_id = job.job_id
                retry_count = job.retry_count
                ingest_version_id = job.version_id or version_id

                if retry_count >= self.max_retries:
                    print(
                        f"[WORKER] Job {job_id} exceeded max retries ({self.max_retries})"
                    )
                    job_repo.update_job_status(
                        job_id,
                        "failed",
                        f"Exceeded max retries: {self.max_retries}",
                    )
                    return

                print(
                    f"[WORKER] Processing job {job_id} for document {document_id} version {version_id}"
                )
                job_repo.update_job_status(job_id, "running")

                if not ingest_version_id:
                    latest_version = DocumentVersionRepository(db).get_latest_version(
                        document_id
                    )
                    ingest_version_id = (
                        latest_version.version_id if latest_version else None
                    )

            if not ingest_version_id:
                raise ValueError(
                    f"Could not resolve version to ingest for document {document_id}"
                )

            try:
                result = pipeline.ingest(ingest_version_id)

                with SessionLocal() as db:
                    ProcessingJobRepository(db).update_job_status(job_id, "completed")

                print(
                    f"[WORKER] Job {job_id} completed: "
                    f"{result.get('chunk_count', 0)} chunks processed"
                )

            except Exception as e:
                error_msg = str(e)
                print(f"[WORKER] Job {job_id} failed: {error_msg}")

                with SessionLocal() as db:
                    job_repo = ProcessingJobRepository(db)
                    updated_job = job_repo.increment_retry_count(job_id)

                    if updated_job.retry_count < self.max_retries:
                        job_repo.reset_job_to_pending(job_id)
                        self.job_queue.put(
                            {
                                "document_id": document_id,
                                "version_id": version_id,
                            }
                        )
                        print(
                            f"[WORKER] Job {job_id} reset to pending (retry {updated_job.retry_count})"
                        )
                    else:
                        job_repo.update_job_status(
                            job_id,
                            "failed",
                            f"Ingest failed: {error_msg}",
                        )

        except Exception as e:
            print(f"[WORKER] Fatal error processing job {document_id}: {str(e)}")


background_worker: Optional[BackgroundWorker] = None


def get_worker() -> BackgroundWorker:
    """Get or initialize the global worker instance."""
    global background_worker
    if background_worker is None:
        background_worker = BackgroundWorker(max_retries=3)
    return background_worker


def start_background_worker():
    """Start the global worker."""
    worker = get_worker()
    if not worker.running:
        worker.start()


def stop_background_worker():
    """Stop the global worker."""
    global background_worker
    if background_worker:
        background_worker.stop()
