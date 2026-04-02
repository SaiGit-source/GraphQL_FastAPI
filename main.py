from fastapi import FastAPI
from controller.user import user
app = FastAPI()
app.include_router(user)

