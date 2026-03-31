from fastapi import FastAPI
from .routers import router

app = FastAPI(title="RAG API", version="1.0")

app.include_router(router, prefix="/api")
