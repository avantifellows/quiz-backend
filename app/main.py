from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from routers import questions, quizzes, session_answers, sessions, organizations, forms
from models import APIErrorResponse
from mangum import Mangum
import random
import string
import time
from logger_config import setup_logger

logger = setup_logger()

COMPRESS_MIN_THRESHOLD = 1000  # if more than 1000 bytes (~1KB), compress

app = FastAPI()


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle standard HTTP exceptions."""
    logger.warning(f"HTTP error: {exc.detail} (status_code={exc.status_code})")
    content = APIErrorResponse(
        success=False, message=exc.detail, details=None
    ).dict()
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors."""
    logger.warning(f"Validation error: {exc.errors()}")
    content = APIErrorResponse(
        success=False, message="Validation failed", details=exc.errors()
    ).dict()
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=content
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handle all other unhandled exceptions."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    content = APIErrorResponse(
        success=False, message="Internal server error", details=None
    ).dict()
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=content
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Intercepts all http requests and logs their details like
    path, method, headers, time taken by request etc.

    Each request is assigned a random id (rid) which is used
    to track the request in logs.
    """
    # random id for request so that we can track it in logs
    idem = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    logger.info(
        f"rid={idem} start request path={request.url.path} method={request.method} headers={request.headers}"
    )
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    formatted_process_time = "{0:.2f}".format(process_time)
    logger.info(
        f"rid={idem} completed_in={formatted_process_time}ms status_code={response.status_code}"
    )

    return response


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


handler = Mangum(app)
