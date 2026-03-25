from typing import Any

from pydantic import BaseModel, Field

class Document(BaseModel):
    doc_id: str
    source_path: str
    source_type: str
    title: str
    raw_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    
