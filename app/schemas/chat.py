from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., description="The user's query")


class SourceDocument(BaseModel):
    title: str | None = None
    section_path: str | None = None
    source: str | None = None
    file_path: str | None = None
    preview_url: str | None = None
    document_id: str | None = None
    mime_type: str | None = None
    score: float | None = None
    rerank_score: float | None = None
    lexical_score: float | None = None
    matched_query_count: int | None = None
    citation_id: int | None = None
    context: str | None = None


class ChatResponse(BaseModel):
    answer: str
    source: list[SourceDocument] = Field(default_factory=list)


ChatRole = Literal["user", "assistant"]
FeedbackReason = Literal[
    "incorrect",
    "incomplete",
    "irrelevant",
    "bad_citation",
    "outdated",
    "other",
]
AdminFeedbackStatus = Literal["open", "reviewed", "resolved"]


class ChatSessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class ChatSessionUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class ChatSessionOut(BaseModel):
    id: UUID
    user_id: UUID | None = None
    anonymous_id: str | None = None
    title: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionListItem(BaseModel):
    id: UUID
    title: str | None = None
    created_at: datetime
    updated_at: datetime
    last_message_preview: str | None = None
    message_count: int


class ChatMessageCreate(BaseModel):
    content: str = Field(..., min_length=1)


class MessageRagTraceOut(BaseModel):
    id: UUID
    message_id: UUID
    route: str | None = None
    latency_ms: int | None = None
    model_name: str | None = None
    retrieved_contexts: list[dict] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageFeedbackCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    reason: FeedbackReason | None = None
    comment: str | None = None
    expected_answer: str | None = None


class MessageFeedbackUpdate(BaseModel):
    admin_status: AdminFeedbackStatus | None = None
    admin_note: str | None = None


class MessageFeedbackOut(BaseModel):
    id: UUID
    message_id: UUID
    user_id: UUID | None = None
    rating: int
    reason: FeedbackReason | None = None
    comment: str | None = None
    expected_answer: str | None = None
    admin_status: AdminFeedbackStatus
    admin_note: str | None = None
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageOut(BaseModel):
    id: UUID
    session_id: UUID
    role: ChatRole
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageWithFeedbackOut(ChatMessageOut):
    feedback: MessageFeedbackOut | None = None
    rag_trace: MessageRagTraceOut | None = None


class ChatMessageSendResponse(ChatResponse):
    user_message: ChatMessageOut
    assistant_message: ChatMessageWithFeedbackOut
    rag_trace: MessageRagTraceOut | None = None


class ChatDeleteResponse(BaseModel):
    success: bool


class UserBasicOut(BaseModel):
    user_id: UUID
    email: str
    full_name: str | None = None

    model_config = {"from_attributes": True}


class AdminFeedbackItemOut(BaseModel):
    feedback: MessageFeedbackOut
    user: UserBasicOut | None = None
    assistant_message: ChatMessageOut
    user_question: ChatMessageOut | None = None
    session: ChatSessionOut
    rag_trace: MessageRagTraceOut | None = None


class AdminFeedbackFilters(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    reason: FeedbackReason | None = None
    admin_status: AdminFeedbackStatus | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class EvaluationDashboardOut(BaseModel):
    total_sessions: int
    total_messages: int
    total_feedbacks: int
    average_rating: float | None = None
    rating_distribution: dict[int, int]
    low_rating_reasons: dict[str, int]
    average_latency_ms: float | None = None
    route_distribution: dict[str, int]
    recent_feedbacks: list[AdminFeedbackItemOut]
    recent_sessions: list[ChatSessionListItem]
