from __future__ import annotations

from sentence_transformers import SentenceTransformer
from typing import List

class Embbedder: 
    def __init__(self, model_name: str= "BAAI/bge-m3"):
        self.model = SentenceTransformer(model_name)
        
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts: 
            return []
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=True,
        )
        return embeddings.tolist()
    
    def embed_query(self, query: str) -> List[float]:
        embedding = self.model.encode(
            [query],
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        
        return embedding[0].tolist()
    
    