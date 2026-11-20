"""Private worker invocation. Mangum returns the validated final result to the worker."""
import http.client
import json
import re

from mangum import Mangum

from inference.citations import supported_items
from inference.progress import publish_field
from inference.server import app

_asgi = Mangum(app, lifespan="off")


def handler(event, context):
    # This metadata comes from the IAM-authorized invoker, outside the HTTP request body.
    progress = event.get("hirelensProgress")
    if not progress:
        return _asgi(event, context)
    host, job, credential = (progress.get(key, "") for key in ("host", "jobId", "token"))
    if not (re.fullmatch(r"[a-zA-Z0-9.-]+", host) and re.fullmatch(r"[a-f0-9-]{36}", job)
            and re.fullmatch(r"[a-f0-9]{64}", credential)):
        return _asgi(event, context)
    draft = {}
    enabled = True
    try:  # drafts are held to the final answer's evidence rule, so they need the documents
        body = json.loads(event.get("body") or "{}")
        documents = (str(body["resume"]), str(body["jd"]))
    except (TypeError, ValueError, KeyError):
        documents = None

    def publish(key, value):
        nonlocal enabled
        if not enabled:
            return
        if key is None:
            draft.clear()
        elif key in ("strengths", "gaps"):
            if documents is None:
                return  # cannot verify quotes: show this field only in the final answer
            draft[key] = supported_items(key, value, *documents)
        elif key in ("fitScore", "verdict", "interviewQuestions"):
            draft[key] = value
        else:
            return
        # Best effort. Losing a preview must not lose the authoritative final assessment.
        connection = http.client.HTTPSConnection(host, timeout=2)
        try:
            connection.request("POST", f"/analyze/{job}/preview", body=json.dumps(draft),
                               headers={"Authorization": f"Bearer {credential}", "Content-Type": "application/json"})
            enabled = connection.getresponse().status == 204
        except (OSError, http.client.HTTPException):
            enabled = False
        finally:
            connection.close()

    token = publish_field.set(publish)
    try:
        return _asgi(event, context)
    finally:
        publish_field.reset(token)
