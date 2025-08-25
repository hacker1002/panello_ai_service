from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import asyncio
from langchain_google_genai import ChatGoogleGenerativeAI
from core.config import settings

router = APIRouter()


class TestAIRequest(BaseModel):
    prompt: str = "Tell me a short joke"
    max_tokens: Optional[int] = 100


@router.post("/test/google-ai")
async def test_google_ai(request: TestAIRequest):
    """
    Test endpoint to verify Google AI integration is working
    """
    try:
        # Initialize Google AI with Gemini model
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=settings.google_api_key,
            max_output_tokens=request.max_tokens
        )

        messages = [
            ("human", request.prompt),
        ]
        
        # Make a simple call to the AI
        response = llm.invoke(messages)
        
        return {
            "status": "success",
            "prompt": request.prompt,
            "response": response.content,
            "model": "gemini-2.5-flash"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google AI test failed: {str(e)}")


@router.get("/test/stream")
async def test_streaming():
    """
    Test endpoint to verify streaming response functionality
    """
    async def generate_stream():
        # Sample paragraph to stream
        paragraph = """This is a test of the streaming response functionality. 
        The text is being sent word by word to demonstrate how Server-Sent Events work in FastAPI. 
        Each word appears with a small delay to simulate real-time streaming, similar to how 
        AI models generate responses token by token. This helps verify that the streaming 
        infrastructure is working correctly before integrating with actual AI services."""
        
        words = paragraph.split()
        
        for word in words:
            # Format as Server-Sent Events
            yield f"data: {word} \n\n"
            # Small delay to simulate streaming
            await asyncio.sleep(0.1)
        
        # Send completion signal
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.get("/test/stream-ai")
async def test_stream_ai():
    """
    Test endpoint that combines Google AI with streaming response
    """
    async def generate_ai_stream():
        try:
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                google_api_key=settings.google_api_key,
                temperature=0,
                timeout=None,
                max_output_tokens=None,
                max_retries=2
            )
            
            prompt = "Write a short story about a robot learning to paint. Make it exactly 3 sentences."
            
            # Stream the response from AI
            for chunk in llm.stream(prompt):
                yield f"data: {chunk.content} \n"
            
        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"
    
    return StreamingResponse(
        generate_ai_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )