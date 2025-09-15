# API Reference

## Base Configuration

**Base URL:** `http://localhost:8000`  
**Content-Type:** `application/json`

## Core Endpoints

### 1. Initialize Chat Stream

Initiates AI response processing and returns a streaming_message_id for real-time subscription.

**Endpoint:** `POST /chat/stream`

**Request:**
```json
{
  "room_id": "uuid",
  "thread_id": "uuid",
  "ai_id": "uuid",
  "user_message_id": "uuid"
}
```

**Response:**
```json
{
  "streaming_message_id": "uuid",
  "status": "processing"
}
```

**Status Codes:**
- `200` - Success
- `400` - Missing required fields
- `404` - AI or message not found
- `409` - Conflict - Another request is already being processed for the same room/thread
- `500` - Server error

**Example:**
```bash
curl -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "room_id": "123e4567-e89b-12d3-a456-426614174000",
    "thread_id": "123e4567-e89b-12d3-a456-426614174001",
    "ai_id": "123e4567-e89b-12d3-a456-426614174002",
    "user_message_id": "123e4567-e89b-12d3-a456-426614174003"
  }'
```

## Test Endpoints

### 2. Test Chat Stream

Test endpoint that handles message saving and streaming in one call.

**Endpoint:** `POST /test/chat-stream`

**Request:**
```json
{
  "ai_id": "uuid",
  "user_prompt": "string",
  "room_id": "string",
  "thread_id": "string",
  "user_id": "string"
}
```

**Response:** Server-Sent Events stream

### 3. List Available AIs

**Endpoint:** `GET /test/list-ai`

**Response:**
```json
{
  "status": "success",
  "total_active": 3,
  "ai_agents": [
    {
      "id": "uuid",
      "name": "Python Expert",
      "model": "gemini-2.0-flash-exp"
    }
  ]
}
```

### 4. Get AI Information

**Endpoint:** `GET /test/ai-info/{ai_id}`

**Response:**
```json
{
  "status": "success",
  "ai_info": {
    "id": "uuid",
    "name": "Python Expert",
    "model": "gemini-2.0-flash-exp",
    "has_system_prompt": true,
    "system_prompt_preview": "You are a Python expert...",
    "is_active": true
  }
}
```

### 5. Mock Chat Stream

**Endpoint:** `POST /test/chat-stream-mock`

Test streaming without database dependencies.

## Health Check

**Endpoint:** `GET /health`

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T00:00:00Z",
  "dependencies": {
    "database": "connected",
    "gemini_api": "available"
  }
}
```

## Error Response Format

All errors follow this format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

## Lock Testing Endpoints

### 6. Test Lock Mechanism

Simulates a long-running request to test the lock mechanism.

**Endpoint:** `POST /test/lock-simulation`

**Request:**
```json
{
  "room_id": "test-room-lock",
  "thread_id": "test-thread-lock",
  "duration": 5
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Successfully held lock for 5.00 seconds",
  "room_id": "test-room-lock",
  "thread_id": "test-thread-lock"
}
```

### 7. Check Lock Status

View currently active locks and memory usage.

**Endpoint:** `GET /test/lock-status`

**Response:**
```json
{
  "status": "success",
  "active_locks": ["room1:thread1", "room2:thread2"],
  "active_count": 2,
  "total_locks_in_memory": 5,
  "timestamp": "2024-01-01T00:00:00.000000"
}
```

### 8. Test Concurrent Locks

Tests concurrent lock acquisition with 5 simultaneous attempts.

**Endpoint:** `POST /test/concurrent-lock-test`

**Request:** Same as lock-simulation

## Concurrent Request Protection

The API uses database thread locks to prevent concurrent processing:

### Database Thread Locks
- **Purpose**: Prevent concurrent message processing and coordinate across services
- **Table**: `thread_locks` in Supabase
- **Implementation**: `services/lock_manager.py`

### Lock Flow

#### Simplified Flow (Current Implementation)
The current client implementation uses a **simplified approach** that relies primarily on server-side locking:

1. **Client sends message**: User submits message → client saves to database → gets `user_message_id`
2. **Client calls streaming endpoint**: POST to `/chat/stream` with the `user_message_id`
3. **Server handles locking**: Server fetches user message and manages all lock logic:
   - `ai_streaming` lock exists → Reject with HTTP 409
   - `user_message` lock by different user → Reject with HTTP 409  
   - `user_message` lock by same user → Transition to AI lock (`transition_lock_to_ai`)
   - No lock → Create new AI lock
4. **AI Processing**: Server processes with exclusive thread access
5. **Lock Release**: Server releases lock after AI completes (`release_thread_lock`)
6. **Client UI**: Client disables send button based on streaming state (`isSendingDisabled`)

#### Advanced Flow (Optional Client-Side Locking)
For more sophisticated clients that want to prevent conflicts earlier:

1. **Client acquires lock**: Call `acquire_thread_lock('user_message', profile_id, thread_id)` before sending
2. **Client sends message**: Save message to database with existing lock
3. **Client calls streaming**: POST to `/chat/stream` endpoint
4. **Server transitions lock**: Server calls `transition_lock_to_ai` to change lock ownership
5. **AI Processing**: Server processes with exclusive access
6. **Server releases lock**: Lock automatically released after completion or error

#### Client UI State Management
- **Send Button**: Disabled when `isSendingDisabled` is true (based on streaming state)
- **Streaming State**: Managed by `useAIStreaming` hook tracking active AI responses
- **Auto-enable**: Send button re-enabled when streaming completes (`completeStreamingMessage`)

### Lock Types
- `user_message`: User is sending a message
- `ai_streaming`: AI is generating a response

### Features
- **Fault Tolerance**: Server automatically handles locks if client fails
- **Auto-expiry**: Locks expire after 30-120 seconds to prevent deadlocks
- **Conflict Detection**: Returns HTTP 409 with wait time for concurrent requests
- **Error Recovery**: Locks are released on errors to prevent deadlocks
- **Cross-service**: Works across multiple service instances

This simplified database-only locking system ensures data consistency, prevents duplicate AI responses, and provides reliable concurrency control across all services.

## Rate Limiting

Currently not implemented. Recommended limits for production:
- Chat streams: 10 requests/minute per IP
- Test endpoints: 30 requests/minute per IP