from fastapi import FastAPI
from routers import chat

app = FastAPI()

app.include_router(chat.router)

@app.get("/")
def read_root():
    return {"message": "AI Integration Service is running!"}

# Chạy server bằng lệnh: uvicorn main:app --reload