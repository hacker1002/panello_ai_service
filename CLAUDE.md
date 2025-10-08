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

This is a **streaming AI chat service** built with FastAPI that provides mentor-based conversational experiences with real-time multi-client synchronization. The service supports two backends:

1. **Chat Router** (`/chat/stream`): Integrates with Google's Gemini models via LangChain
2. **QA Router** (`/qa/stream`): Integrates with a custom document QA API (http://35.239.237.244:8000)

Both services use Supabase for data persistence and real-time updates.

### Request Flow (Simplified with Database-Only Locking)

The system uses database thread locks for all concurrency control:
- **Database Thread Locks** (`thread_locks` table): Manages all lock states across services
- **Fault Tolerance**: Server can acquire/transition locks if client fails

1. **Client Preparation**: 
   - User message is saved to `messages` table by the client
   - Client attempts to create a thread lock in `thread_locks` table (lock_type: 'user_message')
   - If client lock fails, server will handle it (fault tolerance)
   
2. **API Layer** (`routers/chat.py` or `routers/qa.py`): Receives chat request with `user_message_id`
   - Fetches user message to get sender's profile_id
   - **Lock Status Check**:
     - If `ai_streaming` lock: Returns HTTP 409 (AI already processing)
     - If `user_message` lock by different user: Returns HTTP 409 (another user sending)
     - If `user_message` lock by same user: Proceeds to transition lock
     - If no lock: Proceeds to create AI lock
   - **Lock Transition**: Transitions to AI lock or creates new AI lock
   - **Background Task**: Launches streaming process
   - Returns streaming_message_id immediately to client

3. **Orchestration**:
   - **Chat Orchestrator** (`services/chat_orchestrator.py`): Uses LangChain + Google Gemini
     - Cleans up any incomplete streaming messages for the room/thread
     - Fetches AI configuration from `ai` table (model, system_prompt, name, is_moderator)
     - Retrieves user message content using `user_message_id`
     - Fetches last 10 messages from `messages` table for context
     - Constructs contextualized prompt using system_prompt
     - Streams responses using LangChain's astream

   - **QA Orchestrator** (`services/qa_orchestrator.py`): Uses custom document QA API
     - Same database operations as ChatOrchestrator
     - Formats chat history as Question/Answer pairs
     - For moderator AI: Calls `/api/qa/professional-sync` (synchronous, returns JSON with `ai_id` and `message`)
     - For normal AI: Calls `/api/qa/professional-stream` (streaming, returns chunks with `status` and `chunk`)
     - Processes streaming responses and updates Supabase in real-time
   
4. **Streaming Process**:
   - As chunks arrive from Gemini, they're upserted to `streaming_messages` table
   - Other clients can subscribe to `streaming_messages` changes for real-time updates
   - Database lock prevents other users from sending messages
   
5. **Completion**:
   - When streaming completes, `complete_streaming_message()` is called
   - Final message is saved to `messages` table
   - **Lock Release**: `release_thread_lock()` releases the AI lock in database
   - On error: Lock is released to prevent deadlocks

### Key Integration Points

**Supabase Tables:**
- `ai`: Stores AI configurations (id, name, model, system_prompt, is_moderator)
  - `model`: Specifies which Gemini model to use (null defaults to gemini-2.0-flash-exp)
  - `system_prompt`: The AI's behavioral instructions
  - `is_moderator`: Boolean flag to identify moderator AIs
- `messages`: Permanent message storage (room_id, thread_id, content, sender_type, sender_id)
- `streaming_messages`: Temporary streaming state for active AI responses
  - `content`: Accumulated streaming content
  - `is_complete`: Whether streaming has finished
  - `final_message_id`: Reference to final message once complete
  - `user_message_id`: The user message being responded to
- `thread_locks`: Thread-level locking to prevent concurrent messages
  - `thread_id`: The thread being locked
  - `locked_by_profile_id`: User or AI ID holding the lock
  - `lock_type`: 'user_message' or 'ai_streaming'
  - `expires_at`: Auto-expiry timestamp for cleanup

**Supabase Functions (RPC):**
- `upsert_streaming_message`: Creates or updates streaming message
- `complete_streaming_message`: Finalizes streaming and creates message record
- `cleanup_old_streaming_messages`: Removes old completed streaming records
- `acquire_thread_lock`: Client acquires lock before sending message
- `release_thread_lock`: Server releases lock after AI completes
- `transition_lock_to_ai`: Transfer lock from user to AI (optional)
- `refresh_thread_lock`: Extend lock expiry for long operations

**External Services:**
- Google Gemini API (via GOOGLE_API_KEY) - Used by Chat Router
- Custom Document QA API (http://35.239.237.244:8000) - Used by QA Router
  - `/api/qa/professional-sync`: Synchronous QA endpoint for moderators
  - `/api/qa/professional-stream`: Streaming QA endpoint for normal AIs
- Supabase Database (via SUPABASE_URL and SUPABASE_KEY)

### Service Layer Pattern

**ChatOrchestrator** (`services/chat_orchestrator.py`): Core business logic for LangChain/Gemini integration

**Core Methods:**
- `process_streaming_response()`: Main background streaming method (processes AI responses asynchronously)
- `initialize_streaming_message()`: Creates initial streaming message entry
- `_get_ai_info()`: Fetches AI configuration including `is_moderator` field
- `_get_chat_history()`: Retrieves conversation context
- `_get_llm()`: Initializes appropriate Gemini model
- `_save_message()`: Saves messages to database
- `_upsert_streaming_message()`: Updates streaming state
- `_complete_streaming_message()`: Finalizes streaming
- `_release_thread_lock()`: Releases database thread lock after completion
- `cleanup_incomplete_streaming_messages()`: Cleanup on start
- `_extract_ai_name_from_moderator_response()`: Extracts selected AI name from moderator response
- `_get_ai_id_by_name()`: Retrieves AI ID by name from room's available AIs

**QAOrchestrator** (`services/qa_orchestrator.py`): Core business logic for custom document QA API integration

**Core Methods:**
- `process_streaming_response()`: Main background streaming method using HTTP requests to QA API
- `initialize_streaming_message()`: Creates initial streaming message entry (same as ChatOrchestrator)
- `_get_ai_info()`: Fetches AI configuration including `is_moderator` field
- `_get_chat_history()`: Retrieves conversation context
- `_format_chat_history_for_api()`: Formats history as Question/Answer pairs for QA API
- `_build_moderator_system_prompt()`: Builds prompt with available AIs list for moderator
- `_call_professional_sync()`: HTTP POST to `/api/qa/professional-sync` for moderator responses
- `_call_professional_stream()`: HTTP POST to `/api/qa/professional-stream` for streaming responses
- `_upsert_streaming_message()`: Updates streaming state (same as ChatOrchestrator)
- `_complete_streaming_message()`: Finalizes streaming (same as ChatOrchestrator)
- `_release_thread_lock()`: Releases database thread lock after completion

**Lock Manager** (`services/lock_manager.py`):
- `check_thread_lock()`: Checks thread lock status in database
- `transition_to_ai_lock()`: Transitions user lock to AI lock or creates new AI lock
- `release_thread_lock()`: Releases the thread lock after processing
- `refresh_thread_lock()`: Extends lock expiry for long operations

**Important Changes:**
- User messages are now saved BEFORE calling the streaming API
- The API accepts `user_message_id` instead of raw prompt text
- Streaming messages provide real-time synchronization across clients
- Automatic cleanup prevents orphaned streaming messages
- Database locks prevent concurrent processing for same thread
- Simplified architecture uses only database locks for all concurrency control

### Moderator Flow

The system supports moderator AIs (identified by `is_moderator: true` in the `ai` table) that can automatically forward users to the most appropriate AI mentor:

**Moderator Detection:**
- System checks the `is_moderator` field from the `ai` table
- If `is_moderator == true`, the AI is treated as a moderator

**Moderator Process:**
1. When `is_moderator == true`, the system builds an enhanced prompt including all available non-moderator AIs in the room
2. **Chat Router**: The moderator AI responds with a pattern like `Forward to AI mentor: **{AI name}**`
   - Extracts the AI name using regex pattern `**{AI name}**`
   - Looks up the AI ID by name from the room's available AIs
3. **QA Router**: The moderator AI responds with JSON containing `ai_id` and `message` fields
   - Directly uses the `ai_id` from the response
4. After the moderator completes streaming, the backend:
   - Automatically triggers a new stream to the selected AI
   - Uses the same `user_message_id` for continuity

**Key Features:**
- Dynamic moderator detection via database field (no hardcoded IDs)
- Multiple moderators can exist in the system
- Moderators are filtered out from available AI lists (self-reference prevention)
- Automatic background processing of the next AI stream
- Real-time updates via streaming_messages table
- Graceful handling if no AI is selected or found

### QA API Integration Details

The QA router integrates with a custom document-based QA service:

**Request Format** (both endpoints):
```json
{
  "question_text": "User's question with optional system prompt context",
  "model": "gemini-2.5-flash",
  "ai_info": {
    "id": "ai-uuid",
    "name": "AI Name",
    "description": "AI description",
    "personality": "AI personality",
    "system_prompt": "System instructions"
  },
  "room_id": "room-uuid",
  "top_k": 10,
  "histories_chat": [
    {
      "Question": "Previous user question",
      "Answer": "Previous AI answer"
    }
  ],
  "embedding_model": "embedding-001"
}
```

**Response Format** (`/api/qa/professional-sync`):
```json
{
  "id": "chatcmpl-xxx",
  "timestamp": "2025-10-08T07:11:10.948958Z",
  "modelId": "gemini-2.5-flash",
  "messages": [
    {
      "role": "assistant",
      "content": [
        {
          "type": "text",
          "text": "```json\n{\"message\": \"Response text\", \"ai_id\": \"selected-ai-uuid\"}\n```"
        }
      ],
      "id": "message-uuid"
    }
  ]
}
```

**Streaming Response Format** (`/api/qa/professional-stream`):
```
{"status": "answering", "chunk": "text chunk"}
{"status": "answering", "chunk": "more text"}
{"status": "complete", "message": "Answer generation completed"}
```

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