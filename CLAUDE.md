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

This is a **streaming AI chat service** built with FastAPI that provides mentor-based conversational experiences with real-time multi-client synchronization. The service integrates with Google's Gemini models via LangChain and uses Supabase for data persistence and real-time updates.

### Request Flow (Updated with Streaming Messages and Lock Mechanism)

1. **Client Preparation**: User message is saved to `messages` table by the client
2. **API Layer** (`routers/chat.py`): Receives chat request with `user_message_id`
   - **Lock Check**: Verifies no existing request is processing for same room_id/thread_id
   - If locked: Returns HTTP 409 (Conflict) immediately
   - If available: Acquires lock for exclusive processing
3. **Orchestration** (`services/chat_orchestrator.py`): 
   - Cleans up any incomplete streaming messages for the room/thread
   - Fetches AI configuration from `ai` table (model, system_prompt, name)
   - Retrieves user message content using `user_message_id`
   - Fetches last 10 messages from `messages` table for context
   - Constructs contextualized prompt using system_prompt
4. **Streaming Process**:
   - As chunks arrive from Gemini, they're upserted to `streaming_messages` table
   - Other clients can subscribe to `streaming_messages` changes for real-time updates
   - Each chunk is also sent via SSE to the requesting client
5. **Completion**:
   - When streaming completes, `complete_streaming_message()` is called
   - Final message is saved to `messages` table
   - Streaming message is marked as complete
   - **Lock Release**: Lock is automatically released for the room_id/thread_id

### Key Integration Points

**Supabase Tables:**
- `ai`: Stores AI configurations (id, name, model, system_prompt)
  - `model`: Specifies which Gemini model to use (null defaults to gemini-2.0-flash-exp)
  - `system_prompt`: The AI's behavioral instructions
- `messages`: Permanent message storage (room_id, thread_id, content, sender_type, sender_id)
- `streaming_messages`: Temporary streaming state for active AI responses
  - `content`: Accumulated streaming content
  - `is_complete`: Whether streaming has finished
  - `final_message_id`: Reference to final message once complete
  - `user_message_id`: The user message being responded to

**Supabase Functions (RPC):**
- `upsert_streaming_message`: Creates or updates streaming message
- `complete_streaming_message`: Finalizes streaming and creates message record
- `cleanup_old_streaming_messages`: Removes old completed streaming records

**External Services:**
- Google Gemini API (via GOOGLE_API_KEY)
- Supabase Database (via SUPABASE_URL and SUPABASE_KEY)

### Service Layer Pattern

The `ChatOrchestrator` class in `services/chat_orchestrator.py` is the core business logic handler:

**Core Methods:**
- `stream_response()`: Main streaming method (now accepts `user_message_id` instead of `user_prompt`)
- `_get_ai_info()`: Fetches AI configuration
- `_get_chat_history()`: Retrieves conversation context
- `_get_llm()`: Initializes appropriate Gemini model
- `_save_message()`: Saves messages to database
- `_upsert_streaming_message()`: Updates streaming state
- `_complete_streaming_message()`: Finalizes streaming
- `cleanup_incomplete_streaming_messages()`: Cleanup on start
- `_extract_ai_name_from_moderator_response()`: Extracts selected AI name from moderator response
- `_get_ai_id_by_name()`: Retrieves AI ID by name from room's available AIs

**Lock Manager** (`services/lock_manager.py`):
- `acquire_lock()`: Async context manager for exclusive access to room/thread
- `is_locked()`: Check if room/thread is currently being processed
- `get_active_locks()`: Monitor active locks for debugging
- Automatic cleanup of unused locks to prevent memory leaks

**Important Changes:**
- User messages are now saved BEFORE calling the streaming API
- The API accepts `user_message_id` instead of raw prompt text
- Streaming messages provide real-time synchronization across clients
- Automatic cleanup prevents orphaned streaming messages
- Lock mechanism prevents concurrent processing for same room/thread

### Moderator Flow

The system includes a special moderator AI (ID: `10000000-0000-0000-0000-000000000007`) that can automatically forward users to the most appropriate AI mentor:

**Moderator Process:**
1. When `ai_id == MODERATOR_AI_ID`, the system builds an enhanced prompt including all available AIs in the room
2. The moderator AI responds with a specific format when selecting an AI:
   ```
   Forward to AI mentor: **{AI name}**.
   Reason is {reason why you choose them in max 100 words}
   ```
3. After the moderator completes streaming, the backend:
   - Extracts the AI name using regex pattern `**{AI name}**`
   - Looks up the AI ID by name from the room's available AIs
   - Automatically triggers a new stream to the selected AI
   - Uses the same `user_message_id` for continuity

**Key Features:**
- The moderator cannot select itself (self-reference prevention)
- Case-insensitive AI name matching
- Automatic background processing of the next AI stream
- Real-time updates via streaming_messages table
- Graceful handling if no AI is selected or found

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

#### 5. Test Lock Mechanism
```bash
# Simulate long-running request (holds lock for 5 seconds)
curl -X POST http://localhost:8000/test/lock-simulation \
  -H "Content-Type: application/json" \
  -d '{"room_id": "test-room", "thread_id": "test-thread", "duration": 5}'

# Check active locks
curl http://localhost:8000/test/lock-status

# Test concurrent lock behavior (5 simultaneous attempts)
curl -X POST http://localhost:8000/test/concurrent-lock-test \
  -H "Content-Type: application/json" \
  -d '{"room_id": "test-room", "thread_id": "test-thread"}'
```

### Testing Flow

1. **Start the server**: `uvicorn main:app --reload`
2. **List available AIs**: Use `/test/list-ai` to get AI IDs
3. **Check AI config**: Use `/test/ai-info/{ai_id}` to verify model and system_prompt
4. **Test streaming**: Use `/test/chat-stream` with the AI ID
5. **Mock testing**: Use `/test/chat-stream-mock` for database-independent testing
6. **Test locks**: Use lock testing endpoints to verify concurrent request protection

### Expected Behavior

- If `model` is null in the database, defaults to `gemini-2.5-flash`
- System prompts define AI behavior and personality
- Streaming responses use Server-Sent Events (SSE) format
- Chat history is maintained per room/thread combination
- **Concurrent Protection**: Second request to same room/thread receives HTTP 409 while first is processing