from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import chat, test

app = FastAPI()

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(test.router)

@app.get("/")
def read_root():
    return {"message": "AI Integration Service is running!"}

# Chạy server bằng lệnh: uvicorn main:app --reload