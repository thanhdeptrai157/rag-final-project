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


class ChatResponse(BaseModel):
    answer: str
    source: list[SourceDocument] = Field(default_factory=list)
