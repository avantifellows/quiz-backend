from fastapi import FastAPI
from routes import player
app = FastAPI()

app.include_router(player)
