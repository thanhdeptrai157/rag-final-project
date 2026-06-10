from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_current_admin_user
from app.api.repositories.user_repository import UserRepository
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
from app.schemas.common import PageResponse
from app.schemas.user import UserResponse

admin_router = APIRouter(dependencies=[Depends(get_current_admin_user)])


@admin_router.get("/feedbacks", response_model=PageResponse[AdminFeedbackItemOut])
def list_feedbacks(
    rating: int | None = Query(default=None, ge=1, le=5),
    reason: FeedbackReason | None = Query(default=None),
    admin_status: AdminFeedbackStatus | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    service: AdminFeedbackService = Depends(),
) -> PageResponse[AdminFeedbackItemOut]:
    return service.list_feedbacks(
        rating=rating,
        reason=reason,
        admin_status=admin_status,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
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


@admin_router.get(
    "/users",
    response_model=PageResponse[UserResponse],
)
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    service: UserRepository = Depends(),
):
    users, total = service.list_paginated(
        page=page,
        page_size=page_size,
    )

    return PageResponse[UserResponse].create(
        items=[UserResponse.model_validate(user) for user in users],
        total=total,
        page=page,
        page_size=page_size,
    )
