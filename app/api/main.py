from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.workers.background_worker import (
    start_background_worker,
    stop_background_worker,
)
from .routers import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Khởi động/dừng background worker cùng với app lifecycle."""
    print("[APP] Starting up...")
    start_background_worker()
    yield
    print("[APP] Shutting down...")
    stop_background_worker()


app = FastAPI(title="RAG API", version="1.0", lifespan=lifespan)

app.include_router(router, prefix="/api")
