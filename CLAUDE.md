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
1. **API Layer** (`routers/chat.py`): Receives chat requests with user_id, mentor_id, and user_prompt
2. **Orchestration** (`services/chat_orchestrator.py`): 
   - Fetches mentor persona from Supabase `mentors` table
   - Retrieves last 10 messages from `chat_history` table
   - Constructs contextualized prompt using LangChain templates
3. **AI Processing**: Streams response from Google Gemini Pro model
4. **Response**: Returns Server-Sent Events (SSE) stream to client

### Key Integration Points

**Supabase Tables:**
- `mentors`: Stores mentor personas (id, persona fields)
- `chat_history`: Stores conversations (user_id, mentor_id, message, sender, timestamp)

**External Services:**
- Google Gemini Pro API (via GOOGLE_API_KEY)
- Supabase Database (via SUPABASE_URL and SUPABASE_KEY)

### Service Layer Pattern

The `ChatOrchestrator` class in `services/chat_orchestrator.py` is the core business logic handler. When modifying chat behavior:
- Persona retrieval logic: `_get_mentor_persona()` method
- History management: `_get_chat_history()` method  
- Streaming logic: `stream_response()` method
- Prompt template modifications: Update the `PromptTemplate` in `stream_response()`

### Configuration Management

All configuration is centralized in `core/config.py` using Pydantic Settings. Environment variables are automatically loaded from `.env` file. Required variables:
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `GOOGLE_API_KEY`