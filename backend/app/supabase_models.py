# models.py
from pydantic import BaseModel, EmailStr, validator
from typing import Optional, List
from datetime import datetime, date
from enum import Enum
import uuid

# === ENUMS ===
class CargoEnum(str, Enum):
    OPERADOR = "operador"
    SUPERVISOR = "supervisor"
    ADMIN = "admin"

class StatusTransacaoEnum(str, Enum):
    PENDENTE = "PENDENTE"
    CONCILIADO = "CONCILIADO"

class BancoEnum(str, Enum):
    AAI = "AAI"
    EDUCACAO = "EDUCAÇÃO"

# === MODELOS BASE ===
class BaseResponse(BaseModel):
    success: bool = True
    message: Optional[str] = None

# === MODELOS DE USUÁRIO ===
class UsuarioCreate(BaseModel):
    nome: str
    email: EmailStr
    cargo: CargoEnum = CargoEnum.OPERADOR
    password: str
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError('Senha deve ter pelo menos 6 caracteres')
        return v

class UsuarioUpdate(BaseModel):
    nome: Optional[str] = None
    cargo: Optional[CargoEnum] = None
    ativo: Optional[bool] = None

class UsuarioResponse(BaseModel):
    id: str
    nome: str
    email: str
    cargo: CargoEnum
    ativo: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    user: UsuarioResponse

# === MODELOS DE CONFIGURAÇÃO ===
class ClassificacaoCreate(BaseModel):
    nome: str
    descricao: Optional[str] = None

class ClassificacaoUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    ativo: Optional[bool] = None

class ClassificacaoResponse(BaseModel):
    id: str
    nome: str
    descricao: Optional[str]
    ativo: bool
    created_at: datetime
    planos_count: Optional[int] = 0
    
    class Config:
        from_attributes = True

class PlanoContasCreate(BaseModel):
    classificacao_id: str
    nome: str
    descricao: Optional[str] = None

class PlanoContasUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    ativo: Optional[bool] = None

class PlanoContasResponse(BaseModel):
    id: str
    classificacao_id: str
    nome: str
    descricao: Optional[str]
    ativo: bool
    created_at: datetime
    classificacao_nome: str
    itens_count: Optional[int] = 0
    
    class Config:
        from_attributes = True

class ItemCreate(BaseModel):
    plano_contas_id: str
    nome: str
    descricao: Optional[str] = None

class ItemUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    ativo: Optional[bool] = None

class ItemResponse(BaseModel):
    id: str
    plano_contas_id: str
    nome: str
    descricao: Optional[str]
    ativo: bool
    created_at: datetime
    classificacao_nome: str
    plano_contas_nome: str
    
    class Config:
        from_attributes = True

# === MODELOS DE TRANSAÇÕES ===
class TransacaoCreate(BaseModel):
    banco: BancoEnum
    data: date
    historico: str
    documento: Optional[str] = None
    valor: float
    saldo: Optional[float] = None
    tipo_transacao: Optional[str] = None
    extrato_id: Optional[str] = None

class ConciliacaoRequest(BaseModel):
    transacao_id: str
    classificacao_id: str
    plano_contas_id: str
    item_id: str
    forma_pagamento: Optional[str] = None
    centro_custo: Optional[str] = None
    nome_recebedor: Optional[str] = None
    contraparte: Optional[str] = None
    data_pagamento: Optional[date] = None
    data_referencia: Optional[date] = None
    observacoes: Optional[str] = None

class TransacaoResponse(BaseModel):
    id: str
    banco: BancoEnum
    data: date
    historico: str
    documento: Optional[str]
    valor: float
    saldo: Optional[float]
    tipo_transacao: Optional[str]
    status: StatusTransacaoEnum
    
    # Dados de conciliação
    classificacao_id: Optional[str]
    classificacao_nome: Optional[str]
    plano_contas_id: Optional[str]
    plano_contas_nome: Optional[str]
    item_id: Optional[str]
    item_nome: Optional[str]
    
    forma_pagamento: Optional[str]
    centro_custo: Optional[str]
    nome_recebedor: Optional[str]
    contraparte: Optional[str]
    data_pagamento: Optional[date]
    data_referencia: Optional[date]
    observacoes: Optional[str]
    
    # Auditoria
    conciliado_por_nome: Optional[str]
    conciliado_em: Optional[datetime]
    created_at: datetime
    
    class Config:
        from_attributes = True

class ExtracaoResponse(BaseModel):
    id: str
    banco: BancoEnum
    arquivo_nome: str
    total_transacoes: int
    status: str
    uploaded_by_nome: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True

# === MODELOS DE ESTATÍSTICAS ===
class StatisticsResponse(BaseModel):
    total_transacoes: int
    pendentes: int
    conciliados: int
    valor_total: float
    percentual_conciliado: float
    transacoes_por_banco: dict
    valor_por_banco: dict

# === MODELOS DE FILTROS ===
class TransacaoFilter(BaseModel):
    status: Optional[StatusTransacaoEnum] = None
    banco: Optional[BancoEnum] = None
    data_inicio: Optional[date] = None
    data_fim: Optional[date] = None
    classificacao_id: Optional[str] = None
    busca: Optional[str] = None
    limite: int = 100
    offset: int = 0

# === MODELOS DE RESPOSTA ===
class ListResponse(BaseModel):
    data: List[dict]
    total: int
    offset: int
    limite: int
    has_more: bool

class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    details: Optional[dict] = None
