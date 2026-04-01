from supabase import Client, create_client

from app.core.settings import settings


def get_service_client() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)

