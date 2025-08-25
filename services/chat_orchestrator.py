from langchain.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema.runnable import RunnablePassthrough
from typing import AsyncGenerator
from supabase.client import Client as SupabaseClient

from core.supabase_client import supabase_client
from core.config import settings

class ChatOrchestrator:
    def __init__(self, db_client: SupabaseClient):
        self.db_client = db_client
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash", # 3. Chọn model phù hợp (ví dụ: gemini-2.5-pro)
            temperature=0.7,
            # streaming=True là mặc định, không cần thiết phải ghi rõ
            google_api_key=settings.google_api_key
        )

    async def _get_mentor_persona(self, mentor_id: str) -> str:
        # Lấy thông tin mentor trực tiếp từ Supabase
        response = await self.db_client.from_('mentors').select('*').eq('id', mentor_id).single().execute()
        return response.data['persona']

    async def _get_chat_history(self, user_id: str, mentor_id: str) -> str:
        # Lấy lịch sử trò chuyện gần nhất từ Supabase
        response = await self.db_client.from_('chat_history').select('message, sender').eq('user_id', user_id).eq('mentor_id', mentor_id).order('timestamp', desc=True).limit(10).execute()
        
        # Format lịch sử để đưa vào prompt
        history_str = ""
        for record in reversed(response.data):
            sender = "User" if record['sender'] == 'user' else "Mentor"
            history_str += f"{sender}: {record['message']}\n"
        return history_str

    async def stream_response(self, user_id: str, mentor_id: str, prompt: str) -> AsyncGenerator[str, None]:
        # Bước 1: Lấy dữ liệu cần thiết từ DB
        mentor_persona = await self._get_mentor_persona(mentor_id)
        chat_history = await self._get_chat_history(user_id, mentor_id)
        
        # Bước 2: Xây dựng Master Prompt với LangChain
        template = """
        {mentor_persona}
        
        Lịch sử trò chuyện:
        {chat_history}
        
        User: {user_prompt}
        Mentor:"""
        
        full_prompt = PromptTemplate.from_template(template)
        
        # Bước 3: Chuẩn bị chain để streaming
        chain = (
            RunnablePassthrough() | full_prompt | self.llm
        )
        
        # Bước 4: Gọi LLM và streaming kết quả
        inputs = {
            "mentor_persona": mentor_persona,
            "chat_history": chat_history,
            "user_prompt": prompt
        }

        async for chunk in chain.astream(inputs):
            yield chunk.content