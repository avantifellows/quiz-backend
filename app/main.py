from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import random
import string
import time

import database
from database import init_db, close_db
from cache import init_cache, close_cache
from logger_config import setup_logger
from routers import (
    questions,
    quizzes,
    session_answers,
    sessions,
    organizations,
    forms,
)

logger = setup_logger()

COMPRESS_MIN_THRESHOLD = 1000  # if more than 1000 bytes (~1KB), compress

# Paths whose last segment is a secret (organization API key) and must not be logged
_SECRET_PATH_PREFIXES = ("/organizations/authenticate/",)


def _loggable_path(path: str) -> str:
    for prefix in _SECRET_PATH_PREFIXES:
        if path.startswith(prefix):
            return prefix + "<redacted>"
    return path


@asynccontextmanager
async def lifespan(app):
    init_db()
    # Verify connectivity — fail fast on bad credentials/DNS/network
    await database._client.admin.command("ping")
    # Best-effort Redis init with a bounded connection deadline
    await init_cache()
    yield
    await close_cache()
    await close_db()


def create_app():
    app = FastAPI(lifespan=lifespan)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """
        Logs one line per request when it finishes: path, method,
        status code and time taken.

        Each request is assigned a random id (rid) which is used
        to track the request in logs.

        Request headers are deliberately not logged: they were most of
        the log volume (and CloudWatch cost) and carry client IPs.
        ALB health checks are not logged at all.
        """
        if request.url.path == "/health":
            return await call_next(request)

        # random id for request so that we can track it in logs
        idem = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        start_time = time.time()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            process_time = (time.time() - start_time) * 1000
            formatted_process_time = "{0:.2f}".format(process_time)
            logger.info(
                f"rid={idem} path={_loggable_path(request.url.path)} method={request.method} status_code={status_code} completed_in={formatted_process_time}ms"
            )

    origins = [
        "http://localhost:8080",
        "http://localhost:8081",
        "https://staging-quiz.avantifellows.org",
        "https://quiz.avantifellows.org",
        "http://localhost:3000",
        "https://staging-gurukul.avantifellows.org",
        "https://gurukul.avantifellows.org",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(
        GZipMiddleware,
        minimum_size=COMPRESS_MIN_THRESHOLD,
    )

    app.include_router(questions.router)
    app.include_router(quizzes.router)
    app.include_router(forms.router)
    app.include_router(sessions.router)
    app.include_router(session_answers.router)
    app.include_router(organizations.router)

    @app.get("/health", tags=["Health"])
    async def health_check():
        """Lightweight health check endpoint for ALB."""
        return {"status": "healthy"}

    return app


app = create_app()
