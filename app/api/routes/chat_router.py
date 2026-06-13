from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_current_user
from app.api.service.chat_service import ChatService
from app.api.service.chat_session_service import (
    ChatMessageService,
    ChatSessionService,
    MessageFeedbackService,
)
from app.models.user import User
from app.schemas.chat import (
    ChatDeleteResponse,
    ChatMessageCreate,
    ChatMessageSendResponse,
    ChatMessageWithFeedbackOut,
    ChatRequest,
    ChatResponse,
    ChatSessionCreate,
    ChatSessionListItem,
    ChatSessionOut,
    ChatSessionUpdate,
    MessageFeedbackCreate,
    MessageFeedbackOut,
)

chat_router = APIRouter(tags=["chat"])


@chat_router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    service: ChatService = Depends(),
) -> ChatResponse:
    return service.answer(request.question)


@chat_router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    service: ChatService = Depends(),
) -> StreamingResponse:
    return StreamingResponse(
        service.stream_answer(request.question),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@chat_router.get("/sessions", response_model=list[ChatSessionListItem])
def list_sessions(
    search: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    service: ChatSessionService = Depends(),
) -> list[ChatSessionListItem]:
    return service.list_sessions(
        current_user=current_user,
        search=search,
        limit=limit,
        offset=offset,
    )


@chat_router.post(
    "/sessions",
    response_model=ChatSessionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    payload: ChatSessionCreate,
    current_user: User = Depends(get_current_user),
    service: ChatSessionService = Depends(),
) -> ChatSessionOut:
    return service.create_session(current_user=current_user, payload=payload)


@chat_router.patch("/sessions/{session_id}", response_model=ChatSessionOut)
def update_session(
    session_id: UUID,
    payload: ChatSessionUpdate,
    current_user: User = Depends(get_current_user),
    service: ChatSessionService = Depends(),
) -> ChatSessionOut:
    return service.update_session(
        current_user=current_user,
        session_id=session_id,
        payload=payload,
    )


@chat_router.delete("/sessions/{session_id}", response_model=ChatDeleteResponse)
def delete_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ChatSessionService = Depends(),
) -> ChatDeleteResponse:
    service.delete_session(current_user=current_user, session_id=session_id)
    return ChatDeleteResponse(success=True)


@chat_router.get(
    "/sessions/{session_id}/messages",
    response_model=list[ChatMessageWithFeedbackOut],
)
def list_messages(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ChatMessageService = Depends(),
) -> list[ChatMessageWithFeedbackOut]:
    return service.list_messages(current_user=current_user, session_id=session_id)


@chat_router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatMessageSendResponse,
    status_code=status.HTTP_201_CREATED,
)
def send_message(
    session_id: UUID,
    payload: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    service: ChatMessageService = Depends(),
) -> ChatMessageSendResponse:
    return service.send_message(
        current_user=current_user,
        session_id=session_id,
        payload=payload,
    )


@chat_router.post("/sessions/{session_id}/messages/stream")
def send_message_stream(
    session_id: UUID,
    payload: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    service: ChatMessageService = Depends(),
) -> StreamingResponse:
    return StreamingResponse(
        service.stream_send_message(
            current_user=current_user,
            session_id=session_id,
            payload=payload,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@chat_router.post(
    "/messages/{message_id}/feedback",
    response_model=MessageFeedbackOut,
    status_code=status.HTTP_201_CREATED,
)
def submit_feedback(
    message_id: UUID,
    payload: MessageFeedbackCreate,
    current_user: User = Depends(get_current_user),
    service: MessageFeedbackService = Depends(),
) -> MessageFeedbackOut:
    return service.submit_feedback(
        current_user=current_user,
        message_id=message_id,
        payload=payload,
    )


@chat_router.get("/history", response_model=list[ChatSessionListItem])
def chat_history(
    search: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    has_feedback: bool | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    service: ChatSessionService = Depends(),
) -> list[ChatSessionListItem]:
    return service.list_sessions(
        current_user=current_user,
        search=search,
        date_from=date_from,
        date_to=date_to,
        has_feedback=has_feedback,
        limit=limit,
        offset=offset,
    )
