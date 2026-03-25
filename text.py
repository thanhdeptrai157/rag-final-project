from app.loaders.pdf_loader import PDFLoader
from app.preprocessing.cleaners.text_cleaner import TextCleaner
from app.chunking.regulation_chunker import RegulationChunker
from app.schemas.document import Document
import uuid
from pathlib import Path

loader = PDFLoader(force_ocr=True)
cleaner = TextCleaner()
chunker = RegulationChunker()

raw_dir = Path("data/raw")
supported_suffixes = {".pdf"}

if not raw_dir.exists():
    raise FileNotFoundError(f"Raw directory not found: {raw_dir}")

raw_files = sorted([p for p in raw_dir.iterdir() if p.is_file()])
if not raw_files:
    raise FileNotFoundError(f"No files found in raw directory: {raw_dir}")

all_chunks = []
per_file_stats = []

for file_path in raw_files:
    if file_path.suffix.lower() not in supported_suffixes:
        print(f"[SKIP] Unsupported file type: {file_path.name}")
        continue

    print(f"[LOAD] {file_path}")
    doc_raw = loader.load(file_path)

    # tạo Document chuẩn schema
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
    per_file_stats.append((file_path.name, len(chunks)))
    print(f"[DONE] {file_path.name}: {len(chunks)} chunks")

print(f"Total files processed: {len(per_file_stats)}")
print(f"Total chunks: {len(all_chunks)}")

output_path = Path("data/processed/chunks_output2.txt")
output_path.parent.mkdir(parents=True, exist_ok=True)

with output_path.open("w", encoding="utf-8") as f:
    f.write(f"Total files processed: {len(per_file_stats)}\n")
    f.write(f"Total chunks: {len(all_chunks)}\n\n")

    f.write("Chunks per file:\n")
    for file_name, chunk_count in per_file_stats:
        f.write(f"- {file_name}: {chunk_count}\n")
    f.write("\n")

    for i, c in enumerate(all_chunks, start=1):
        f.write("=" * 100 + "\n")
        f.write(f"Chunk #{i}\n")
        f.write(f"chunk_id: {c.chunk_id}\n")
        f.write(f"document_id: {c.document_id}\n")
        f.write(f"chunk_type: {c.chunk_type}\n")
        f.write(f"section_path: {c.section_path}\n")
        f.write(f"title: {c.title}\n")
        f.write(f"chunk_index: {c.chunk_index}\n")
        f.write(f"total_chunks: {c.total_chunks}\n")
        f.write("metadata:\n")
        for k, v in c.metadata.items():
            f.write(f"  - {k}: {v}\n")
        f.write("\ntext:\n")
        f.write(c.text)
        f.write("\n\n")

print(f"Saved chunks to: {output_path}")
