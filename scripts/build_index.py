from __future__ import annotations
import sys
from pathlib import Path

# Thêm root directory vào sys.path để có thể import app
sys.path.insert(0, str(Path(__file__).parent.parent))

import uuid
from app.chunking.regulation_chunker import RegulationChunker
from app.embedding.sentence_transformer_embedder import Embbedder
from app.loaders.pdf_loader import PDFLoader
from app.preprocessing.cleaners.text_cleaner import TextCleaner
from app.retrieval.indexing_service import chunk_to_payload, prepare_text_for_embedding
from app.schemas.document import Document
from app.vectordb.qdrant_store import QdrantStore


def main():
    loader = PDFLoader(force_ocr=True)
    cleaner = TextCleaner()
    chunker = RegulationChunker()
    embedder = Embbedder(model_name="BAAI/bge-m3")
    store = QdrantStore(collection_name="regulations")

    raw_dir = Path("data/raw")
    supported_suffixes = {".pdf"}

    if not raw_dir.exists():
        raise FileNotFoundError(f"Raw directory not found: {raw_dir}")

    raw_files = sorted([p for p in raw_dir.iterdir() if p.is_file()])
    if not raw_files:
        raise FileNotFoundError(f"No supported files found in raw directory: {raw_dir}")

    all_chunks = []

    for file_path in raw_files:
        if file_path.suffix.lower() not in supported_suffixes:
            print(f"[SKIP] Unsupported file type: {file_path.name}")
            continue

        print(f"[LOAD] {file_path}")
        doc_raw = loader.load(file_path)

        document = Document(
            doc_id=str(uuid.uuid4()),
            source_path=str(file_path),
            source_type=file_path.suffix.lower().lstrip("."),
            title=doc_raw.title,
            raw_text=cleaner.clean(doc_raw.raw_text),
            metadata=doc_raw.metadata,
        )

        chunks = chunker.chunk(document)
        all_chunks.extend(chunks)
        print(f"[CHUNKED] {file_path.name}: {len(chunks)} chunks")

    if not all_chunks:
        print("No chunks to process. Exiting.")
        return
    texts = [prepare_text_for_embedding(chunk) for chunk in all_chunks]
    payloads = [chunk_to_payload(chunk) for chunk in all_chunks]

    print(f"[EMBEDDING] Generating embeddings for {len(texts)} chunks...")
    vectors = embedder.embed_texts(texts)

    vector_size = len(vectors[0]) if vectors else 0
    print(
        f"[QDRANT] Upserting {len(vectors)} vectors into Qdrant (vector size: {vector_size})..."
    )
    store.recreate_collection(vector_size=vector_size)

    ids = [str(uuid.uuid4()) for _ in all_chunks]
    print(f"[QDRANT] Upserting vectors with IDs: {ids[:5]}... (showing first 5)")
    store.upsert_chunks(ids=ids, vectors=vectors, payloads=payloads)
    print("[DONE] Indexing complete.")


if __name__ == "__main__":
    main()
