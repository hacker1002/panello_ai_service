from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional
import asyncio

from services.chat_orchestrator import ChatOrchestrator

router = APIRouter()

class ChatRequest(BaseModel):
    room_id: str
    thread_id: str
    ai_id: str
    user_message_id: str  # ID of the already saved user message

class ChatResponse(BaseModel):
    streaming_message_id: str
    status: str = "processing"

@router.options("/chat/stream")
async def chat_stream_options():
    """Handle OPTIONS preflight request for CORS"""
    return Response(
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }
    )

@router.post("/chat/stream", response_model=ChatResponse)
async def chat_stream(request: ChatRequest, background_tasks: BackgroundTasks):
    """
    Initialize AI chat response processing and return streaming_message_id
    
    Parameters:
    - room_id: The room/conversation ID
    - thread_id: The thread ID within the room
    - ai_id: The AI personality to use
    - user_message_id: The ID of the already saved user message
    
    Returns:
    - streaming_message_id: ID to subscribe to for real-time updates
    - status: Processing status
    """
    
    # Validate required fields
    if not request.room_id or not request.thread_id or not request.ai_id:
        raise HTTPException(status_code=400, detail="room_id, thread_id, and ai_id are required")
    
    if not request.user_message_id:
        raise HTTPException(status_code=400, detail="user_message_id cannot be empty")
    
    # Initialize orchestrator
    orchestrator = ChatOrchestrator()
    
    # Initialize streaming message and get its ID
    streaming_message_id = orchestrator.initialize_streaming_message(
        room_id=request.room_id,
        thread_id=request.thread_id,
        ai_id=request.ai_id,
        user_message_id=request.user_message_id
    )
    
    if not streaming_message_id:
        raise HTTPException(status_code=500, detail="Failed to initialize streaming message")
    
    # Process AI response in background
    background_tasks.add_task(
        orchestrator.process_streaming_response,
        room_id=request.room_id,
        thread_id=request.thread_id,
        ai_id=request.ai_id,
        user_message_id=request.user_message_id,
        streaming_message_id=streaming_message_id
    )
    
    return ChatResponse(
        streaming_message_id=streaming_message_id,
        status="processing"
    )