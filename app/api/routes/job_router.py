"""
API router để query processing job status.
"""

from fastapi import APIRouter, Depends, HTTPException, status
import uuid
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.processing_job import ProcessingJob
from pydantic import BaseModel


class JobStatusResponse(BaseModel):
    job_id: str
    document_id: str
    job_type: str
    status: str  # pending, running, completed, failed
    started_at: str | None
    finished_at: str | None
    error_message: str | None
    retry_count: int


job_router = APIRouter()


@job_router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    tags=["job"],
)
def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
) -> JobStatusResponse:
    """Lấy trạng thái processing job."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid job_id format",
        )

    job = db.query(ProcessingJob).filter(ProcessingJob.job_id == job_uuid).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    return JobStatusResponse(
        job_id=str(job.job_id),
        document_id=str(job.document_id),
        job_type=job.job_type,
        status=job.status,
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
        error_message=job.error_message,
        retry_count=job.retry_count,
    )
