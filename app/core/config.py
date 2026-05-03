import dotenv
import os

dotenv.load_dotenv()


class Config:

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
    R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
    R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
    R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")

    QDRANT_HOST_URL = os.getenv("QDRANT_HOST_URL")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
    QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "regulations")
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 800))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 150))

    DATABASE_URL = os.getenv("DATABASE_URL")

    # Tesseract OCR path (Windows/Linux/Mac)
    TESSERACT_CMD = os.getenv("TESSERACT_CMD")
