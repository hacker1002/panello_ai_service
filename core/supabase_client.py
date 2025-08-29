import supabase

from core.config import settings

def get_supabase_client():
    # Use service role key to bypass RLS for server-side operations
    # Make sure you have SUPABASE_SERVICE_KEY in your .env file
    return supabase.create_client(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_service_key if hasattr(settings, 'supabase_service_key') else settings.supabase_key
    )

supabase_client = get_supabase_client()