from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from routers import questions, quizzes, session_answers, sessions, organizations
from mangum import Mangum

COMPRESS_MIN_THRESHOLD = 100  # if more than 100 bytes, compress

app = FastAPI()

origins = [
    "http://localhost:8080",
    "https://staging-quiz.avantifellows.org",
    "https://quiz.avantifellows.org",
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
app.include_router(sessions.router)
app.include_router(session_answers.router)
app.include_router(organizations.router)

handler = Mangum(app)
