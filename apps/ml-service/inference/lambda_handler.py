"""Lambda entry point (Phase 8.3).

Lambda hands the function an event dict, not an HTTP request. Mangum translates between that
and ASGI so the same FastAPI app runs locally under uvicorn and in Lambda unchanged.
"""

from mangum import Mangum

from inference.server import app

handler = Mangum(app, lifespan="off")
