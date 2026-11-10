"""Exercise authentication and real stub generation in a freshly built runtime."""
import os
import secrets
from fastapi.testclient import TestClient
from common import validate_analysis
from inference.server import app

os.environ["ML_SERVICE_TOKEN"] = secrets.token_hex(32)
with TestClient(app) as client:
    assert client.get("/health").status_code == 200
    assert client.post("/infer", json={}).status_code == 401
    response = client.post("/infer", headers={"Authorization": "Bearer " + os.environ["ML_SERVICE_TOKEN"]}, json={
        "resume": "Backend engineer using Python, SQL and testing to build reliable services. " * 3,
        "jd": "Seeking a Python engineer with SQL and testing experience for backend services. " * 3,
    })
    assert response.status_code == 200, response.status_code
    assert response.json()["metadata"]["backend"] == "stub"
    assert not validate_analysis(response.json()["result"])
print("Clean-runtime inference smoke passed (stub)")
