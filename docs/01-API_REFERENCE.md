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

The API implements a lock mechanism to prevent concurrent processing of requests for the same room_id and thread_id combination:

- **First request**: Acquires lock and processes normally
- **Concurrent requests**: Receive HTTP 409 (Conflict) immediately
- **Lock release**: Automatic on completion or error
- **Memory management**: Unused locks are cleaned up automatically

This ensures data consistency and prevents duplicate AI responses when multiple clients or requests target the same conversation simultaneously.

## Rate Limiting

Currently not implemented. Recommended limits for production:
- Chat streams: 10 requests/minute per IP
- Test endpoints: 30 requests/minute per IP