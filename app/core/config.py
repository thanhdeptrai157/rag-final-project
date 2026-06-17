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
    RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
    RERANKER_ENABLED = os.getenv("RERANKER_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    RERANKER_CACHE_DIR = os.getenv(
        "RERANKER_CACHE_DIR",
        os.path.join(os.getenv("HF_HOME", "/app/.cache/huggingface"), "reranker"),
    )
    RERANKER_LOCAL_FILES_ONLY = os.getenv(
        "RERANKER_LOCAL_FILES_ONLY", "false"
    ).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    RERANKER_BATCH_SIZE = int(os.getenv("RERANKER_BATCH_SIZE", "8"))
    RERANKER_MAX_LENGTH = int(os.getenv("RERANKER_MAX_LENGTH", "1024"))
    RERANKER_MAX_CANDIDATES = int(os.getenv("RERANKER_MAX_CANDIDATES", "30"))
    PDF_OCR_PROVIDER = os.getenv("PDF_OCR_PROVIDER", "paddle").lower()

    DATABASE_URL = os.getenv("DATABASE_URL")
    DATABASE_POOL_RECYCLE_SECONDS = int(
        os.getenv("DATABASE_POOL_RECYCLE_SECONDS", "1800")
    )

    # Tesseract OCR path (Windows/Linux/Mac)
    TESSERACT_CMD = os.getenv("TESSERACT_CMD")

    OLLAMA_HOST = os.getenv("OLLAMA_HOST")
    OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")

    JWT_SECRET_KEY = os.getenv(
        "JWT_SECRET_KEY", "dev-only-change-this-jwt-secret"
    )
    ACCESS_TOKEN_EXPIRE_MINUTES = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")
    )
    REFRESH_TOKEN_EXPIRE_MINUTES = int(
        os.getenv("REFRESH_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 30))
    )
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
