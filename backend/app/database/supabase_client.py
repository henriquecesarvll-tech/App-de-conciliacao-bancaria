from supabase import create_client, Client
from config.settings import get_settings
import logging

logger = logging.getLogger(__name__)

class SupabaseClient:
    def __init__(self):
        settings = get_settings()
        self.url = settings.SUPABASE_URL
        self.key = settings.SUPABASE_SERVICE_KEY
        self.admin_client: Client = None
        
    def connect(self):
        try:
            self.admin_client = create_client(self.url, self.key)
            logger.info("✅ Supabase conectado")
            return True
        except Exception as e:
            logger.error(f"❌ Erro Supabase: {e}")
            return False

supabase_client = SupabaseClient()

def init_supabase():
    supabase_client.connect()

def get_supabase() -> SupabaseClient:
    return supabase_client
