from langchain.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema.runnable import RunnablePassthrough
from typing import AsyncGenerator, Optional, List, Dict, Any
from datetime import datetime
import uuid
import logging

from core.supabase_client import supabase_client
from core.config import settings

# Configure logging
logger = logging.getLogger(__name__)

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
            logger.error(f"Error fetching AI info for AI ID {ai_id}: {e}")
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
            logger.error(f"Error fetching chat history for room {room_id}, thread {thread_id}: {e}")
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
                     ai_id_list: Optional[List[str]] = None,
                     response_to_message: Optional[str] = None) -> Optional[str]:
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
                'response_to_message': response_to_message,
                'created_at': datetime.utcnow().isoformat()
            }
            
            response = self.db_client.table('messages').insert(message_data).execute()
            return response.data[0]['id'] if response.data else None
        except Exception as e:
            logger.error(f"Error saving message to room {room_id}, thread {thread_id}: {e}")
            return None
    
    def _upsert_streaming_message(self, streaming_id: Optional[str], room_id: str, 
                                 thread_id: str, ai_id: str, user_message_id: str,
                                 content: str, is_complete: bool = False) -> Optional[str]:
        """Upsert streaming message using the Supabase function"""
        try:
            # Call the upsert_streaming_message function
            response = self.db_client.rpc('upsert_streaming_message', {
                'p_room_id': room_id,
                'p_thread_id': thread_id,
                'p_ai_id': ai_id,
                'p_user_message_id': user_message_id,
                'p_content': content,
                'p_is_complete': is_complete
            }).execute()
            
            return response.data if response.data else streaming_id
        except Exception as e:
            logger.error(f"Error upserting streaming message for room {room_id}, thread {thread_id}: {e}")
            return streaming_id
    
    def _complete_streaming_message(self, streaming_id: str) -> Optional[str]:
        """Complete streaming message and create final message"""
        try:
            # Call the complete_streaming_message function
            response = self.db_client.rpc('complete_streaming_message', {
                'p_streaming_id': streaming_id
            }).execute()
            
            logger.info(f"Successfully completed streaming message {streaming_id}")
            return response.data if response.data else None
        except Exception as e:
            logger.error(f"Error completing streaming message {streaming_id}: {e}")
            return None
    
    def cleanup_incomplete_streaming_messages(self, room_id: str, thread_id: str) -> None:
        """Cleanup any incomplete streaming messages for a room/thread"""
        try:
            # Find incomplete streaming messages
            response = self.db_client.table('streaming_messages')\
                .select('id')\
                .eq('room_id', room_id)\
                .eq('thread_id', thread_id)\
                .eq('is_complete', False)\
                .execute()
            
            if response.data:
                for msg in response.data:
                    logger.warning(f"Cleaning up incomplete streaming message {msg['id']}")
                    self._complete_streaming_message(msg['id'])
        except Exception as e:
            logger.error(f"Error cleaning up incomplete streaming messages: {e}")
    
    def initialize_streaming_message(self, room_id: str, thread_id: str, 
                                    ai_id: str, user_message_id: str) -> Optional[str]:
        """Initialize a streaming message and return its ID"""
        try:
            # Cleanup any incomplete streaming messages first
            self.cleanup_incomplete_streaming_messages(room_id, thread_id)
            
            # Create initial streaming message
            streaming_message_id = self._upsert_streaming_message(
                streaming_id=None,
                room_id=room_id,
                thread_id=thread_id,
                ai_id=ai_id,
                user_message_id=user_message_id,
                content="",  # Start with empty content
                is_complete=False
            )
            
            logger.info(f"Initialized streaming message {streaming_message_id}")
            return streaming_message_id
            
        except Exception as e:
            logger.error(f"Error initializing streaming message: {e}")
            return None
    
    async def process_streaming_response(self, room_id: str, thread_id: str, 
                                        ai_id: str, user_message_id: str,
                                        streaming_message_id: str) -> None:
        """Process AI response and update streaming message in background"""
        try:
            # Get AI info
            ai_info = self._get_ai_info(ai_id)
            if not ai_info:
                logger.error(f"AI {ai_id} not found")
                self._upsert_streaming_message(
                    streaming_id=streaming_message_id,
                    room_id=room_id,
                    thread_id=thread_id,
                    ai_id=ai_id,
                    user_message_id=user_message_id,
                    content="Error: AI not found",
                    is_complete=True
                )
                return
            
            # Get user message content
            try:
                user_msg_response = self.db_client.table('messages')\
                    .select('content, sender_id')\
                    .eq('id', user_message_id)\
                    .single()\
                    .execute()
                
                if not user_msg_response.data:
                    logger.error(f"User message {user_message_id} not found")
                    self._upsert_streaming_message(
                        streaming_id=streaming_message_id,
                        room_id=room_id,
                        thread_id=thread_id,
                        ai_id=ai_id,
                        user_message_id=user_message_id,
                        content="Error: User message not found",
                        is_complete=True
                    )
                    return
                    
                user_prompt = user_msg_response.data['content']
            except Exception as e:
                logger.error(f"Error fetching user message {user_message_id}: {e}")
                self._upsert_streaming_message(
                    streaming_id=streaming_message_id,
                    room_id=room_id,
                    thread_id=thread_id,
                    ai_id=ai_id,
                    user_message_id=user_message_id,
                    content="Error: Failed to fetch user message",
                    is_complete=True
                )
                return
            
            # Get model and system prompt
            model = ai_info.get('model')
            system_prompt = ai_info.get('system_prompt', 'You are a helpful AI assistant.')
            ai_name = ai_info.get('name', 'Assistant')
            
            # Get LLM instance
            llm = self._get_llm(model)
            
            # Get chat history
            messages = self._get_chat_history(room_id, thread_id)
            chat_history = self._format_chat_history(messages, ai_name)
            
            # Build the prompt
            template = """{system_prompt}

Previous conversation:
{chat_history}

User: {user_prompt}
Assistant:"""
            
            from langchain.prompts import PromptTemplate
            from langchain.schema.runnable import RunnablePassthrough
            
            prompt = PromptTemplate.from_template(template)
            chain = RunnablePassthrough() | prompt | llm
            
            inputs = {
                "system_prompt": system_prompt,
                "chat_history": chat_history,
                "user_prompt": user_prompt
            }
            
            logger.debug(f"Processing AI response for streaming message {streaming_message_id}")
            
            # Stream response and update streaming message
            full_response = ""
            async for chunk in chain.astream(inputs):
                content = chunk.content
                full_response += content
                
                # Update streaming message with accumulated content
                self._upsert_streaming_message(
                    streaming_id=streaming_message_id,
                    room_id=room_id,
                    thread_id=thread_id,
                    ai_id=ai_id,
                    user_message_id=user_message_id,
                    content=full_response,
                    is_complete=False
                )
            
            # Complete the streaming message
            self._complete_streaming_message(streaming_message_id)
            logger.info(f"Completed processing for streaming message {streaming_message_id}")
            
        except Exception as e:
            logger.error(f"Error processing streaming response: {e}")
            # Mark as complete with error
            if streaming_message_id:
                try:
                    self._upsert_streaming_message(
                        streaming_id=streaming_message_id,
                        room_id=room_id,
                        thread_id=thread_id,
                        ai_id=ai_id,
                        user_message_id=user_message_id,
                        content=f"Error: {str(e)}",
                        is_complete=True
                    )
                except Exception as complete_error:
                    logger.error(f"Failed to mark streaming message as complete on error: {complete_error}")

    async def stream_response(self, room_id: str, thread_id: str, ai_id: str, 
                            user_message_id: str) -> AsyncGenerator[str, None]:
        """Stream AI response based on room context and AI system prompt"""
        
        # Cleanup any incomplete streaming messages first
        self.cleanup_incomplete_streaming_messages(room_id, thread_id)
        
        # Get AI info
        ai_info = self._get_ai_info(ai_id)
        if not ai_info:
            yield "Error: AI not found"
            return
        
        # Get user message content
        try:
            user_msg_response = self.db_client.table('messages')\
                .select('content, sender_id')\
                .eq('id', user_message_id)\
                .single()\
                .execute()
            
            if not user_msg_response.data:
                yield "Error: User message not found"
                return
                
            user_prompt = user_msg_response.data['content']
        except Exception as e:
            logger.error(f"Error fetching user message {user_message_id}: {e}")
            yield "Error: Failed to fetch user message"
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

        logger.debug(f"Chat inputs for room {room_id}, thread {thread_id}: {inputs}")
        
        # Initialize streaming message ID
        streaming_message_id = None
        
        # Stream response and collect for saving
        full_response = ""
        try:
            async for chunk in chain.astream(inputs):
                content = chunk.content
                full_response += content
                
                # Upsert to streaming_messages table
                streaming_message_id = self._upsert_streaming_message(
                    streaming_id=streaming_message_id,
                    room_id=room_id,
                    thread_id=thread_id,
                    ai_id=ai_id,
                    user_message_id=user_message_id,
                    content=full_response,
                    is_complete=False
                )
                
                yield content
            
            # Complete the streaming message and create final message
            if streaming_message_id:
                self._complete_streaming_message(streaming_message_id)
        
        except Exception as e:
            logger.error(f"Error during streaming for room {room_id}, thread {thread_id}: {e}")
            # Mark streaming as complete even on error
            if streaming_message_id:
                try:
                    self._complete_streaming_message(streaming_message_id)
                except Exception as complete_error:
                    logger.error(f"Failed to complete streaming message on error: {complete_error}")
            raise