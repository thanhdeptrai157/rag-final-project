from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_current_admin_user
from app.api.service.chat_session_service import (
    AdminFeedbackService,
    EvaluationDashboardService,
)
from app.models.user import User
from app.schemas.chat import (
    AdminFeedbackStatus,
    AdminFeedbackItemOut,
    EvaluationDashboardOut,
    FeedbackReason,
    MessageFeedbackOut,
    MessageFeedbackUpdate,
)

admin_router = APIRouter(dependencies=[Depends(get_current_admin_user)])


@admin_router.get("/feedbacks", response_model=list[AdminFeedbackItemOut])
def list_feedbacks(
    rating: int | None = Query(default=None, ge=1, le=5),
    reason: FeedbackReason | None = Query(default=None),
    admin_status: AdminFeedbackStatus | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: AdminFeedbackService = Depends(),
) -> list[AdminFeedbackItemOut]:
    return service.list_feedbacks(
        rating=rating,
        reason=reason,
        admin_status=admin_status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


@admin_router.patch("/feedbacks/{feedback_id}", response_model=MessageFeedbackOut)
def update_feedback(
    feedback_id: UUID,
    payload: MessageFeedbackUpdate,
    current_admin: User = Depends(get_current_admin_user),
    service: AdminFeedbackService = Depends(),
) -> MessageFeedbackOut:
    return service.update_feedback(
        current_admin=current_admin,
        feedback_id=feedback_id,
        payload=payload,
    )


@admin_router.get(
    "/evaluation/dashboard",
    response_model=EvaluationDashboardOut,
)
def evaluation_dashboard(
    service: EvaluationDashboardService = Depends(),
) -> EvaluationDashboardOut:
    return service.get_dashboard()
