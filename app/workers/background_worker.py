"""
Background Worker: Chạy job ingest trong thread riêng.

Sử dụng:
- threading.Queue để enqueue job
- Worker thread chạy liên tục
- Retry logic: nếu failed thì reset sang pending + retry sau
"""

import threading
import uuid
from queue import Queue, Empty
from typing import Optional

from app.core.database import SessionLocal
from app.api.repositories.processing_repository import ProcessingJobRepository
from app.pipeline.ingest_pipeline import IngestPipeline


class BackgroundWorker:
    """Worker chạy background job ingest."""

    def __init__(self, max_retries: int = 3):
        self.job_queue: Queue = Queue()
        self.max_retries = max_retries
        self.worker_thread: Optional[threading.Thread] = None
        self.running = False

    def start(self):
        """Khởi động worker thread."""
        if self.running:
            print("[WORKER] Already running")
            return

        self.running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        print("[WORKER] Started background worker")

    def stop(self):
        """Dừng worker thread."""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        print("[WORKER] Stopped background worker")

    def enqueue_document(self, document_id: uuid.UUID):
        """Enqueue document để ingest."""
        self.job_queue.put(document_id)
        print(f"[WORKER] Enqueued document {document_id}")

    def _worker_loop(self):
        """Main loop xử lý job từ queue."""
        pipeline = IngestPipeline()

        while self.running:
            try:
                # Lấy 1 job từ queue với timeout 1s
                document_id = self.job_queue.get(timeout=1)
            except Empty:
                continue

            try:
                self._process_job(document_id, pipeline)
            except Exception as e:
                print(f"[WORKER] Unhandled error for {document_id}: {str(e)}")

    def _process_job(self, document_id: uuid.UUID, pipeline: IngestPipeline):
        """Xử lý 1 job ingest với retry logic."""
        db = SessionLocal()
        try:
            job_repo = ProcessingJobRepository(db)

            # Lấy job pending cho document này
            pending_jobs = job_repo.get_pending_jobs(document_id=document_id, limit=1)
            if not pending_jobs:
                print(f"[WORKER] No pending job found for document {document_id}")
                return

            job = pending_jobs[0]

            # Check retry limit
            if job.retry_count >= self.max_retries:
                print(
                    f"[WORKER] Job {job.job_id} exceeded max retries ({self.max_retries})"
                )
                job_repo.update_job_status(
                    job.job_id,
                    "failed",
                    f"Exceeded max retries: {self.max_retries}",
                )
                return

            # Update job status = running
            print(f"[WORKER] Processing job {job.job_id} for document {document_id}")
            job_repo.update_job_status(job.job_id, "running")

            # Chạy ingest pipeline
            try:
                result = pipeline.ingest(document_id, db)

                # Mark job completed
                job_repo.update_job_status(job.job_id, "completed")
                print(
                    f"[WORKER] ✓ Job {job.job_id} completed: "
                    f"{result.get('chunk_count', 0)} chunks processed"
                )

            except Exception as e:
                error_msg = str(e)
                print(f"[WORKER] ✗ Job {job.job_id} failed: {error_msg}")

                # Increment retry count
                job_repo.increment_retry_count(job.job_id)

                # Reset job to pending nếu còn retry
                if job.retry_count + 1 < self.max_retries:
                    job_repo.reset_job_to_pending(job.job_id)
                    print(
                        f"[WORKER] Job {job.job_id} reset to pending (retry {job.retry_count + 1})"
                    )
                else:
                    # Mark job failed vì vượt retry
                    job_repo.update_job_status(
                        job.job_id,
                        "failed",
                        f"Ingest failed: {error_msg}",
                    )

        except Exception as e:
            print(f"[WORKER] Fatal error processing job {document_id}: {str(e)}")
        finally:
            db.close()


# Global worker instance
background_worker: Optional[BackgroundWorker] = None


def get_worker() -> BackgroundWorker:
    """Get hoặc khởi tạo global worker instance."""
    global background_worker
    if background_worker is None:
        background_worker = BackgroundWorker(max_retries=3)
    return background_worker


def start_background_worker():
    """Khởi động background worker."""
    worker = get_worker()
    if not worker.running:
        worker.start()


def stop_background_worker():
    """Dừng background worker."""
    global background_worker
    if background_worker:
        background_worker.stop()
