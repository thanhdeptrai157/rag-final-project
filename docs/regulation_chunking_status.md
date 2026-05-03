# Status: Chunking 1 văn bản regulation

Cập nhật: 2026-05-03

## Mục tiêu hiện tại

Mục tiêu của nhánh hiện tại là ingest một văn bản regulation từ file upload, trích xuất nội dung, tách thành các chunk theo cấu trúc pháp lý, sau đó lưu chunk vào Postgres và đẩy embedding lên Qdrant để phục vụ truy hồi.

## Luồng xử lý hiện tại

### 1. Upload tài liệu
- API upload nằm ở `app/api/routes/document_router.py`.
- Service upload nằm ở `app/api/service/document_service.py`.
- File được lưu lên R2 thông qua `R2Storage`.
- Bản ghi document được tạo với `status=uploaded` và một ingest job được enqueue.

### 2. Download file từ R2
- Worker/ingest pipeline lấy `file_path` từ document.
- `IngestPipeline` tải file bytes từ R2 trong `app/pipeline/ingest_pipeline.py`.
- File bytes được ghi ra temp file `.pdf` để OCR và đọc nội dung.

### 3. OCR và clean text
- `PDFLoader` trong `app/loaders/pdf_loader.py` đọc PDF bằng PyMuPDF.
- Nếu text quá ngắn hoặc `force_ocr=True`, hệ thống sẽ OCR từng trang bằng Tesseract.
- Output là `Document` schema có `raw_text` và metadata theo từng trang.
- `TextCleaner` được dùng để làm sạch text trước khi chunk.

### 4. Parse cấu trúc regulation
- Hiện tại pipeline đang dùng `RegulationParser` ở `app/preprocessing/structure/regulation_parser.py`.
- Parser này dựa vào `SectionDetector` để phát hiện:
  - chương
  - mục
  - điều
- Kết quả parse là danh sách `ParsedArticle`, mỗi phần tử đại diện cho một điều luật.

### 5. Tạo chunk regulation
- `RegulationChunker` ở `app/chunking/regulation_chunker.py` biến mỗi điều thành một chunk.
- Mỗi chunk gồm:
  - `chunk_type = regulation`
  - `title` là tiêu đề điều
  - `section_path` ghép từ chương / mục / điều
  - `metadata` chứa `source`, `doc_title`, `chapter`, `section`, `article_number`
- Đây là nơi quyết định cách tách 1 văn bản regulation thành nhiều chunk logic.

### 6. Lưu chunk và index
- Chunk được insert vào Postgres qua `ChunkRepository`.
- Nội dung chunk được embed bằng `Embbedder`.
- Vector và payload được upsert vào Qdrant.
- Sau đó hệ thống cập nhật `embedding_id` cho từng chunk và mark document là `processed`.

## Trạng thái hiện tại của support regulation

### Đã làm được
- Có pipeline end-to-end cho regulation.
- Có parser riêng cho cấu trúc regulation.
- Có chunker riêng cho regulation.
- Có lưu version text raw/cleaned lên R2.
- Có lưu chunk, embedding và payload lên Qdrant.

### Chưa hoàn chỉnh / giới hạn hiện tại
- Pipeline ingest đang hardcode `RegulationChunker`, nên hiện chỉ đi theo luồng regulation.
- Các file cho loại văn bản khác như `announcement_chunker.py` và `curriculum_parser.py` هنوز trống.
- `DocumentService` cho phép upload PDF, DOCX, TXT, nhưng `PDFLoader` hiện chỉ xử lý PDF trực tiếp trong pipeline.
- Cách chunk hiện tại phụ thuộc khá nhiều vào nhận diện heading chuẩn OCR; nếu OCR bẩn hoặc heading không ổn định thì có thể không tách được chunk.

## Khi chunk 1 regulation document, logic hiện tại là gì?

1. Upload file regulation.
2. Worker tải file từ R2.
3. OCR toàn bộ PDF nếu cần.
4. Clean text.
5. Parser tìm các mốc cấu trúc như chương, mục, điều.
6. Mỗi điều trở thành 1 chunk.
7. Chunk được gắn `section_path` để giữ ngữ cảnh.
8. Chunk được lưu DB và index lên Qdrant.

## Kết luận ngắn

Ở thời điểm hiện tại, project đã có một luồng chunking khá rõ ràng cho **1 văn bản regulation**, nhưng đây עדיין là luồng chuyên biệt. Nếu muốn mở rộng sang thông báo hoặc loại văn bản khác, cần tách ingest theo document type và bổ sung parser/chunker tương ứng.
