from langchain.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema.runnable import RunnablePassthrough
from typing import AsyncGenerator, Optional, List, Dict, Any
from datetime import datetime
import uuid
import logging
import re
import asyncio

from core.supabase_client import supabase_client
from core.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(asctime)s - %(name)s - %(message)s')

logger = logging.getLogger(__name__)

# Moderator AI
MODERATOR_AI_ID = "10000000-0000-0000-0000-000000000007"

class ChatOrchestrator:
    def __init__(self):
        self.db_client = supabase_client
        # LLM will be initialized dynamically based on AI model

    def _get_ai_info(self, ai_id: str) -> Optional[Dict[str, Any]]:
        """Fetch AI info from the 'ai' table"""
        try:
            response = self.db_client.table('ai').select('model, system_prompt, description, personality, name').eq('id', ai_id).single().execute()
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
    
    def _build_enhanced_system_prompt(self, base_prompt: str, ai_name: str, 
                                     description: str, personality: str) -> str:
        """Build enhanced system prompt for normal AIs with description and personality"""
        enhanced_prompt = base_prompt
        
        # Add description and personality if available
        if description or personality:
            enhanced_prompt += "\n\n## About You:"
            
            if description:
                enhanced_prompt += f"\nDescription: {description}"
            
            if personality:
                enhanced_prompt += f"\nPersonality: {personality}"
            
            enhanced_prompt += f"\n\nYour name is {ai_name}. Respond according to your described personality and expertise."
        
        return enhanced_prompt
    
    def _build_moderator_system_prompt(self, base_prompt: str, room_id: str,
                                      ai_name: str, description: str, personality: str) -> str:
        """Build system prompt for moderator AI including available AIs in the room"""
        # Start with enhanced base prompt
        enhanced_prompt = self._build_enhanced_system_prompt(
            base_prompt, ai_name, description, personality
        )
        
        # Get all AIs in the room
        try:
            # Fetch room AIs
            room_ai_response = self.db_client.table('room_ai')\
                .select('ai_id')\
                .eq('room_id', room_id)\
                .eq('is_active', True)\
                .execute()
            
            if room_ai_response.data:
                # Filter out the moderator AI to avoid self-reference
                ai_ids = [ra['ai_id'] for ra in room_ai_response.data 
                         if ra['ai_id'] != MODERATOR_AI_ID]
                
                if ai_ids:  # Only proceed if there are non-moderator AIs
                    # Fetch AI details for all non-moderator AIs in the room
                    ai_details_response = self.db_client.table('ai')\
                        .select('id, name, description, personality')\
                        .in_('id', ai_ids)\
                        .eq('is_active', True)\
                        .execute()
                    
                    if ai_details_response.data:
                        # Filter out moderator again (extra safety) and build available AIs section
                        non_moderator_ais = [ai for ai in ai_details_response.data 
                                            if ai.get('id') != MODERATOR_AI_ID]
                        
                        if non_moderator_ais:
                            enhanced_prompt += "\n\n## Available AI Mentors in this room:"
                            
                            for ai in non_moderator_ais:
                                enhanced_prompt += f"\n- Name: {ai['name']}"
                                if ai.get('description'):
                                    enhanced_prompt += f". Description: {ai['description']}"
                                if ai.get('personality'):
                                    enhanced_prompt += f". Personality: {ai['personality']}"
                                enhanced_prompt += "."
                            
                            enhanced_prompt += """\n\nAs the moderator, you can help users choose the right AI mentor based on their needs. DON'T CHOOSE YOURSELF!

When you decide to forward a user to a specific AI mentor, you MUST use this exact format:
Forward to AI mentor: **{AI name}**.
Reason is {reason why you choose them in max 100 words}

IMPORTANT: Always use the exact AI name as listed above and put it between ** ** markers."""
                    
        except Exception as e:
            logger.warning(f"Error fetching room AIs for moderator prompt: {e}")
            # Continue with base prompt if fetching room AIs fails
        
        return enhanced_prompt

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
    
    def _extract_ai_name_from_moderator_response(self, response: str) -> Optional[str]:
        """Extract AI name from moderator response format: Forward to AI mentor: **{AI name}**"""
        try:
            # Use regex to extract AI name between ** **
            pattern = r'\*\*([^*]+)\*\*'
            matches = re.findall(pattern, response)
            
            if matches:
                # Return the first match (should be the AI name)
                ai_name = matches[0].strip()
                logger.info(f"Extracted AI name from moderator response: {ai_name}")
                return ai_name
            else:
                logger.warning(f"Could not extract AI name from moderator response: {response[:100]}...")
                return None
        except Exception as e:
            logger.error(f"Error extracting AI name from moderator response: {e}")
            return None
    
    def _get_ai_id_by_name(self, ai_name: str, room_id: str) -> Optional[str]:
        """Get AI ID by name from the room's available AIs"""
        try:
            # First get all AIs in the room
            room_ai_response = self.db_client.table('room_ai')\
                .select('ai_id')\
                .eq('room_id', room_id)\
                .eq('is_active', True)\
                .execute()
            
            if not room_ai_response.data:
                logger.warning(f"No AIs found in room {room_id}")
                return None
            
            ai_ids = [ra['ai_id'] for ra in room_ai_response.data]
            
            # Now get AI details and match by name
            ai_details_response = self.db_client.table('ai')\
                .select('id, name')\
                .in_('id', ai_ids)\
                .eq('is_active', True)\
                .execute()
            
            if ai_details_response.data:
                for ai in ai_details_response.data:
                    # Case-insensitive comparison
                    if ai['name'].lower() == ai_name.lower():
                        logger.info(f"Found AI ID {ai['id']} for name {ai_name}")
                        return ai['id']
            
            logger.warning(f"Could not find AI with name {ai_name} in room {room_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting AI ID by name {ai_name}: {e}")
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
            
            # Get AI attributes
            model = ai_info.get('model')
            base_system_prompt = ai_info.get('system_prompt', 'You are a helpful AI assistant.')
            ai_name = ai_info.get('name', 'Assistant')
            description = ai_info.get('description', '')
            personality = ai_info.get('personality', '')
            
            # Build enhanced system prompt
            if ai_id == MODERATOR_AI_ID:
                # For moderator AI, include available AIs in the room
                system_prompt = self._build_moderator_system_prompt(
                    base_system_prompt, room_id, ai_name, description, personality
                )
            else:
                # For normal AI, enhance with description and personality
                system_prompt = self._build_enhanced_system_prompt(
                    base_system_prompt, ai_name, description, personality
                )

            # logger.info(f"system_prompt: {system_prompt}")
            
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
            final_message_id = self._complete_streaming_message(streaming_message_id)
            logger.info(f"Completed processing for streaming message {streaming_message_id}")
            
            # Check if this was a moderator response and if it selected an AI
            if ai_id == MODERATOR_AI_ID and full_response:
                logger.info("Checking if moderator selected an AI to forward to...")
                selected_ai_name = self._extract_ai_name_from_moderator_response(full_response)
                
                if selected_ai_name:
                    selected_ai_id = self._get_ai_id_by_name(selected_ai_name, room_id)
                    
                    if selected_ai_id:
                        logger.info(f"Moderator selected AI {selected_ai_name} (ID: {selected_ai_id}). Triggering next stream...")
                        
                        # Create a new streaming message for the selected AI
                        next_streaming_id = self.initialize_streaming_message(
                            room_id=room_id,
                            thread_id=thread_id,
                            ai_id=selected_ai_id,
                            user_message_id=user_message_id  # Use the same user message
                        )
                        
                        if next_streaming_id:
                            # Process the next AI response in the background
                            logger.info(f"Starting background processing for selected AI {selected_ai_id}")
                            asyncio.create_task(
                                self.process_streaming_response(
                                    room_id=room_id,
                                    thread_id=thread_id,
                                    ai_id=selected_ai_id,
                                    user_message_id=user_message_id,
                                    streaming_message_id=next_streaming_id
                                )
                            )
                        else:
                            logger.error(f"Failed to initialize streaming message for selected AI {selected_ai_id}")
                    else:
                        logger.warning(f"Could not find AI ID for selected AI name: {selected_ai_name}")
                else:
                    logger.info("Moderator response did not select a specific AI")
            
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
        
        # Get AI attributes
        model = ai_info.get('model')
        base_system_prompt = ai_info.get('system_prompt', 'You are a helpful AI assistant.')
        ai_name = ai_info.get('name', 'Assistant')
        description = ai_info.get('description', '')
        personality = ai_info.get('personality', '')
        
        # Build enhanced system prompt
        if ai_id == MODERATOR_AI_ID:
            # For moderator AI, include available AIs in the room
            system_prompt = self._build_moderator_system_prompt(
                base_system_prompt, room_id, ai_name, description, personality
            )
        else:
            # For normal AI, enhance with description and personality
            system_prompt = self._build_enhanced_system_prompt(
                base_system_prompt, ai_name, description, personality
            )
        
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
                final_message_id = self._complete_streaming_message(streaming_message_id)
                
                # Check if this was a moderator response and if it selected an AI
                if ai_id == MODERATOR_AI_ID and full_response:
                    logger.info("Checking if moderator selected an AI to forward to...")
                    selected_ai_name = self._extract_ai_name_from_moderator_response(full_response)
                    
                    if selected_ai_name:
                        selected_ai_id = self._get_ai_id_by_name(selected_ai_name, room_id)
                        
                        if selected_ai_id:
                            logger.info(f"Moderator selected AI {selected_ai_name} (ID: {selected_ai_id}). Triggering next stream...")
                            
                            # Create a new streaming message for the selected AI
                            next_streaming_id = self.initialize_streaming_message(
                                room_id=room_id,
                                thread_id=thread_id,
                                ai_id=selected_ai_id,
                                user_message_id=user_message_id  # Use the same user message
                            )
                            
                            if next_streaming_id:
                                # Process the next AI response in the background
                                logger.info(f"Starting background processing for selected AI {selected_ai_id}")
                                asyncio.create_task(
                                    self.process_streaming_response(
                                        room_id=room_id,
                                        thread_id=thread_id,
                                        ai_id=selected_ai_id,
                                        user_message_id=user_message_id,
                                        streaming_message_id=next_streaming_id
                                    )
                                )
                            else:
                                logger.error(f"Failed to initialize streaming message for selected AI {selected_ai_id}")
                        else:
                            logger.warning(f"Could not find AI ID for selected AI name: {selected_ai_name}")
                    else:
                        logger.info("Moderator response did not select a specific AI")
        
        except Exception as e:
            logger.error(f"Error during streaming for room {room_id}, thread {thread_id}: {e}")
            # Mark streaming as complete even on error
            if streaming_message_id:
                try:
                    self._complete_streaming_message(streaming_message_id)
                except Exception as complete_error:
                    logger.error(f"Failed to complete streaming message on error: {complete_error}")
            raise