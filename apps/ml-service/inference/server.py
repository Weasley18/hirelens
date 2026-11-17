"""Authenticated, bounded inference; candidate text is never included in logs/errors."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv
_parents = Path(__file__).resolve().parents
if os.environ.get("APP_ENV", "development") == "development" and len(_parents) > 3:
    load_dotenv(_parents[3] / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from common import validate_analysis
from inference.limits import JD_MAX, JD_MIN, RESUME_MAX, RESUME_MIN
from inference.llm import BACKEND, generate_analysis, ContextLimitError, get_llm
from inference.skills import extract_skills, jd_only_skills
from inference.security import ServiceBoundary, service_token

log = logging.getLogger("hirelens")
_inference_lock = Lock()

@asynccontextmanager
async def lifespan(app):
    service_token()
    if os.environ.get("APP_ENV") == "production" and BACKEND != "gguf":
        raise RuntimeError("Production requires the gguf backend")
    if BACKEND == "gguf":
        get_llm()  # Fail startup if the configured artifact cannot be loaded.
    yield

app = FastAPI(title="HireLens inference", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.add_middleware(ServiceBoundary)

class AnalyzeRequest(BaseModel):
    resume: str = Field(min_length=RESUME_MIN, max_length=RESUME_MAX)
    jd: str = Field(min_length=JD_MIN, max_length=JD_MAX)

    @field_validator("resume", "jd", mode="before")
    @classmethod
    def document(cls, value):
        if not isinstance(value, str) or "<|" in value or "|>" in value:
            raise ValueError("Invalid document")
        return value.strip()

@app.exception_handler(RequestValidationError)
async def invalid_request(_request, _exc):
    # Default Pydantic responses can echo the supplied document.
    return JSONResponse({"error": "Invalid documents"}, status_code=422)

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

@app.get("/ready")
def readiness() -> dict:
    try:
        if BACKEND == "gguf":
            get_llm()
        elif os.environ.get("APP_ENV") == "production":
            raise RuntimeError("Invalid backend")
        from rag.retrieve import get_connection
        from rag.embedder import embed_query
        embed_query("readiness")
        with get_connection().cursor() as cursor:
            cursor.execute('SELECT count(*) FROM "KnowledgeChunk" WHERE embedding IS NOT NULL')
            if cursor.fetchone()[0] == 0:
                raise RuntimeError("Knowledge base empty")
    except Exception:
        raise HTTPException(503, "Service unavailable") from None
    return {"status": "ready"}

@app.post("/infer")
def infer(req: AnalyzeRequest) -> dict:
    if not _inference_lock.acquire(blocking=False):
        raise HTTPException(429, "Inference busy", headers={"Retry-After": "5"})
    try:
        if os.environ.get("APP_ENV") == "production" and BACKEND != "gguf":
            raise HTTPException(503, "Service unavailable")
        gaps = jd_only_skills(req.resume, req.jd, limit=3)
        skills = list(dict.fromkeys(gaps + extract_skills(req.resume, req.jd, limit=6)))
        chunks = []
        try:
            from rag.retrieve import retrieve_for_skills
            chunks = retrieve_for_skills(skills)
        except Exception:
            log.warning("Retrieval unavailable")
        try:
            analysis = generate_analysis(req.resume, req.jd, chunks)
        except ContextLimitError:
            raise HTTPException(422, "Documents exceed the model context budget") from None
        except Exception:
            log.warning("Inference failed")
            raise HTTPException(502, "Inference failed") from None
        if validate_analysis(analysis):
            log.warning("Invalid model output")
            raise HTTPException(502, "Invalid model output")
        return {"result": analysis, "metadata": {"backend": BACKEND, "grounded": bool(chunks)}}
    finally:
        _inference_lock.release()
