# supabase_client.py
import os
from supabase import create_client, Client
from typing import Optional, Dict, Any, List
import logging
from datetime import datetime
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

logger = logging.getLogger(__name__)

class SupabaseClient:
    def __init__(self):
        """Inicializar cliente Supabase"""
        self.url = os.getenv("SUPABASE_URL")
        self.anon_key = os.getenv("SUPABASE_ANON_KEY") 
        self.service_key = os.getenv("SUPABASE_SERVICE_KEY")
        
        if not self.url:
            raise ValueError("SUPABASE_URL não configurada")
        if not self.anon_key:
            raise ValueError("SUPABASE_ANON_KEY não configurada")
        if not self.service_key:
            raise ValueError("SUPABASE_SERVICE_KEY não configurada")
        
        try:
            # Cliente para operações normais (com RLS)
            self.client: Client = create_client(self.url, self.anon_key)
            
            # Cliente administrativo (bypassa RLS quando necessário) 
            self.admin_client: Client = create_client(self.url, self.service_key)
            
            logger.info("Cliente Supabase inicializado com sucesso")
            
        except Exception as e:
            logger.error(f"Erro ao inicializar Supabase: {str(e)}")
            raise ValueError(f"Erro ao conectar com Supabase: {str(e)}")
    
    # === MÉTODOS DE AUTENTICAÇÃO (SIMPLIFICADOS) ===
    def sign_up_user(self, email: str, password: str, user_metadata: Dict[str, Any] = None):
        """Criar novo usuário - usando método correto"""
        try:
            response = self.client.auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "data": user_metadata or {}
                }
            })
            
            if hasattr(response, 'user') and response.user:
                logger.info(f"Usuário criado: {email}")
                return response
            else:
                raise Exception("Falha ao criar usuário")
                
        except Exception as e:
            logger.error(f"Erro ao criar usuário {email}: {str(e)}")
            raise
    
    def sign_in_user(self, email: str, password: str):
        """Login do usuário - usando método correto"""
        try:
            response = self.client.auth.sign_in_with_password({
                "email": email, 
                "password": password
            })
            
            if hasattr(response, 'session') and response.session:
                logger.info(f"Login realizado: {email}")
                return response
            else:
                raise Exception("Credenciais inválidas")
                
        except Exception as e:
            logger.error(f"Erro no login {email}: {str(e)}")
            raise
    
    def get_current_user(self):
        """Obter usuário atual"""
        try:
            response = self.client.auth.get_user()
            return response
        except Exception as e:
            logger.error(f"Erro ao obter usuário: {str(e)}")
            raise
    
    def sign_out_user(self):
        """Logout"""
        try:
            response = self.client.auth.sign_out()
            logger.info("Logout realizado")
            return response
        except Exception as e:
            logger.error(f"Erro no logout: {str(e)}")
            raise
    
    # === MÉTODOS DE DADOS ===
    def get_table(self, table_name: str, admin: bool = False):
        """Obter referência para tabela"""
        client = self.admin_client if admin else self.client
        return client.table(table_name)
    
    # === MÉTODOS AUXILIARES ===
    def create_user_profile(self, user_id: str, nome: str, email: str, cargo: str = 'operador'):
        """Criar perfil de usuário na tabela usuarios"""
        try:
            result = self.admin_client.table("usuarios").insert({
                "id": user_id,
                "nome": nome,
                "email": email,
                "cargo": cargo,
                "ativo": True,
                "created_at": datetime.now().isoformat()
            }).execute()
            
            logger.info(f"Perfil criado para usuário: {email}")
            return result.data[0] if result.data else None
            
        except Exception as e:
            logger.error(f"Erro ao criar perfil {email}: {str(e)}")
            raise
    
    def log_action(self, usuario_id: str, acao: str, tabela: str, 
                   registro_id: str = None, dados_antes: dict = None, 
                   dados_depois: dict = None):
        """Registrar ação no log de auditoria"""
        try:
            self.admin_client.table("audit_logs").insert({
                "usuario_id": usuario_id,
                "acao": acao,
                "tabela": tabela,
                "registro_id": registro_id,
                "dados_antes": dados_antes,
                "dados_depois": dados_depois,
                "created_at": datetime.now().isoformat()
            }).execute()
            
        except Exception as e:
            logger.warning(f"Erro ao registrar log: {str(e)}")
            # Não fazer raise para não quebrar a operação principal

    # === MÉTODO DE TESTE ===
    def test_connection(self):
        """Testar conexão com o banco"""
        try:
            # Teste simples - tentar contar registros de uma tabela
            result = self.admin_client.table("usuarios").select("id", count="exact").limit(1).execute()
            logger.info("Conexão com Supabase testada com sucesso")
            return True
        except Exception as e:
            logger.error(f"Erro ao testar conexão: {str(e)}")
            return False