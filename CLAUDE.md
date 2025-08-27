# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Development Server
```bash
# Run the FastAPI development server with auto-reload
uvicorn main:app --reload

# Run on specific host/port
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Dependencies
```bash
# Install all dependencies
pip install -r requirements.txt

# Upgrade dependencies
pip install --upgrade -r requirements.txt
```

### Environment Setup
```bash
# Copy environment template
cp .env.example .env
# Then edit .env with your actual credentials
```

## Architecture Overview

This is a **streaming AI chat service** built with FastAPI that provides mentor-based conversational experiences. The service integrates with Google's Gemini Pro model via LangChain and uses Supabase for data persistence.

### Request Flow
1. **API Layer** (`routers/chat.py`): Receives chat requests with user_id, ai_id, and user_prompt
2. **Orchestration** (`services/chat_orchestrator.py`): 
   - Fetches AI configuration from Supabase `ai` table (model, system_prompt, name)
   - Retrieves last 10 messages from `messages` table
   - Constructs contextualized prompt using system_prompt
3. **AI Processing**: Streams response from Google Gemini model (uses model from DB or defaults to gemini-2.5-flash)
4. **Response**: Returns Server-Sent Events (SSE) stream to client

### Key Integration Points

**Supabase Tables:**
- `ai`: Stores AI configurations (id, name, model, system_prompt)
  - `model`: Specifies which Gemini model to use (null defaults to gemini-2.5-flash)
  - `system_prompt`: The AI's behavioral instructions
- `messages`: Stores conversations (room_id, thread_id, content, sender_type, sender_id)

**External Services:**
- Google Gemini API (via GOOGLE_API_KEY)
- Supabase Database (via SUPABASE_URL and SUPABASE_KEY)

### Service Layer Pattern

The `ChatOrchestrator` class in `services/chat_orchestrator.py` is the core business logic handler. When modifying chat behavior:
- AI info retrieval: `_get_ai_info()` method
- History management: `_get_chat_history()` method  
- Model selection: `_get_llm()` method (uses model from DB or defaults)
- Streaming logic: `stream_response()` method
- System prompt usage: Directly from `system_prompt` field in `ai` table

### Configuration Management

All configuration is centralized in `core/config.py` using Pydantic Settings. Environment variables are automatically loaded from `.env` file. Required variables:
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `GOOGLE_API_KEY`

## Testing

### Test Endpoints

The service includes test endpoints in `routers/test.py` for validating the chat streaming functionality:

#### 1. List Available AIs
```bash
# Get all active AI agents from the database
curl http://localhost:8000/test/list-ai
```

#### 2. Check AI Configuration
```bash
# View specific AI's model and system prompt
curl http://localhost:8000/test/ai-info/{ai_id}
```

#### 3. Test Chat Streaming
```bash
# Test actual chat with an AI from the database
curl -X POST http://localhost:8000/test/chat-stream \
  -H "Content-Type: application/json" \
  -d '{
    "ai_id": "your-ai-id-here",
    "user_prompt": "Tell me about yourself"
  }'
```

#### 4. Test with Mock Data
```bash
# Test without database dependency
curl -X POST http://localhost:8000/test/chat-stream-mock
```

### Testing Flow

1. **Start the server**: `uvicorn main:app --reload`
2. **List available AIs**: Use `/test/list-ai` to get AI IDs
3. **Check AI config**: Use `/test/ai-info/{ai_id}` to verify model and system_prompt
4. **Test streaming**: Use `/test/chat-stream` with the AI ID
5. **Mock testing**: Use `/test/chat-stream-mock` for database-independent testing

### Expected Behavior

- If `model` is null in the database, defaults to `gemini-2.5-flash`
- System prompts define AI behavior and personality
- Streaming responses use Server-Sent Events (SSE) format
- Chat history is maintained per room/thread combination