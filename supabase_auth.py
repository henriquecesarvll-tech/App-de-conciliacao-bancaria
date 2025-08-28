# auth.py
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, List
import jwt
import os
from supabase_models import CargoEnum, UsuarioResponse
from supabase_client import SupabaseClient
import logging

# Instância global do cliente
_supabase_client = None

def get_supabase_client():
    """Obter instância do cliente Supabase"""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = SupabaseClient()
    return _supabase_client

logger = logging.getLogger(__name__)

# Security scheme
security = HTTPBearer(auto_error=False)

class AuthenticationError(HTTPException):
    def __init__(self, detail: str = "Não autenticado"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

class AuthorizationError(HTTPException):
    def __init__(self, detail: str = "Acesso negado"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    """Middleware para verificar autenticação"""
    
    if not credentials:
        raise AuthenticationError("Token de acesso necessário")
    
    try:
        token = credentials.credentials
        
        # Decodificar token JWT (Supabase já verificou a assinatura)
        payload = jwt.decode(
            token, 
            options={
                "verify_signature": False,  # Supabase já verificou
                "verify_exp": True,        # Verificar expiração
                "verify_aud": False        # Não verificar audience
            }
        )
        
        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationError("Token inválido: sem user ID")
        
        # Configurar auth no cliente Supabase
        get_supabase_client().set_auth(token)
        
        # Buscar dados completos do usuário
        result = get_supabase_client().get_table("usuarios").select("""
            id, nome, email, cargo, ativo, created_at
        """).eq("id", user_id).execute()
        
        if not result.data:
            raise AuthenticationError("Usuário não encontrado")
        
        user = result.data[0]
        
        # Verificar se usuário está ativo
        if not user.get("ativo", True):
            raise AuthenticationError("Usuário inativo")
        
        # Adicionar token aos dados do usuário para uso posterior
        user["access_token"] = token
        
        logger.debug(f"Usuário autenticado: {user['email']} ({user['cargo']})")
        return user
        
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token expirado")
    except jwt.PyJWTError as e:
        logger.warning(f"Erro JWT: {str(e)}")
        raise AuthenticationError("Token inválido")
    except Exception as e:
        logger.error(f"Erro na autenticação: {str(e)}")
        raise AuthenticationError("Erro interno de autenticação")

async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[dict]:
    """Obter usuário se autenticado (opcional)"""
    try:
        if credentials:
            return await get_current_user(credentials)
        return None
    except:
        return None

def require_cargo(required_cargos: List[CargoEnum]):
    """Decorator para verificar cargo do usuário"""
    def dependency(user: dict = Depends(get_current_user)) -> dict:
        user_cargo = user.get("cargo")
        
        if user_cargo not in [cargo.value for cargo in required_cargos]:
            logger.warning(f"Acesso negado para {user['email']}: cargo {user_cargo} insuficiente")
            raise AuthorizationError(
                f"Acesso negado. Cargo necessário: {', '.join([c.value for c in required_cargos])}"
            )
        
        return user
    
    return dependency

# Shortcuts para diferentes níveis de acesso
require_admin = require_cargo([CargoEnum.ADMIN])
require_supervisor = require_cargo([CargoEnum.SUPERVISOR, CargoEnum.ADMIN])
require_operador = require_cargo([CargoEnum.OPERADOR, CargoEnum.SUPERVISOR, CargoEnum.ADMIN])

# Alias para compatibilidade
require_authenticated = get_current_user

async def log_user_action(user: dict, acao: str, tabela: str, 
                         registro_id: str = None, dados_antes: dict = None, 
                         dados_depois: dict = None):
    """Registrar ação do usuário para auditoria"""
    try:
        await get_supabase_client().log_action(
            usuario_id=user["id"],
            acao=acao,
            tabela=tabela,
            registro_id=registro_id,
            dados_antes=dados_antes,
            dados_depois=dados_depois
        )
    except Exception as e:
        logger.warning(f"Erro ao registrar log: {str(e)}")

# Utilitário para verificar permissões específicas
def can_modify_configurations(user: dict) -> bool:
    """Verificar se usuário pode modificar configurações"""
    return user.get("cargo") in ["supervisor", "admin"]

def can_view_audit_logs(user: dict) -> bool:
    """Verificar se usuário pode ver logs de auditoria"""
    return user.get("cargo") == "admin"

def can_manage_users(user: dict) -> bool:
    """Verificar se usuário pode gerenciar outros usuários"""
    return user.get("cargo") in ["supervisor", "admin"]