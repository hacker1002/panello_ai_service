from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from services.chat_orchestrator import ChatOrchestrator

router = APIRouter()

class ChatRequest(BaseModel):
    room_id: str
    thread_id: str
    ai_id: str
    user_prompt: str
    user_id: Optional[str] = None

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Stream chat responses from AI based on room context
    
    Parameters:
    - room_id: The room/conversation ID
    - thread_id: The thread ID within the room
    - ai_id: The AI personality to use
    - user_prompt: The user's message
    - user_id: Optional user ID for tracking
    """
    
    # Validate required fields
    if not request.room_id or not request.thread_id or not request.ai_id:
        raise HTTPException(status_code=400, detail="room_id, thread_id, and ai_id are required")
    
    if not request.user_prompt:
        raise HTTPException(status_code=400, detail="user_prompt cannot be empty")
    
    # Initialize orchestrator
    orchestrator = ChatOrchestrator()
    
    # Stream the response
    return StreamingResponse(
        orchestrator.stream_response(
            room_id=request.room_id,
            thread_id=request.thread_id,
            ai_id=request.ai_id,
            user_prompt=request.user_prompt,
            user_id=request.user_id
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )