from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import asyncio
from langchain_google_genai import ChatGoogleGenerativeAI
from core.config import settings
from services.chat_orchestrator import ChatOrchestrator
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
            
            # Stream the actual response
            async for chunk in orchestrator.stream_response(
                room_id=request.room_id,
                thread_id=request.thread_id,
                ai_id=request.ai_id,
                user_prompt=request.user_prompt,
                user_id=request.user_id
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
            
            # Replace methods with mocks
            orchestrator._get_ai_info = mock_get_ai_info
            orchestrator._get_chat_history = mock_get_chat_history
            orchestrator._save_message = mock_save_message
            
            yield f"data: [INFO] Starting mock chat stream...\n\n"
            yield f"data: ---\n\n"
            
            # Stream the response
            async for chunk in orchestrator.stream_response(
                room_id='mock-room',
                thread_id='mock-thread',
                ai_id='mock-ai',
                user_prompt='Explain how to create a simple FastAPI endpoint',
                user_id='mock-user'
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