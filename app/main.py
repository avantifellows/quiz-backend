from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import questions, quizzes, session_answers, sessions
from mangum import Mangum

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

app.include_router(questions.router)
app.include_router(quizzes.router)
app.include_router(sessions.router)
app.include_router(session_answers.router)

handler = Mangum(app)
