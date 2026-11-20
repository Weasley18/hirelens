"""Authenticated, bounded inference; candidate text is never included in logs/errors."""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from queue import SimpleQueue
from threading import Lock, Thread

from dotenv import load_dotenv
_parents = Path(__file__).resolve().parents
if os.environ.get("APP_ENV", "development") == "development" and len(_parents) > 3:
    load_dotenv(_parents[3] / ".env")

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from common import validate_analysis
from inference.citations import removed_upstream, supported_items, verify
from inference.limits import JD_MAX, JD_MIN, RESUME_MAX, RESUME_MIN
from inference.llm import BACKEND, PRODUCTION_BACKENDS, generate_analysis, ContextLimitError, get_llm
from inference.progress import publish_field
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
    upstream = removed_upstream.set(0)
    try:
        analysis = generate_analysis(resume, jd, chunks)
        removed_before = removed_upstream.get()
    finally:
        removed_upstream.reset(upstream)
    if validate_analysis(analysis):
        raise InvalidModelOutput()
    # Every backend is held to the same rule: only claims whose quotes occur in the documents.
    supported, report = verify(analysis, resume, jd)
    if validate_analysis(supported):
        raise InvalidModelOutput()  # no supported strength left
    citations = {"checked": report.checked + removed_before, "removed": len(report.removed) + removed_before}
    return {"result": supported, "metadata": {"backend": BACKEND, "grounded": bool(chunks), "citations": citations}}


def _infer(req):
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


def _stream_inference(req):
    events = SimpleQueue()

    def field(key, value):
        if key is None:
            events.put({"reset": True})
        elif key in ("fitScore", "verdict", "strengths", "gaps", "interviewQuestions"):
            # Drafts are held to the same evidence rule as the final answer.
            events.put({"field": key, "value": supported_items(key, value, req.resume, req.jd)})

    def produce():
        token = publish_field.set(field)
        try:
            events.put({"done": _infer(req)})
        except HTTPException as exc:
            events.put({"error": exc.status_code})
        finally:
            publish_field.reset(token)
            _inference_lock.release()
            events.put(None)

    def lines():
        while (event := events.get()) is not None:
            yield json.dumps(event, ensure_ascii=False) + "\n"

    Thread(target=produce, daemon=True).start()
    return StreamingResponse(lines(), media_type="application/x-ndjson")


@app.post("/infer", response_model=None)
def infer(req: AnalyzeRequest, request: Request):
    if os.environ.get("APP_ENV") == "production" and BACKEND not in PRODUCTION_BACKENDS:
        raise HTTPException(503, "Service unavailable")
    if not _inference_lock.acquire(blocking=False):
        raise HTTPException(429, "Inference busy", headers={"Retry-After": "5"})
    if request.headers.get("accept") == "application/x-ndjson":
        return _stream_inference(req)
    try:
        return _infer(req)
    finally:
        _inference_lock.release()
