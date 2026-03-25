from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class Chunk(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    cleaned_text: str
    
    chunk_type: str
    title: Optional[str] = None
    section_path: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    chunk_index: int = 0
    total_chunks: int = 0
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    