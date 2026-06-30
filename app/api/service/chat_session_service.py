from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import and_, exists, func, or_
from sqlalchemy.orm import Session, joinedload

from app.api.repositories.chat_repository import ChatRepository
from app.api.service.chat_service import format_sse
from app.core.database import get_db
from app.models.chat import (
    ChatMessage,
    ChatSession,
    MessageFeedback,
    MessageRagTrace,
)
from app.models.user import User
from app.schemas.chat import (
    AdminFeedbackItemOut,
    ChatMessageCreate,
    ChatMessageOut,
    ChatMessageSendResponse,
    ChatMessageWithFeedbackOut,
    ChatSessionCreate,
    ChatSessionListItem,
    ChatSessionOut,
    ChatSessionUpdate,
    EvaluationDashboardOut,
    MessageFeedbackCreate,
    MessageFeedbackOut,
    MessageFeedbackUpdate,
    MessageRagTraceOut,
    UserBasicOut,
)
from app.schemas.common import PageResponse


class ChatSessionService:
    def __init__(self, db: Session = Depends(get_db)) -> None:
        self.db = db

    def list_sessions(
        self,
        *,
        current_user: User,
        search: str | None = None,
        limit: int = 20,
        offset: int = 0,
        has_feedback: bool | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[ChatSessionListItem]:
        query = self._owned_sessions_query(current_user)

        if search:
            pattern = f"%{search.strip()}%"
            message_match = exists().where(
                and_(
                    ChatMessage.session_id == ChatSession.id,
                    ChatMessage.content.ilike(pattern),
                )
            )
            query = query.filter(or_(ChatSession.title.ilike(pattern), message_match))

        if date_from:
            query = query.filter(ChatSession.updated_at >= date_from)
        if date_to:
            query = query.filter(ChatSession.updated_at <= date_to)
        if has_feedback is not None:
            feedback_exists = exists().where(
                and_(
                    ChatMessage.session_id == ChatSession.id,
                    MessageFeedback.message_id == ChatMessage.id,
                )
            )
            query = query.filter(feedback_exists if has_feedback else ~feedback_exists)

        sessions = (
            query.order_by(ChatSession.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._to_session_list_item(session) for session in sessions]

    def create_session(
        self, *, current_user: User, payload: ChatSessionCreate
    ) -> ChatSessionOut:
        session = ChatSession(
            user_id=current_user.user_id,
            title=self._clean_title(payload.title),
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return ChatSessionOut.model_validate(session)

    def update_session(
        self, *, current_user: User, session_id: UUID, payload: ChatSessionUpdate
    ) -> ChatSessionOut:
        session = self.require_owned_session(session_id, current_user)
        data = payload.model_dump(exclude_unset=True)
        if "title" in data:
            session.title = self._clean_title(data["title"])
        session.updated_at = _utcnow()
        self.db.commit()
        self.db.refresh(session)
        return ChatSessionOut.model_validate(session)

    def delete_session(self, *, current_user: User, session_id: UUID) -> None:
        session = self.require_owned_session(session_id, current_user)
        now = _utcnow()
        session.deleted_at = now
        session.updated_at = now
        self.db.commit()

    def require_owned_session(
        self, session_id: UUID, current_user: User
    ) -> ChatSession:
        session = (
            self._owned_sessions_query(current_user)
            .filter(ChatSession.id == session_id)
            .first()
        )
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session not found",
            )
        return session

    def _owned_sessions_query(self, current_user: User):
        return self.db.query(ChatSession).filter(
            ChatSession.user_id == current_user.user_id,
            ChatSession.deleted_at.is_(None),
        )

    def _to_session_list_item(self, session: ChatSession) -> ChatSessionListItem:
        last_message = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        message_count = (
            self.db.query(func.count(ChatMessage.id))
            .filter(ChatMessage.session_id == session.id)
            .scalar()
            or 0
        )
        return ChatSessionListItem(
            id=session.id,
            title=session.title,
            created_at=session.created_at,
            updated_at=session.updated_at,
            last_message_preview=_preview(
                last_message.content if last_message else None
            ),
            message_count=message_count,
        )

    def _clean_title(self, title: str | None) -> str | None:
        value = str(title or "").strip()
        return value[:255] if value else None


class ChatMessageService:
    def __init__(
        self,
        db: Session = Depends(get_db),
        chat_repo: ChatRepository = Depends(),
        session_service: ChatSessionService = Depends(),
    ) -> None:
        self.db = db
        self.chat_repo = chat_repo
        self.session_service = session_service

    def list_messages(
        self, *, current_user: User, session_id: UUID
    ) -> list[ChatMessageWithFeedbackOut]:
        self.session_service.require_owned_session(session_id, current_user)
        messages = (
            self.db.query(ChatMessage)
            .options(
                joinedload(ChatMessage.rag_trace),
                joinedload(ChatMessage.feedbacks),
            )
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        return [
            self._to_message_with_feedback(message, current_user)
            for message in messages
        ]

    def send_message(
        self, *, current_user: User, session_id: UUID, payload: ChatMessageCreate
    ) -> ChatMessageSendResponse:
        session = self.session_service.require_owned_session(session_id, current_user)
        content = payload.content.strip()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Message content is required",
            )

        chat_history = self._load_chat_history(session.id)

        user_message = ChatMessage(
            session_id=session.id,
            role="user",
            content=content,
        )
        self.db.add(user_message)
        self.db.flush()

        start = _utcnow()
        try:
            result = self.chat_repo.answer_query(
                question=content,
                top_k=3,
                chat_history=chat_history,
            )
        except Exception as exc:
            result = {
                "answer": f"Error processing request: {str(exc)}",
                "sources": [],
                "route": "fallback",
            }
        latency_ms = int((_utcnow() - start).total_seconds() * 1000)

        assistant_message = ChatMessage(
            session_id=session.id,
            role="assistant",
            content=str(result.get("answer") or ""),
        )
        self.db.add(assistant_message)
        self.db.flush()

        rag_trace = MessageRagTrace(
            message_id=assistant_message.id,
            route=result.get("route"),
            latency_ms=latency_ms,
            model_name=self._model_name(),
            retrieved_contexts=_json_list(result.get("sources")),
            citations=_json_list(result.get("citations") or result.get("sources")),
        )
        self.db.add(rag_trace)

        now = _utcnow()
        if not session.title:
            session.title = self._generate_title(content)
        session.updated_at = now
        self.db.commit()
        self.db.refresh(user_message)
        self.db.refresh(assistant_message)
        self.db.refresh(rag_trace)

        assistant_out = self._to_message_with_feedback(assistant_message, current_user)
        return ChatMessageSendResponse(
            answer=assistant_out.content,
            source=_json_list(result.get("sources")),
            user_message=ChatMessageOut.model_validate(user_message),
            assistant_message=assistant_out,
            rag_trace=MessageRagTraceOut.model_validate(rag_trace),
        )

    def stream_send_message(
        self, *, current_user: User, session_id: UUID, payload: ChatMessageCreate
    ) -> Iterator[str]:
        session = self.session_service.require_owned_session(session_id, current_user)
        content = payload.content.strip()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Message content is required",
            )

        chat_history = self._load_chat_history(session.id)

        return self._stream_send_message_events(
            current_user=current_user,
            session=session,
            content=content,
            chat_history=chat_history,
        )

    def _stream_send_message_events(
        self,
        *,
        current_user: User,
        session: ChatSession,
        content: str,
        chat_history: list[dict] | None = None,
    ) -> Iterator[str]:
        user_message = ChatMessage(
            session_id=session.id,
            role="user",
            content=content,
        )
        self.db.add(user_message)
        self.db.flush()
        yield format_sse(
            {
                "type": "message_saved",
                "role": "user",
                "user_message": ChatMessageOut.model_validate(user_message).model_dump(
                    mode="json"
                ),
            }
        )

        start = _utcnow()
        answer_parts = []
        final_result = {
            "answer": "",
            "sources": [],
            "route": None,
        }

        try:
            for event in self.chat_repo.stream_answer_query(
                question=content,
                top_k=3,
                chat_history=chat_history,
            ):
                event_type = event.get("type")

                if event_type == "answer_delta":
                    answer_parts.append(str(event.get("delta") or ""))
                    yield format_sse(event)
                    continue

                if event_type == "done":
                    final_result = event
                    continue

                yield format_sse(event)
        except Exception as exc:
            final_result = {
                "answer": f"Error processing request: {str(exc)}",
                "sources": [],
                "route": "fallback",
            }
            yield format_sse(
                {
                    "type": "error",
                    "message": final_result["answer"],
                }
            )

        latency_ms = int((_utcnow() - start).total_seconds() * 1000)
        answer = str(final_result.get("answer") or "".join(answer_parts))
        sources = _json_list(final_result.get("sources"))

        assistant_message = ChatMessage(
            session_id=session.id,
            role="assistant",
            content=answer,
        )
        self.db.add(assistant_message)
        self.db.flush()

        rag_trace = MessageRagTrace(
            message_id=assistant_message.id,
            route=final_result.get("route"),
            latency_ms=latency_ms,
            model_name=self._model_name(),
            retrieved_contexts=sources,
            citations=_json_list(final_result.get("citations") or sources),
        )
        self.db.add(rag_trace)

        now = _utcnow()
        if not session.title:
            session.title = self._generate_title(content)
        session.updated_at = now
        self.db.commit()
        self.db.refresh(user_message)
        self.db.refresh(assistant_message)
        self.db.refresh(rag_trace)

        assistant_out = self._to_message_with_feedback(assistant_message, current_user)
        yield format_sse(
            {
                "type": "message_saved",
                "role": "assistant",
                "assistant_message": assistant_out.model_dump(mode="json"),
                "rag_trace": MessageRagTraceOut.model_validate(rag_trace).model_dump(
                    mode="json"
                ),
            }
        )
        yield format_sse(
            {
                "type": "done",
                "answer": assistant_out.content,
                "sources": sources,
                "route": final_result.get("route"),
                "user_message": ChatMessageOut.model_validate(user_message).model_dump(
                    mode="json"
                ),
                "assistant_message": assistant_out.model_dump(mode="json"),
                "rag_trace": MessageRagTraceOut.model_validate(rag_trace).model_dump(
                    mode="json"
                ),
            }
        )

    def _to_message_with_feedback(
        self, message: ChatMessage, current_user: User
    ) -> ChatMessageWithFeedbackOut:
        feedback = None
        if message.role == "assistant":
            feedback = next(
                (
                    item
                    for item in (message.feedbacks or [])
                    if item.user_id == current_user.user_id
                ),
                None,
            )

        return ChatMessageWithFeedbackOut(
            **ChatMessageOut.model_validate(message).model_dump(),
            feedback=(
                MessageFeedbackOut.model_validate(feedback) if feedback else None
            ),
            rag_trace=(
                MessageRagTraceOut.model_validate(message.rag_trace)
                if message.rag_trace
                else None
            ),
        )

    def _load_chat_history(
        self,
        session_id: UUID,
        limit: int = 12,
    ) -> list[dict]:
        messages = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in reversed(messages)
        ]

    def _generate_title(self, content: str) -> str:
        title = " ".join(content.split())
        return title[:80]

    def _model_name(self) -> str | None:
        llm = getattr(getattr(self.chat_repo, "rag_service", None), "llm", None)
        if not llm:
            return None
        return (
            getattr(llm, "model", None)
            or getattr(llm, "model_name", None)
            or llm.__class__.__name__
        )


class MessageFeedbackService:
    def __init__(
        self,
        db: Session = Depends(get_db),
        session_service: ChatSessionService = Depends(),
    ) -> None:
        self.db = db
        self.session_service = session_service

    def submit_feedback(
        self, *, current_user: User, message_id: UUID, payload: MessageFeedbackCreate
    ) -> MessageFeedbackOut:
        message = self._require_feedback_target(message_id, current_user)
        feedback = (
            self.db.query(MessageFeedback)
            .filter(
                MessageFeedback.message_id == message.id,
                MessageFeedback.user_id == current_user.user_id,
            )
            .first()
        )

        data = payload.model_dump()

        if feedback:
            for key, value in data.items():
                setattr(feedback, key, value)
        else:
            feedback = MessageFeedback(
                message_id=message.id,
                user_id=current_user.user_id,
                **data,
            )
            self.db.add(feedback)

        self.db.commit()
        self.db.refresh(feedback)
        return MessageFeedbackOut.model_validate(feedback)

    def _require_feedback_target(
        self, message_id: UUID, current_user: User
    ) -> ChatMessage:
        message = (
            self.db.query(ChatMessage)
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)
            .filter(
                ChatMessage.id == message_id,
                ChatMessage.role == "assistant",
                ChatSession.user_id == current_user.user_id,
                ChatSession.deleted_at.is_(None),
            )
            .first()
        )
        if not message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assistant message not found",
            )
        return message


class AdminFeedbackService:
    def __init__(self, db: Session = Depends(get_db)) -> None:
        self.db = db

    def list_feedbacks(
        self,
        *,
        rating: int | None = None,
        reason: str | None = None,
        admin_status: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PageResponse[AdminFeedbackItemOut]:
        query = self._feedback_query()
        query = self._apply_filters(
            query,
            rating=rating,
            reason=reason,
            admin_status=admin_status,
            date_from=date_from,
            date_to=date_to,
        )
        total: int = query.count()
        offset = (page - 1) * page_size
        feedbacks = (
            query.order_by(MessageFeedback.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )
        return PageResponse[AdminFeedbackItemOut].create(
            items=[self._to_admin_feedback_item(feedback) for feedback in feedbacks],
            total=total,
            page=page,
            page_size=page_size,
        )

    def update_feedback(
        self, *, current_admin: User, feedback_id: UUID, payload: MessageFeedbackUpdate
    ) -> MessageFeedbackOut:
        feedback = (
            self.db.query(MessageFeedback)
            .filter(MessageFeedback.id == feedback_id)
            .first()
        )
        if not feedback:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Feedback not found",
            )

        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(feedback, key, value)
        feedback.reviewed_by = current_admin.user_id
        feedback.reviewed_at = _utcnow()
        self.db.commit()
        self.db.refresh(feedback)
        return MessageFeedbackOut.model_validate(feedback)

    def _feedback_query(self):
        return self.db.query(MessageFeedback).options(
            joinedload(MessageFeedback.user),
            joinedload(MessageFeedback.message)
            .joinedload(ChatMessage.session)
            .joinedload(ChatSession.user),
            joinedload(MessageFeedback.message).joinedload(ChatMessage.rag_trace),
        )

    def _apply_filters(self, query, **filters):
        if filters["rating"] is not None:
            query = query.filter(MessageFeedback.rating == filters["rating"])
        if filters["reason"]:
            query = query.filter(MessageFeedback.reason == filters["reason"])
        if filters["admin_status"]:
            query = query.filter(
                MessageFeedback.admin_status == filters["admin_status"]
            )
        if filters["date_from"]:
            query = query.filter(MessageFeedback.created_at >= filters["date_from"])
        if filters["date_to"]:
            query = query.filter(MessageFeedback.created_at <= filters["date_to"])
        return query

    def _to_admin_feedback_item(
        self, feedback: MessageFeedback
    ) -> AdminFeedbackItemOut:
        assistant_message = feedback.message
        session = assistant_message.session
        user_question = (
            self.db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == assistant_message.session_id,
                ChatMessage.role == "user",
                ChatMessage.created_at <= assistant_message.created_at,
            )
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        return AdminFeedbackItemOut(
            feedback=MessageFeedbackOut.model_validate(feedback),
            user=UserBasicOut.model_validate(feedback.user) if feedback.user else None,
            assistant_message=ChatMessageOut.model_validate(assistant_message),
            user_question=(
                ChatMessageOut.model_validate(user_question) if user_question else None
            ),
            session=ChatSessionOut.model_validate(session),
            rag_trace=(
                MessageRagTraceOut.model_validate(assistant_message.rag_trace)
                if assistant_message.rag_trace
                else None
            ),
        )


class EvaluationDashboardService:
    def __init__(
        self,
        db: Session = Depends(get_db),
        admin_feedback_service: AdminFeedbackService = Depends(),
        session_service: ChatSessionService = Depends(),
    ) -> None:
        self.db = db
        self.admin_feedback_service = admin_feedback_service
        self.session_service = session_service

    def get_dashboard(self) -> EvaluationDashboardOut:
        total_sessions = self.db.query(func.count(ChatSession.id)).scalar() or 0
        total_messages = self.db.query(func.count(ChatMessage.id)).scalar() or 0
        total_feedbacks = self.db.query(func.count(MessageFeedback.id)).scalar() or 0
        average_rating = self.db.query(func.avg(MessageFeedback.rating)).scalar()
        average_latency = self.db.query(func.avg(MessageRagTrace.latency_ms)).scalar()

        rating_distribution = {rating: 0 for rating in range(1, 6)}
        for rating, count in (
            self.db.query(MessageFeedback.rating, func.count(MessageFeedback.id))
            .group_by(MessageFeedback.rating)
            .all()
        ):
            rating_distribution[int(rating)] = count

        low_rating_reasons = {
            str(reason): count
            for reason, count in (
                self.db.query(MessageFeedback.reason, func.count(MessageFeedback.id))
                .filter(MessageFeedback.rating <= 3, MessageFeedback.reason.isnot(None))
                .group_by(MessageFeedback.reason)
                .all()
            )
        }
        route_distribution = {
            str(route): count
            for route, count in (
                self.db.query(MessageRagTrace.route, func.count(MessageRagTrace.id))
                .filter(MessageRagTrace.route.isnot(None))
                .group_by(MessageRagTrace.route)
                .all()
            )
        }
        recent_feedbacks = self.admin_feedback_service.list_feedbacks(page=1, page_size=5).items
        recent_sessions = (
            self.db.query(ChatSession)
            .filter(ChatSession.deleted_at.is_(None))
            .order_by(ChatSession.updated_at.desc())
            .limit(5)
            .all()
        )

        return EvaluationDashboardOut(
            total_sessions=total_sessions,
            total_messages=total_messages,
            total_feedbacks=total_feedbacks,
            average_rating=(
                float(average_rating) if average_rating is not None else None
            ),
            rating_distribution=rating_distribution,
            low_rating_reasons=low_rating_reasons,
            average_latency_ms=(
                float(average_latency) if average_latency is not None else None
            ),
            route_distribution=route_distribution,
            recent_feedbacks=recent_feedbacks,
            recent_sessions=[
                self.session_service._to_session_list_item(session)
                for session in recent_sessions
            ],
        )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _preview(value: str | None, limit: int = 160) -> str | None:
    if not value:
        return None
    compact = " ".join(value.split())
    return compact[:limit]


def _json_list(value) -> list[dict]:
    if not value:
        return []
    if isinstance(value, list):
        return [item if isinstance(item, dict) else {"value": item} for item in value]
    return [{"value": value}]
