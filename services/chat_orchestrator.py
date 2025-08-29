from langchain.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema.runnable import RunnablePassthrough
from typing import AsyncGenerator, Optional, List, Dict, Any
from datetime import datetime
import uuid

from core.supabase_client import supabase_client
from core.config import settings

class ChatOrchestrator:
    def __init__(self):
        self.db_client = supabase_client
        # LLM will be initialized dynamically based on AI model

    def _get_ai_info(self, ai_id: str) -> Optional[Dict[str, Any]]:
        """Fetch AI info from the 'ai' table"""
        try:
            response = self.db_client.table('ai').select('model, system_prompt, name').eq('id', ai_id).single().execute()
            return response.data
        except Exception as e:
            print(f"Error fetching AI info: {e}")
            return None

    def _get_chat_history(self, room_id: str, thread_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch chat history from messages table for a specific room and thread"""
        try:
            response = self.db_client.table('messages')\
                .select('*')\
                .eq('room_id', room_id)\
                .eq('thread_id', thread_id)\
                .order('created_at', desc=True)\
                .limit(limit)\
                .execute()
            return response.data if response.data else []
        except Exception as e:
            print(f"Error fetching chat history: {e}")
            return []

    def _format_chat_history(self, messages: List[Dict[str, Any]], ai_name: str = "Assistant") -> str:
        """Format chat history for the prompt"""
        if not messages:
            return "No previous messages"
        
        history_str = ""
        for msg in reversed(messages):
            # sender_type: 1=user, 2=ai
            if msg['sender_type'] == 1:
                sender_name = "User"
            else:
                sender_name = ai_name
            
            history_str += f"{sender_name}: {msg['content']}\n"
        
        return history_str

    def _get_llm(self, model: Optional[str] = None) -> ChatGoogleGenerativeAI:
        """Get LLM instance with the specified model"""
        model_name = model if model else "gemini-2.5-flash"
        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0.2,
            google_api_key=settings.google_api_key
        )

    def _save_message(self, room_id: str, thread_id: str, content: str, 
                     sender_type: int, sender_id: Optional[str] = None,
                     ai_id_list: Optional[List[str]] = None) -> Optional[str]:
        """Save a message to the database"""
        try:
            message_data = {
                'id': str(uuid.uuid4()),
                'room_id': room_id,
                'thread_id': thread_id,
                'content': content,
                'sender_type': sender_type,  # 1=user, 2=ai
                'sender_id': sender_id,
                'ai_id_list': ai_id_list if ai_id_list else [],
                'created_at': datetime.utcnow().isoformat()
            }
            
            response = self.db_client.table('messages').insert(message_data).execute()
            return response.data[0]['id'] if response.data else None
        except Exception as e:
            print(f"Error saving message: {e}")
            return None

    async def stream_response(self, room_id: str, thread_id: str, ai_id: str, 
                            user_prompt: str, user_id: Optional[str] = None) -> AsyncGenerator[str, None]:
        """Stream AI response based on room context and AI system prompt"""
        
        # Get AI info
        ai_info = self._get_ai_info(ai_id)
        if not ai_info:
            yield "Error: AI not found"
            return
        
        # Get model and system prompt
        model = ai_info.get('model')
        system_prompt = ai_info.get('system_prompt', 'You are a helpful AI assistant.')
        ai_name = ai_info.get('name', 'Assistant')
        
        # Get LLM instance with the appropriate model
        llm = self._get_llm(model)
        
        # Get chat history
        messages = self._get_chat_history(room_id, thread_id)
        chat_history = self._format_chat_history(messages, ai_name)
        
        # Build the prompt using system_prompt
        template = """{system_prompt}

Previous conversation:
{chat_history}

User: {user_prompt}
Assistant:"""
        
        prompt = PromptTemplate.from_template(template)
        
        # Create chain for streaming
        chain = RunnablePassthrough() | prompt | llm
        
        # Prepare inputs
        inputs = {
            "system_prompt": system_prompt,
            "chat_history": chat_history,
            "user_prompt": user_prompt
        }

        print(inputs)
        
        # Stream response and collect for saving
        full_response = ""
        async for chunk in chain.astream(inputs):
            content = chunk.content
            full_response += content
            yield content
        
        # Save AI response
        self._save_message(
            room_id=room_id,
            thread_id=thread_id,
            content=full_response,
            sender_type=2,  # ai
            sender_id=ai_id,
            ai_id_list=[ai_id]
        )