from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., description="The user's query")


class SourceDocument(BaseModel):
    title: str
    section_path: str | None = None
    source: str | None = None


class ChatResponse(BaseModel):
    answer: str
    source: list[SourceDocument] = []
