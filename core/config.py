import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv # Thêm dòng này

# Tải các biến môi trường từ file .env
load_dotenv()

class Settings(BaseSettings):
    supabase_url: str = os.getenv("SUPABASE_URL")
    supabase_key: str = os.getenv("SUPABASE_KEY")
    supabase_service_key: str = os.getenv("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_KEY"))  # Falls back to anon key if service key not provided
    google_api_key: str = os.getenv("GOOGLE_API_KEY")

settings = Settings()