from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional
import asyncio
import logging

from services.chat_orchestrator import ChatOrchestrator
from services.lock_manager import lock_manager, ConflictException

router = APIRouter()
logger = logging.getLogger(__name__)

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
    
    Raises:
    - HTTPException 409: If another request is already processing for the same room/thread
    """
    
    # Validate required fields
    if not request.room_id or not request.thread_id or not request.ai_id:
        raise HTTPException(status_code=400, detail="room_id, thread_id, and ai_id are required")
    
    if not request.user_message_id:
        raise HTTPException(status_code=400, detail="user_message_id cannot be empty")
    
    # Check for concurrent requests before acquiring lock
    if lock_manager.is_locked(request.room_id, request.thread_id):
        logger.warning(f"Concurrent request blocked for room {request.room_id}, thread {request.thread_id}")
        raise HTTPException(
            status_code=409, 
            detail=f"Another request is already being processed for room {request.room_id} and thread {request.thread_id}. Please wait for it to complete."
        )
    
    try:
        # Acquire lock for this room/thread combination
        async with lock_manager.acquire_lock(request.room_id, request.thread_id):
            logger.info(f"Processing chat request for room {request.room_id}, thread {request.thread_id}")
            
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
            
            # Process AI response in background with protected execution
            background_tasks.add_task(
                _process_with_lock_protection,
                orchestrator=orchestrator,
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
            
    except ConflictException as e:
        logger.warning(f"Lock conflict for room {request.room_id}, thread {request.thread_id}: {str(e)}")
        raise HTTPException(
            status_code=409, 
            detail=f"Another request is already being processed for room {request.room_id} and thread {request.thread_id}. Please wait for it to complete."
        )
    except Exception as e:
        logger.error(f"Unexpected error in chat_stream for room {request.room_id}, thread {request.thread_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error occurred while processing request")


async def _process_with_lock_protection(orchestrator: ChatOrchestrator, room_id: str, 
                                       thread_id: str, ai_id: str, user_message_id: str,
                                       streaming_message_id: str):
    """
    Protected wrapper for background processing that ensures proper lock management.
    
    This function acquires its own lock to ensure the background task has exclusive access
    to the room/thread combination during processing.
    """
    try:
        async with lock_manager.acquire_lock(room_id, thread_id):
            await orchestrator.process_streaming_response(
                room_id=room_id,
                thread_id=thread_id,
                ai_id=ai_id,
                user_message_id=user_message_id,
                streaming_message_id=streaming_message_id
            )
    except ConflictException:
        # This should not happen since we already have the lock, but handle gracefully
        logger.error(f"Unexpected lock conflict in background task for room {room_id}, thread {thread_id}")
        # Mark streaming message as failed
        try:
            orchestrator._upsert_streaming_message(
                streaming_id=streaming_message_id,
                room_id=room_id,
                thread_id=thread_id,
                ai_id=ai_id,
                user_message_id=user_message_id,
                content="Error: Processing was interrupted due to lock conflict",
                is_complete=True
            )
        except Exception as e:
            logger.error(f"Failed to mark streaming message as failed: {e}")
    except Exception as e:
        logger.error(f"Error in background processing for room {room_id}, thread {thread_id}: {e}")
        # The orchestrator should handle marking the message as complete with error