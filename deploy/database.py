from supabase import create_client, Client
from .config import settings, validate_config
from loguru import logger
import os

# Cliente Supabase global
supabase: Client = None
supabase_admin: Client = None

def init_supabase():
    """Inicializar cliente Supabase"""
    global supabase, supabase_admin
    
    try:
        # Validar configurações
        validate_config()
        
        # Criar cliente normal (com anon key)
        supabase = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_ANON_KEY
        )
        
        # Criar cliente admin (com service key) - opcional
        if settings.SUPABASE_SERVICE_KEY:
            supabase_admin = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_SERVICE_KEY
            )
        
        # Testar conexão
        result = supabase.table('companies').select('id').limit(1).execute()
        logger.info("✅ Conexão com Supabase estabelecida")
        
        return supabase
        
    except Exception as e:
        logger.error(f"❌ Erro ao conectar com Supabase: {e}")
        logger.warning("⚠️ Continuando sem conexão total com Supabase")
        return None

def get_supabase() -> Client:
    """Obter cliente Supabase normal"""
    if not supabase:
        init_supabase()
    return supabase

def get_supabase_admin() -> Client:
    """Obter cliente Supabase com permissões de administrador"""
    if not supabase_admin and settings.SUPABASE_SERVICE_KEY:
        init_supabase()
    return supabase_admin

# Classe helper para operações básicas
class SupabaseTable:
    def __init__(self, table_name: str, admin: bool = False):
        self.table_name = table_name
        self.client = get_supabase_admin() if admin else get_supabase()
    
    def select_all(self, limit: int = 100):
        """Buscar todos os registros"""
        try:
            if not self.client:
                logger.warning("Cliente Supabase não disponível")
                return []
            result = self.client.table(self.table_name).select('*').limit(limit).execute()
            return result.data
        except Exception as e:
            logger.error(f"Erro ao buscar {self.table_name}: {e}")
            return []
    
    def insert(self, data: dict):
        """Inserir registro"""
        try:
            if not self.client:
                logger.warning("Cliente Supabase não disponível")
                return None
            result = self.client.table(self.table_name).insert(data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Erro ao inserir em {self.table_name}: {e}")
            return None
    
    def update(self, id: str, data: dict):
        """Atualizar registro"""
        try:
            if not self.client:
                logger.warning("Cliente Supabase não disponível")
                return None
            result = self.client.table(self.table_name).update(data).eq('id', id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Erro ao atualizar {self.table_name}: {e}")
            return None
    
    def delete(self, id: str):
        """Deletar registro"""
        try:
            if not self.client:
                logger.warning("Cliente Supabase não disponível")
                return False
            result = self.client.table(self.table_name).delete().eq('id', id).execute()
            return True
        except Exception as e:
            logger.error(f"Erro ao deletar em {self.table_name}: {e}")
            return False