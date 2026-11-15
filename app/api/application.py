"""FastAPI entry point for the separate LessonForge tutor API."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.tutor_routes import router as tutor_router
from app.conversation.database import init_tutor_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_tutor_db()
    yield


app = FastAPI(
    title="LessonForge AI Tutor API",
    version="1.0.0",
    description="Conversational tutor for completed LessonForge lessons.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(tutor_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "lessonforge-tutor"}
