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
from inference.llm import BACKEND, PRODUCTION_BACKENDS, generate_analysis, ContextLimitError, get_llm
from inference.skills import extract_skills, jd_only_skills
from inference.security import ServiceBoundary, service_token

log = logging.getLogger("hirelens")
_inference_lock = Lock()

@asynccontextmanager
async def lifespan(app):
    service_token()
    if os.environ.get("APP_ENV") == "production" and BACKEND not in PRODUCTION_BACKENDS:
        raise RuntimeError("Production requires the hosted or gguf backend")
    _check_backend()  # Fail startup if the model cannot be used.
    yield

def _check_backend() -> None:
    if BACKEND == "gguf":
        get_llm()
    elif BACKEND == "hosted":
        from inference.hosted import check_configuration
        check_configuration()  # settings only: readiness probes must not spend provider credit


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
        if os.environ.get("APP_ENV") == "production" and BACKEND not in PRODUCTION_BACKENDS:
            raise RuntimeError("Invalid backend")
        _check_backend()
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

class InvalidModelOutput(RuntimeError):
    pass


def analyze_documents(resume: str, jd: str) -> dict:
    """Retrieval, generation and validation: everything /infer does after authentication.

    eval.run_eval --direct calls this in-process, so the evaluation exercises the same path.
    """
    gaps = jd_only_skills(resume, jd, limit=3)
    skills = list(dict.fromkeys(gaps + extract_skills(resume, jd, limit=6)))
    chunks = []
    try:
        from rag.retrieve import retrieve_for_skills
        chunks = retrieve_for_skills(skills)
    except Exception:
        log.warning("Retrieval unavailable")
    analysis = generate_analysis(resume, jd, chunks)
    if validate_analysis(analysis):
        raise InvalidModelOutput()
    return {"result": analysis, "metadata": {"backend": BACKEND, "grounded": bool(chunks)}}


@app.post("/infer")
def infer(req: AnalyzeRequest) -> dict:
    if not _inference_lock.acquire(blocking=False):
        raise HTTPException(429, "Inference busy", headers={"Retry-After": "5"})
    try:
        if os.environ.get("APP_ENV") == "production" and BACKEND not in PRODUCTION_BACKENDS:
            raise HTTPException(503, "Service unavailable")
        try:
            return analyze_documents(req.resume, req.jd)
        except ContextLimitError:
            raise HTTPException(422, "Documents exceed the model context budget") from None
        except InvalidModelOutput:
            log.warning("Invalid model output")
            raise HTTPException(502, "Invalid model output") from None
        except Exception:
            log.warning("Inference failed")
            raise HTTPException(502, "Inference failed") from None
    finally:
        _inference_lock.release()
