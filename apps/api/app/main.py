"""FastAPI entry point for the MemoryCue vertical slice."""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import models  # noqa: F401 - registers models before table creation
from .database import get_db, init_db
from .query_service import answer_question
from .schemas import HealthResponse, QueryRequest, QueryResponse, SeedResponse
from .seed import seed_demo_data


init_db()

app = FastAPI(title="MemoryCue API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/api/demo/seed", response_model=SeedResponse)
def seed_demo(db: Session = Depends(get_db)) -> SeedResponse:
    return SeedResponse(status="ok", **seed_demo_data(db))


@app.post("/api/query", response_model=QueryResponse)
def query(request: QueryRequest, db: Session = Depends(get_db)) -> QueryResponse:
    return answer_question(db, request.question)
