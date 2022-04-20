from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import questions, quizzes
from mangum import Mangum

app = FastAPI()

origins = ["http://localhost:8080"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(questions.router)
app.include_router(quizzes.router)

handler = Mangum(app)
