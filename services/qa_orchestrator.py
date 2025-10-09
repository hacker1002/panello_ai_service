from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
import logging
import json
import time
import asyncio
import aiohttp

from core.supabase_client import supabase_client
from core.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(asctime)s - %(name)s - %(message)s')

logger = logging.getLogger(__name__)

# Custom AI API base URL
QA_API_BASE_URL = "http://34.27.126.117:8000"

class QAOrchestrator:
    def __init__(self):
        self.db_client = supabase_client

    def get_message_by_id(self, message_id: str) -> Optional[dict]:
        """Get a message by its ID"""
        try:
            response = self.db_client.from_('messages').select('*').eq('id', message_id).single().execute()
            return response.data
        except Exception as e:
            logger.error(f"Error fetching message {message_id}: {e}")
            return None

    def _get_ai_info(self, ai_id: str) -> Optional[Dict[str, Any]]:
        """Fetch AI info from the 'ai' table"""
        try:
            response = self.db_client.table('ai').select('model, system_prompt, description, personality, name, is_moderator').eq('id', ai_id).single().execute()
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

    def _format_chat_history_for_api(self, messages: List[Dict[str, Any]], ai_name: str = "Assistant") -> List[Dict[str, str]]:
        """Format chat history for the QA API with Question/Answer pairs"""
        if not messages:
            return []

        history = []
        # Reverse to get chronological order
        messages_sorted = list(reversed(messages))

        for i in range(len(messages_sorted)):
            msg = messages_sorted[i]
            if msg['sender_type'] == 1: # user message
                j = i + 1
                while j < len(messages_sorted):
                    next_msg = messages_sorted[j]
                    if next_msg['sender_type'] == 2 and next_msg['response_to_message'] == msg['id']:
                        history.append({
                            "Question": msg['content'],
                            "Answer": next_msg['content']
                        })
                    j += 1

        return history

    def _build_moderator_system_prompt(self, user_prompt: str, room_id: str) -> str:
        """Build system prompt for moderator AI including available AIs in the room"""
        # Start with enhanced base prompt
        enhanced_prompt = f"User Promt: {user_prompt}."

        # Get all AIs in the room
        try:
            # Fetch room AIs
            room_ai_response = self.db_client.table('room_ai')\
                .select('ai_id')\
                .eq('room_id', room_id)\
                .eq('is_active', True)\
                .execute()

            if room_ai_response.data:
                ai_ids = [ra['ai_id'] for ra in room_ai_response.data]

                if ai_ids:
                    # Fetch AI details for all AIs in the room (including is_moderator field)
                    ai_details_response = self.db_client.table('ai')\
                        .select('id, name, description, personality, is_moderator')\
                        .in_('id', ai_ids)\
                        .eq('is_active', True)\
                        .execute()

                    if ai_details_response.data:
                        # Filter out moderator AIs and build available AIs section
                        non_moderator_ais = [ai for ai in ai_details_response.data
                                            if not ai.get('is_moderator', False)]

                        if non_moderator_ais:
                            enhanced_prompt += "\n\n## Available AI Mentors in this room:"

                            for ai in non_moderator_ais:
                                enhanced_prompt += f"\n- AI ID: {ai['id']}, Name: {ai['name']}"
                                if ai.get('description'):
                                    enhanced_prompt += f". Description: {ai['description']}"
                                if ai.get('personality'):
                                    enhanced_prompt += f". Personality: {ai['personality']}"
                                enhanced_prompt += "."

        except Exception as e:
            logger.warning(f"Error fetching room AIs for moderator prompt: {e}")
            # Continue with base prompt if fetching room AIs fails

        return enhanced_prompt

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

    def _release_thread_lock(self, thread_id: str, ai_id: str):
        """Release the thread lock after AI completes streaming"""
        from services.lock_manager import lock_manager

        try:
            success = lock_manager.release_thread_lock(thread_id, ai_id)
            if not success:
                logger.warning(f"Failed to release thread lock for thread {thread_id}")
            return success
        except Exception as e:
            logger.error(f"Error releasing thread lock for thread {thread_id}: {e}")
            # Don't raise - we want to complete even if lock release fails


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

    async def _call_professional_sync(self, question_text: str, model: str, ai_info: dict,
                                      room_id: str, histories_chat: List[Dict[str, str]]) -> Optional[str]:
        """Call the professional-sync API endpoint"""
        try:
            url = f"{QA_API_BASE_URL}/api/qa/professional-sync"
            payload = {
                "question_text": question_text,
                "model": model or "gemini-2.5-flash",
                "ai_info": ai_info,
                "room_id": room_id,
                "top_k": 10,
                "histories_chat": histories_chat,
                "embedding_model": "embedding-001"
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Extract text from response structure
                        if data.get('messages') and len(data['messages']) > 0:
                            message = data['messages'][0]
                            if message.get('content') and len(message['content']) > 0:
                                return message['content'][0].get('text', '')
                        return None
                    else:
                        logger.error(f"Professional-sync API error: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error calling professional-sync API: {e}")
            return None

    async def _call_professional_stream(self, question_text: str, model: str, ai_info: dict,
                                       room_id: str, histories_chat: List[Dict[str, str]],
                                       streaming_message_id: str, thread_id: str, ai_id: str,
                                       user_message_id: str) -> str:
        """Call the professional-stream API endpoint and process streaming response"""
        try:
            url = f"{QA_API_BASE_URL}/api/qa/professional-stream"
            payload = {
                "question_text": question_text,
                "model": model or "gemini-2.5-flash",
                "ai_info": ai_info,
                "room_id": room_id,
                "top_k": 10,
                "histories_chat": histories_chat,
                "embedding_model": "embedding-001"
            }

            full_response = ""

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        # Read streaming response line by line
                        async for line in response.content:
                            if line:
                                try:
                                    line_str = line.decode('utf-8').strip()
                                    if line_str:
                                        chunk_data = json.loads(line_str)
                                        status = chunk_data.get('status')

                                        if status == 'answering':
                                            chunk = chunk_data.get('chunk', '')
                                            full_response += chunk

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
                                            time.sleep(0.5)  # wait for response stream to client

                                        elif status == 'complete':
                                            logger.info("Streaming complete")
                                            break
                                except json.JSONDecodeError as e:
                                    logger.warning(f"Failed to decode JSON chunk: {e}")
                                    continue
                    else:
                        logger.error(f"Professional-stream API error: {response.status}")
                        error_text = await response.text()
                        logger.error(f"Error response: {error_text}")

            return full_response
        except Exception as e:
            logger.error(f"Error calling professional-stream API: {e}")
            return f"Error: {str(e)}"

    async def process_streaming_response(self, room_id: str, thread_id: str,
                                        ai_id: str, user_message_id: str,
                                        streaming_message_id: str) -> None:
        """Process AI response using the custom QA API and update streaming message in background"""
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
            ai_system_prompt = ai_info.get('system_prompt', 'You are a helpful AI assistant.')
            ai_name = ai_info.get('name', 'Assistant')
            description = ai_info.get('description', '')
            personality = ai_info.get('personality', '')

            # Get chat history
            messages = self._get_chat_history(room_id, thread_id)
            histories_chat = self._format_chat_history_for_api(messages, ai_name)

            # Prepare AI info for API
            api_ai_info = {
                "id": ai_id,
                "name": ai_name,
                "description": description,
                "personality": personality,
                "system_prompt": ai_system_prompt
            }

            logger.debug(f"Processing AI response for streaming message {streaming_message_id}")

            # Check if this is the moderator AI
            is_moderator = ai_info.get('is_moderator', False)
            if is_moderator:
                # For moderator, use professional-sync (non-streaming)
                logger.info("Moderator AI detected, using professional-sync API")
                prompt = self._build_moderator_system_prompt(user_prompt, room_id)

                full_response = await self._call_professional_sync(
                    question_text=prompt,
                    model=model,
                    ai_info=api_ai_info,
                    room_id=room_id,
                    histories_chat=histories_chat
                )

                if not full_response:
                    full_response = "Error: Failed to get response from moderator"

                # Parse JSON response (strip markdown code block if present)
                try:
                    # Strip markdown code block markers if present
                    json_content = full_response.strip()
                    if json_content.startswith('```json'):
                        json_content = json_content[7:]  # Remove ```json
                    elif json_content.startswith('```'):
                        json_content = json_content[3:]  # Remove ```

                    if json_content.endswith('```'):
                        json_content = json_content[:-3]  # Remove trailing ```

                    json_content = json_content.strip()

                    response_json = json.loads(json_content)
                    message_content = response_json.get('message', '')
                    selected_ai_id = response_json.get('ai_id', None)

                    logger.info(f"Moderator response parsed: ai_id={selected_ai_id}, message={message_content[:100]}...")

                    # Save only the message content to streaming_messages
                    self._upsert_streaming_message(
                        streaming_id=streaming_message_id,
                        room_id=room_id,
                        thread_id=thread_id,
                        ai_id=ai_id,
                        user_message_id=user_message_id,
                        content=message_content,
                        is_complete=False
                    )

                    time.sleep(0.5)  # wait for response stream to client

                    # Store the selected AI ID for later processing
                    moderator_selected_ai_id = selected_ai_id

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse moderator JSON response: {e}. Response: {full_response}")
                    # If JSON parsing fails, save the raw response
                    self._upsert_streaming_message(
                        streaming_id=streaming_message_id,
                        room_id=room_id,
                        thread_id=thread_id,
                        ai_id=ai_id,
                        user_message_id=user_message_id,
                        content=full_response,
                        is_complete=True
                    )
                    moderator_selected_ai_id = None
            else:
                # For normal AI, use professional-stream
                logger.info("Normal AI detected, using professional-stream API")
                full_response = await self._call_professional_stream(
                    question_text=user_prompt,
                    model=model,
                    ai_info=api_ai_info,
                    room_id=room_id,
                    histories_chat=histories_chat,
                    streaming_message_id=streaming_message_id,
                    thread_id=thread_id,
                    ai_id=ai_id,
                    user_message_id=user_message_id
                )
                moderator_selected_ai_id = None

            # Complete the streaming message
            final_message_id = self._complete_streaming_message(streaming_message_id)
            logger.info(f"Completed processing for streaming message {streaming_message_id}")

            # Release the thread lock after AI completes streaming
            try:
                self._release_thread_lock(thread_id, ai_id)
                logger.info(f"Released thread lock for thread {thread_id} after AI {ai_id} completed streaming")
            except Exception as lock_error:
                logger.error(f"Failed to release thread lock for thread {thread_id}: {lock_error}")

            # Check if moderator selected an AI
            if is_moderator and 'moderator_selected_ai_id' in locals() and moderator_selected_ai_id:
                logger.info(f"Moderator selected AI ID: {moderator_selected_ai_id}. Triggering next stream...")

                # Verify the AI exists
                selected_ai_info = self._get_ai_info(moderator_selected_ai_id)
                if selected_ai_info:
                    # Create a new streaming message for the selected AI
                    next_streaming_id = self.initialize_streaming_message(
                        room_id=room_id,
                        thread_id=thread_id,
                        ai_id=moderator_selected_ai_id,
                        user_message_id=user_message_id  # Use the same user message
                    )

                    if next_streaming_id:
                        # Process the next AI response in the background
                        logger.info(f"Starting background processing for selected AI {moderator_selected_ai_id}")
                        asyncio.create_task(
                            self.process_streaming_response(
                                room_id=room_id,
                                thread_id=thread_id,
                                ai_id=moderator_selected_ai_id,
                                user_message_id=user_message_id,
                                streaming_message_id=next_streaming_id
                            )
                        )
                    else:
                        logger.error(f"Failed to initialize streaming message for selected AI {moderator_selected_ai_id}")
                else:
                    logger.warning(f"Selected AI ID {moderator_selected_ai_id} not found in database")
            elif is_moderator:
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

            # Always try to release the thread lock even on error
            try:
                self._release_thread_lock(thread_id, ai_id)
                logger.info(f"Released thread lock for thread {thread_id} after error")
            except Exception as lock_error:
                logger.error(f"Failed to release thread lock for thread {thread_id} on error: {lock_error}")
