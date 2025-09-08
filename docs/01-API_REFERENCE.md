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

## Rate Limiting

Currently not implemented. Recommended limits for production:
- Chat streams: 10 requests/minute per IP
- Test endpoints: 30 requests/minute per IP