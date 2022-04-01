from fastapi import FastAPI
from routers import questions
from mangum import Mangum

app = FastAPI()

app.include_router(questions.router)

handler = Mangum(app)