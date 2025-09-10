from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
import asyncio
import uuid
from datetime import datetime
from langchain_google_genai import ChatGoogleGenerativeAI
from core.config import settings
from services.chat_orchestrator import ChatOrchestrator
from services.lock_manager import lock_manager
from supabase import create_client, Client

router = APIRouter()


class TestChatStreamRequest(BaseModel):
    ai_id: str
    user_prompt: str = "What are your capabilities?"
    room_id: str = "test-room-001"
    thread_id: str = "test-thread-001"
    user_id: str = "test-user-001"


@router.post("/test/chat-stream")
async def test_chat_stream(request: TestChatStreamRequest):
    """
    Test the chat streaming API with the new AI table structure.
    This endpoint tests:
    - AI info retrieval from 'ai' table (with model and system_prompt)
    - Dynamic model selection (defaults to gemini-2.5-flash if null)
    - System prompt usage
    - Streaming response generation
    """
    async def generate_stream():
        try:
            # Create orchestrator instance
            orchestrator = ChatOrchestrator()
            
            # Log the AI being used
            yield f"data: [INFO] Testing with AI ID: {request.ai_id}\n\n"
            yield f"data: [INFO] User prompt: {request.user_prompt}\n\n"
            yield f"data: [INFO] Starting chat stream...\n\n"
            yield f"data: ---\n\n"
            
            # First save the user message
            import uuid
            from datetime import datetime
            supabase: Client = create_client(settings.supabase_url, settings.supabase_key)
            
            user_message_data = {
                'id': str(uuid.uuid4()),
                'room_id': request.room_id,
                'thread_id': request.thread_id,
                'content': request.user_prompt,
                'sender_type': 1,  # user
                'sender_id': request.user_id,
                'ai_id_list': [request.ai_id],
                'created_at': datetime.utcnow().isoformat()
            }
            
            message_response = supabase.table('messages').insert(user_message_data).execute()
            user_message_id = message_response.data[0]['id'] if message_response.data else None
            
            if not user_message_id:
                yield f"data: [ERROR] Failed to save user message\n\n"
                return
            
            yield f"data: [INFO] User message saved with ID: {user_message_id}\n\n"
            
            # Stream the actual response
            async for chunk in orchestrator.stream_response(
                room_id=request.room_id,
                thread_id=request.thread_id,
                ai_id=request.ai_id,
                user_message_id=user_message_id
            ):
                yield f"data: {chunk}\n\n"
                await asyncio.sleep(0.01)  # Small delay for smooth streaming
            
            yield f"data: \n\n"
            yield f"data: ---\n\n"
            yield f"data: [INFO] Stream completed successfully\n\n"
            yield f"data: [DONE]\n\n"
            
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"
            yield f"data: [DONE]\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable Nginx buffering
        }
    )


@router.get("/test/ai-info/{ai_id}")
async def test_get_ai_info(ai_id: str):
    """
    Helper endpoint to check AI configuration in the database.
    Shows the model and system_prompt for a given AI.
    """
    try:
        supabase: Client = create_client(settings.supabase_url, settings.supabase_key)
        
        response = supabase.table('ai') \
            .select('id, name, model, system_prompt, is_active') \
            .eq('id', ai_id) \
            .single() \
            .execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail=f"AI with id {ai_id} not found")
        
        ai_data = response.data
        return {
            "status": "success",
            "ai_info": {
                "id": ai_data['id'],
                "name": ai_data['name'],
                "model": ai_data.get('model') or 'gemini-2.5-flash',
                "has_system_prompt": bool(ai_data.get('system_prompt')),
                "system_prompt_preview": (ai_data.get('system_prompt') or 'No system prompt defined')[:200],
                "is_active": ai_data['is_active']
            }
        }
    except Exception as e:
        if "404" in str(e):
            raise HTTPException(status_code=404, detail=f"AI with id {ai_id} not found")
        raise HTTPException(status_code=500, detail=f"Failed to fetch AI info: {str(e)}")


@router.get("/test/list-ai")
async def test_list_available_ai():
    """
    List all active AI agents available for testing.
    Shows their IDs, names, and configured models.
    """
    try:
        supabase: Client = create_client(settings.supabase_url, settings.supabase_key)
        
        response = supabase.table('ai') \
            .select('id, name, model') \
            .eq('is_active', True) \
            .execute()
        
        ai_list = []
        for ai in response.data:
            ai_list.append({
                "id": ai['id'],
                "name": ai['name'],
                "model": ai.get('model') or 'gemini-2.5-flash'
            })
        
        return {
            "status": "success",
            "total_active": len(ai_list),
            "ai_agents": ai_list,
            "usage": "Use the 'id' field with /test/chat-stream endpoint"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list AI agents: {str(e)}")


@router.post("/test/chat-stream-mock")
async def test_chat_stream_mock():
    """
    Test chat streaming with mock data (no database required).
    Useful for testing when database is not available.
    """
    async def generate_mock_stream():
        try:
            # Create orchestrator with mocked methods
            orchestrator = ChatOrchestrator()
            
            # Mock the AI info retrieval
            def mock_get_ai_info(ai_id):
                return {
                    'id': ai_id,
                    'name': 'Mock AI Assistant',
                    'system_prompt': 'You are a helpful AI assistant specialized in Python and FastAPI development.',
                    'model': None,  # Test default model behavior
                    'is_active': True
                }
            
            # Mock chat history
            def mock_get_chat_history(room_id, thread_id, limit=10):
                return []  # Empty history for fresh conversation
            
            # Mock message saving
            def mock_save_message(*args, **kwargs):
                return 'mock-message-id'
            
            # Mock upsert streaming message
            def mock_upsert_streaming_message(*args, **kwargs):
                return 'mock-streaming-id'
            
            # Mock complete streaming message
            def mock_complete_streaming_message(*args, **kwargs):
                return 'mock-final-message-id'
            
            # Mock cleanup
            def mock_cleanup_incomplete_streaming_messages(*args, **kwargs):
                pass
            
            # Create a mock database client with chained methods
            class MockTable:
                def __init__(self, data=None):
                    self.data = data or {}
                
                def select(self, *args):
                    return self
                
                def eq(self, *args):
                    return self
                
                def single(self):
                    return self
                
                def execute(self):
                    class MockResponse:
                        def __init__(self, data):
                            self.data = data
                    return MockResponse({
                        'content': 'Explain how to create a simple FastAPI endpoint',
                        'sender_id': 'mock-user'
                    })
            
            class MockDBClient:
                def table(self, name):
                    if name == 'messages':
                        return MockTable()
                    return MockTable()
            
            # Replace methods with mocks
            orchestrator._get_ai_info = mock_get_ai_info
            orchestrator._get_chat_history = mock_get_chat_history
            orchestrator._save_message = mock_save_message
            orchestrator._upsert_streaming_message = mock_upsert_streaming_message
            orchestrator._complete_streaming_message = mock_complete_streaming_message
            orchestrator.cleanup_incomplete_streaming_messages = mock_cleanup_incomplete_streaming_messages
            orchestrator.db_client = MockDBClient()  # Mock the database client
            
            yield f"data: [INFO] Starting mock chat stream...\n\n"
            yield f"data: ---\n\n"
            
            # Create a mock user message ID
            mock_user_message_id = 'mock-user-message-id-001'
            
            # Stream the response
            async for chunk in orchestrator.stream_response(
                room_id='mock-room',
                thread_id='mock-thread',
                ai_id='mock-ai',
                user_message_id=mock_user_message_id
            ):
                yield f"data: {chunk}\n\n"
                await asyncio.sleep(0.01)
            
            yield f"data: \n\n"
            yield f"data: ---\n\n"
            yield f"data: [INFO] Mock stream completed\n\n"
            yield f"data: [DONE]\n\n"
            
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"
            yield f"data: [DONE]\n\n"
    
    return StreamingResponse(
        generate_mock_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


class LockTestRequest(BaseModel):
    room_id: str = "test-room-lock"
    thread_id: str = "test-thread-lock"
    duration: int = 5  # How long to hold the lock in seconds


@router.post("/test/lock-simulation")
async def test_lock_simulation(request: LockTestRequest):
    """
    Test the lock mechanism by simulating a long-running request.
    This endpoint will hold a lock for the specified duration to test concurrent access.
    
    Use this with multiple concurrent requests to test lock behavior:
    - First request should succeed and hold the lock
    - Subsequent requests should return 409 Conflict
    """
    try:
        # Check if already locked (fast path)
        if lock_manager.is_locked(request.room_id, request.thread_id):
            raise HTTPException(
                status_code=409, 
                detail=f"Lock already held for room {request.room_id}, thread {request.thread_id}"
            )
        
        async with lock_manager.acquire_lock(request.room_id, request.thread_id):
            start_time = datetime.utcnow()
            
            # Simulate processing time
            await asyncio.sleep(request.duration)
            
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            return {
                "status": "success",
                "message": f"Successfully held lock for {duration:.2f} seconds",
                "room_id": request.room_id,
                "thread_id": request.thread_id,
                "requested_duration": request.duration,
                "actual_duration": duration,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat()
            }
    except Exception as e:
        if "409" in str(e) or "already" in str(e).lower():
            raise HTTPException(
                status_code=409, 
                detail=f"Another request is already being processed for room {request.room_id} and thread {request.thread_id}"
            )
        raise HTTPException(status_code=500, detail=f"Lock test failed: {str(e)}")


@router.get("/test/lock-status")
async def test_lock_status():
    """
    Get current lock status for monitoring and debugging.
    Shows all active locks and their counts.
    """
    try:
        active_locks = lock_manager.get_active_locks()
        lock_count = lock_manager.get_lock_count()
        
        return {
            "status": "success",
            "active_locks": list(active_locks),
            "active_count": len(active_locks),
            "total_locks_in_memory": lock_count,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get lock status: {str(e)}")


@router.post("/test/concurrent-lock-test")
async def test_concurrent_locks(request: LockTestRequest):
    """
    Test concurrent lock behavior by attempting to acquire multiple locks simultaneously.
    This simulates what happens when multiple clients try to start chat streams at the same time.
    """
    
    async def attempt_lock_acquisition(attempt_id: int):
        """Helper function to attempt lock acquisition"""
        try:
            start_time = datetime.utcnow()
            async with lock_manager.acquire_lock(request.room_id, request.thread_id):
                acquired_time = datetime.utcnow()
                acquisition_duration = (acquired_time - start_time).total_seconds()
                
                # Hold the lock for a short time
                await asyncio.sleep(1)
                
                release_time = datetime.utcnow()
                hold_duration = (release_time - acquired_time).total_seconds()
                
                return {
                    "attempt_id": attempt_id,
                    "status": "success",
                    "start_time": start_time.isoformat(),
                    "acquired_time": acquired_time.isoformat(),
                    "release_time": release_time.isoformat(),
                    "acquisition_duration": acquisition_duration,
                    "hold_duration": hold_duration
                }
        except Exception as e:
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            return {
                "attempt_id": attempt_id,
                "status": "failed",
                "error": str(e),
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration": duration
            }
    
    try:
        # Launch 5 concurrent attempts
        tasks = [attempt_lock_acquisition(i) for i in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        successful_attempts = []
        failed_attempts = []
        
        for result in results:
            if isinstance(result, Exception):
                failed_attempts.append({
                    "status": "exception",
                    "error": str(result)
                })
            elif result.get("status") == "success":
                successful_attempts.append(result)
            else:
                failed_attempts.append(result)
        
        return {
            "status": "completed",
            "room_id": request.room_id,
            "thread_id": request.thread_id,
            "total_attempts": 5,
            "successful_attempts": len(successful_attempts),
            "failed_attempts": len(failed_attempts),
            "success_details": successful_attempts,
            "failure_details": failed_attempts,
            "expected_behavior": "Only 1 attempt should succeed, others should fail with ConflictException"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Concurrent lock test failed: {str(e)}")


@router.get("/test/lock-help")
async def test_lock_help():
    """
    Get information about available lock testing endpoints and how to use them.
    """
    return {
        "status": "help",
        "available_endpoints": {
            "/test/lock-simulation": {
                "method": "POST",
                "description": "Simulates a long-running request that holds a lock",
                "parameters": {
                    "room_id": "string (default: test-room-lock)",
                    "thread_id": "string (default: test-thread-lock)", 
                    "duration": "integer seconds (default: 5)"
                },
                "usage": "Send multiple concurrent requests to test lock behavior"
            },
            "/test/lock-status": {
                "method": "GET",
                "description": "Shows current active locks and memory usage",
                "parameters": "None"
            },
            "/test/concurrent-lock-test": {
                "method": "POST", 
                "description": "Tests concurrent lock acquisition with 5 simultaneous attempts",
                "parameters": "Same as lock-simulation",
                "expected": "Only 1 attempt should succeed"
            }
        },
        "testing_scenarios": [
            "1. Start a lock-simulation with long duration (10s)",
            "2. While it's running, try another lock-simulation - should get 409",
            "3. Check lock-status to see active locks",
            "4. Run concurrent-lock-test to see multiple simultaneous attempts",
            "5. Verify proper cleanup after requests complete"
        ]
    }