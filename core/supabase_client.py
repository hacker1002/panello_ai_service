import supabase

from config import settings

def get_supabase_client():
    return supabase.create_client(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_key
    )

supabase_client = get_supabase_client()