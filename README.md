# Panello AI Service

A high-performance streaming AI chat service built with FastAPI, designed for real-time conversational AI experiences with multi-client synchronization support.

## ✨ Features

- **Real-time Streaming**: Background processing with Supabase real-time subscriptions
- **Multi-AI Support**: Dynamic AI personality selection with customizable system prompts
- **Multi-Client Sync**: All clients in a room receive updates automatically
- **Conversation Context**: Maintains chat history within rooms and threads
- **Model Flexibility**: Support for multiple Google Gemini models
- **Concurrent Request Protection**: Lock mechanism prevents duplicate processing for same room/thread
- **Production Ready**: Built-in error handling, logging, and cleanup mechanisms

## 🚀 New Architecture (v2.0)

The service now uses a scalable architecture with Supabase real-time subscriptions:

1. **Immediate Response**: API returns `streaming_message_id` instantly
2. **Background Processing**: AI responses processed asynchronously
3. **Real-time Updates**: Clients subscribe to database changes
4. **Multi-client Support**: All clients receive updates automatically

## 📋 Prerequisites

- Python 3.8+
- Supabase account with configured database
- Google Cloud account with Gemini API access
- pip or poetry for dependency management

## 🛠️ Installation

### 1. Clone the repository
```bash
git clone <repository-url>
cd panello_ai_service
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set up environment variables
```bash
cp .env.example .env
```

Edit `.env` with your credentials:
```env
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key

# Google AI Configuration  
GOOGLE_API_KEY=your-google-api-key

# Optional
ENVIRONMENT=development
LOG_LEVEL=INFO
```

### 4. Run database migrations

Apply the streaming messages migration to your Supabase database:
```sql
-- Copy and run the migration from:
-- ai-mentor-panello/supabase/migrations/20250905000000_create_streaming_messages_system.sql
```

Enable real-time:
```sql
ALTER PUBLICATION supabase_realtime ADD TABLE streaming_messages;
```

## 🏃 Running the Service

### Development Mode
```bash
# With auto-reload
uvicorn main:app --reload

# Specify host and port
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Production Mode
```bash
# Using Gunicorn with Uvicorn workers
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Docker
```bash
# Build and run with Docker
docker build -t panello-ai-service .
docker run -p 8000:8000 --env-file .env panello-ai-service

# Or use Docker Compose
docker-compose up -d
```

## 🏗️ Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Client    │────▶│  FastAPI     │────▶│  Google Gemini  │
│  (Frontend) │◀────│   Service    │◀────│      API        │
└─────────────┘     └──────────────┘     └─────────────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │   Supabase   │
                    │   Database   │
                    └──────────────┘
```

### Message Flow
```
1. User saves message to database
2. Client calls POST /chat/stream with message_id
3. API returns streaming_message_id immediately
4. Background task processes AI response
5. Updates stream to streaming_messages table
6. All subscribed clients receive real-time updates
7. On completion, final message saved to messages table
```

## 💻 Client Integration

### Quick Example (JavaScript)
```javascript
// 1. Save user message
const { data: userMessage } = await supabase
  .from('messages')
  .insert({ room_id, thread_id, content, sender_type: 1 })
  .select()
  .single();

// 2. Request AI response
const { streaming_message_id } = await fetch('/api/chat/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    room_id, thread_id, ai_id,
    user_message_id: userMessage.id
  })
}).then(r => r.json());

// 3. Subscribe to updates (all clients in room do this)
supabase.channel(`room-${room_id}`)
  .on('postgres_changes', {
    event: '*',
    table: 'streaming_messages',
    filter: `room_id=eq.${room_id}`
  }, (payload) => {
    // Handle streaming updates
    updateUI(payload.new.content);
  })
  .subscribe();
```

## 📚 Documentation

Detailed documentation available in the `/docs` folder:

- **[API Reference](docs/01-API_REFERENCE.md)** - Complete API endpoints documentation
- **[Streaming Architecture](docs/02-STREAMING_ARCHITECTURE.md)** - Technical architecture details
- **[Client Integration](docs/03-CLIENT_INTEGRATION.md)** - Implementation guides for React, Vue, JavaScript, Flutter
- **[Deployment Guide](docs/04-DEPLOYMENT.md)** - Production deployment and scaling

## 🧪 Testing

### Test Endpoints
```bash
# List available AIs
curl http://localhost:8000/test/list-ai

# Test streaming without database
curl -X POST http://localhost:8000/test/chat-stream-mock

# Test with real AI
curl -X POST http://localhost:8000/test/chat-stream \
  -H "Content-Type: application/json" \
  -d '{"ai_id": "your-ai-id", "user_prompt": "Hello"}'

# Test lock mechanism
curl -X POST http://localhost:8000/test/lock-simulation \
  -H "Content-Type: application/json" \
  -d '{"room_id": "test-room", "thread_id": "test-thread", "duration": 5}'

# Check active locks
curl http://localhost:8000/test/lock-status
```

### Health Check
```bash
curl http://localhost:8000/health
```

## 📊 Database Schema

### Core Tables
- **`ai`**: AI configurations (model, system_prompt, name)
- **`messages`**: Permanent message storage
- **`streaming_messages`**: Temporary streaming state for active AI responses
- **`rooms`**: Conversation spaces
- **`threads`**: Topics within rooms

### Key Functions
- `upsert_streaming_message()`: Create/update streaming message
- `complete_streaming_message()`: Finalize and save to messages
- `cleanup_old_streaming_messages()`: Periodic cleanup

## 🔧 Configuration

### AI Models
Configure in the `ai` table. Supported models:
- `gemini-2.0-flash-exp` (default)
- `gemini-1.5-pro`
- `gemini-1.5-flash`

### System Prompts
Define AI personality in the `ai` table's `system_prompt` field:
```sql
UPDATE ai 
SET system_prompt = 'You are a helpful Python expert...'
WHERE id = 'your-ai-id';
```

## 🚀 Performance

- **Database indexes** for efficient queries
- **Connection pooling** for database connections
- **Async/await** throughout for non-blocking I/O
- **Batched updates** to reduce database writes
- **Horizontal scaling** ready

## 🔒 Security & Reliability

- Row Level Security (RLS) on all tables
- Input validation with Pydantic models
- Environment variables for sensitive data
- Rate limiting recommended for production
- Supabase authentication integration ready
- **Concurrent Request Protection**: Automatic lock mechanism prevents duplicate AI processing for the same room/thread combination, returning HTTP 409 for conflicting requests

## 🐛 Troubleshooting

### Common Issues

1. **Streaming not updating**: Check Supabase real-time is enabled
2. **Connection errors**: Verify environment variables
3. **AI not responding**: Check Google API key and quotas

### Debug Mode
```bash
# Enable debug logging
LOG_LEVEL=DEBUG uvicorn main:app --reload
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📝 License

[Your License Here]

## 💬 Support

- GitHub Issues: [repository-url]/issues
- Documentation: See `/docs` folder
- API Docs: Available at `/docs` endpoint when running

## 🙏 Acknowledgments

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Modern web framework
- [Supabase](https://supabase.com/) - Real-time database
- [Google Gemini](https://ai.google.dev/) - AI model
- [LangChain](https://langchain.com/) - LLM framework