import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv # Thêm dòng này

# Tải các biến môi trường từ file .env
load_dotenv()

class Settings(BaseSettings):
    supabase_url: str = os.getenv("SUPABASE_URL")
    supabase_key: str = os.getenv("SUPABASE_KEY")
    google_api_key: str = os.getenv("GOOGLE_API_KEY")

settings = Settings()