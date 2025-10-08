from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional
import asyncio
import logging

from services.qa_orchestrator import QAOrchestrator
from services.lock_manager import lock_manager

router = APIRouter()
logger = logging.getLogger(__name__)

class QARequest(BaseModel):
    room_id: str
    thread_id: str
    ai_id: str
    user_message_id: str  # ID of the already saved user message

class QAResponse(BaseModel):
    streaming_message_id: str
    status: str = "processing"

@router.options("/qa/stream")
async def qa_stream_options():
    """Handle OPTIONS preflight request for CORS"""
    return Response(
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }
    )

@router.post("/qa/stream", response_model=QAResponse)
async def qa_stream(request: QARequest, background_tasks: BackgroundTasks):
    """
    Initialize AI QA response processing and return streaming_message_id

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

    # Get user profile_id from the user message
    orchestrator = QAOrchestrator()
    user_message = orchestrator.get_message_by_id(request.user_message_id)
    if not user_message:
        raise HTTPException(status_code=404, detail="User message not found")

    user_profile_id = user_message.get('sender_id')

    # Check database lock status
    lock_status = lock_manager.check_thread_lock(request.thread_id)
    if lock_status and lock_status.get('is_locked'):
        lock_type = lock_status.get('lock_type')
        locked_by = lock_status.get('locked_by_profile_id')

        if lock_type == 'ai_streaming':
            # AI is already processing, reject
            logger.warning(f"AI already processing for thread {request.thread_id}")
            raise HTTPException(
                status_code=409,
                detail=f"AI is already processing a response for this thread. Please wait."
            )
        elif lock_type == 'user_message':
            # Check if the lock belongs to the user who sent this message
            if locked_by != user_profile_id:
                # Different user has the lock
                logger.warning(f"Thread {request.thread_id} locked by different user: {locked_by} != {user_profile_id}")
                raise HTTPException(
                    status_code=409,
                    detail=f"Another user is currently sending a message. Please wait."
                )
            # Same user has the lock, we can transition it
            logger.info(f"User {user_profile_id} has lock for thread {request.thread_id}, will transition to AI")

    # Try to acquire or transition the database lock to AI
    lock_result = lock_manager.transition_to_ai_lock(request.thread_id, request.ai_id)
    if not lock_result or not lock_result.get('success'):
        logger.warning(f"Could not acquire AI lock for thread {request.thread_id}")
        raise HTTPException(
            status_code=409,
            detail="Could not acquire lock for processing. Another request may be in progress."
        )

    logger.info(f"Acquired AI lock for thread {request.thread_id}, processing request")

    try:
        # Initialize orchestrator
        orchestrator = QAOrchestrator()

        # Initialize streaming message and get its ID
        streaming_message_id = orchestrator.initialize_streaming_message(
            room_id=request.room_id,
            thread_id=request.thread_id,
            ai_id=request.ai_id,
            user_message_id=request.user_message_id
        )

        if not streaming_message_id:
            # Release lock on error
            lock_manager.release_thread_lock(request.thread_id, request.ai_id)
            raise HTTPException(status_code=500, detail="Failed to initialize streaming message")

        # Process AI response in background (lock will be released by orchestrator after completion)
        background_tasks.add_task(
            orchestrator.process_streaming_response,
            room_id=request.room_id,
            thread_id=request.thread_id,
            ai_id=request.ai_id,
            user_message_id=request.user_message_id,
            streaming_message_id=streaming_message_id
        )

        return QAResponse(
            streaming_message_id=streaming_message_id,
            status="processing"
        )

    except Exception as e:
        # Release lock on any unexpected error
        try:
            lock_manager.release_thread_lock(request.thread_id, request.ai_id)
        except:
            pass

        logger.error(f"Unexpected error in qa_stream for room {request.room_id}, thread {request.thread_id}: {str(e)}")
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail="Internal server error occurred while processing request")
