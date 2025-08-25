from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from services.chat_orchestrator import ChatOrchestrator
from core.supabase_client import supabase_client

router = APIRouter()
chat_orchestrator = ChatOrchestrator(db_client=supabase_client)

@router.post("/chat/stream")
async def chat_with_mentor(request: dict):
    user_id = request.get("user_id")
    mentor_id = request.get("mentor_id")
    user_prompt = request.get("user_prompt")
    
    # Validation cơ bản
    if not all([user_id, mentor_id, user_prompt]):
        return {"error": "Missing required fields"}

    # Trả về StreamingResponse
    return StreamingResponse(
        chat_orchestrator.stream_response(user_id, mentor_id, user_prompt),
        media_type="text/event-stream"
    )