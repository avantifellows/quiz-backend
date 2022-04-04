from fastapi import FastAPI
from routers import questions, quizzes
from mangum import Mangum

app = FastAPI()

app.include_router(questions.router)
app.include_router(quizzes.router)

handler = Mangum(app)
