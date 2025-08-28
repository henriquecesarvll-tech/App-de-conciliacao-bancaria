from fastapi import FastAPI, HTTPException, UploadFile, Depends, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    pd = None
from cache_service import cache
import io
import uuid
import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
load_dotenv()

from supabase_client import SupabaseClient
from supabase_auth import get_current_user, require_operador, require_supervisor, require_admin
from supabase_models import LoginRequest, LoginResponse, UsuarioResponse

from loguru import logger

from passlib.context import CryptContext

# ⭐ ADICIONAR ESTAS LINHAS PARA RATE LIMITING:
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import time
from typing import Dict, Any, Optional


# Após as importações, adicionar:
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-key-123")

# Configuração condicional
if ENVIRONMENT == "production":
    # Logs menos verbosos
    import logging
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# Configurar context para hash de senhas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Criar hash da senha"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verificar senha contra hash"""
    return pwd_context.verify(plain_password, hashed_password)

# Configurar logs
os.makedirs("logs", exist_ok=True)
logger.add("logs/app.log", rotation="1 day", level="INFO")

# Criar app FastAPI
app = FastAPI(
    title="Sistema de Conciliação Bancária",
    description="Upload e processamento de extratos AAI e EDUCA",
    version="2.0.0"
)
# Instanciar cliente Supabase
try:
    supabase = SupabaseClient()
    # Testar a conexão
    if supabase.test_connection():
        print("✅ Supabase conectado com sucesso!")
    else:
        print("⚠️ Supabase inicializado mas conexão com problema")
        supabase = None
except Exception as e:
    print(f"❌ Erro ao conectar Supabase: {e}")
    supabase = None 

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://sistema-conciliacao-bancaria-production.up.railway.app",
        "https://*.railway.app",  # Para outros ambientes Railway
        "http://localhost:8000",  # Para desenvolvimento local
        "http://127.0.0.1:8000",  # Para desenvolvimento local
        "http://localhost:3000",  # Caso tenha frontend separado
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],  # Específico em vez de "*"
    allow_headers=["*"],  # Pode manter assim para facilitar
)

@app.middleware("http")
async def error_handler(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        # Verificar se está em produção
        environment = os.getenv("ENVIRONMENT", "development")
        
        if environment == "production":
            # Em produção, não expor detalhes
            logger.error(f"Erro não tratado: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={"detail": "Erro interno do servidor"}
            )
        else:
            # Em desenvolvimento, mostrar erro completo
            logger.error(f"Erro detalhado: {str(e)}")
            raise e

# ⭐ ADICIONAR TAMBÉM - CONFIGURAÇÃO DE RATE LIMITING:
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Classificações hierárquicas expandidas
classificacoes = {
    'CUSTOS AAI': {
        'Advogados': ['Veritas'],
        'E-mail 360': ['BHS AXTER'],
        'Gravador de voz': ['Link Solution'],
        'Relatórios': ['BDM', 'IR', 'IR TRADE', 'Lemit', 'OPLAB', 'Quantum'],
        'Taxa fiscalização CVM': ['0'],
        'Treinamento Assessores': ['Prova FEBRABAN']
    },
    'DESPESA COM MARKETING': {
        'Agência de Mktg': ['0'],
        'Almoço com clientes': ['Clientes Daniel', 'Clientes Leandro'],
        'Associação Comercial': ['ACIP'],
        'Brindes Assessores': ['Thera Day'],
        'Brindes Clientes': ['Cliente Unimed'],
        'Cartões de Visita': ['0'],
        'Eventos': ['Bar', 'Bônus HH', 'Buffet', 'Caixas', 'Camisetas Beacth', 'Champanheira', 'Evento Silvia', 'Fisio', 'Garçom', 'Hotel Rafi', 'Manobrista', 'Mesas', 'Mesas e taças', 'Mulheres / Taças /Toalhas', 'Musico', 'Play Tennis / Promoter', 'Projetor', 'Promoter', 'Queijos', 'Som', 'Sorvete', 'Toalhas beach tennis', 'Utensilíos', 'Vinhos'],
        'Eventos Interno Thera': ['Camisetas', 'Camisetas Thera Day', 'Fotográfo', 'Som', 'Thera Day - Chopp', 'Thera Day - Iphone', 'Thera Day - Notebook', 'Thera Day - Placas', 'Thera Day - Projetor', 'Thera Day - Relógio', 'Van Campinas', 'Van RP', 'Vila Dei Colori'],
        'Facebook Ads': ['0'],
        'Google Ads': ['0'],
        'Materiais Institucionais': ['Brochuras'],
        'Outras Despesas Mktg': ['Campanha Patrocinada', 'Lembrança dia das mães'],
        'Patrocínios': ['Ajuda Unimed', 'Alphaville', 'Araraquarense', 'Associação Comercial', 'Fundesport', 'Play Tennis'],
        'Site e E-mail Mktg': ['0']
    },
    'DESPESA COM RH': {
        'Assessor Comercial': ['Bonificação - CFA - 2s.2024', 'Bonificação CFA - Panthera - 2s.2024', 'Bônus', 'Bônus ', 'Bônus Cluster A', 'Bônus Cluster B', 'Fixo', 'Gestor', 'Piso', 'Variável'],
        'Assessor de Produtos': ['Bonificação - CFA - 2s.2024', 'Bônus', 'Bônus ', 'Fixo', 'Variável'],
        'Assistente Operacional': ['Bonificação - CFA - 2s.2024', 'Bônus', 'Fixo', 'Reembolso - Prova Ancord', 'Variável'],
        'CLTs': ['Férias', 'Recisão', 'Salário', 'Vale alimentação', 'Vale Transporte'],
        'Diretores': ['Bonificação - CFA - 2s.2024', 'Fixo'],
        'Operador de Mesa': ['Bonificação - CFA - 2s.2024', 'Variável'],
        'Plano de Saúde': ['Bradesco', 'CLT\'s', 'José Rafael e Thiago Menezes', 'Luiz Toloi (Unimed)', 'Variável', 'Livia Benassi', 'Parceiro Pedro (Willian Nascimento)']
    },
    'DESPESAS FINANCEIRAS': {
        'Imposto Retroativo': ['0'],
        'Outros Valores': ['Patrick', 'Thiago Menezes','0']
    },
    'DESPESAS OPERACIONAIS': {
        'Aluguel': ['Arenco', 'IPTU', 'Nova Camp', 'Pereira Alvim', 'Ribeirão Imóveis'],
        'Cartuchos': ['0'],
        'Condomínio': ['0'],
        'Conta de água': ['0'],
        'Contabilidade': ['Audiplan', 'Certificação Digital'],
        'Emissor de notas': ['Site Notas'],
        'CPFL / Energia': ['0'],
        'Estacionamento': ['0'],
        'Faxineira': ['Jeni', 'Maria Brasileira', 'Nil'],
        'Internet': ['Alcans', 'Algar', 'NET', 'Vivo'],
        'Materiais de escritório': ['0', 'Café', 'Computador', 'Fita', 'Fone', 'Lampadas', 'Maquina de café', 'Teclado e Mouse'],
        'Materiais de limpeza': ['0'],
        'Outras Despesas': ['Estorno ', 'Renovação Seguro', 'Seguro Incêndio', 'ZOOM'],
        'Serviços de Manutenção': ['0', 'Chaves', 'Cortina', 'Limpeza Pisos'],
        'Supermercados': ['0'],
        'Tarifas bancárias': ['0', 'Pacote Serviços', 'Tarifa Avulso Pix'],
        'Tecnico Informática': ['0'],
        'Telefone': ['Algar', 'Celulares Claro', 'Directcall', 'DIRECTCALL BRASIL'],
        'Uber': ['0'],
        'Viagens': ['Arthur / 2 Dias XP', 'Bruno Yudi', 'Guilherme Rossetti', 'José Rafael', 'José Rafael (Passagem Aérea)', 'José Rafael e Luiz Toloi (B2B Experience)', 'Lucas Lima', 'Luciano Mudesto']
    },
    'IMPOSTOS': {
        'COFINS': ['0'],
        'CSLL': ['0', '10', '11', '12'],
        'FGTS': ['0'],
        'GPS': ['0'],
        'IRPJ': ['0', '10', '11', '12'],
        'IRPJ ADICIONAL': ['0'],
        'ISS': ['0'],
        'PIS': ['0']
    },
    'RECEITA INVESTIMENTOS': {
        'Asset': ['0'],
        'BM&F': ['0'],
        'Bovespa': ['0'],
        'Bovespa FIIs': ['0'],
        'BTC': ['0'],
        'Campanha Fundos Imobiliários': ['0'],
        'Campanha RV': ['0'],
        'Campanhas': ['0'],
        'Clearthrough': ['COE', 'Renda Fixa', 'RF'],
        'COE': ['0'],
        'Desconto de Transferência de Clientes': ['0'],
        'Enquadramento RLP': ['0'],
        'Erro Operacional': ['0'],
        'Fee Fixo': ['0'],
        'Internacional': ['0'],
        'Oferta RF': ['0'],
        'Outros Valores': ['0'],
        'Produtos Estruturados': ['0'],
        'Renda Fixa': ['0'],
        'Secundário FIIs': ['0']
    },
    'RECEITA OUTROS PRODUTOS': {
        'Câmbio XP': ['0', 'Crédito Reserva'],
        'Campanhas PJ2': ['0'],
        'Câmbio': ['Mercado Internacional'],
        'Previdência': ['Previdência XP'],
        'Conta Global': ['0'],
        'Crédito': ['0', 'FMB4', 'Franq'],
        'Crédito Colaterizado': ['0'],
        'IAXP': ['0'],
        'Mercado Internacional': ['0'],
        'Outras Receitas': ['0'],
        'Previdência - Co-corretagem': ['0'],
        'RV': ['Previdência XP'],
        'Seguro de vida': ['0', 'MetLife', 'Mongeral', 'Previdência', 'Prudential'],
        'Taxa de Performance': ['0']
    }
}

centros_custo = ['Araraquara', 'Campinas', 'Ribeirão Preto', 'Thera Geral']

def detectar_forma_pagamento(historico):
    """Detectar forma de pagamento baseado no histórico"""
    historico_upper = historico.upper()
    
    if 'PIX' in historico_upper:
        return 'PIX'
    elif 'TED' in historico_upper:
        return 'TED'
    elif 'DOC' in historico_upper:
        return 'DOC'
    elif 'DÉBITO AUTOMÁTICO' in historico_upper or 'DEBITO AUTOMATICO' in historico_upper:
        return 'Débito Automático'
    elif 'CARTÃO' in historico_upper or 'CARTAO' in historico_upper:
        return 'Cartão'
    elif 'BOLETO' in historico_upper:
        return 'Boleto'
    elif 'TRANSFERÊNCIA' in historico_upper or 'TRANSFERENCIA' in historico_upper:
        return 'Transferência'
    elif 'DEPÓSITO' in historico_upper or 'DEPOSITO' in historico_upper:
        return 'Depósito'
    elif 'SAQUE' in historico_upper:
        return 'Saque'
    elif 'TARIFA' in historico_upper:
        return 'Tarifa'
    else:
        return 'Outros'

# Modelos Pydantic para validação
class ConciliacaoRequest(BaseModel):
    transacao_id: str
    classificacao: str
    plano_contas: str
    item: str
    forma_pagamento: str
    banco_origem: str
    centro_custo: str
    nome_recebedor: str = ""
    data_pagamento: str
    data_referencia: str = ""
    observacoes: str = ""
    contraparte: str = ""

class ConciliacaoLoteRequest(BaseModel):
    transacao_ids: List[str]

# Modelos para Configurações
class ClassificacaoRequest(BaseModel):
    nome: str
    
class PlanoContasRequest(BaseModel):
    classificacao: str
    nome: str
    
class ItemRequest(BaseModel):
    classificacao: str
    plano_contas: str
    nome: str

class UpdateClassificacaoRequest(BaseModel):
    nome_antigo: str
    nome_novo: str
    
class UpdatePlanoContasRequest(BaseModel):
    classificacao: str
    nome_antigo: str
    nome_novo: str
    
class UpdateItemRequest(BaseModel):
    classificacao: str
    plano_contas: str
    nome_antigo: str
    nome_novo: str    

def processar_valor_moeda(valor_raw):
    """Função para processar valores monetários uniformemente"""
    if isinstance(valor_raw, str):
        # Remove espaços, pontos (milhares) e substitui vírgula por ponto (decimal)
        valor_str = str(valor_raw).strip()
        # Remove símbolos de moeda se existir
        valor_str = valor_str.replace('R$', '').replace('$', '').strip()
        # Remove pontos que são separadores de milhares e substitui vírgula por ponto
        valor_str = valor_str.replace('.', '').replace(',', '.')
        # Remove espaços extras
        valor_str = valor_str.replace(' ', '')
        try:
            return float(valor_str) if valor_str and valor_str != '-' else 0.0
        except ValueError:
            logger.warning(f"Valor inválido encontrado: {valor_raw}")
            return 0.0
    else:
        return float(valor_raw) if pd.notna(valor_raw) else 0.0

def processar_arquivo(file_content: bytes, filename: str, banco: str):
    """Processar arquivo CSV ou Excel e extrair transações"""
    try:
        if not PANDAS_AVAILABLE:
            raise ValueError("Pandas não disponível - funcionalidade de processamento de arquivos limitada")
        
        logger.info(f"Iniciando processamento de {filename} para banco {banco}")
        
        # Detectar tipo de arquivo
        if filename.endswith('.csv'):
            # Processar CSV - aplicar mesma tratativa para ambos os bancos
            logger.info("Processando arquivo CSV...")
            
            # Tentar diferentes codificações
            encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
            df = None
            
            for encoding in encodings:
                try:
                    content_str = file_content.decode(encoding)
                    # Tentar diferentes separadores
                    separadores = [';', ',', '\t']
                    for sep in separadores:
                        try:
                            df = pd.read_csv(
                                io.StringIO(content_str), 
                                sep=sep,
                                encoding=encoding,
                                na_values=['', 'nan', 'NaN', 'null', 'NULL']
                            )
                            if len(df.columns) > 1:  # Se encontrou múltiplas colunas, provavelmente acertou o separador
                                logger.info(f"CSV lido com encoding {encoding} e separador '{sep}'")
                                break
                        except:
                            continue
                    if df is not None and len(df.columns) > 1:
                        break
                except:
                    continue
                    
            if df is None:
                raise ValueError("Não foi possível ler o arquivo CSV com nenhuma codificação testada")
                
        else:
            # Processar Excel - aplicar mesma tratativa para ambos os bancos
            logger.info("Processando arquivo Excel...")
            df = pd.read_excel(
                io.BytesIO(file_content), 
                engine='openpyxl',
                na_values=['', 'nan', 'NaN', 'null', 'NULL']
            )
        
        logger.info(f"Arquivo lido com {len(df)} linhas e colunas: {list(df.columns)}")
        
        # Limpar nomes das colunas (remover espaços extras)
        df.columns = df.columns.str.strip()
        
        # Verificar se tem as colunas necessárias - mesmo critério para ambos os bancos
        colunas_necessarias = ['Data', 'Histórico', 'Valor (R$)']
        colunas_faltando = [col for col in colunas_necessarias if col not in df.columns]
        
        if colunas_faltando:
            logger.warning(f"Colunas obrigatórias não encontradas: {colunas_faltando}")
            logger.info(f"Colunas disponíveis: {list(df.columns)}")
            raise ValueError(f"Colunas obrigatórias não encontradas: {colunas_faltando}")
        
        transacoes = []
        linhas_processadas = 0
        
        for index, row in df.iterrows():
            try:
                # Pular linha de cabeçalho e saldo anterior - mesmo critério para ambos
                if pd.isna(row.get('Data')) or 'SALDO ANTERIOR' in str(row.get('Histórico', '')).upper():
                    continue
                    
                # Extrair dados - mesmo processamento para ambos os bancos
                data = row.get('Data')
                if isinstance(data, pd.Timestamp):
                    data_str = data.strftime('%Y-%m-%d')
                else:
                    data_str = str(data)
                    
                historico = str(row.get('Histórico', '')).strip()
                documento = str(row.get('Documento', '')).strip()
                
                # APLICAR MESMA TRATATIVA DE VALOR PARA AMBOS OS BANCOS
                valor_raw = row.get('Valor (R$)', 0)
                valor = processar_valor_moeda(valor_raw)
                
                # APLICAR MESMA TRATATIVA DE SALDO PARA AMBOS OS BANCOS
                saldo_raw = row.get('Saldo (R$)', 0)
                saldo = processar_valor_moeda(saldo_raw)
                
                # Log para debug - especialmente para EDUCAÇÃO
                if banco == 'EDUCAÇÃO':
                    logger.debug(f"EDUCAÇÃO - Linha {index}: Valor raw='{valor_raw}' -> processado={valor}, Saldo raw='{saldo_raw}' -> processado={saldo}")
                
                # Classificar tipo de transação - mesmo critério para ambos
                tipo_transacao = 'OUTROS'
                historico_upper = historico.upper()
                if 'PIX' in historico_upper:
                    tipo_transacao = 'PIX'
                elif 'TED' in historico_upper:
                    tipo_transacao = 'TED'
                elif 'PAGAMENTO' in historico_upper:
                    tipo_transacao = 'PAGAMENTO'
                elif 'TARIFA' in historico_upper:
                    tipo_transacao = 'TARIFA'
                elif 'DEBITO' in historico_upper or 'DÉBITO' in historico_upper:
                    tipo_transacao = 'DÉBITO'
                elif 'CREDITO' in historico_upper or 'CRÉDITO' in historico_upper:
                    tipo_transacao = 'CRÉDITO'
                
                transacao = {
                    'id': str(uuid.uuid4()),
                    'banco': banco,
                    'data': data_str,
                    'historico': historico,
                    'documento': documento,
                    'valor': valor,
                    'saldo': saldo,
                    'tipo_transacao': tipo_transacao,
                    'status': 'PENDENTE',
                    'classificacao': '',
                    'plano_contas': '',
                    'item': '',
                    'forma_pagamento': detectar_forma_pagamento(historico),  # Autopreenchido
                    'banco_origem': banco,  # Autopreenchido (AAI ou EDUCAÇÃO)
                    'centro_custo': '',
                    'nome_recebedor': '',
                    'data_pagamento': data_str,  # Autopreenchido com data do extrato
                    'data_referencia': '',
                    'observacoes': '',
                    'conciliado_em': None,
                    'conciliado_por': None,
                    'created_at': datetime.now().isoformat(),
                    'contraparte': detectar_contraparte_backend(historico)  # NOVO CAMPO ADICIONADO
                }
                
                transacoes.append(transacao)
                linhas_processadas += 1
                
            except Exception as e:
                logger.warning(f"Erro ao processar linha {index}: {e}")
                continue
        
        logger.info(f"Processamento concluído para {banco}: {linhas_processadas} transações de {len(df)} linhas")
        return transacoes
        
    except Exception as e:
        logger.error(f"ERRO CRÍTICO ao processar arquivo {banco}: {e}")
        logger.error(f"Tipo do erro: {type(e)}")
        import traceback
        logger.error(f"Traceback completo: {traceback.format_exc()}")
        raise ValueError(f"Erro ao processar arquivo: {str(e)}")

def detectar_contraparte_backend(historico):
    """Detectar contraparte baseado no histórico"""
    if not historico:
        return 'Não identificado'
    
    historico = historico.upper()
    
    # Padrões comuns de contrapartes
    padroes = [
        ('PAGSEGURO', 'PagSeguro'),
        ('MERCADO PAGO', 'Mercado Pago'),
        ('IFood', 'iFood'),
        ('UBER', 'Uber'),
        ('99', '99 Taxi'),
        ('TÁXI', 'Taxi'),
        ('POSTO', 'Posto de Combustível'),
        ('DROGARIA', 'Drogaria'),
        ('FARMÁCIA', 'Farmácia'),
        ('SUPERMERCADO', 'Supermercado'),
        ('RESTAURANTE', 'Restaurante'),
        ('HOSPITAL', 'Hospital'),
        ('CLÍNICA', 'Clínica'),
        ('ESCOLA', 'Escola'),
        ('UNIVERSIDADE', 'Universidade'),
        ('ALUGUEL', 'Proprietário'),
        ('CONDOMINIO', 'Síndico'),
        ('IPTU', 'Prefeitura'),
        ('IPVA', 'Governo Estadual'),
        ('ENERGIA', 'Companhia Energética'),
        ('ÁGUA', 'Companhia de Água'),
        ('TELEFONE', 'Operadora Telefônica'),
        ('INTERNET', 'Provedor Internet'),
        ('NETFLIX', 'Netflix'),
        ('SPOTIFY', 'Spotify'),
        ('AMAZON', 'Amazon'),
        ('GOOGLE', 'Google'),
        ('FACEBOOK', 'Facebook'),
        ('INSTAGRAM', 'Instagram'),
        ('IFOOD', 'iFood'),
        ('RAKUTEN', 'Rakuten'),
        ('PICPAY', 'PicPay'),
        ('NUBANK', 'Nubank'),
        ('ITAU', 'Itaú'),
        ('BRADESCO', 'Bradesco'),
        ('SANTANDER', 'Santander'),
        ('BB', 'Banco do Brasil'),
        ('CAIXA', 'Caixa Econômica'),
        ('BANCO', 'Banco'),
        ('SALÁRIO', 'Empregador'),
        ('FGTS', 'Governo'),
        ('INSS', 'Governo'),
        ('IRPF', 'Receita Federal'),
        ('PIX', 'Transferência PIX'),
        ('TED', 'Transferência TED'),
        ('DOC', 'Transferência DOC'),
        ('BOLETO', 'Cobrança Boleto')
    ]
    
    for padrao, contraparte in padroes:
        if padrao in historico:
            return contraparte
    
    # Tentar identificar CPF/CNPJ no histórico
    import re
    cpf_cnpj = re.search(r'(\d{3}\.?\d{3}\.?\d{3}-?\d{2}|\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})', historico)
    if cpf_cnpj:
        return f"CPF/CNPJ: {cpf_cnpj.group(0)}"
    
    # Se não encontrou nenhum padrão específico
    partes = historico.split()
    if len(partes) > 3:
        return ' '.join(partes[:3]) + '...'
    
    return historico if historico else 'Não identificado'

@app.on_event("startup")
async def startup():
    """Inicializar aplicação"""
    logger.info("🚀 Iniciando Sistema de Conciliação Bancária...")
    
    # Pré-carrega lookups no cache
    await carregar_lookups_cache()
    
    logger.info("✅ Sistema iniciado com sucesso!")

@app.get("/")
async def root():
    """Página inicial"""
    html_content = r"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Sistema de Conciliação Bancária</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {
                /* Design System - Colors */
                --primary-50: #eff6ff;
                --primary-100: #dbeafe;
                --primary-500: #3b82f6;
                --primary-600: #2563eb;
                --primary-700: #1d4ed8;
                --primary-900: #1e3a8a;
                
                --success-50: #f0fdf4;
                --success-100: #dcfce7;
                --success-500: #22c55e;
                --success-600: #16a34a;
                
                --warning-50: #fffbeb;
                --warning-100: #fef3c7;
                --warning-500: #f59e0b;
                --warning-600: #d97706;
                
                --danger-50: #fef2f2;
                --danger-500: #ef4444;
                --danger-600: #dc2626;
                
                --gray-50: #f9fafb;
                --gray-100: #f3f4f6;
                --gray-200: #e5e7eb;
                --gray-300: #d1d5db;
                --gray-400: #9ca3af;
                --gray-500: #6b7280;
                --gray-600: #4b5563;
                --gray-700: #374151;
                --gray-800: #1f2937;
                --gray-900: #111827;
                
                /* Spacing */
                --space-1: 0.25rem;
                --space-2: 0.5rem;
                --space-3: 0.75rem;
                --space-4: 1rem;
                --space-5: 1.25rem;
                --space-6: 1.5rem;
                --space-8: 2rem;
                --space-10: 2.5rem;
                --space-12: 3rem;
                --space-16: 4rem;
                
                /* Border Radius */
                --radius-sm: 0.375rem;
                --radius-md: 0.5rem;
                --radius-lg: 0.75rem;
                --radius-xl: 1rem;
                --radius-2xl: 1.5rem;
                
                /* Shadows */
                --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
                --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
                --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
                --shadow-xl: 0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1);
            }
            
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, var(--primary-50) 0%, var(--primary-100) 100%);
                min-height: 100vh;
                color: var(--gray-900);
                line-height: 1.6;
            }
            
            .container {
                max-width: 1280px;
                margin: 0 auto;
                padding: var(--space-6);
            }
            
            /* Header */
            .header {
                background: white;
                border-radius: var(--radius-2xl);
                padding: var(--space-10);
                margin-bottom: var(--space-8);
                box-shadow: var(--shadow-lg);
                text-align: center;
                border: 1px solid var(--gray-100);
            }
            
            .header h1 {
                font-size: 2.5rem;
                font-weight: 700;
                color: var(--gray-900);
                margin-bottom: var(--space-4);
                letter-spacing: -0.025em;
            }
            
            .header p {
                font-size: 1.125rem;
                color: var(--gray-600);
                font-weight: 400;
            }
            
            /* Navigation */
            .nav-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: var(--space-4);
                margin-bottom: var(--space-8);
            }
            
            .nav-card {
                background: white;
                border: 1px solid var(--gray-200);
                border-radius: var(--radius-xl);
                padding: var(--space-5);
                text-decoration: none;
                color: var(--gray-700);
                transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
                box-shadow: var(--shadow-sm);
                display: flex;
                align-items: center;
                gap: var(--space-3);
                font-weight: 500;
            }
            
            .nav-card:hover {
                transform: translateY(-2px);
                box-shadow: var(--shadow-md);
                border-color: var(--primary-200);
                color: var(--primary-700);
            }
            
            .nav-card .icon {
                font-size: 1.25rem;
                min-width: 24px;
            }
            
            /* Main Content Grid */
            .main-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
                gap: var(--space-8);
                margin-bottom: var(--space-8);
            }
            
            /* Cards */
            .card {
                background: white;
                border-radius: var(--radius-2xl);
                padding: var(--space-8);
                box-shadow: var(--shadow-lg);
                border: 1px solid var(--gray-100);
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            }
            
            .card:hover {
                transform: translateY(-4px);
                box-shadow: var(--shadow-xl);
            }
            
            .card h3 {
                font-size: 1.5rem;
                font-weight: 600;
                color: var(--gray-900);
                margin-bottom: var(--space-6);
                display: flex;
                align-items: center;
                gap: var(--space-3);
            }
            
            /* Upload Area */
            .upload-area {
                border: 2px dashed var(--primary-300);
                background: var(--primary-50);
                border-radius: var(--radius-xl);
                padding: var(--space-8);
                text-align: center;
                margin: var(--space-6) 0;
                transition: all 0.2s ease;
            }
            
            .upload-area:hover {
                border-color: var(--primary-500);
                background: var(--primary-100);
            }
            
            .upload-area p {
                font-weight: 600;
                color: var(--gray-700);
                margin-bottom: var(--space-4);
            }
            
            .upload-area input[type="file"] {
                margin: var(--space-4) 0;
                padding: var(--space-3);
                border: 1px solid var(--gray-300);
                border-radius: var(--radius-md);
                background: white;
                font-family: inherit;
            }
            
            /* Buttons */
            .btn {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-3) var(--space-6);
                border: none;
                border-radius: var(--radius-lg);
                font-weight: 600;
                font-size: 0.875rem;
                text-decoration: none;
                cursor: pointer;
                transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
                box-shadow: var(--shadow-sm);
                font-family: inherit;
            }
            
            .btn-primary {
                background: var(--primary-600);
                color: white;
            }
            
            .btn-primary:hover {
                background: var(--primary-700);
                transform: translateY(-1px);
                box-shadow: var(--shadow-md);
            }
            
            .btn-success {
                background: var(--success-600);
                color: white;
            }
            
            .btn-success:hover {
                background: var(--success-700);
                transform: translateY(-1px);
                box-shadow: var(--shadow-md);
            }
            
            .btn-warning {
                background: var(--warning-500);
                color: white;
            }
            
            .btn-warning:hover {
                background: var(--warning-600);
                transform: translateY(-1px);
                box-shadow: var(--shadow-md);
            }
            
            .btn-danger {
                background: var(--danger-500);
                color: white;
            }
            
            .btn-danger:hover {
                background: var(--danger-600);
                transform: translateY(-1px);
                box-shadow: var(--shadow-md);
            }
            
            /* Stats */
            .stats-card {
                background: white;
                border-radius: var(--radius-2xl);
                padding: var(--space-8);
                box-shadow: var(--shadow-lg);
                border: 1px solid var(--gray-100);
            }
            
            .stats-card h3 {
                font-size: 1.5rem;
                font-weight: 600;
                color: var(--gray-900);
                margin-bottom: var(--space-6);
                display: flex;
                align-items: center;
                gap: var(--space-3);
            }
            
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: var(--space-4);
                margin-bottom: var(--space-6);
            }
            
            .stat {
                background: var(--gray-50);
                border-radius: var(--radius-xl);
                padding: var(--space-5);
                text-align: center;
                border: 1px solid var(--gray-200);
            }
            
            .stat-number {
                font-size: 2rem;
                font-weight: 700;
                color: var(--primary-600);
                margin-bottom: var(--space-1);
                display: block;
            }
            
            .stat-label {
                font-size: 0.875rem;
                color: var(--gray-600);
                font-weight: 500;
            }
            
            .actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-3);
                align-items: center;
            }
            
            /* Responsive */
            @media (max-width: 768px) {
                .container {
                    padding: var(--space-4);
                }
                
                .header {
                    padding: var(--space-6);
                }
                
                .header h1 {
                    font-size: 2rem;
                }
                
                .main-grid {
                    grid-template-columns: 1fr;
                    gap: var(--space-6);
                }
                
                .nav-grid {
                    grid-template-columns: 1fr;
                    gap: var(--space-3);
                }
                
                .actions {
                    flex-direction: column;
                    align-items: stretch;
                }
                
                .actions .btn {
                    justify-content: center;
                }
                /* 🆕 ADICIONAR AQUI O CSS DE LOADING */
            .loading-spinner {
                display: inline-block;
                width: 20px;
                height: 20px;
                border: 3px solid #f3f4f6;
                border-top: 3px solid #3b82f6;
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin-right: 8px;
            }
            
            .loading-spinner.large {
                width: 40px;
                height: 40px;
                border-width: 4px;
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            .upload-loading {
                display: none;
                text-align: center;
                padding: 2rem;
                background: #f0f9ff;
                border: 2px dashed #3b82f6;
                border-radius: 12px;
                margin: 1rem 0;
            }
            
            .upload-loading.active {
                display: block;
            }
            
            .btn-loading {
                position: relative;
                pointer-events: none;
                opacity: 0.7;
            }
            /* FIM DOS ESTILOS DE LOADING */
            }
        </style>
    </head>
    <body>
        <div class="container">
            <!-- Header -->
            <header class="header">
                <h1>🏦 Sistema de Conciliação Bancária</h1>
                <p>Gerencie extratos AAI e EDUCAÇÃO com eficiência e precisão</p>
            </header>
            
            <!-- Navigation -->
            <nav class="nav-grid">
            <a href="/pendentes" class="nav-card">
            <span class="icon">📋</span>
            Conciliações Pendentes
            </a>
            <a href="/conciliados" class="nav-card">
            <span class="icon">✅</span>
            Já Conciliados
            </a>
            <a href="/relatorios" class="nav-card">
            <span class="icon">📊</span>
            Relatórios
            </a>
            <a href="/configuracoes" class="nav-card">
            <span class="icon">⚙️</span>
            Configurações
            </a>
            <a href="/usuarios" class="nav-card">
            <span class="icon">👥</span>
            Gerenciar Usuários
            </a>
            <a href="/docs" class="nav-card">
            <span class="icon">📚</span>
            Documentação API
            </a>
            </nav>
            
            <!-- Main Content -->
            <main class="main-grid">
                <!-- Upload AAI -->
                <section class="card">
                    <h3>
                        <span>📤</span>
                        Upload Extrato AAI
                    </h3>
                    <div class="upload-area">
                        <form action="/upload-extrato" method="post" enctype="multipart/form-data">
                            <input type="hidden" name="banco" value="AAI">
                            <p>Selecione o arquivo do banco AAI</p>
                            <input type="file" name="file" accept=".xlsx,.xls,.csv" required>
                            <br>
                            <button type="submit" class="btn btn-primary">
                                <span>🚀</span>
                                Processar Extrato AAI
                            </button>
                        </form>
                    </div>
                </section>
                
                <!-- Upload EDUCAÇÃO -->
                <section class="card">
                    <h3>
                        <span>📤</span>
                        Upload Extrato EDUCAÇÃO
                    </h3>
                    <div class="upload-area">
                        <form action="/upload-extrato" method="post" enctype="multipart/form-data">
                            <input type="hidden" name="banco" value="EDUCAÇÃO">
                            <p>Selecione o arquivo do banco EDUCAÇÃO</p>
                            <input type="file" name="file" accept=".xlsx,.xls,.csv" required>
                            <br>
                            <button type="submit" class="btn btn-primary">
                                <span>🚀</span>
                                Processar Extrato EDUCAÇÃO
                            </button>
                        </form>
                    </div>
                </section>
            </main>
            
            <!-- Statistics -->
            <section class="stats-card">
                <h3>
                    <span>📊</span>
                    Estatísticas do Sistema
                </h3>
                
                <div class="stats-grid" id="stats">
                    <div class="stat">
                        <span class="stat-number" id="total-transacoes">0</span>
                        <span class="stat-label">Total Transações</span>
                    </div>
                    <div class="stat">
                        <span class="stat-number" id="pendentes">0</span>
                        <span class="stat-label">Pendentes</span>
                    </div>
                    <div class="stat">
                        <span class="stat-number" id="conciliados">0</span>
                        <span class="stat-label">Conciliados</span>
                    </div>
                    <div class="stat">
                        <span class="stat-number" id="valor-total">R$ 0</span>
                        <span class="stat-label">Valor Total</span>
                    </div>
                </div>
                
                <div class="actions">
                    <button onclick="atualizarStats()" class="btn btn-success">
                        <span>🔄</span>
                        Atualizar Estatísticas
                    </button>
                    <a href="/pendentes" class="btn btn-warning">
                        <span>📋</span>
                        Ver Pendentes
                    </a>
                    <a href="/conciliados" class="btn btn-primary">
                        <span>✅</span>
                        Ver Conciliados
                    </a>
                    </div>
            </section>
        </div>
        
        <script>
        async function atualizarStats() {
            try {
                const response = await fetch('/api/stats');
                const data = await response.json();
                
                document.getElementById('total-transacoes').textContent = data.total_transacoes;
                document.getElementById('pendentes').textContent = data.pendentes;
                document.getElementById('conciliados').textContent = data.conciliados;
                document.getElementById('valor-total').textContent = 'R$ ' + data.valor_total.toLocaleString('pt-BR', {minimumFractionDigits: 2});
            } catch (error) {
                console.error('Erro ao atualizar stats:', error);
            }
        }
        
        
        function detectarContraparte(historico) {
    if (!historico || typeof historico !== 'string') {
        return '';
    }
    
    const historicoUpper = historico.toUpperCase().trim();
    let contraparte = '';
    
    // Padrões para PIX
    if (historicoUpper.includes('PIX')) {
        let match = historico.match(/PIX\\s+(?:RECEBIDO\\s+DE|ENVIADO\\s+PARA|DE|PARA)\\s+([A-Za-zÀ-ÿ\\s]+)/i);
        if (match) {
            contraparte = match[1].trim();
        } else {
            match = historico.match(/PIX\\s*[-–]\\s*([A-Za-zÀ-ÿ\\s]+)/i);
            if (match) {
                contraparte = match[1].trim();
            }
        }
    }
    
    // Padrões para TED
    else if (historicoUpper.includes('TED')) {
        let match = historico.match(/TED\\s+(?:RECEBIDA\\s+DE|ENVIADA\\s+PARA|DE|PARA)\\s+([A-Za-zÀ-ÿ\\s&\\.]+)/i);
        if (match) {
            contraparte = match[1].trim();
        }
    }
    
    // Padrões para Transferência
    else if (historicoUpper.includes('TRANSFERENCIA') || historicoUpper.includes('TRANSFERÊNCIA')) {
        let match = historico.match(/TRANSFER[EÊ]NCIA\s+(?:DE|PARA)\s+([A-Za-zÀ-ÿ\s&\.]+)/i);
        if (match) {
            contraparte = match[1].trim();
        }
    }
    
    // Padrões para Pagamento
    else if (historicoUpper.includes('PAGAMENTO')) {
        let match = historico.match(/PAGAMENTO\s*[-–]\s*([A-Za-zÀ-ÿ\s&\.]+?)(?:\s*-|\s*REF|$)/i);
        if (match) {
            contraparte = match[1].trim();
        }
    }
    
    // Padrão genérico - nome após hífen
    if (!contraparte) {
        let match = historico.match(/[-–:]\s*([A-Za-zÀ-ÿ\s&\.]{3,}?)(?:\s*[-–]|\s*REF|\s*CPF|\s*CNPJ|$)/i);
        if (match) {
            contraparte = match[1].trim();
        }
    }
    
    // Limpeza
    if (contraparte) {
        const palavrasRemover = ['REF', 'REFERENCIA', 'REFERÊNCIA', 'CPF', 'CNPJ', 'AGENCIA', 'AGÊNCIA'];
        palavrasRemover.forEach(palavra => {
            contraparte = contraparte.replace(new RegExp('\\b' + palavra + '\\b.*', 'gi'), '').trim();
        });
                
        contraparte = contraparte.toLowerCase().replace(/\b\w/g, l => l.toUpperCase());
    }
    
    return contraparte || 'Não identificado';
}
        
        window.onload = atualizarStats;
        </script>
            
        <!-- NOVO: Header de autenticação (adicionar ANTES de </body>) -->
        <div id="auth-header" style="
            position: fixed; 
            top: 0; 
            left: 0; 
            right: 0; 
            background: linear-gradient(135deg, #3b82f6, #2563eb); 
            color: white; 
            padding: 0.75rem 1.5rem; 
            display: none; 
            justify-content: space-between; 
            align-items: center; 
            box-shadow: 0 2px 4px rgba(0,0,0,0.1); 
            z-index: 1000;
            font-family: 'Inter', Arial, sans-serif;
        ">
            <div style="display: flex; align-items: center; gap: 1rem;">
                <span>👤 Olá, <strong id="auth-user-name">Usuário</strong>!</span>
                <span style="background: rgba(255,255,255,0.2); padding: 0.25rem 0.75rem; border-radius: 12px; font-size: 0.875rem;" id="auth-user-cargo">...</span>
            </div>
            <button onclick="authLogout()" style="
                background: #ef4444; 
                color: white; 
                border: none; 
                padding: 0.5rem 1rem; 
                border-radius: 6px; 
                cursor: pointer; 
                font-weight: 600;
                font-size: 0.875rem;
            ">
                🚪 Sair
            </button>
        </div>
        
        <!-- Loading overlay para autenticação -->
        <div id="auth-loading" style="
            position: fixed; 
            top: 0; 
            left: 0; 
            right: 0; 
            bottom: 0; 
            background: rgba(255,255,255,0.95); 
            display: flex; 
            justify-content: center; 
            align-items: center; 
            flex-direction: column; 
            gap: 1rem; 
            z-index: 2000;
            font-family: 'Inter', Arial, sans-serif;
        ">
            <div style="
                width: 40px; 
                height: 40px; 
                border: 4px solid #e5e7eb; 
                border-top: 4px solid #3b82f6; 
                border-radius: 50%; 
                animation: spin 1s linear infinite;
            "></div>
            <div style="font-size: 1.1rem; color: #4b5563;">🔄 Verificando autenticação...</div>
        </div>
        
        <!-- NOVO: Script de autenticação -->
        <script>
        // Adicionar espaço no topo quando o header aparecer
        function adjustBodyPadding() {
            const authHeader = document.getElementById('auth-header');
            if (authHeader.style.display !== 'none') {
                document.body.style.paddingTop = '60px';
            } else {
                document.body.style.paddingTop = '0px';
            }
        }
        
        // Verificar autenticação
        async function checkAuth() {
            console.log('🔍 Verificando autenticação...');
            
            const token = localStorage.getItem('access_token');
            const userData = localStorage.getItem('user');
            
            if (!token || !userData) {
                console.log('❌ Sem token/dados, redirecionando para login');
                window.location.href = '/login';
                return;
            }
            
            try {
                const user = JSON.parse(userData);
                console.log('✅ Usuário autenticado:', user);
                
                // Atualizar header
                document.getElementById('auth-user-name').textContent = user.nome || 'Usuário';
                document.getElementById('auth-user-cargo').textContent = user.cargo || 'operador';
                
                // Mostrar header e esconder loading
                document.getElementById('auth-header').style.display = 'flex';
                document.getElementById('auth-loading').style.display = 'none';
                
                // Ajustar padding do body
                adjustBodyPadding();
                
                console.log('✅ Interface de autenticação carregada!');
                
            } catch (error) {
                console.error('❌ Erro ao processar dados do usuário:', error);
                localStorage.removeItem('access_token');
                localStorage.removeItem('user');
                window.location.href = '/login';
            }
        }
        
        // Logout
        function authLogout() {
            if (confirm('Deseja realmente sair do sistema?')) {
                console.log('🚪 Fazendo logout...');
                localStorage.removeItem('access_token');
                localStorage.removeItem('user');
                window.location.href = '/login';
            }
        }
        
        // Executar verificação de auth quando a página carregar
        document.addEventListener('DOMContentLoaded', function() {
            checkAuth();
        });
        
        // Se o window.onload já existir, vamos executar junto
        const originalOnLoad = window.onload;
        window.onload = function() {
            checkAuth();
            if (originalOnLoad) {
                originalOnLoad();
            }
        };

        class LoadingManager {
            showButtonLoading(buttonElement, loadingText = 'Carregando...') {
                if (!buttonElement) return;
                
                const originalText = buttonElement.innerHTML;
                buttonElement.dataset.originalText = originalText;
                buttonElement.innerHTML = `<div class="loading-spinner"></div>${loadingText}`;
                buttonElement.classList.add('btn-loading');
                buttonElement.disabled = true;
                
                return () => this.hideButtonLoading(buttonElement);
            }
            
            hideButtonLoading(buttonElement) {
                if (!buttonElement) return;
                
                const originalText = buttonElement.dataset.originalText || 'Salvar';
                buttonElement.innerHTML = originalText;
                buttonElement.classList.remove('btn-loading');
                buttonElement.disabled = false;
                delete buttonElement.dataset.originalText;
            }
            
            showUploadLoading(formElement) {
                let loadingDiv = formElement.querySelector('.upload-loading');
                if (!loadingDiv) {
                    loadingDiv = document.createElement('div');
                    loadingDiv.className = 'upload-loading';
                    loadingDiv.innerHTML = `
                        <div style="display: flex; align-items: center; justify-content: center; gap: 1rem;">
                            <div class="loading-spinner large"></div>
                            <div>
                                <div style="font-weight: 600; color: #3b82f6;">Processando arquivo...</div>
                                <div style="font-size: 0.875rem; color: #6b7280;">Aguarde enquanto processamos seu extrato</div>
                            </div>
                        </div>
                    `;
                    formElement.appendChild(loadingDiv);
                }
                
                loadingDiv.classList.add('active');
                return () => loadingDiv.classList.remove('active');
            }
        }
        
        // Instância global
        window.loadingManager = new LoadingManager();
        
        // 🆕 MELHORAR A FUNÇÃO EXISTENTE atualizarStats
        const originalAtualizarStats = atualizarStats;
        atualizarStats = async function() {
            // Mostrar loading nos números
            document.getElementById('total-transacoes').innerHTML = '<div class="loading-spinner"></div>';
            document.getElementById('pendentes').innerHTML = '<div class="loading-spinner"></div>';
            document.getElementById('conciliados').innerHTML = '<div class="loading-spinner"></div>';
            document.getElementById('valor-total').innerHTML = '<div class="loading-spinner"></div>';
            
            // Executar função original
            try {
                await originalAtualizarStats();
            } catch (error) {
                console.error('Erro ao atualizar stats:', error);
            }
        };
        
        // 🆕 ADICIONAR LOADING AO UPLOAD
        document.querySelectorAll('form[action="/upload-extrato"]').forEach(form => {
            form.addEventListener('submit', function(e) {
                const hideLoading = loadingManager.showUploadLoading(this);
                
                // Esconder loading após 30 segundos como fallback
                setTimeout(hideLoading, 30000);
            });
        });
        
        // 🆕 AUTO-LOADING PARA TODOS OS BOTÕES
        document.addEventListener('click', function(e) {
            const button = e.target.closest('button');
            if (button && button.type === 'submit') {
                loadingManager.showButtonLoading(button);
            }
        });
        
        // FIM DOS SCRIPTS DE LOADING
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/upload-extrato")
async def upload_extrato(file: UploadFile = File(...), banco: str = Form(...)):
    """Upload e processamento de extrato bancário - SALVANDO NO BANCO"""
    
    logger.info(f"Recebido upload: {file.filename} para banco {banco}")
    
    if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
        logger.error(f"Arquivo inválido: {file.filename}")
        return HTMLResponse(
            content=f"""
            <html><body>
                <h2>❌ Erro</h2>
                <p>Apenas arquivos Excel (.xlsx, .xls) ou CSV (.csv) são aceitos</p>
                <a href="/">Voltar</a>
            </body></html>
            """,
            status_code=400
        )
    
    if banco not in ['AAI', 'EDUCAÇÃO']:
        logger.error(f"Banco inválido: {banco}")
        return HTMLResponse(
            content=f"""
            <html><body>
                <h2>❌ Erro</h2>
                <p>Banco deve ser AAI ou EDUCAÇÃO</p>
                <a href="/">Voltar</a>
            </body></html>
            """,
            status_code=400
        )
    
    try:
        logger.info("Lendo conteúdo do arquivo...")
        content = await file.read()
        logger.info(f"Arquivo lido: {len(content)} bytes")
        
        logger.info("Processando arquivo...")
        transacoes = processar_arquivo(content, file.filename, banco)
        logger.info(f"Processadas {len(transacoes)} transações")
        
        # NOVO: Verificar se Supabase está configurado
        if not supabase:
            logger.error("❌ Supabase não configurado")
            raise HTTPException(status_code=500, detail="Banco de dados não configurado")
        
        logger.info("💾 Salvando extrato no banco...")
        
        # 1. Inserir extrato
        extrato_data = {
            'banco': banco,
            'arquivo': file.filename,
            'total_transacoes': len(transacoes),
            'status': 'PROCESSADO',
            'processado_em': datetime.now().isoformat(),
            'processado_por': 'Sistema'  # TODO: pegar usuário logado
        }
        
        extrato_result = supabase.admin_client.table("extratos").insert(extrato_data).execute()
        
        if not extrato_result.data:
            logger.error("❌ Erro ao salvar extrato no banco")
            raise HTTPException(status_code=500, detail="Erro ao salvar extrato no banco")
        
        extrato_id = extrato_result.data[0]['id']
        logger.info(f"✅ Extrato salvo com ID: {extrato_id}")
        
        # 2. Preparar transações para o banco
        logger.info("💾 Preparando transações para salvar...")
        
        transacoes_para_banco = []
        for transacao in transacoes:
            # Criar dados para o banco
            transacao_banco = {
                'extrato_id': extrato_id,
                'banco': transacao['banco'],
                'data': datetime.strptime(transacao['data'], "%d/%m/%Y").date().isoformat() if transacao['data'] else None,
                'historico': transacao['historico'],
                'documento': transacao['documento'],
                'valor': float(transacao['valor']) if transacao['valor'] else 0,
                'saldo': float(transacao['saldo']) if transacao['saldo'] else 0,
                'tipo_transacao': transacao['tipo_transacao'],
                'status': 'PENDENTE',
                'forma_pagamento': transacao['forma_pagamento'],
                'banco_origem': transacao['banco_origem'],
                'contraparte': transacao['contraparte'],
                'data_pagamento': datetime.strptime(transacao['data_pagamento'], "%d/%m/%Y").date().isoformat() if transacao['data_pagamento'] else None,
                'created_at': datetime.now().isoformat()
            }
            
            transacoes_para_banco.append(transacao_banco)
        
        # 3. Inserir transações em lotes (Supabase tem limite)
        logger.info(f"💾 Salvando {len(transacoes_para_banco)} transações no banco...")
        
        batch_size = 100  # Inserir de 100 em 100
        transacoes_salvas = 0
        
        for i in range(0, len(transacoes_para_banco), batch_size):
            batch = transacoes_para_banco[i:i + batch_size]
            
            transacoes_result = supabase.admin_client.table("transacoes").insert(batch).execute()
            
            if transacoes_result.data:
                transacoes_salvas += len(transacoes_result.data)
                logger.info(f"✅ Lote {i//batch_size + 1}: {len(transacoes_result.data)} transações salvas")
            else:
                logger.error(f"❌ Erro ao salvar lote {i//batch_size + 1}")
        
        logger.info(f"✅ Total de transações salvas: {transacoes_salvas}")
        
        # Calcular estatísticas
        valor_total = sum(t['valor'] for t in transacoes)
        creditos = [t for t in transacoes if t['valor'] > 0]
        debitos = [t for t in transacoes if t['valor'] < 0]
        
        logger.info(f"🎉 Extrato {banco} processado e salvo com sucesso!")
        
        # Retornar página de sucesso
        html_sucesso = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Upload Concluído</title>
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
            <style>
                body {{ font-family: 'Inter', Arial, sans-serif; background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%); min-height: 100vh; color: #111827; line-height: 1.6; padding: 1.5rem; }}
                .container {{ max-width: 900px; margin: 0 auto; }}
                .success-card {{ background: white; border-radius: 1.5rem; padding: 2.5rem; box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.1); text-align: center; }}
                .success-icon {{ font-size: 4rem; display: block; margin-bottom: 1.5rem; }}
                h1 {{ font-size: 2.5rem; font-weight: 700; color: #111827; margin-bottom: 2rem; }}
                .success-info {{ background: #f0fdf4; border: 1px solid #dcfce7; border-radius: 1rem; padding: 1.5rem; margin-bottom: 2rem; }}
                .success-info h3 {{ font-size: 1.25rem; font-weight: 600; color: #166534; margin-bottom: 1rem; display: flex; align-items: center; justify-content: center; gap: 0.5rem; }}
                .success-info p {{ color: #374151; margin: 0.5rem 0; }}
                .success-info p strong {{ font-weight: 600; color: #1f2937; }}
                .btn {{ display: inline-flex; align-items: center; gap: 0.75rem; padding: 0.75rem 1.5rem; border: none; border-radius: 0.75rem; font-weight: 600; text-decoration: none; cursor: pointer; transition: all 0.3s ease; margin: 0.5rem; }}
                .btn-primary {{ background: #2563eb; color: white; }}
                .btn-primary:hover {{ background: #1d4ed8; transform: translateY(-2px); }}
                .actions {{ display: flex; justify-content: center; flex-wrap: wrap; margin-top: 2rem; }}
                .highlight {{ background: linear-gradient(135deg, #22c55e, #16a34a); color: white; padding: 1rem; border-radius: 1rem; margin: 1rem 0; }}
                
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success-card">
                    <span class="success-icon">🎉</span>
                    <h1>Upload Concluído com Sucesso!</h1>
                    
                    <div class="success-info">
                        <h3>
                            <span>💾</span>
                            Extrato {banco} Salvo no Banco de Dados
                        </h3>
                        <p><strong>Arquivo:</strong> {file.filename}</p>
                        <p><strong>Status:</strong> Processado e persistido com sucesso</p>
                        <p><strong>Data/Hora:</strong> {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}</p>
                        <p><strong>ID do Extrato:</strong> {extrato_id}</p>
                    </div>
                    
                    <div class="highlight">
                        <h3 style="margin: 0 0 1rem 0;">📊 Resumo do Processamento</h3>
                        <p><strong>Transações Importadas:</strong> {len(transacoes)}</p>
                        <p><strong>Transações Salvas:</strong> {transacoes_salvas}</p>
                        <p><strong>Entradas (+):</strong> {len(creditos)} transações</p>
                        <p><strong>Saídas (-):</strong> {len(debitos)} transações</p>
                        <p><strong>Valor Total:</strong> R$ {valor_total:,.2f}</p>
                    </div>
                    
                    <div class="actions">
                        <a href="/pendentes" class="btn btn-primary">
                            <span>📋</span>
                            Ver Transações Pendentes ({transacoes_salvas})
                        </a>
                        <a href="/" class="btn btn-primary">
                            <span>🏠</span>
                            Voltar ao Início
                        </a>
                        <a href="/relatorios" class="btn btn-primary">
                            <span>📊</span>
                            Ver Relatórios
                        </a>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_sucesso)
        
    except Exception as e:
        logger.error(f"ERRO CRÍTICO ao processar extrato {banco}: {str(e)}")
        import traceback
        logger.error(f"Traceback completo: {traceback.format_exc()}")
        
        # Retornar página de erro
        html_erro = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Erro no Upload</title>
            <style>
                body {{ font-family: Arial, sans-serif; background: #f8f9fa; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; padding: 30px; box-shadow: 0 3px 10px rgba(0,0,0,0.1); }}
                .error {{ background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 8px; padding: 20px; color: #721c24; }}
                .btn {{ background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; text-decoration: none; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>❌ Erro no Processamento</h1>
                <div class="error">
                    <h3>Não foi possível processar e salvar o arquivo no banco</h3>
                    <p><strong>Erro:</strong> {str(e)}</p>
                    <p><strong>Arquivo:</strong> {file.filename}</p>
                    <p><strong>Banco:</strong> {banco}</p>
                </div>
                
                <div style="margin-top: 20px; text-align: center;">
                    <a href="/" class="btn">🏠 Voltar e Tentar Novamente</a>
                </div>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_erro, status_code=400)
        
    except Exception as e:
        logger.error(f"ERRO ao processar extrato {banco}: {str(e)}")
        logger.error(f"Tipo do erro: {type(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Retornar página de erro
        html_erro = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Erro no Upload</title>
            <style>
                body {{ font-family: Arial, sans-serif; background: #f8f9fa; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; padding: 30px; box-shadow: 0 3px 10px rgba(0,0,0,0.1); }}
                .error {{ background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 8px; padding: 20px; color: #721c24; }}
                .btn {{ background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; text-decoration: none; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>❌ Erro no Processamento</h1>
                <div class="error">
                    <h3>Não foi possível processar o arquivo</h3>
                    <p><strong>Erro:</strong> {str(e)}</p>
                    <p><strong>Arquivo:</strong> {file.filename}</p>
                    <p><strong>Banco:</strong> {banco}</p>
                </div>
                
                <div style="margin-top: 20px; text-align: center;">
                    <a href="/" class="btn">🏠 Voltar e Tentar Novamente</a>
                </div>
                
              <div class="form-section">
    <h4>
        <span>📊</span>
        Classificação Hierárquica
    </h4>
                </div>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_erro, status_code=400)


@app.get("/pendentes")
async def listar_pendentes():
    """Listar transações pendentes do Supabase"""
    try:
        if not supabase:
            pendentes = []
        else:
            # Buscar transações pendentes do Supabase
            result = supabase.admin_client.table("transacoes").select("*").eq("status", "PENDENTE").order("created_at", desc=True).execute()
            pendentes = result.data
        
        total_pendentes = len(pendentes)
        logger.info(f"📋 Carregando {total_pendentes} transações pendentes do Supabase")
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar pendentes: {str(e)}")
        pendentes = []
        total_pendentes = 0
    
    # Criar HTML com design moderno (mantendo o visual original)
    html_content = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Conciliações Pendentes</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {{
    
                /* Design System - Colors - MANTENDO CORES ORIGINAIS */
                --primary-50: #eff6ff;
                --primary-100: #dbeafe;
                --primary-200: #bfdbfe;
                --primary-300: #93c5fd;
                --primary-500: #3b82f6;
                --primary-600: #2563eb;
                --primary-700: #1d4ed8;
                --primary-900: #1e3a8a;
                
                --success-50: #f0fdf4;
                --success-100: #dcfce7;
                --success-500: #22c55e;
                --success-600: #16a34a;
                --success-700: #15803d;
                
                --warning-50: #fffbeb;
                --warning-100: #fef3c7;
                --warning-200: #fde68a;
                --warning-500: #f59e0b;
                --warning-600: #d97706;
                
                --danger-50: #fef2f2;
                --danger-500: #ef4444;
                --danger-600: #dc2626;
                
                --gray-50: #f9fafb;
                --gray-100: #f3f4f6;
                --gray-200: #e5e7eb;
                --gray-300: #d1d5db;
                --gray-400: #9ca3af;
                --gray-500: #6b7280;
                --gray-600: #4b5563;
                --gray-700: #374151;
                --gray-800: #1f2937;
                --gray-900: #111827;
                
                --space-1: 0.25rem;
                --space-2: 0.5rem;
                --space-3: 0.75rem;
                --space-4: 1rem;
                --space-5: 1.25rem;
                --space-6: 1.5rem;
                --space-8: 2rem;
                --space-10: 2.5rem;
                --space-12: 3rem;
                --space-16: 4rem;
                
                --radius-sm: 0.375rem;
                --radius-md: 0.5rem;
                --radius-lg: 0.75rem;
                --radius-xl: 1rem;
                --radius-2xl: 1.5rem;
                
                --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
                --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
                --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
                --shadow-xl: 0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1);
            }}
            
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: var(--gray-50);
                min-height: 100vh;
                color: var(--gray-900);
                line-height: 1.6;
                padding-top: 60px;
            }}
            
            .container {{
                max-width: 1400px;
                margin: 0 auto;
                padding: var(--space-6);
            }}
            
            /* Header - MANTENDO ESTILO ORIGINAL */
            .header {{
                background: white;
                border-radius: var(--radius-2xl);
                padding: var(--space-8);
                margin-bottom: var(--space-6);
                box-shadow: var(--shadow-lg);
                border: 1px solid var(--gray-200);
                display: flex;
                justify-content: space-between;
                align-items: center;
                flex-wrap: wrap;
                gap: var(--space-4);
            }}
            
            .header-content h1 {{
                font-size: 2rem;
                font-weight: 700;
                color: var(--gray-900);
                margin-bottom: var(--space-2);
                display: flex;
                align-items: center;
                gap: var(--space-3);
            }}
            
            .header-content p {{
                color: var(--gray-600);
                font-size: 1rem;
            }}
            
            /* Filters - MANTENDO ESTILO ORIGINAL */
            .filters {{
                background: white;
                border-radius: var(--radius-xl);
                padding: var(--space-6);
                margin-bottom: var(--space-6);
                box-shadow: var(--shadow-md);
                border: 1px solid var(--gray-200);
                display: flex;
                gap: var(--space-4);
                flex-wrap: wrap;
                align-items: center;
            }}
            
            .filter-group {{
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }}
            
            .filter-group label {{
                font-size: 0.875rem;
                font-weight: 600;
                color: var(--gray-700);
            }}
            
            /* Table Container - MANTENDO ESTILO ORIGINAL */
            .table-container {{
                background: white;
                border-radius: var(--radius-2xl);
                overflow: hidden;
                box-shadow: var(--shadow-lg);
                border: 1px solid var(--gray-200);
            }}
            
            table {{
                width: 100%;
                border-collapse: collapse;
            }}
            
            th {{
                background: var(--primary-600);
                color: white;
                padding: var(--space-4);
                text-align: left;
                font-weight: 600;
                font-size: 0.875rem;
                letter-spacing: 0.025em;
            }}
            
            td {{
                padding: var(--space-4);
                border-bottom: 1px solid var(--gray-200);
                font-size: 0.875rem;
            }}
            
            tr:hover {{
                background: var(--gray-50);
            }}
            
            tr:last-child td {{
                border-bottom: none;
            }}
            
            /* Buttons - MANTENDO ESTILO ORIGINAL */
            .btn {{
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-4);
                border: none;
                border-radius: var(--radius-lg);
                font-weight: 600;
                font-size: 0.75rem;
                text-decoration: none;
                cursor: pointer;
                transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
                box-shadow: var(--shadow-sm);
                font-family: inherit;
            }}
            
            .btn-primary {{
                background: var(--primary-600);
                color: white;
            }}
            
            .btn-primary:hover {{
                background: var(--primary-700);
                transform: translateY(-1px);
                box-shadow: var(--shadow-md);
            }}
            
            .btn-success {{
                background: var(--success-600);
                color: white;
            }}
            
            .btn-success:hover {{
                background: var(--success-700);
                transform: translateY(-1px);
                box-shadow: var(--shadow-md);
            }}
            
            /* Status - MANTENDO ESTILO ORIGINAL */
            .status-pendente {{
                background: var(--warning-100);
                color: var(--warning-600);
                padding: var(--space-1) var(--space-3);
                border-radius: var(--radius-md);
                font-size: 0.75rem;
                font-weight: 600;
                letter-spacing: 0.025em;
            }}
            
            /* Values - MANTENDO ESTILO ORIGINAL */
            .valor-positivo {{
                color: var(--success-600);
                font-weight: 700;
            }}
            
            .valor-negativo {{
                color: var(--danger-500);
                font-weight: 700;
            }}
            
            /* Form Elements - MANTENDO ESTILO ORIGINAL */
            select, input {{
                padding: var(--space-3);
                border: 1px solid var(--gray-300);
                border-radius: var(--radius-md);
                font-size: 0.875rem;
                font-family: inherit;
                background: white;
                transition: all 0.2s ease;
            }}
            
            select:focus, input:focus {{
                outline: none;
                border-color: var(--primary-500);
                box-shadow: 0 0 0 3px var(--primary-100);
            }}

            /* Modal - MANTENDO ESTILO ORIGINAL */
            .modal {{
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                backdrop-filter: blur(4px);
                z-index: 1000;
                overflow-y: auto;
                padding: var(--space-4);
            }}

            .modal-content {{
                position: relative;
                background: white;
                margin: var(--space-8) auto;
                padding: var(--space-10);
                border-radius: var(--radius-2xl);
                width: 100%;
                max-width: 900px;
                max-height: calc(100vh - 4rem);
                overflow-y: auto;
                box-shadow: var(--shadow-xl);
                border: 1px solid var(--gray-200);
            }}

            .modal-header {{
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                margin-bottom: var(--space-8);
                padding-bottom: var(--space-6);
                border-bottom: 1px solid var(--gray-200);
            }}

            .modal-header > div:first-child {{
                flex: 1;
            }}

            .modal-header h3 {{
                font-size: 1.75rem;
                font-weight: 700;
                color: var(--gray-900);
                display: flex;
                align-items: center;
                gap: var(--space-3);
                margin-bottom: 0;
            }}

            .btn-close {{
                background: var(--danger-500);
                color: white;
                border: none;
                border-radius: var(--radius-lg);
                padding: var(--space-2) var(--space-4);
                cursor: pointer;
                font-size: 1rem;
                font-weight: 600;
                transition: all 0.2s ease;
                min-width: 40px;
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
            }}

            .btn-close:hover {{
                background: var(--danger-600);
                transform: scale(1.05);
            }}

            /* NOVO: Estilos para o campo de valor no cabeçalho */
            .valor-transacao {{
                background: linear-gradient(135deg, var(--primary-50), var(--primary-100));
                border: 2px solid var(--primary-200);
                border-radius: var(--radius-xl);
                padding: var(--space-4) var(--space-6);
                margin-top: var(--space-6);
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                box-shadow: var(--shadow-sm);
                transition: all 0.3s ease;
            }}

            .valor-transacao:hover {{
                transform: translateY(-1px);
                box-shadow: var(--shadow-md);
            }}

            .valor-label {{
                font-size: 0.875rem;
                font-weight: 600;
                color: var(--gray-600);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }}

            .valor-amount {{
                font-size: 1.5rem;
                font-weight: 800;
                color: var(--primary-700);
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }}

            .valor-amount.positivo {{
                color: var(--success-600);
            }}

            .valor-amount.negativo {{
                color: var(--danger-600);
            }}

            .valor-amount::before {{
                content: '💰';
                font-size: 1.25rem;
            }}

            /* Seções do formulário */
            .form-section {{
                margin-bottom: var(--space-8);
            }}

            .form-section h4 {{
                font-size: 1.125rem;
                font-weight: 600;
                color: var(--gray-800);
                margin-bottom: var(--space-4);
                padding-bottom: var(--space-2);
                border-bottom: 1px solid var(--gray-200);
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }}

            /* Form */
            .form-row {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-6);
                margin: var(--space-6) 0;
            }}
            
            .form-group {{
                margin: var(--space-4) 0;
            }}
            
            .form-group.full-width {{
                grid-column: 1 / -1;
            }}
            
            .form-group label {{
                display: block;
                margin-bottom: var(--space-2);
                font-weight: 600;
                color: var(--gray-700);
                font-size: 0.875rem;
            }}
            
            .form-group select,
            .form-group input,
            .form-group textarea {{
                width: 100%;
                padding: var(--space-4);
                border: 1px solid var(--gray-300);
                border-radius: var(--radius-lg);
                font-size: 0.875rem;
                font-family: inherit;
                background: white;
                transition: all 0.2s ease;
            }}
            
            .form-group select:focus,
            .form-group input:focus,
            .form-group textarea:focus {{
                outline: none;
                border-color: var(--primary-500);
                box-shadow: 0 0 0 3px var(--primary-100);
            }}
            
            .form-group textarea {{
                height: 100px;
                resize: vertical;
            }}
            
            .form-group select:disabled,
            .form-group input:disabled,
            .form-group input:read-only {{
                background-color: var(--primary-50);
                border-color: var(--primary-200);
            }}
            
            .auto-filled {{
                background-color: var(--primary-50) !important;
                border-color: var(--primary-200) !important;
            }}
            
            .required {{
                color: var(--danger-500);
            }}
            
            /* Form Buttons */
            .form-buttons {{
                display: flex;
                justify-content: flex-end;
                gap: var(--space-4);
                margin-top: var(--space-8);
                padding-top: var(--space-6);
                border-top: 1px solid var(--gray-200);
            }}
            
            .btn-cancel {{
                background: var(--gray-600);
                color: white;
                padding: var(--space-3) var(--space-6);
            }}
            
            .btn-cancel:hover {{
                background: var(--gray-700);
            }}
            
            .btn-save {{
                background: var(--success-600);
                color: white;
                padding: var(--space-3) var(--space-6);
            }}
            
            .btn-save:hover {{
                background: var(--success-700);
            }}
            
            /* Header de autenticação - ADICIONANDO */
            #auth-header {{
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                background: linear-gradient(135deg, #3b82f6, #2563eb);
                color: white;
                padding: 0.75rem 1.5rem;
                display: none;
                justify-content: space-between;
                align-items: center;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                z-index: 1000;
                font-family: 'Inter', Arial, sans-serif;
            }}
            
            #auth-loading {{
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(255,255,255,0.95);
                display: flex;
                justify-content: center;
                align-items: center;
                flex-direction: column;
                gap: 1rem;
                z-index: 2000;
                font-family: 'Inter', Arial, sans-serif;
            }}
            
            
            /* Responsive */
            @media (max-width: 768px) {{
                .container {{
                    padding: var(--space-4);
                }}
                
                .header {{
                    flex-direction: column;
                    align-items: stretch;
                    text-align: center;
                }}
                
                .filters {{
                    flex-direction: column;
                    align-items: stretch;
                }}
                
                .filter-group {{
                    width: 100%;
                }}
                
                .form-row {{
                    grid-template-columns: 1fr;
                    gap: var(--space-4);
                }}
                
                .modal-content {{
                    margin: var(--space-4) auto;
                    padding: var(--space-6);
                }}
                
                .form-buttons {{
                    flex-direction: column;
                }}
                
                table {{
                    font-size: 0.75rem;
                }}
                
                    th, td {{
                    padding: var(--space-2);
                }}
                       
        </style>
    </head>
    <body>
        <!-- Loading overlay para autenticação -->
        <div id="auth-loading" style="
            position: fixed; 
            top: 0; 
            left: 0; 
            right: 0; 
            bottom: 0; 
            background: rgba(255,255,255,0.95); 
            display: flex; 
            justify-content: center; 
            align-items: center; 
            flex-direction: column; 
            gap: 1rem; 
            z-index: 2000;
            font-family: 'Inter', Arial, sans-serif;
        ">
            <div style="
                width: 40px; 
                height: 40px; 
                border: 4px solid #e5e7eb; 
                border-top: 4px solid #3b82f6; 
                border-radius: 50%; 
                animation: spin 1s linear infinite;
            "></div>
            <div style="font-size: 1.1rem; color: #4b5563;">🔄 Verificando autenticação...</div>
        </div>
        
        <!-- Header de autenticação -->
        <div id="auth-header">
            <div style="display: flex; align-items: center; gap: 1rem;">
                <span>👤 Olá, <strong id="auth-user-name">Usuário</strong>!</span>
                <span style="background: rgba(255,255,255,0.2); padding: 0.25rem 0.75rem; border-radius: 12px; font-size: 0.875rem;" id="auth-user-cargo">...</span>
            </div>
            <button onclick="authLogout()" style="
                background: #ef4444; 
                color: white; 
                border: none; 
                padding: 0.5rem 1rem; 
                border-radius: 6px; 
                cursor: pointer; 
                font-weight: 600;
                font-size: 0.875rem;
            ">
                🚪 Sair
            </button>
        </div>

        <div class="container">
            <!-- Header -->
            <header class="header">
                <div class="header-content">
                    <h1>
                        <span>📋</span>
                        Conciliações Pendentes
                    </h1>
                    <p>Total de {total_pendentes} transações aguardando conciliação</p>
                </div>
                <a href="/" class="btn btn-primary">
                    <span>🏠</span>
                    Voltar ao Início
                </a>
            </header>
            
            <!-- Filters -->
            <section class="filters">
                <div class="filter-group">
                    <label for="filtro-banco">Banco</label>
                    <select id="filtro-banco" onchange="filtrarTabela()">
                        <option value="">Todos os Bancos</option>
                        <option value="AAI">AAI</option>
                        <option value="EDUCAÇÃO">EDUCAÇÃO</option>
                    </select>
                </div>
                
                <div class="filter-group">
                    <label for="filtro-tipo">Tipo</label>
                    <select id="filtro-tipo" onchange="filtrarTabela()">
                        <option value="">Todos os Tipos</option>
                        <option value="PIX">PIX</option>
                        <option value="TED">TED</option>
                        <option value="PAGAMENTO">PAGAMENTO</option>
                        <option value="TARIFA">TARIFA</option>
                        <option value="DÉBITO">DÉBITO</option>
                    </select>
                </div>
                
                <div class="filter-group">
                    <label for="filtro-busca">Buscar</label>
                    <input type="text" id="filtro-busca" placeholder="Buscar no histórico..." onkeyup="filtrarTabela()">
                </div>
                
                <div class="filter-group">
                    <label>&nbsp;</label>
                    <button class="btn btn-success" onclick="conciliarSelecionados()">
                        <span>✅</span>
                        Conciliar Selecionados
                    </button>
                </div>
            </section>
            
            <!-- Table -->
            <section class="table-container">
                <table id="tabela-pendentes">
                    <thead>
                        <tr>
                            <th><input type="checkbox" id="select-all" onchange="selecionarTodos()"></th>
                            <th>Banco</th>
                            <th>Data</th>
                            <th>Histórico</th>
                            <th>Tipo</th>
                            <th>Valor</th>
                            <th>Status</th>
                            <th>Ações</th>
                        </tr>
                    </thead>
                    <tbody>"""

    # ADICIONANDO TRANSAÇÕES DO SUPABASE NO HTML
    if not pendentes:
        html_content += """
                        <tr>
                            <td colspan="8" style="text-align: center; padding: var(--space-8); color: var(--gray-600);">
                                <div style="display: flex; flex-direction: column; align-items: center; gap: 1rem;">
                                    <span style="font-size: 3rem;">📋</span>
                                    <div>
                                        <h3 style="color: var(--gray-800); margin-bottom: 0.5rem;">Nenhuma transação pendente</h3>
                                        <p>Todas as transações foram conciliadas ou não há extratos processados.</p>
                                    </div>
                                    <a href="/" class="btn btn-primary">🏠 Voltar ao início</a>
                                </div>
                            </td>
                        </tr>"""
    else:
        for transacao in pendentes:
            # Formatar data brasileira
            try:
                if isinstance(transacao.get('data'), str):
                    if transacao['data'].count('-') == 2:  # formato yyyy-mm-dd
                        data_obj = datetime.strptime(transacao['data'], '%Y-%m-%d')
                        data_formatada = data_obj.strftime('%d/%m/%Y')
                    else:
                        data_formatada = transacao['data']
                else:
                    data_formatada = transacao.get('data', '')
            except:
                data_formatada = transacao.get('data', '')
            
            valor_class = "valor-positivo" if float(transacao.get('valor', 0)) >= 0 else "valor-negativo"
            valor_float = float(transacao.get('valor', 0))
            
            html_content += f"""
                        <tr data-banco="{transacao.get('banco', '')}" data-tipo="{transacao.get('tipo_transacao', '')}" data-historico="{transacao.get('historico', '').lower()}">
                            <td><input type="checkbox" class="select-transacao" value="{transacao.get('id', '')}"></td>
                            <td><strong>{transacao.get('banco', '')}</strong></td>
                            <td>{data_formatada}</td>
                            <td title="{transacao.get('historico', '')}">{transacao.get('historico', '')[:60]}{'...' if len(transacao.get('historico', '')) > 60 else ''}</td>
                            <td>{transacao.get('tipo_transacao', '')}</td>
                            <td class="{valor_class}">R$ {valor_float:,.2f}</td>
                            <td><span class="status-pendente">PENDENTE</span></td>
                            <td>
                                <button class="btn btn-primary" onclick="abrirModalConciliacao('{transacao.get('id', '')}')">
                                    <span>🔖</span>
                                    Conciliar
                                </button>
                            </td>
                        </tr>"""

    html_content += """
                    </tbody>
                </table>
            </section>
        </div>
        
       <!-- Modal de Conciliação - MANTENDO ORIGINAL -->
       <div id="modal-conciliacao" class="modal">
           <div class="modal-content">
               <div class="modal-header">
                   <div>
                       <h3>
                           <span>🔖</span>
                           Conciliar Transação
                       </h3>
                       <!-- Campo do valor no cabeçalho -->
                       <div class="valor-transacao" id="valor-transacao">
                           <span class="valor-label">Valor da Transação:</span>
                           <span class="valor-amount" id="valor-amount">R$ 0,00</span>
                       </div>
                   </div>
                   <button class="btn-close" onclick="fecharModal()">✕</button>
               </div>
               
               <form id="form-conciliacao">
                   <input type="hidden" id="transacao-id">
                   
                   <!-- Seção 1: Hierarquia de Classificação -->
                   <div class="form-section">
                       <h4>
                           <span>📊</span>
                           Classificação Hierárquica
                       </h4>
                       
                       <div class="form-row">
                           <div class="form-group">
                               <label>1. Classificação <span class="required">*</span></label>
                               <select id="classificacao" onchange="atualizarPlanoContas()" required>
                                   <option value="">Selecionar classificação...</option>""" + \
                                    ''.join([f'</select>' for classif in classificacoes.keys()]) + """
                               </select>
                           </div>
                           <div class="form-group">
                               <label>2. Plano de Contas <span class="required">*</span></label>
                               <select id="plano-contas" onchange="atualizarItens()" disabled required>
                                   <option value="">Selecione uma classificação primeiro</option>
                               </select>
                           </div>
                       </div>
                       
                       <div class="form-group">
                           <label>3. Item <span class="required">*</span></label>
                           <select id="item" disabled required>
                               <option value="">Selecione um plano de contas primeiro</option>
                           </select>
                       </div>
                   </div>
                   
                   <!-- Seção 2: Informações de Pagamento -->
                   <div class="form-section">
                       <h4>
                           <span>💳</span>
                           Informações de Pagamento
                       </h4>
                       
                       <div class="form-row">
                           <div class="form-group">
                               <label>Forma de Pagamento <small style="color: var(--gray-500);">(Automática)</small></label>
                               <select id="forma-pagamento" class="auto-filled" disabled>
                                   <option value="PIX">PIX</option>
                                   <option value="TED">TED</option>
                                   <option value="DOC">DOC</option>
                                   <option value="Débito Automático">Débito Automático</option>
                                   <option value="Cartão">Cartão</option>
                                   <option value="Boleto">Boleto</option>
                                   <option value="Transferência">Transferência</option>
                                   <option value="Depósito">Depósito</option>
                                   <option value="Saque">Saque</option>
                                   <option value="Tarifa">Tarifa</option>
                                   <option value="Outros">Outros</option>
                               </select>
                           </div>
                           <div class="form-group">
                           <label>Contraparte <small style="color: var(--gray-500);">(Automática)</small></label>
                           <input type="text" id="contraparte" class="auto-filled" readonly placeholder="Será preenchido automaticamente baseado no histórico">
                           </div>

                           <div class="form-group">
                               <label>Banco <small style="color: var(--gray-500);">(Automático)</small></label>
                               <select id="banco-origem" class="auto-filled" disabled>
                                   <option value="AAI">AAI</option>
                                   <option value="EDUCAÇÃO">EDUCAÇÃO</option>
                               </select>
                           </div>
                       </div>
                   </div>
                   
                   <!-- Seção 3: Detalhes da Transação -->
                   <div class="form-section">
                       <h4>
                           <span>📝</span>
                           Detalhes da Transação
                       </h4>
                       
                       <div class="form-row">
                           <div class="form-group">
                               <label>Centro de Custo <span class="required">*</span></label>
                               <select id="centro-custo" required>
                                   <option value="">Selecionar centro de custo...</option>""" + \
                                    ''.join([f'<option value="{centro}">{centro}</option>' for centro in centros_custo]) + """
                               </select>
                           </div>
                           <div class="form-group">
                               <label>Data de Pagamento <small style="color: var(--gray-500);">(Automática)</small></label>
                               <input type="date" id="data-pagamento" class="auto-filled" readonly>
                           </div>
                       </div>
                       
                       <div class="form-row">
                           <div class="form-group">
                               <label>Nome Completo do Recebedor</label>
                               <input type="text" id="nome-recebedor" placeholder="Digite o nome completo do recebedor">
                           </div>
                           <div class="form-group">
                               <label>Data de Referência</label>
                               <input type="date" id="data-referencia">
                           </div>
                       </div>
                       
                       <div class="form-group full-width">
                           <label>Observações</label>
                           <textarea id="observacoes" placeholder="Observações adicionais sobre a transação..."></textarea>
                       </div>
                   </div>
                   
                   <div class="form-buttons">
                       <button type="button" onclick="fecharModal()" class="btn-cancel">
                           <span>✕</span>
                           Cancelar
                       </button>
                       <button type="button" onclick="salvarConciliacao()" class="btn-save">
                           <span>✅</span>
                           Conciliar Transação
                       </button>
                   </div>
               </form>
           </div>
        </div>
         <script>
// Cache simples no frontend
let classificacoesCache = null;
let cacheTimestamp = 0;
const CACHE_DURATION = 5 * 60 * 1000; // 5 minutos

async function obterClassificacoes() {
    const agora = Date.now();
    
    // Verificar se cache ainda é válido
    if (classificacoesCache && (agora - cacheTimestamp) < CACHE_DURATION) {
        console.log('Usando cache do frontend');
        return classificacoesCache;
    }
    
    console.log('Buscando classificações do servidor...');
    
    try {
        const response = await fetch('/api/classificacoes');
        const data = await response.json();
        
        // Atualizar cache
        classificacoesCache = data.classificacoes;
        cacheTimestamp = agora;
        
        console.log('Cache atualizado');
        return classificacoesCache;
        
    } catch (error) {
        console.error('Erro ao buscar classificações:', error);
        return classificacoesCache || {}; // Retorna cache antigo se houver erro
    }
}

function invalidarCacheFrontend() {
    console.log('Cache do frontend invalidado');
    classificacoesCache = null;
    cacheTimestamp = 0;
}

function detectarContraparte(historico) {
    if (!historico || typeof historico !== 'string') {
        return 'Não identificado';
    }
    
    const historicoUpper = historico.toUpperCase().trim();
    let contraparte = '';
    
    // Padrões para PIX
    if (historicoUpper.includes('PIX')) {
        let match = historico.match(/PIX\\s+(?:RECEBIDO\\s+DE|ENVIADO\\s+PARA|DE|PARA)\\s+([A-Za-zÀ-ÿ\\s]+)/i);
        if (match) {
            contraparte = match[1].trim();
        } else {
            match = historico.match(/PIX\\s*[-–]\\s*([A-Za-zÀ-ÿ\\s]+)/i);
            if (match) {
                contraparte = match[1].trim();
            }
        }
    }
    
    // Padrões para TED
    else if (historicoUpper.includes('TED')) {
        let match = historico.match(/TED\\s+(?:RECEBIDA\\s+DE|ENVIADA\\s+PARA|DE|PARA)\\s+([A-Za-zÀ-ÿ\\s&\\.]+)/i);
        if (match) {
            contraparte = match[1].trim();
        }
    }
    
    // Limpeza
    if (contraparte) {
        const palavrasRemover = ['REF', 'REFERENCIA', 'REFERÊNCIA', 'CPF', 'CNPJ'];
        palavrasRemover.forEach(palavra => {
            contraparte = contraparte.replace(new RegExp('\\b' + palavra + '\\b.*', 'gi'), '').trim();
        });
        
        contraparte = contraparte.toLowerCase().replace(/\b\w/g, l => l.toUpperCase());
    }
    
    return contraparte || 'Não identificado';
}

function filtrarTabela() {
    const banco = document.getElementById('filtro-banco').value;
    const tipo = document.getElementById('filtro-tipo').value;
    const busca = document.getElementById('filtro-busca').value.toLowerCase();
    
    const linhas = document.querySelectorAll('#tabela-pendentes tbody tr');
    
    linhas.forEach(linha => {
        const bancoDaLinha = linha.getAttribute('data-banco');
        const tipoDaLinha = linha.getAttribute('data-tipo');
        const historicoDaLinha = linha.getAttribute('data-historico');
        
        const mostraBanco = !banco || bancoDaLinha === banco;
        const mostraTipo = !tipo || tipoDaLinha === tipo;
        const mostraBusca = !busca || historicoDaLinha.includes(busca);
        
        linha.style.display = (mostraBanco && mostraTipo && mostraBusca) ? '' : 'none';
    });
}

function selecionarTodos() {
    const selectAll = document.getElementById('select-all');
    const checkboxes = document.querySelectorAll('.select-transacao');
    
    checkboxes.forEach(cb => {
        if (cb.closest('tr').style.display !== 'none') {
            cb.checked = selectAll.checked;
        }
    });
}

async function abrirModalConciliacao(transacaoId) {
    console.log('Abrindo modal para:', transacaoId);
    
    // 1. ABRIR MODAL IMEDIATAMENTE
    document.getElementById('transacao-id').value = transacaoId;
    document.getElementById('modal-conciliacao').style.display = 'block';
    document.body.style.overflow = 'hidden';
    
    // 2. Buscar dados da transação
    buscarDadosTransacao(transacaoId);
    
    // 3. Carregar classificações com cache simples
    try {
        const classificacoes = await obterClassificacoes();
        popularDropdown(classificacoes);
    } catch (error) {
        console.error('Erro ao carregar classificações:', error);
        document.getElementById('classificacao').innerHTML = '<option value="">Erro ao carregar</option>';
    }
}

function popularDropdown(classificacoes) {
    const select = document.getElementById('classificacao');
    select.innerHTML = '<option value="">Selecionar classificação...</option>';
    
    Object.keys(classificacoes).sort().forEach(classif => {
        const option = document.createElement('option');
        option.value = classif;
        option.textContent = classif;
        select.appendChild(option);
    });
    
    select.disabled = false;
}

async function buscarDadosTransacao(transacaoId) {
    try {
        const response = await fetch('/api/transacoes');
        const data = await response.json();
        const transacao = data.transacoes.find(t => t.id === transacaoId);
        if (transacao) {
            preencherModal(transacao);
        }
    } catch (error) {
        console.error('Erro ao buscar transação:', error);
    }
}

function preencherModal(transacao) {
    // Preencher o valor no cabeçalho
    const valorElement = document.getElementById('valor-amount');
    const valorFormatado = new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL',
        minimumFractionDigits: 2
    }).format(transacao.valor);
    
    valorElement.textContent = valorFormatado;
    
    // Adicionar classe CSS baseada no valor (positivo/negativo)
    valorElement.classList.remove('positivo', 'negativo');
    if (transacao.valor >= 0) {
        valorElement.classList.add('positivo');
    } else {
        valorElement.classList.add('negativo');
    }
    
    // Forma de pagamento
    const formaPagamentoSelect = document.getElementById('forma-pagamento');
    formaPagamentoSelect.value = transacao.forma_pagamento || 'Outros';
    
    // Banco origem
    const bancoSelect = document.getElementById('banco-origem');
    bancoSelect.value = transacao.banco_origem || transacao.banco;
    
    // Formatar e preencher data de pagamento
    let dataPagamento = transacao.data_pagamento || transacao.data;
    if (dataPagamento) {
        if (dataPagamento.includes('/')) {
            const parts = dataPagamento.split('/');
            if (parts.length === 3) {
                dataPagamento = `${parts[2]}-${parts[1].padStart(2, '0')}-${parts[0].padStart(2, '0')}`;
            }
        } else if (dataPagamento.includes('-') && dataPagamento.length === 10) {
            dataPagamento = dataPagamento;
        }
        document.getElementById('data-pagamento').value = dataPagamento;

        // Contraparte
        const contraparteInput = document.getElementById('contraparte');
        const contraparteDetectada = detectarContraparte(transacao.historico);
        contraparteInput.value = contraparteDetectada;
    }
}

function atualizarPlanoContas() {
    const classificacao = document.getElementById('classificacao').value;
    const planoContasSelect = document.getElementById('plano-contas');
    const itemSelect = document.getElementById('item');
    
    // Limpar e desabilitar plano de contas e itens
    planoContasSelect.innerHTML = '<option value="">Selecione um plano de contas...</option>';
    itemSelect.innerHTML = '<option value="">Selecione um plano de contas primeiro</option>';
    itemSelect.disabled = true;
    
    if (classificacao && classificacoesCache[classificacao]) {
        planoContasSelect.disabled = false;
        
        // Adicionar opções do plano de contas
        Object.keys(classificacoesCache[classificacao]).forEach(plano => {
            const option = document.createElement('option');
            option.value = plano;
            option.textContent = plano;
            planoContasSelect.appendChild(option);
        });
    } else {
        planoContasSelect.disabled = true;
        planoContasSelect.innerHTML = '<option value="">Selecione uma classificação primeiro</option>';
    }
}

function atualizarItens() {
    const classificacao = document.getElementById('classificacao').value;
    const planoContas = document.getElementById('plano-contas').value;
    const itemSelect = document.getElementById('item');
    
    // Limpar itens
    itemSelect.innerHTML = '<option value="">Selecione um item...</option>';
    
    if (classificacao && planoContas && classificacoesCache[classificacao] && classificacoesCache[classificacao][planoContas]) {
        itemSelect.disabled = false;
        
        // Adicionar opções dos itens
        classificacoesCache[classificacao][planoContas].forEach(item => {
            const option = document.createElement('option');
            option.value = item;
            option.textContent = item;
            itemSelect.appendChild(option);
        });
    } else {
        itemSelect.disabled = true;
        itemSelect.innerHTML = '<option value="">Selecione um plano de contas primeiro</option>';
    }
}

function fecharModal() {
    document.getElementById('modal-conciliacao').style.display = 'none';
    document.body.style.overflow = 'auto';

    // Limpar o valor do cabeçalho
    document.getElementById('valor-amount').textContent = 'R$ 0,00';
    document.getElementById('valor-amount').classList.remove('positivo', 'negativo');

    // Resetar campos editáveis
    document.getElementById('classificacao').value = '';
    document.getElementById('centro-custo').value = '';
    document.getElementById('nome-recebedor').value = '';
    document.getElementById('data-referencia').value = '';
    document.getElementById('observacoes').value = '';
    
    // Resetar dropdowns dependentes
    document.getElementById('plano-contas').disabled = true;
    document.getElementById('item').disabled = true;
    document.getElementById('plano-contas').innerHTML = '<option value="">Selecione uma classificação primeiro</option>';
    document.getElementById('item').innerHTML = '<option value="">Selecione um plano de contas primeiro</option>';
    document.getElementById('contraparte').value = '';
}

async function salvarConciliacao() {
    console.log('Iniciando salvamento da conciliacao...');
    
    const dados = {
        transacao_id: document.getElementById('transacao-id').value,
        classificacao: document.getElementById('classificacao').value,
        plano_contas: document.getElementById('plano-contas').value,
        item: document.getElementById('item').value,
        forma_pagamento: document.getElementById('forma-pagamento').value,
        banco_origem: document.getElementById('banco-origem').value,
        centro_custo: document.getElementById('centro-custo').value,
        nome_recebedor: document.getElementById('nome-recebedor').value,
        contraparte: document.getElementById('contraparte').value,
        data_pagamento: document.getElementById('data-pagamento').value,
        data_referencia: document.getElementById('data-referencia').value,
        observacoes: document.getElementById('observacoes').value,
    };

    // Validações
    if (!dados.transacao_id) {
        alert('ID da transacao nao encontrado!');
        return;
    }
    
    if (!dados.classificacao) {
        alert('Selecione uma classificacao!');
        document.getElementById('classificacao').focus();
        return;
    }
    
    if (!dados.plano_contas) {
        alert('Selecione um plano de contas!');
        document.getElementById('plano-contas').focus();
        return;
    }
    
    if (!dados.item) {
        alert('Selecione um item!');
        document.getElementById('item').focus();
        return;
    }
    
    if (!dados.centro_custo) {
        alert('Selecione um centro de custo!');
        document.getElementById('centro-custo').focus();
        return;
    }
    
    try {
        const response = await fetch('/api/conciliar', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(dados)
        });
        
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error('Erro HTTP ' + response.status + ': ' + errorText);
        }
        
        const result = await response.json();
        
        if (result.success) {
            invalidarCacheFrontend(); // INVALIDAR CACHE APÓS MUDANÇAS
            alert('Transacao conciliada com sucesso!');
            fecharModal();
            location.reload();
        } else {
            alert('Erro: ' + (result.message || 'Erro desconhecido'));
        }
        
    } catch (error) {
        console.error('Erro na requisicao:', error);
        alert('Erro ao conciliar: ' + error.message);
    }
}

async function conciliarSelecionados() {
    const selecionados = Array.from(document.querySelectorAll('.select-transacao:checked')).map(cb => cb.value);
    
    if (selecionados.length === 0) {
        alert('Selecione pelo menos uma transacao');
        return;
    }
    
    if (!confirm(`Deseja conciliar ${selecionados.length} transacao(oes)?`)) {
        return;
    }
    
    try {
        const response = await fetch('/api/conciliar-lote', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({transacao_ids: selecionados})
        });
        
        const result = await response.json();
        
        if (result.success) {
            invalidarCacheFrontend(); // INVALIDAR CACHE APÓS MUDANÇAS
            alert(`${result.total_conciliadas} transacao(oes) conciliada(s)!`);
            location.reload();
        } else {
            alert('Erro: ' + result.message);
        }
        
    } catch (error) {
        alert('Erro: ' + error.message);
    }
}

// Event listeners
document.addEventListener('click', function(event) {
    const modal = document.getElementById('modal-conciliacao');
    if (event.target === modal) {
        fecharModal();
    }
});

document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        fecharModal();
    }
});

// Sistema de autenticação
function adjustBodyPadding() {
    const authHeader = document.getElementById('auth-header');
    if (authHeader.style.display !== 'none') {
        document.body.style.paddingTop = '60px';
    } else {
        document.body.style.paddingTop = '0px';
    }
}

async function checkAuth() {
    console.log('Verificando autenticação...');
    
    const token = localStorage.getItem('access_token');
    const userData = localStorage.getItem('user');
    
    if (!token || !userData) {
        console.log('Sem token/dados, redirecionando para login');
        window.location.href = '/login';
        return;
    }
    
    try {
        const user = JSON.parse(userData);
        console.log('Usuário autenticado:', user);
        
        // Atualizar header
        document.getElementById('auth-user-name').textContent = user.nome || 'Usuário';
        document.getElementById('auth-user-cargo').textContent = user.cargo || 'operador';
        
        // Mostrar header e esconder loading
        document.getElementById('auth-header').style.display = 'flex';
        document.getElementById('auth-loading').style.display = 'none';
        
        // Ajustar padding do body
        adjustBodyPadding();
        
        console.log('Interface de autenticação carregada!');
        
    } catch (error) {
        console.error('Erro ao processar dados do usuário:', error);
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
        window.location.href = '/login';
    }
}

function authLogout() {
    if (confirm('Deseja realmente sair do sistema?')) {
        console.log('Fazendo logout...');
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
        window.location.href = '/login';
    }
}

// Executar verificação de auth quando a página carregar
document.addEventListener('DOMContentLoaded', function() {
    checkAuth();
});

// Adicionar animação de loading
const style = document.createElement('style');
style.textContent = `
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
`;
document.head.appendChild(style);
</script>
    </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

@app.get("/conciliados")
def listar_conciliados():
    """Listar transações já conciliadas do Supabase"""
    try:
        if not supabase:
            conciliados = []
        else:
            # Buscar transações conciliadas do Supabase
            result = supabase.admin_client.table("transacoes").select(
            "*,classificacao:classificacao_id(*),plano_contas:plano_contas_id(*),item:item_id(*)"
            ).eq("status", "CONCILIADO").order("conciliado_em", desc=True).execute()
            
            print("🔍 DEBUG - Resultado da query:")
            if result.data:
                print(f"Total de transações: {len(result.data)}")
                primeira_transacao = result.data[0]
                print(f"Primeira transação: {primeira_transacao}")
                print(f"Classificacao field: {primeira_transacao.get('classificacao')}")
                print(f"Plano_contas field: {primeira_transacao.get('plano_contas')}")
                print(f"Item field: {primeira_transacao.get('item')}")
            
            conciliados = []
            for transacao in result.data:
            # Extrair nomes das tabelas relacionadas
                if transacao.get('classificacao') and transacao['classificacao']:
                    transacao['classificacao_nome'] = transacao['classificacao']['nome']
                else:
                    transacao['classificacao_nome'] = '-'
                
                if transacao.get('plano_contas') and transacao['plano_contas']:
                    transacao['plano_contas_nome'] = transacao['plano_contas']['nome']
                else:
                    transacao['plano_contas_nome'] = '-'
                
                if transacao.get('item') and transacao['item']:
                    transacao['item_nome'] = transacao['item']['nome']
                else:
                    transacao['item_nome'] = '-'
            
                conciliados.append(transacao)
    
    except Exception as e:
        logger.error(f"❌ Erro ao buscar conciliados: {str(e)}")
        conciliados = []
    
    total_conciliados = len(conciliados)
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Transações Conciliadas</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {{
                /* Design System - Colors - MANTENDO ORIGINAL */
                --primary-50: #eff6ff;
                --primary-500: #3b82f6;
                --primary-600: #2563eb;
                --primary-700: #1d4ed8;
                
                --success-50: #f0fdf4;
                --success-100: #dcfce7;
                --success-500: #22c55e;
                --success-600: #16a34a;
                
                --danger-500: #ef4444;
                
                --gray-50: #f9fafb;
                --gray-100: #f3f4f6;
                --gray-200: #e5e7eb;
                --gray-300: #d1d5db;
                --gray-400: #9ca3af;
                --gray-500: #6b7280;
                --gray-600: #4b5563;
                --gray-700: #374151;
                --gray-800: #1f2937;
                --gray-900: #111827;
                
                --space-1: 0.25rem;
                --space-2: 0.5rem;
                --space-3: 0.75rem;
                --space-4: 1rem;
                --space-5: 1.25rem;
                --space-6: 1.5rem;
                --space-8: 2rem;
                --space-10: 2.5rem;
                
                --radius-lg: 0.75rem;
                --radius-xl: 1rem;
                --radius-2xl: 1.5rem;
                
                --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
                --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
                --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
            }}
            
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: var(--gray-50);
                min-height: 100vh;
                color: var(--gray-900);
                line-height: 1.6;
                padding-top: 60px;
            }}
            
            .container {{
                max-width: 1600px;
                margin: 0 auto;
                padding: var(--space-6);
            }}
            
            /* Header - MANTENDO ESTILO ORIGINAL */
            .header {{
                background: white;
                border-radius: var(--radius-2xl);
                padding: var(--space-8);
                margin-bottom: var(--space-6);
                box-shadow: var(--shadow-lg);
                border: 1px solid var(--gray-200);
                display: flex;
                justify-content: space-between;
                align-items: center;
                flex-wrap: wrap;
                gap: var(--space-4);
            }}
            
            .header-content h1 {{
                font-size: 2rem;
                font-weight: 700;
                color: var(--gray-900);
                margin-bottom: var(--space-2);
                display: flex;
                align-items: center;
                gap: var(--space-3);
            }}
            
            .header-content p {{
                color: var(--gray-600);
                font-size: 1rem;
            }}
            
            /* Stats Summary - MANTENDO ESTILO ORIGINAL */
            .stats-summary {{
                background: linear-gradient(135deg, var(--success-500), var(--success-600));
                border-radius: var(--radius-2xl);
                padding: var(--space-8);
                margin-bottom: var(--space-6);
                color: white;
                box-shadow: var(--shadow-lg);
            }}
            
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: var(--space-6);
                margin-top: var(--space-6);
            }}
            
            .stat-item {{
                text-align: center;
            }}
            
            .stat-number {{
                font-size: 2.5rem;
                font-weight: 700;
                margin-bottom: var(--space-2);
                display: block;
            }}
            
            .stat-label {{
                font-size: 0.875rem;
                opacity: 0.9;
                font-weight: 500;
            }}
            
            /* Table Container - MANTENDO ESTILO ORIGINAL */
            .table-container {{
                background: white;
                border-radius: var(--radius-2xl);
                overflow: hidden;
                box-shadow: var(--shadow-lg);
                border: 1px solid var(--gray-200);
                overflow-x: auto;
            }}
            
            table {{
                width: 100%;
                border-collapse: collapse;
                min-width: 1400px;
            }}
            
            th {{
                background: var(--success-600);
                color: white;
                padding: var(--space-4);
                text-align: left;
                font-weight: 600;
                font-size: 0.875rem;
                letter-spacing: 0.025em;
                white-space: nowrap;
            }}
            
            td {{
                padding: var(--space-3);
                border-bottom: 1px solid var(--gray-200);
                font-size: 0.875rem;
                vertical-align: top;
            }}
            
            tr:hover {{
                background: var(--gray-50);
            }}
            
            tr:last-child td {{
                border-bottom: none;
            }}
            
            /* Values - MANTENDO ESTILO ORIGINAL */
            .valor-positivo {{
                color: var(--success-600);
                font-weight: 700;
            }}
            
            .valor-negativo {{
                color: var(--danger-500);
                font-weight: 700;
            }}
            
            /* Status - MANTENDO ESTILO ORIGINAL */
            .status-conciliado {{
                background: var(--success-100);
                color: var(--success-600);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                font-size: 0.75rem;
                font-weight: 700;
                letter-spacing: 0.025em;
                display: inline-block;
            }}
            
            /* Button - MANTENDO ESTILO ORIGINAL */
            .btn {{
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-3) var(--space-6);
                border: none;
                border-radius: var(--radius-lg);
                font-weight: 600;
                font-size: 0.875rem;
                text-decoration: none;
                cursor: pointer;
                transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
                box-shadow: var(--shadow-sm);
                font-family: inherit;
            }}
            
            .btn-primary {{
                background: var(--primary-600);
                color: white;
            }}
            
            .btn-primary:hover {{
                background: var(--primary-700);
                transform: translateY(-1px);
                box-shadow: var(--shadow-md);
            }}

            /* Header de autenticação - ADICIONANDO */
            #auth-header {{
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                background: linear-gradient(135deg, #3b82f6, #2563eb);
                color: white;
                padding: 0.75rem 1.5rem;
                display: none;
                justify-content: space-between;
                align-items: center;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                z-index: 1000;
                font-family: 'Inter', Arial, sans-serif;
            }}
            
            #auth-loading {{
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(255,255,255,0.95);
                display: flex;
                justify-content: center;
                align-items: center;
                flex-direction: column;
                gap: 1rem;
                z-index: 2000;
                font-family: 'Inter', Arial, sans-serif;
            }}
            
            /* Responsive - MANTENDO ORIGINAL */
            @media (max-width: 768px) {{
                .container {{
                    padding: var(--space-4);
                }}
                
                .header {{
                    flex-direction: column;
                    align-items: stretch;
                    text-align: center;
                }}
                
                .stats-grid {{
                    grid-template-columns: repeat(2, 1fr);
                    gap: var(--space-4);
                }}
                
                .stat-number {{
                    font-size: 2rem;
                }}
                
                table {{
                    font-size: 0.75rem;
                    min-width: 1200px;
                }}
                
                th, td {{
                    padding: var(--space-2);
                }}
            
</style>
</head>
    <body>
        <!-- Loading overlay para autenticação -->
        <div id="auth-loading">
            <div style="
                width: 40px; 
                height: 40px; 
                border: 4px solid #e5e7eb; 
                border-top: 4px solid #3b82f6; 
                border-radius: 50%; 
                animation: spin 1s linear infinite;
            "></div>
            <div style="font-size: 1.1rem; color: #4b5563;">🔄 Verificando autenticação...</div>
        </div>
        
        <!-- Header de autenticação -->
        <div id="auth-header">
            <div style="display: flex; align-items: center; gap: 1rem;">
                <span>👤 Olá, <strong id="auth-user-name">Usuário</strong>!</span>
                <span style="background: rgba(255,255,255,0.2); padding: 0.25rem 0.75rem; border-radius: 12px; font-size: 0.875rem;" id="auth-user-cargo">...</span>
            </div>
            <button onclick="authLogout()" style="
                background: #ef4444; 
                color: white; 
                border: none; 
                padding: 0.5rem 1rem; 
                border-radius: 6px; 
                cursor: pointer; 
                font-weight: 600;
                font-size: 0.875rem;
            ">
                🚪 Sair
            </button>
        </div>

        <div class="container">
            <!-- Header -->
            <header class="header">
                <div class="header-content">
                    <h1>
                        <span>✅</span>
                        Transações Conciliadas
                    </h1>
                    <p>Total de {total_conciliados} transações processadas e conciliadas</p>
                </div>
                <a href="/" class="btn btn-primary">
                    <span>🏠</span>
                    Voltar ao Início
                </a>
            </header>
            
            <!-- Stats Summary -->
            <section class="stats-summary">
                <h2 style="font-size: 1.5rem; font-weight: 600; margin-bottom: var(--space-2);">📊 Resumo das Conciliações</h2>
                <p style="opacity: 0.9;">Visão geral das transações processadas com sucesso</p>
                
                <div class="stats-grid">
                    <div class="stat-item">
                        <span class="stat-number">{total_conciliados}</span>
                        <span class="stat-label">Transações Conciliadas</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-number">R$ {sum(float(t.get('valor', 0)) for t in conciliados):,.2f}</span>
                        <span class="stat-label">Valor Total Processado</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-number">{len([t for t in conciliados if float(t.get('valor', 0)) > 0])}</span>
                        <span class="stat-label">Entradas (+)</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-number">{len([t for t in conciliados if float(t.get('valor', 0)) < 0])}</span>
                        <span class="stat-label">Saídas (-)</span>
                    </div>
                </div>
            </section>
            
            <!-- Table -->
            <section class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Banco</th>
                            <th>Data</th>
                            <th>Histórico</th>
                            <th>Valor</th>
                            <th>Classificação</th>
                            <th>Plano de Contas</th>
                            <th>Item</th>
                            <th>Forma Pagamento</th>
                            <th>Centro de Custo</th>
                            <th>Recebedor</th>
                            <th>Data Ref.</th>
                            <th>Status</th>
                            <th>Conciliado</th>
                        </tr>
                    </thead>
                    <tbody>"""

    if not conciliados:
        html_content += """
                        <tr>
                            <td colspan="13" style="text-align: center; padding: var(--space-8); color: var(--gray-600);">
                                <div style="display: flex; flex-direction: column; align-items: center; gap: 1rem;">
                                    <span style="font-size: 3rem;">✅</span>
                                    <div>
                                        <h3 style="color: var(--gray-800); margin-bottom: 0.5rem;">Nenhuma transação conciliada</h3>
                                        <p>Ainda não há transações conciliadas no sistema.</p>
                                    </div>
                                    <a href="/pendentes" class="btn btn-primary">📋 Ver Pendentes</a>
                                </div>
                            </td>
                        </tr>"""
    else:
        for transacao in conciliados:
            # Formatar data brasileira
            try:
                if isinstance(transacao.get('data'), str):
                    if transacao['data'].count('-') == 2:  # formato yyyy-mm-dd
                        data_obj = datetime.strptime(transacao['data'], '%Y-%m-%d')
                        data_formatada = data_obj.strftime('%d/%m/%Y')
                    else:
                        data_formatada = transacao['data']
                else:
                    data_formatada = transacao.get('data', '')
            except:
                data_formatada = transacao.get('data', '')

            valor_class = "valor-positivo" if float(transacao.get('valor', 0)) >= 0 else "valor-negativo"
            valor_float = float(transacao.get('valor', 0))

            # Formatar data de conciliação
            data_conciliacao = ''
            if transacao.get('conciliado_em'):
                try:
                    if 'T' in transacao['conciliado_em']:
                        data_obj = datetime.fromisoformat(transacao['conciliado_em'].replace('Z', '+00:00'))
                        data_conciliacao = data_obj.strftime('%d/%m/%Y')
                    else:
                        data_conciliacao = transacao['conciliado_em']
                except:
                    data_conciliacao = transacao['conciliado_em'][:10] if transacao['conciliado_em'] else ''

            data_referencia = transacao.get('data_referencia', '-') if transacao.get('data_referencia') else '-'
            
            html_content += f"""
                        <tr>
                            <td><strong>{transacao.get('banco', '')}</strong></td>
                            <td style="white-space: nowrap;">{data_formatada}</td>
                            <td title="{transacao.get('historico', '')}" style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{transacao.get('historico', '')[:40]}{'...' if len(transacao.get('historico', '')) > 40 else ''}</td>
                            <td class="{valor_class}" style="white-space: nowrap;">R$ {valor_float:,.2f}</td>
                            <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis;">{transacao.get('classificacao_nome', '-')}</td>
                        <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis;">{transacao.get('plano_contas_nome', '-')}</td>
                        <td style="max-width: 120px; overflow: hidden; text-overflow: ellipsis;">{transacao.get('item_nome', '-')}</td>
                            <td>{transacao.get('forma_pagamento', '-')}</td>
                            <td>{transacao.get('centro_custo', '-')}</td>
                            <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis;" title="{transacao.get('nome_recebedor', '-')}">{transacao.get('nome_recebedor', '-')[:20]}{'...' if len(str(transacao.get('nome_recebedor', ''))) > 20 else ''}</td>
                            <td style="white-space: nowrap;">{data_referencia}</td>
                            <td><span class="status-conciliado">CONCILIADO</span></td>
                            <td style="white-space: nowrap;">{data_conciliacao}</td>
                        </tr>"""

    html_content += """
                    </tbody>
                </table>
            </section>
        </div>

        <script>
        // === SISTEMA DE AUTENTICAÇÃO ===
        
        // Adicionar espaço no topo quando o header aparecer
        function adjustBodyPadding() {
            const authHeader = document.getElementById('auth-header');
            if (authHeader.style.display !== 'none') {
                document.body.style.paddingTop = '60px';
            } else {
                document.body.style.paddingTop = '0px';
            }
        }
        
        // Verificar autenticação
        async function checkAuth() {
            console.log('🔍 Verificando autenticação...');
            
            const token = localStorage.getItem('access_token');
            const userData = localStorage.getItem('user');
            
            if (!token || !userData) {
                console.log('❌ Sem token/dados, redirecionando para login');
                window.location.href = '/login';
                return;
            }
            
            try {
                const user = JSON.parse(userData);
                console.log('✅ Usuário autenticado:', user);
                
                // Atualizar header
                document.getElementById('auth-user-name').textContent = user.nome || 'Usuário';
                document.getElementById('auth-user-cargo').textContent = user.cargo || 'operador';
                
                // Mostrar header e esconder loading
                document.getElementById('auth-header').style.display = 'flex';
                document.getElementById('auth-loading').style.display = 'none';
                
                // Ajustar padding do body
                adjustBodyPadding();
                
                console.log('✅ Interface de autenticação carregada!');
                
            } catch (error) {
                console.error('❌ Erro ao processar dados do usuário:', error);
                localStorage.removeItem('access_token');
                localStorage.removeItem('user');
                window.location.href = '/login';
            }
        }
        
        // Logout
        function authLogout() {
            if (confirm('Deseja realmente sair do sistema?')) {
                console.log('🚪 Fazendo logout...');
                localStorage.removeItem('access_token');
                localStorage.removeItem('user');
                window.location.href = '/login';
            }
        }
        
        // Executar verificação de auth quando a página carregar
        document.addEventListener('DOMContentLoaded', function() {
            checkAuth();
        });

        // Adicionar animação de loading
        const style = document.createElement('style');
        style.textContent = `
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
        `;
        document.head.appendChild(style);
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

@app.get("/debug")
async def debug_info():
    """Informações de debug"""
    try:
        if not supabase:
            return {'error': 'Supabase não configurado'}
        
        # Obter stats do banco
        transacoes_result = supabase.admin_client.table("transacoes").select("id").execute()
        extratos_result = supabase.admin_client.table("extratos").select("id").execute()
        
        return {
            'total_transacoes': len(transacoes_result.data),
            'total_extratos': len(extratos_result.data),
            'database_status': 'connected'
        }
    except Exception as e:
        return {'error': str(e)}

import json

@app.get("/api/stats")
async def get_stats():
    cached_stats = cache.get('main_stats', 'stats')
    if cached_stats:
        logger.info("Stats do cache")
        cached_stats = json.loads(cached_stats)  # 🔥 garante que seja dict
        return cached_stats
    
    """Obter estatísticas do banco de dados Supabase"""
    try:
        if not supabase:
            return {
                'total_transacoes': 0,
                'pendentes': 0,
                'conciliados': 0,
                'valor_total': 0
            }
        
        logger.info("📊 Calculando estatísticas do Supabase...")
        
        all_transacoes = supabase.admin_client.table("transacoes").select("status, valor").execute()
        
        total_transacoes = len(all_transacoes.data)
        pendentes = len([t for t in all_transacoes.data if t.get('status') == 'PENDENTE'])
        conciliados = len([t for t in all_transacoes.data if t.get('status') == 'CONCILIADO'])
        valor_total = sum(float(t.get('valor') or 0) for t in all_transacoes.data)
        
        stats_data = {
            'total_transacoes': total_transacoes,
            'pendentes': pendentes,
            'conciliados': conciliados,
            'valor_total': valor_total
        }

        cache.set('main_stats', json.dumps(stats_data), 'stats')  # 🔥 salva como string JSON
        return stats_data
        
    except Exception as e:
        logger.error(f"❌ Erro ao calcular stats: {str(e)}")
        return {
            'total_transacoes': 0,
            'pendentes': 0,
            'conciliados': 0,
            'valor_total': 0
        }



@app.get("/api/transacoes")
async def listar_transacoes(status: Optional[str] = None, banco: Optional[str] = None):
    """
    Lista transações com lookups otimizados
    """
    logger.info(f"🔍 Consultando transações - Status: {status}, Banco: {banco}")
    
    try:
        # Garante que lookups estejam em cache
        lookups_cache = cache.get_all_lookups()
        if not lookups_cache:
            await carregar_lookups_cache()
        
        # Buscar transações usando supabase (não supabase_pool)
        query = supabase.admin_client.table("transacoes").select("*")
        
        if status:
            query = query.eq("status", status)
            
        if banco:
            query = query.eq("banco", banco)
        
        result = query.order("created_at", desc=True).limit(500).execute()
        rows = result.data
        
        transacoes = []
        lookup_stats = {'classificacao': 0, 'plano': 0, 'item': 0}
        
        logger.info(f"📊 Encontradas {len(rows)} transações")
        
        for row in rows:
            transacao = dict(row)
            
            # Lookups otimizados (cache-first)
            if transacao.get('classificacao_id'):
                nome_classificacao = cache.get_classificacao_by_id(transacao['classificacao_id'])
                if nome_classificacao:
                    transacao['classificacao'] = nome_classificacao['nome']
                    lookup_stats['classificacao'] += 1
            
            if transacao.get('plano_contas_id'):
                nome_plano = cache.get_plano_by_id(transacao['plano_contas_id'])
                if nome_plano:
                    transacao['plano_contas'] = nome_plano['nome'] 
                    lookup_stats['plano'] += 1
            
            if transacao.get('item_id'):
                nome_item = cache.get_item_by_id(transacao['item_id'])
                if nome_item:
                    transacao['item'] = nome_item['nome']
                    lookup_stats['item'] += 1
            
            transacoes.append(transacao)
        
        logger.info(f"✅ Processadas {len(transacoes)} transações com lookup otimizado (cache hits: classificação={lookup_stats['classificacao']}, plano={lookup_stats['plano']}, item={lookup_stats['item']})")
        
        return {"success": True, "transacoes": transacoes, "total": len(transacoes)}
        
    except Exception as e:
        logger.error(f"❌ Erro ao listar transações: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
    
@app.get("/api/debug/transacoes")
async def debug_transacoes():
    """Debug para ver estrutura das transações"""
    try:
        if not supabase:
            return {"error": "Supabase não configurado"}
        
        logger.info("🔍 Debug: Consultando transações...")
        
        # Buscar apenas algumas transações para debug
        result = supabase.admin_client.table("transacoes").select("*").limit(5).execute()
        
        debug_info = {
            "total_transacoes": len(result.data),
            "transacoes_sample": []
        }
        
        for t in result.data:
            transacao_debug = {
                "id": t.get('id'),
                "status": t.get('status'),
                "classificacao_id": t.get('classificacao_id'),
                "plano_contas_id": t.get('plano_contas_id'), 
                "item_id": t.get('item_id'),
                "historico_preview": t.get('historico', '')[:50] + '...'
            }
            
            # Tentar buscar nomes se tem IDs
            if t.get('classificacao_id'):
                try:
                    classif_result = supabase.admin_client.table("classificacoes").select("nome").eq("id", t['classificacao_id']).execute()
                    transacao_debug['classificacao_nome'] = classif_result.data[0]['nome'] if classif_result.data else 'Não encontrado'
                except Exception as e:
                    transacao_debug['classificacao_erro'] = str(e)
            
            debug_info["transacoes_sample"].append(transacao_debug)
        
        return debug_info
        
    except Exception as e:
        logger.error(f"❌ Erro no debug: {str(e)}")
        return {"error": str(e)}

@app.get("/api/debug/classificacoes")
async def debug_classificacoes():
    """Debug para ver estrutura das classificações"""
    try:
        if not supabase:
            return {"error": "Supabase não configurado"}
        
        # Buscar classificações
        classifs = supabase.admin_client.table("classificacoes").select("*").execute()
        planos = supabase.admin_client.table("planos_contas").select("*").execute()  
        itens = supabase.admin_client.table("itens").select("*").execute()
        
        return {
            "classificacoes": len(classifs.data),
            "planos": len(planos.data),
            "itens": len(itens.data),
            "sample_classificacao": classifs.data[0] if classifs.data else None,
            "sample_plano": planos.data[0] if planos.data else None,
            "sample_item": itens.data[0] if itens.data else None
        }
        
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/conciliar")
async def conciliar_transacao(dados: ConciliacaoRequest):
    """Conciliar transação com estrutura normalizada"""
    try:
        if not supabase:
            raise HTTPException(status_code=500, detail="Banco não configurado")
        
        logger.info(f"🔖 Conciliando transação: {dados.transacao_id}")
        
        # Buscar transação
        result = supabase.admin_client.table("transacoes").select("*").eq("id", dados.transacao_id).execute()
        
        if not result.data:
            logger.error(f"❌ Transação não encontrada: {dados.transacao_id}")
            raise HTTPException(status_code=404, detail="Transação não encontrada")
        
        transacao = result.data[0]
        
        if transacao.get('status') == 'CONCILIADO':
            logger.warning(f"⚠️ Transação já conciliada: {dados.transacao_id}")
            raise HTTPException(status_code=400, detail="Transação já está conciliada")
        
        # 🔍 BUSCAR UUIDs das classificações (com tratamento de erro)
        logger.info(f"🔍 Buscando classificação: {dados.classificacao}")
        
        # 1. Buscar classificação
        classif_result = supabase.admin_client.table("classificacoes").select("id").eq("nome", dados.classificacao).eq("ativo", True).execute()
        if not classif_result.data:
            logger.error(f"❌ Classificação não encontrada: {dados.classificacao}")
            raise HTTPException(status_code=400, detail=f"Classificação '{dados.classificacao}' não encontrada")
        classif_id = classif_result.data[0]["id"]
        logger.info(f"✅ Classificação encontrada: {classif_id}")
        
        # 2. Buscar plano de contas
        logger.info(f"🔍 Buscando plano: {dados.plano_contas}")
        plano_result = supabase.admin_client.table("planos_contas").select("id").eq("classificacao_id", classif_id).eq("nome", dados.plano_contas).eq("ativo", True).execute()
        if not plano_result.data:
            logger.error(f"❌ Plano não encontrado: {dados.plano_contas}")
            raise HTTPException(status_code=400, detail=f"Plano de contas '{dados.plano_contas}' não encontrado na classificação '{dados.classificacao}'")
        plano_id = plano_result.data[0]["id"]
        logger.info(f"✅ Plano encontrado: {plano_id}")
        
        # 3. Buscar item
        logger.info(f"🔍 Buscando item: {dados.item}")
        item_result = supabase.admin_client.table("itens").select("id").eq("plano_contas_id", plano_id).eq("nome", dados.item).eq("ativo", True).execute()
        if not item_result.data:
            logger.error(f"❌ Item não encontrado: {dados.item}")
            raise HTTPException(status_code=400, detail=f"Item '{dados.item}' não encontrado no plano '{dados.plano_contas}'")
        item_id = item_result.data[0]["id"]
        logger.info(f"✅ Item encontrado: {item_id}")
        
        # 4. Buscar usuário atual (temporariamente usar admin)
        user_result = supabase.admin_client.table("usuarios").select("id").eq("cargo", "admin").eq("ativo", True).limit(1).execute()
        user_id = user_result.data[0]["id"] if user_result.data else None
        logger.info(f"✅ Usuário para conciliação: {user_id}")
        
        # ✅ ATUALIZAR COM UUIDs
        update_data = {
            'status': 'CONCILIADO',
            'classificacao_id': classif_id,      # UUID em vez de string
            'plano_contas_id': plano_id,         # UUID em vez de string  
            'item_id': item_id,                  # UUID em vez de string
            'forma_pagamento': dados.forma_pagamento,
            'banco_origem': dados.banco_origem,
            'centro_custo': dados.centro_custo,
            'nome_recebedor': dados.nome_recebedor,
            'contraparte': dados.contraparte,
            'data_pagamento': dados.data_pagamento,
            'data_referencia': dados.data_referencia if dados.data_referencia else None,
            'observacoes': dados.observacoes,
            'conciliado_por': user_id,           # UUID do usuário
            'conciliado_em': datetime.now().isoformat(),
        }
        
        logger.info(f"💾 Atualizando transação com dados: {update_data}")
        
        update_result = supabase.admin_client.table("transacoes").update(update_data).eq("id", dados.transacao_id).execute()
        
        if not update_result.data:
            logger.error("❌ Nenhum dado retornado do update")
            raise HTTPException(status_code=500, detail="Erro ao atualizar transação")
        
        logger.info(f"✅ Transação {dados.transacao_id} conciliada com sucesso")

        # 🟢 Invalida cache após sucesso
        cache.invalidate_pattern('*', 'transacoes')
        cache.invalidate_pattern('*', 'stats')
        
        return {'success': True, 'message': 'Transação conciliada com sucesso'}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao conciliar transação: {str(e)}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

async def carregar_lookups_cache():
    """
    Carrega todos os lookups uma única vez para o cache
    """
    logger.info("🔄 Carregando lookups para cache...")
    
    try:
        if not supabase or not hasattr(supabase, 'admin_client') or not supabase.admin_client:
            logger.warning("⚠️ Supabase não disponível, pulando carregamento de lookups")
            return False
        # Busca todos os dados estruturais de uma vez usando supabase (não supabase_pool)
        classificacoes_result = supabase.admin_client.table("classificacoes").select("id, nome").eq("ativo", True).order("nome").execute()
        classificacoes = classificacoes_result.data
        
        planos_result = supabase.admin_client.table("planos_contas").select("id, nome, classificacao_id").eq("ativo", True).order("nome").execute()
        planos = planos_result.data
        
        itens_result = supabase.admin_client.table("itens").select("id, nome, plano_contas_id").eq("ativo", True).order("nome").execute()
        itens = itens_result.data
        
        # Armazena no cache
        cache.set_all_lookups(classificacoes, planos, itens)
        
        logger.info(f"✅ Lookups carregados: {len(classificacoes)} classificações, {len(planos)} planos, {len(itens)} itens")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro ao carregar lookups: {e}")
        return False

async def obter_lookup_classificacao(id_classificacao: int) -> Optional[str]:
    """
    Busca nome da classificação (cache-first)
    """
    # Tenta cache primeiro
    classificacao = cache.get_classificacao_by_id(id_classificacao)
    if classificacao:
        return classificacao['nome']
    
    # Cache miss - recarrega todos os lookups
    logger.debug(f"🔄 Cache miss para classificação {id_classificacao}, recarregando lookups...")
    await carregar_lookups_cache()
    
    # Tenta novamente
    classificacao = cache.get_classificacao_by_id(id_classificacao)
    return classificacao['nome'] if classificacao else None

async def obter_lookup_plano(id_plano: int) -> Optional[str]:
    """
    Busca nome do plano (cache-first)
    """
    # Tenta cache primeiro
    plano = cache.get_plano_by_id(id_plano)
    if plano:
        return plano['nome']
    
    # Cache miss - recarrega todos os lookups
    logger.debug(f"🔄 Cache miss para plano {id_plano}, recarregando lookups...")
    await carregar_lookups_cache()
    
    # Tenta novamente
    plano = cache.get_plano_by_id(id_plano)
    return plano['nome'] if plano else None

async def obter_lookup_item(id_item: int) -> Optional[str]:
    """
    Busca nome do item (cache-first)
    """
    # Tenta cache primeiro
    item = cache.get_item_by_id(id_item)
    if item:
        return item['nome']
    
    # Cache miss - recarrega todos os lookups
    logger.debug(f"🔄 Cache miss para item {id_item}, recarregando lookups...")
    await carregar_lookups_cache()
    
    # Tenta novamente
    item = cache.get_item_by_id(id_item)
    return item['nome'] if item else None


@app.get("/relatorios")
async def relatorios():
    """Página de relatórios aprimorada - SEM CORES PURPLE"""
    html_content = """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Relatórios - Sistema de Conciliação</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
        <style>
            :root {
                /* Enhanced Color System - SEM PURPLE */
                --primary-50: #eff6ff;
                --primary-100: #dbeafe;
                --primary-200: #bfdbfe;
                --primary-500: #3b82f6;
                --primary-600: #2563eb;
                --primary-700: #1d4ed8;
                
                --success-50: #f0fdf4;
                --success-100: #dcfce7;
                --success-500: #22c55e;
                --success-600: #16a34a;
                --success-700: #15803d;
                
                --warning-50: #fffbeb;
                --warning-100: #fef3c7;
                --warning-500: #f59e0b;
                --warning-600: #d97706;
                
                /* NOVA PALETA: Azul Slate (substitui o purple) */
                --slate-50: #f8fafc;
                --slate-100: #f1f5f9;
                --slate-500: #64748b;
                --slate-600: #475569;
                --slate-700: #334155;
                --slate-800: #1e293b;
                --slate-900: #0f172a;
                
                --emerald-50: #ecfdf5;
                --emerald-500: #10b981;
                --emerald-600: #059669;
                
                --rose-50: #fef2f2;
                --rose-500: #ef4444;
                --rose-600: #dc2626;
                
                --gray-50: #f9fafb;
                --gray-100: #f3f4f6;
                --gray-200: #e5e7eb;
                --gray-300: #d1d5db;
                --gray-400: #9ca3af;
                --gray-500: #6b7280;
                --gray-600: #4b5563;
                --gray-700: #374151;
                --gray-800: #1f2937;
                --gray-900: #111827;
                
                --space-2: 0.5rem;
                --space-3: 0.75rem;
                --space-4: 1rem;
                --space-5: 1.25rem;
                --space-6: 1.5rem;
                --space-8: 2rem;
                --space-10: 2.5rem;
                --space-12: 3rem;
                
                --radius-lg: 0.75rem;
                --radius-xl: 1rem;
                --radius-2xl: 1.5rem;
                --radius-3xl: 2rem;
                
                --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
                --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
                --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
                --shadow-xl: 0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1);
                --shadow-2xl: 0 25px 50px -12px rgb(0 0 0 / 0.25);
            }
            
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, var(--primary-50) 0%, var(--slate-50) 50%, var(--emerald-50) 100%);
                min-height: 100vh;
                color: var(--gray-900);
                line-height: 1.6;
            }
            
            .container {
                max-width: 1400px;
                margin: 0 auto;
                padding: var(--space-6);
            }
            
            /* Enhanced Header */
            .header {
                background: linear-gradient(135deg, rgba(255,255,255,0.95) 0%, rgba(255,255,255,0.8) 100%);
                backdrop-filter: blur(20px);
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: var(--radius-3xl);
                padding: var(--space-12);
                margin-bottom: var(--space-8);
                box-shadow: var(--shadow-2xl);
                text-align: center;
                position: relative;
                overflow: hidden;
            }
            
            .header::before {
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent);
                animation: shimmer 3s infinite;
            }
            
            @keyframes shimmer {
                0% { left: -100%; }
                100% { left: 100%; }
            }
            
            .header h1 {
                font-size: 3rem;
                font-weight: 900;
                background: linear-gradient(135deg, var(--primary-600), var(--slate-700), var(--emerald-600));
                background-clip: text;
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: var(--space-4);
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-4);
                position: relative;
                z-index: 1;
            }
            
            .header p {
                font-size: 1.125rem;
                color: var(--gray-600);
                margin-bottom: var(--space-6);
                font-weight: 500;
                position: relative;
                z-index: 1;
            }
            
            /* Enhanced Stats Cards */
            .quick-stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: var(--space-8);
                margin-bottom: var(--space-8);
            }
            
            .stat-card {
                background: linear-gradient(135deg, rgba(255,255,255,0.9) 0%, rgba(255,255,255,0.7) 100%);
                backdrop-filter: blur(20px);
                border: 1px solid rgba(255,255,255,0.3);
                border-radius: var(--radius-3xl);
                padding: var(--space-10);
                box-shadow: var(--shadow-xl);
                text-align: center;
                transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
                position: relative;
                overflow: hidden;
            }
            
            .stat-card::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 4px;
                background: linear-gradient(90deg, var(--primary-500), var(--primary-400));
                transform: scaleX(0);
                transition: transform 0.4s ease;
            }
            
            .stat-card:hover {
                transform: translateY(-8px) scale(1.02);
                box-shadow: var(--shadow-2xl);
            }
            
            .stat-card:hover::before {
                transform: scaleX(1);
            }
            
            .stat-card.primary {
                background: linear-gradient(135deg, var(--primary-500), var(--primary-600));
                color: white;
            }
            
            .stat-card.success {
                background: linear-gradient(135deg, var(--success-500), var(--success-600));
                color: white;
            }
            
            .stat-card.warning {
                background: linear-gradient(135deg, var(--warning-500), var(--warning-600));
                color: white;
            }
            
            .stat-card.slate {
                background: linear-gradient(135deg, var(--slate-600), var(--slate-700));
                color: white;
            }
            
            .stat-icon {
                font-size: 3rem;
                margin-bottom: var(--space-4);
                display: block;
                animation: float 3s ease-in-out infinite;
            }
            
            @keyframes float {
                0%, 100% { transform: translateY(0); }
                50% { transform: translateY(-8px); }
            }
            
            .stat-number {
                font-size: 2.5rem;
                font-weight: 900;
                margin-bottom: var(--space-2);
                display: block;
            }
            
            .stat-label {
                font-size: 1rem;
                font-weight: 600;
                opacity: 0.9;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }
            
            /* Enhanced Report Cards */
            .reports-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(450px, 1fr));
                gap: var(--space-8);
                margin-bottom: var(--space-8);
            }
            
            .report-card {
                background: linear-gradient(135deg, rgba(255,255,255,0.95) 0%, rgba(255,255,255,0.85) 100%);
                backdrop-filter: blur(20px);
                border: 1px solid rgba(255,255,255,0.3);
                border-radius: var(--radius-3xl);
                padding: var(--space-8);
                box-shadow: var(--shadow-xl);
                transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
                position: relative;
                overflow: hidden;
            }
            
            .report-card::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 5px;
                background: linear-gradient(90deg, var(--emerald-500), var(--primary-500), var(--slate-600));
                transform: scaleX(0);
                transition: transform 0.4s ease;
            }
            
            .report-card:hover {
                transform: translateY(-6px);
                box-shadow: var(--shadow-2xl);
            }
            
            .report-card:hover::before {
                transform: scaleX(1);
            }
            
            .report-card h3 {
                font-size: 1.5rem;
                font-weight: 700;
                color: var(--gray-900);
                margin-bottom: var(--space-6);
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding-bottom: var(--space-4);
                border-bottom: 2px solid var(--gray-100);
            }
            
            .report-content {
                min-height: 250px;
                margin-bottom: var(--space-6);
            }
            
            .report-content.loading {
                display: flex;
                align-items: center;
                justify-content: center;
                flex-direction: column;
                gap: var(--space-4);
                color: var(--gray-500);
            }
            
            .report-content.loaded {
                display: block;
            }
            
            /* Enhanced Data Items */
            .data-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: var(--space-5) var(--space-6);
                margin: var(--space-4) 0;
                background: linear-gradient(135deg, var(--gray-50), var(--gray-100));
                border-radius: var(--radius-xl);
                border-left: 5px solid var(--primary-500);
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                position: relative;
                overflow: hidden;
            }
            
            .data-item::before {
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(59, 130, 246, 0.1), transparent);
                transition: left 0.5s ease;
            }
            
            .data-item:hover {
                background: linear-gradient(135deg, var(--primary-50), var(--primary-100));
                border-left-color: var(--primary-600);
                transform: translateX(6px);
                box-shadow: var(--shadow-md);
            }
            
            .data-item:hover::before {
                left: 100%;
            }
            
            .data-item-label {
                font-weight: 600;
                color: var(--gray-800);
                font-size: 0.95rem;
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }
            
            .data-item-value {
                font-weight: 800;
                font-size: 1.1rem;
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }
            
            .data-item-value.success {
                color: var(--success-600);
            }
            
            .data-item-value.warning {
                color: var(--warning-600);
            }
            
            .data-item-value.primary {
                color: var(--primary-600);
            }
            
            .data-item-value.danger {
                color: var(--rose-600);
            }
            
            /* Progress Bars */
            .progress-container {
                margin: var(--space-5) 0;
            }
            
            .progress-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: var(--space-3);
            }
            
            .progress-label {
                font-size: 0.95rem;
                font-weight: 600;
                color: var(--gray-700);
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }
            
            .progress-percentage {
                font-size: 1.1rem;
                font-weight: 800;
                color: var(--primary-600);
            }
            
            .progress-bar {
                width: 100%;
                height: 14px;
                background: var(--gray-200);
                border-radius: var(--radius-xl);
                overflow: hidden;
                position: relative;
                box-shadow: inset 0 2px 4px rgba(0,0,0,0.1);
            }
            
            .progress-fill {
                height: 100%;
                background: linear-gradient(90deg, var(--success-500), var(--success-400));
                border-radius: var(--radius-xl);
                transition: width 1.5s cubic-bezier(0.4, 0, 0.2, 1);
                position: relative;
                overflow: hidden;
            }
            
            .progress-fill::after {
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent);
                animation: progress-shine 2s infinite;
            }
            
            @keyframes progress-shine {
                0% { left: -100%; }
                100% { left: 100%; }
            }
            
            /* Status Badges */
            .status-badge {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-lg);
                font-size: 0.875rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }
            
            .status-badge.excellent {
                background: var(--success-100);
                color: var(--success-700);
                border: 1px solid var(--success-200);
            }
            
            .status-badge.good {
                background: var(--primary-100);
                color: var(--primary-700);
                border: 1px solid var(--primary-200);
            }
            
            .status-badge.warning {
                background: var(--warning-100);
                color: var(--warning-700);
                border: 1px solid var(--warning-200);
            }
            
            .status-badge.danger {
                background: var(--rose-100);
                color: var(--rose-700);
                border: 1px solid var(--rose-200);
            }
            
            /* Enhanced Buttons */
            .btn {
                display: inline-flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-4) var(--space-6);
                border: none;
                border-radius: var(--radius-xl);
                font-weight: 600;
                font-size: 0.95rem;
                text-decoration: none;
                cursor: pointer;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                box-shadow: var(--shadow-md);
                font-family: inherit;
                position: relative;
                overflow: hidden;
            }
            
            .btn::before {
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
                transition: left 0.5s ease;
            }
            
            .btn:hover::before {
                left: 100%;
            }
            
            .btn-primary {
                background: linear-gradient(135deg, var(--primary-600), var(--primary-700));
                color: white;
            }
            
            .btn-primary:hover {
                background: linear-gradient(135deg, var(--primary-700), var(--primary-800));
                transform: translateY(-2px);
                box-shadow: var(--shadow-lg);
            }
            
            .btn-secondary {
                background: linear-gradient(135deg, rgba(255,255,255,0.9), rgba(255,255,255,0.8));
                color: var(--gray-700);
                border: 1px solid var(--gray-300);
                backdrop-filter: blur(10px);
            }
            
            .btn-secondary:hover {
                background: linear-gradient(135deg, rgba(255,255,255,1), rgba(255,255,255,0.9));
                border-color: var(--gray-400);
                transform: translateY(-2px);
                box-shadow: var(--shadow-lg);
            }
            
            /* Loading Animation */
            .loading {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                color: var(--gray-500);
                font-size: 0.95rem;
                font-weight: 500;
            }
            
            .spinner {
                width: 24px;
                height: 24px;
                border: 3px solid var(--gray-200);
                border-top: 3px solid var(--primary-500);
                border-radius: 50%;
                animation: spin 1s linear infinite;
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            /* Actions Section */
            .actions {
                display: flex;
                justify-content: center;
                gap: var(--space-4);
                flex-wrap: wrap;
                margin-top: var(--space-8);
            }
            
            /* Chart Styling */
            .chart-container {
                margin: var(--space-6) 0;
            }
            
            .chart-item {
                display: flex;
                align-items: center;
                gap: var(--space-4);
                margin: var(--space-3) 0;
                padding: var(--space-3);
                background: var(--gray-50);
                border-radius: var(--radius-lg);
                transition: all 0.3s ease;
            }
            
            .chart-item:hover {
                background: var(--primary-50);
                transform: translateX(4px);
            }
            
            .chart-label {
                min-width: 120px;
                font-size: 0.875rem;
                font-weight: 600;
                color: var(--gray-700);
            }
            
            .chart-bar-container {
                flex: 1;
                height: 20px;
                background: var(--gray-200);
                border-radius: var(--radius-lg);
                overflow: hidden;
                position: relative;
            }
            
            .chart-bar-fill {
                height: 100%;
                background: linear-gradient(90deg, var(--primary-500), var(--primary-400));
                border-radius: var(--radius-lg);
                transition: width 1.5s cubic-bezier(0.4, 0, 0.2, 1);
            }
            
            .chart-value {
                min-width: 80px;
                text-align: right;
                font-size: 0.95rem;
                font-weight: 700;
                color: var(--primary-600);
            }
            
            /* Responsive */
            @media (max-width: 1200px) {
                .reports-grid {
                    grid-template-columns: 1fr;
                }
            }
            
            @media (max-width: 768px) {
                .container {
                    padding: var(--space-4);
                }
                
                .header {
                    padding: var(--space-8);
                }
                
                .header h1 {
                    font-size: 2.25rem;
                }
                
                .quick-stats {
                    grid-template-columns: 1fr;
                    gap: var(--space-6);
                }
                
                .reports-grid {
                    gap: var(--space-6);
                }
                
                .report-card {
                    padding: var(--space-6);
                }
                
                .data-item {
                    flex-direction: column;
                    align-items: flex-start;
                    gap: var(--space-2);
                }
                
                .actions {
                    flex-direction: column;
                    align-items: stretch;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <!-- Header -->
            <header class="header">
                <h1>
                    <span>📊</span>
                    Dashboard Analytics
                </h1>
                <p>Visão completa e em tempo real do desempenho das conciliações bancárias</p>
                <a href="/" class="btn btn-primary">
                    <span>🏠</span>
                    Voltar ao Sistema
                </a>
            </header>
            
            <!-- Quick Stats -->
            <section class="quick-stats">
                <div class="stat-card primary">
                    <span class="stat-icon">📈</span>
                    <span class="stat-number" id="total-transacoes">0</span>
                    <span class="stat-label">Total de Transações</span>
                </div>
                
                <div class="stat-card warning">
                    <span class="stat-icon">⏳</span>
                    <span class="stat-number" id="pendentes">0</span>
                    <span class="stat-label">Pendentes</span>
                </div>
                
                <div class="stat-card success">
                    <span class="stat-icon">✅</span>
                    <span class="stat-number" id="conciliados">0</span>
                    <span class="stat-label">Conciliadas</span>
                </div>
                
                <div class="stat-card slate">
                    <span class="stat-icon">💰</span>
                    <span class="stat-number" id="valor-total">R$ 0</span>
                    <span class="stat-label">Valor Total</span>
                </div>
            </section>
            
            <!-- Reports -->
            <section class="reports-grid">
                <!-- Resumo Executivo -->
                <div class="report-card">
                    <h3>
                        <span>📈</span>
                        Resumo Executivo
                    </h3>
                    <div class="report-content" id="resumo-geral">
                        <div class="loading">
                            <div class="spinner"></div>
                            Carregando dados...
                        </div>
                    </div>
                    <button onclick="carregarResumo()" class="btn btn-secondary">
                        <span>🔄</span>
                        Atualizar Resumo
                    </button>
                </div>
                
                <!-- Por Banco -->
                <div class="report-card">
                    <h3>
                        <span>🏦</span>
                        Análise por Banco
                    </h3>
                    <div class="report-content" id="por-banco">
                        <div class="loading">
                            <div class="spinner"></div>
                            Carregando dados...
                        </div>
                    </div>
                    <button onclick="carregarPorBanco()" class="btn btn-secondary">
                        <span>🔄</span>
                        Atualizar por Banco
                    </button>
                </div>
                
                <!-- Por Classificação -->
                <div class="report-card">
                    <h3>
                        <span>📋</span>
                        Análise por Classificação
                    </h3>
                    <div class="report-content" id="por-classificacao">
                        <div class="loading">
                            <div class="spinner"></div>
                            Carregando dados...
                        </div>
                    </div>
                    <button onclick="carregarPorClassificacao()" class="btn btn-secondary">
                        <span>🔄</span>
                        Atualizar por Classificação
                    </button>
                </div>
                
                <!-- Performance -->
                <div class="report-card">
                    <h3>
                        <span>📊</span>
                        Performance do Sistema
                    </h3>
                    <div class="report-content" id="performance">
                        <div class="loading">
                            <div class="spinner"></div>
                            Carregando métricas...
                        </div>
                    </div>
                    <button onclick="carregarPerformance()" class="btn btn-secondary">
                        <span>🔄</span>
                        Atualizar Performance
                    </button>
                </div>
            </section>
            
            <!-- Actions -->
            <section class="actions">
                <button onclick="atualizarTodosRelatorios()" class="btn btn-primary">
                    <span>🔄</span>
                    Atualizar Todos os Relatórios
                </button>
                <a href="/pendentes" class="btn btn-secondary">
                    <span>📋</span>
                    Ver Pendentes
                </a>
                <a href="/conciliados" class="btn btn-secondary">
                    <span>✅</span>
                    Ver Conciliados
                </a>
            </section>
        </div>
        
        
        <script>
        async function atualizarStats() {
            try {
                const response = await fetch('/api/stats');
                const data = await response.json();
                
                document.getElementById('total-transacoes').textContent = data.total_transacoes;
                document.getElementById('pendentes').textContent = data.pendentes;
                document.getElementById('conciliados').textContent = data.conciliados;
                document.getElementById('valor-total').textContent = 'R$ ' + data.valor_total.toLocaleString('pt-BR', {minimumFractionDigits: 2});
            } catch (error) {
                console.error('Erro ao atualizar stats:', error);
            }
        }
        
        async function carregarResumo() {
            const container = document.getElementById('resumo-geral');
            container.innerHTML = '<div class="loading"><div class="spinner"></div>Carregando...</div>';
            
            try {
                const response = await fetch('/api/stats');
                const data = await response.json();
                
                const percentualConciliado = data.total_transacoes > 0 ? ((data.conciliados / data.total_transacoes) * 100).toFixed(1) : 0;
                
                setTimeout(() => {
                    container.innerHTML = `
                        <div class="progress-container">
                            <div class="progress-header">
                                <div class="progress-label">
                                    <span>📊</span>
                                    Taxa de Conciliação
                                </div>
                                <div class="progress-percentage">${percentualConciliado}%</div>
                            </div>
                            <div class="progress-bar">
                                <div class="progress-fill" style="width: ${percentualConciliado}%"></div>
                            </div>
                            <div style="margin-top: var(--space-2); font-size: 0.875rem; color: var(--gray-600); text-align: center;">
                                ${data.conciliados} de ${data.total_transacoes} transações
                            </div>
                        </div>
                        
                        <div class="data-item">
                            <div class="data-item-label">
                                <span>💰</span>
                                Valor Total Processado
                            </div>
                            <div class="data-item-value primary">
                                R$ ${data.valor_total.toLocaleString('pt-BR', {minimumFractionDigits: 2})}
                            </div>
                        </div>
                        
                        <div class="data-item">
                            <div class="data-item-label">
                                <span>⏳</span>
                                Pendências
                            </div>
                            <div class="data-item-value ${data.pendentes === 0 ? 'success' : 'warning'}">
                                ${data.pendentes} transações aguardando
                            </div>
                        </div>
                        
                        <div class="data-item">
                            <div class="data-item-label">
                                <span>🎯</span>
                                Status Geral
                            </div>
                            <div class="data-item-value">
                                <span class="status-badge ${data.pendentes === 0 ? 'excellent' : 'warning'}">
                                    ${data.pendentes === 0 ? '✅ Todas Conciliadas' : '⚠️ Há Pendências'}
                                </span>
                            </div>
                        </div>
                    `;
                    container.classList.add('loaded');
                }, 500);
                
            } catch (error) {
                setTimeout(() => {
                    container.innerHTML = '<div style="color: var(--rose-500); text-align: center;">❌ Erro ao carregar dados</div>';
                }, 500);
            }
        }
        
        async function carregarPorBanco() {
            const container = document.getElementById('por-banco');
            container.innerHTML = '<div class="loading"><div class="spinner"></div>Carregando...</div>';
            
            try {
                const response = await fetch('/api/transacoes');
                const data = await response.json();
                
                const porBanco = {};
                data.transacoes.forEach(t => {
                    if (!porBanco[t.banco]) porBanco[t.banco] = {total: 0, valor: 0, conciliados: 0};
                    porBanco[t.banco].total++;
                    porBanco[t.banco].valor += t.valor;
                    if (t.status === 'CONCILIADO') porBanco[t.banco].conciliados++;
                });
                
                setTimeout(() => {
                    let html = '';
                    
                    if (Object.keys(porBanco).length === 0) {
                        html = '<div style="text-align: center; color: var(--gray-600); padding: var(--space-8);">📊 Nenhum dado bancário disponível</div>';
                    } else {
                        html += '<div class="chart-container">';
                        
                        const maxTotal = Math.max(...Object.values(porBanco).map(b => b.total));
                        
                        Object.entries(porBanco).forEach(([banco, info]) => {
                            const percentual = info.total > 0 ? ((info.conciliados / info.total) * 100).toFixed(1) : 0;
                            const barWidth = maxTotal > 0 ? (info.total / maxTotal) * 100 : 0;
                            
                            html += `
                                <div class="chart-item">
                                    <div class="chart-label">🏦 ${banco}</div>
                                    <div class="chart-bar-container">
                                        <div class="chart-bar-fill" style="width: ${barWidth}%"></div>
                                    </div>
                                    <div class="chart-value">${info.total}</div>
                                </div>
                            `;
                        });
                        
                        html += '</div>';
                        
                        Object.entries(porBanco).forEach(([banco, info]) => {
                            const percentual = info.total > 0 ? ((info.conciliados / info.total) * 100).toFixed(1) : 0;
                            
                            html += `
                                <div class="data-item">
                                    <div class="data-item-label">
                                        <span>📈</span>
                                        Taxa ${banco}
                                    </div>
                                    <div class="data-item-value ${percentual == 100 ? 'success' : percentual >= 80 ? 'primary' : 'warning'}">
                                        ${percentual}% conciliado
                                    </div>
                                </div>
                                
                                <div class="data-item">
                                    <div class="data-item-label">
                                        <span>💸</span>
                                        Volume ${banco}
                                    </div>
                                    <div class="data-item-value primary">
                                        R$ ${info.valor.toLocaleString('pt-BR', {minimumFractionDigits: 2})}
                                    </div>
                                </div>
                            `;
                        });
                    }
                    
                    container.innerHTML = html;
                    container.classList.add('loaded');
                }, 800);
                
            } catch (error) {
                setTimeout(() => {
                    container.innerHTML = '<div style="color: var(--rose-500); text-align: center;">❌ Erro ao carregar dados bancários</div>';
                }, 800);
            }
        }
        
        async function debugClassificacoes() {
    console.log('🔍 DEBUG: Testando API de transações...');
    
    try {
        const response = await fetch('/api/transacoes');
        const data = await response.json();
        
        console.log('📊 Total de transações:', data.transacoes?.length || 0);
        
        if (data.transacoes && data.transacoes.length > 0) {
            console.log('📋 Primeira transação:', data.transacoes[0]);
            
            // Contar status
            const status = {};
            const classificacoes = {};
            
            data.transacoes.forEach(t => {
                // Contar por status
                const st = t.status || 'INDEFINIDO';
                status[st] = (status[st] || 0) + 1;
                
                // Contar por classificação
                const cl = t.classificacao || 'Não Classificado';
                classificacoes[cl] = (classificacoes[cl] || 0) + 1;
            });
            
            console.log('📈 Por Status:', status);
            console.log('📈 Por Classificação:', classificacoes);
        }
        
    } catch (error) {
        console.error('❌ Erro no debug:', error);
    }
}

        async function carregarPorClassificacao() {
    const container = document.getElementById('por-classificacao');
    container.innerHTML = '<div class="loading"><div class="spinner"></div>Carregando...</div>';
    
    try {
        const response = await fetch('/api/transacoes');
        const data = await response.json();
        
        if (!data.success || !data.transacoes) {
            throw new Error('Dados inválidos recebidos da API');
        }
        
        // Agrupar por classificação
        const porClassificacao = {};
        
        data.transacoes.forEach(t => {
            let classificacao = 'Não Classificado';
            
            if (t.classificacao && t.classificacao.trim() !== '') {
                classificacao = t.classificacao.trim();
            }
            
            if (!porClassificacao[classificacao]) {
                porClassificacao[classificacao] = { total: 0, conciliados: 0 };
            }
            
            porClassificacao[classificacao].total++;
            if (t.status === 'CONCILIADO') {
                porClassificacao[classificacao].conciliados++;
            }
        });
        
        setTimeout(() => {
            let html = '<div class="chart-container">';
            
            if (Object.keys(porClassificacao).length === 0) {
                html = '<div style="text-align: center; color: var(--gray-600); padding: var(--space-8);">📊 Nenhuma transação disponível</div>';
            } else {
                const sorted = Object.entries(porClassificacao)
                    .sort(([,a], [,b]) => b.total - a.total);
                
                const maxTotal = sorted[0][1].total;
                
                sorted.forEach(([classif, info]) => {
                    const barWidth = (info.total / maxTotal) * 100;
                    const percentual = info.total > 0 ? ((info.conciliados / info.total) * 100).toFixed(1) : '0';
                    const textoTransacao = info.total === 1 ? 'transação' : 'transações';
                    
                    let cor = 'var(--primary-500)';
                    if (classif === 'Não Classificado') cor = 'var(--gray-500)';
                    else if (classif.includes('RECEITA')) cor = 'var(--success-500)';
                    else if (classif.includes('DESPESA') || classif.includes('CUSTOS')) cor = 'var(--warning-500)';
                    
                    html += `
                        <div class="chart-item">
                            <div class="chart-label" title="${classif} - ${info.total} ${textoTransacao} (${percentual}% conciliadas)">
                                📋 ${classif}
                            </div>
                            <div class="chart-bar-container">
                                <div class="chart-bar-fill" style="width: ${barWidth}%; background: ${cor};"></div>
                            </div>
                            <div class="chart-value">
                                ${info.total}
                            </div>
                        </div>
                    `;
                });
                
                html += '</div>';
            }
            
            container.innerHTML = html;
            container.classList.add('loaded');
        }, 400);
        
    } catch (error) {
        console.error('❌ Erro:', error);
        setTimeout(() => {
            container.innerHTML = '<div style="color: var(--rose-500); text-align: center;">❌ Erro ao carregar dados</div>';
        }, 400);
    }
}
        
        async function carregarPerformance() {
            const container = document.getElementById('performance');
            container.innerHTML = '<div class="loading"><div class="spinner"></div>Carregando...</div>';
            
            try {
                const response = await fetch('/api/stats');
                const data = await response.json();
                
                const mediaValorTransacao = data.total_transacoes > 0 ? (data.valor_total / data.total_transacoes) : 0;
                const eficiencia = data.total_transacoes > 0 ? ((data.conciliados / data.total_transacoes) * 100) : 0;
                
                setTimeout(() => {
                    container.innerHTML = `
                        <div class="progress-container">
                            <div class="progress-header">
                                <div class="progress-label">
                                    <span>⚡</span>
                                    Eficiência de Conciliação
                                </div>
                                <div class="progress-percentage">${eficiencia.toFixed(1)}%</div>
                            </div>
                            <div class="progress-bar">
                                <div class="progress-fill" style="width: ${eficiencia}%"></div>
                            </div>
                        </div>
                        
                        <div class="data-item">
                            <div class="data-item-label">
                                <span>📊</span>
                                Valor Médio por Transação
                            </div>
                            <div class="data-item-value primary">
                                R$ ${mediaValorTransacao.toLocaleString('pt-BR', {minimumFractionDigits: 2})}
                            </div>
                        </div>
                        
                        <div class="data-item">
                            <div class="data-item-label">
                                <span>📄</span>
                                Total de Extratos Processados
                            </div>
                            <div class="data-item-value ${data.total_transacoes > 0 ? 'success' : 'warning'}">
                                ${data.total_transacoes > 0 ? 'Sistema ativo' : 'Nenhum extrato processado'}
                            </div>
                        </div>
                        
                        <div class="data-item">
                            <div class="data-item-label">
                                <span>🔥</span>
                                Status do Sistema
                            </div>
                            <div class="data-item-value">
                                <span class="status-badge ${data.total_transacoes > 0 ? 'excellent' : 'warning'}">
                                    ${data.total_transacoes > 0 ? '🟢 Operacional' : '🟡 Aguardando dados'}
                                </span>
                            </div>
                        </div>
                    `;
                    container.classList.add('loaded');
                }, 1200);
                
            } catch (error) {
                setTimeout(() => {
                    container.innerHTML = '<div style="color: var(--rose-500); text-align: center;">❌ Erro ao carregar métricas</div>';
                }, 1200);
            }
        }
        
        async function atualizarTodosRelatorios() {
            await atualizarStats();
            await Promise.all([
                carregarResumo(),
                carregarPorBanco(),
                carregarPorClassificacao(),
                carregarPerformance()
            ]);
        }
        
        // Carregar dados quando a página carrega
        window.onload = () => {
            atualizarTodosRelatorios();
        };
        </script>
    </body>
    </html>
    """


    return HTMLResponse(content=html_content)

@app.get("/configuracoes")
async def pagina_configuracoes():
    """Página de configurações das classificações"""
    html_content = """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Configurações - Sistema de Conciliação</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {
                /* Design System - Colors */
                --primary-50: #eff6ff;
                --primary-100: #dbeafe;
                --primary-200: #bfdbfe;
                --primary-300: #93c5fd;
                --primary-500: #3b82f6;
                --primary-600: #2563eb;
                --primary-700: #1d4ed8;
                --primary-900: #1e3a8a;
                
                --success-50: #f0fdf4;
                --success-100: #dcfce7;
                --success-500: #22c55e;
                --success-600: #16a34a;
                --success-700: #15803d;
                
                --warning-50: #fffbeb;
                --warning-100: #fef3c7;
                --warning-200: #fde68a;
                --warning-500: #f59e0b;
                --warning-600: #d97706;
                
                --danger-50: #fef2f2;
                --danger-100: #fee2e2;
                --danger-500: #ef4444;
                --danger-600: #dc2626;
                
                --slate-50: #f8fafc;
                --slate-100: #f1f5f9;
                --slate-500: #64748b;
                --slate-600: #475569;
                --slate-700: #334155;
                
                --gray-50: #f9fafb;
                --gray-100: #f3f4f6;
                --gray-200: #e5e7eb;
                --gray-300: #d1d5db;
                --gray-400: #9ca3af;
                --gray-500: #6b7280;
                --gray-600: #4b5563;
                --gray-700: #374151;
                --gray-800: #1f2937;
                --gray-900: #111827;
                
                --space-1: 0.25rem;
                --space-2: 0.5rem;
                --space-3: 0.75rem;
                --space-4: 1rem;
                --space-5: 1.25rem;
                --space-6: 1.5rem;
                --space-8: 2rem;
                --space-10: 2.5rem;
                --space-12: 3rem;
                --space-16: 4rem;
                
                --radius-sm: 0.375rem;
                --radius-md: 0.5rem;
                --radius-lg: 0.75rem;
                --radius-xl: 1rem;
                --radius-2xl: 1.5rem;
                
                --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
                --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
                --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
                --shadow-xl: 0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1);
            }
            
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, var(--primary-50) 0%, var(--slate-50) 50%, var(--success-50) 100%);
                min-height: 100vh;
                color: var(--gray-900);
                line-height: 1.6;
            }
            
            .container {
                max-width: 1400px;
                margin: 0 auto;
                padding: var(--space-6);
            }
            
            /* Header */
            .header {
                background: linear-gradient(135deg, rgba(255,255,255,0.95) 0%, rgba(255,255,255,0.8) 100%);
                backdrop-filter: blur(20px);
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: var(--radius-2xl);
                padding: var(--space-10);
                margin-bottom: var(--space-8);
                box-shadow: var(--shadow-xl);
                text-align: center;
                position: relative;
                overflow: hidden;
            }
            
            .header::before {
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent);
                animation: shimmer 3s infinite;
            }
            
            @keyframes shimmer {
                0% { left: -100%; }
                100% { left: 100%; }
            }
            
            .header h1 {
                font-size: 2.5rem;
                font-weight: 700;
                background: linear-gradient(135deg, var(--primary-600), var(--slate-700), var(--success-600));
                background-clip: text;
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: var(--space-4);
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                position: relative;
                z-index: 1;
            }
            
            .header p {
                color: var(--gray-600);
                font-size: 1.125rem;
                margin-bottom: var(--space-6);
                position: relative;
                z-index: 1;
            }
            
            /* Navigation Tabs */
            .nav-tabs {
                display: flex;
                gap: var(--space-2);
                background: rgba(255,255,255,0.9);
                backdrop-filter: blur(10px);
                border-radius: var(--radius-2xl);
                padding: var(--space-2);
                margin-bottom: var(--space-8);
                box-shadow: var(--shadow-lg);
                border: 1px solid var(--gray-200);
            }
            
            .nav-tab {
                flex: 1;
                padding: var(--space-4) var(--space-6);
                border: none;
                border-radius: var(--radius-xl);
                font-weight: 600;
                font-size: 0.95rem;
                cursor: pointer;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                background: transparent;
                color: var(--gray-600);
                display: flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
            }
            
            .nav-tab.active {
                background: linear-gradient(135deg, var(--primary-600), var(--primary-700));
                color: white;
                box-shadow: var(--shadow-md);
                transform: translateY(-1px);
            }
            
            .nav-tab:hover:not(.active) {
                background: var(--gray-100);
                color: var(--gray-800);
            }
            
            /* Tab Content */
            .tab-content {
                display: none;
                animation: fadeIn 0.3s ease-in-out;
            }
            
            .tab-content.active {
                display: block;
            }
            
            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }
            
            /* Cards */
            .config-card {
                background: linear-gradient(135deg, rgba(255,255,255,0.95) 0%, rgba(255,255,255,0.85) 100%);
                backdrop-filter: blur(20px);
                border: 1px solid rgba(255,255,255,0.3);
                border-radius: var(--radius-2xl);
                padding: var(--space-8);
                margin-bottom: var(--space-6);
                box-shadow: var(--shadow-xl);
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            }
            
            .config-card:hover {
                transform: translateY(-2px);
                box-shadow: var(--shadow-2xl);
            }
            
            .config-card h3 {
                font-size: 1.5rem;
                font-weight: 700;
                color: var(--gray-900);
                margin-bottom: var(--space-6);
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding-bottom: var(--space-4);
                border-bottom: 2px solid var(--gray-100);
            }
            
            /* Buttons */
            .btn {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-3) var(--space-6);
                border: none;
                border-radius: var(--radius-lg);
                font-weight: 600;
                font-size: 0.875rem;
                text-decoration: none;
                cursor: pointer;
                transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
                box-shadow: var(--shadow-sm);
                font-family: inherit;
                position: relative;
                overflow: hidden;
            }
            
            .btn::before {
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
                transition: left 0.5s ease;
            }
            
            .btn:hover::before {
                left: 100%;
            }
            
            .btn-primary {
                background: linear-gradient(135deg, var(--primary-600), var(--primary-700));
                color: white;
            }
            
            .btn-primary:hover {
                background: linear-gradient(135deg, var(--primary-700), var(--primary-800));
                transform: translateY(-1px);
                box-shadow: var(--shadow-md);
            }
            
            .btn-success {
                background: linear-gradient(135deg, var(--success-600), var(--success-700));
                color: white;
            }
            
            .btn-success:hover {
                background: linear-gradient(135deg, var(--success-700), var(--success-800));
                transform: translateY(-1px);
                box-shadow: var(--shadow-md);
            }
            
            .btn-warning {
                background: linear-gradient(135deg, var(--warning-500), var(--warning-600));
                color: white;
            }
            
            .btn-warning:hover {
                background: linear-gradient(135deg, var(--warning-600), var(--warning-700));
                transform: translateY(-1px);
                box-shadow: var(--shadow-md);
            }
            
            .btn-danger {
                background: linear-gradient(135deg, var(--danger-500), var(--danger-600));
                color: white;
            }
            
            .btn-danger:hover {
                background: linear-gradient(135deg, var(--danger-600), var(--danger-700));
                transform: translateY(-1px);
                box-shadow: var(--shadow-md);
            }
            
            .btn-secondary {
                background: linear-gradient(135deg, var(--gray-100), var(--gray-200));
                color: var(--gray-700);
                border: 1px solid var(--gray-300);
            }
            
            .btn-secondary:hover {
                background: linear-gradient(135deg, var(--gray-200), var(--gray-300));
                border-color: var(--gray-400);
                transform: translateY(-1px);
                box-shadow: var(--shadow-md);
            }
            
            /* Table */
            .table-container {
                background: white;
                border-radius: var(--radius-2xl);
                overflow: hidden;
                box-shadow: var(--shadow-lg);
                border: 1px solid var(--gray-200);
                margin-top: var(--space-6);
            }
            
            table {
                width: 100%;
                border-collapse: collapse;
            }
            
            th {
                background: var(--slate-600);
                color: white;
                padding: var(--space-4);
                text-align: left;
                font-weight: 600;
                font-size: 0.875rem;
                letter-spacing: 0.025em;
            }
            
            td {
                padding: var(--space-4);
                border-bottom: 1px solid var(--gray-200);
                font-size: 0.875rem;
            }
            
            tr:hover {
                background: var(--gray-50);
            }
            
            tr:last-child td {
                border-bottom: none;
            }
            
            /* Hierarchical Structure */
            .hierarchy-item {
                margin: var(--space-4) 0;
                border: 1px solid var(--gray-200);
                border-radius: var(--radius-xl);
                overflow: hidden;
                background: white;
                box-shadow: var(--shadow-sm);
            }
            
            .hierarchy-header {
                background: linear-gradient(135deg, var(--slate-600), var(--slate-700));
                color: white;
                padding: var(--space-4) var(--space-6);
                font-weight: 600;
                display: flex;
                justify-content: space-between;
                align-items: center;
                cursor: pointer;
                transition: all 0.2s ease;
            }
            
            .hierarchy-header:hover {
                background: linear-gradient(135deg, var(--slate-700), var(--slate-800));
            }
            
            .hierarchy-content {
                padding: var(--space-6);
                border-top: 1px solid var(--gray-200);
                background: var(--gray-50);
            }
            
            .hierarchy-content.collapsed {
                display: none;
            }
            
            .plano-item {
                margin: var(--space-3) 0;
                padding: var(--space-4);
                background: white;
                border-radius: var(--radius-lg);
                border-left: 4px solid var(--primary-500);
                box-shadow: var(--shadow-sm);
            }
            
            .plano-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: var(--space-3);
            }
            
            .plano-title {
                font-weight: 600;
                color: var(--gray-800);
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }
            
            .items-list {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                margin-top: var(--space-3);
            }
            
            .item-tag {
                background: var(--primary-100);
                color: var(--primary-700);
                padding: var(--space-1) var(--space-3);
                border-radius: var(--radius-md);
                font-size: 0.75rem;
                font-weight: 600;
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
            }
            
            /* Modal */
            .modal {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                backdrop-filter: blur(4px);
                z-index: 1000;
                overflow-y: auto;
                padding: var(--space-4);
            }
            
            .modal-content {
                position: relative;
                background: white;
                margin: var(--space-8) auto;
                padding: var(--space-10);
                border-radius: var(--radius-2xl);
                width: 100%;
                max-width: 600px;
                max-height: calc(100vh - 4rem);
                overflow-y: auto;
                box-shadow: var(--shadow-xl);
                border: 1px solid var(--gray-200);
            }
            
            .modal-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: var(--space-8);
                padding-bottom: var(--space-6);
                border-bottom: 1px solid var(--gray-200);
            }
            
            .modal-header h3 {
                font-size: 1.75rem;
                font-weight: 700;
                color: var(--gray-900);
                display: flex;
                align-items: center;
                gap: var(--space-3);
            }
            
            .btn-close {
                background: var(--danger-500);
                color: white;
                border: none;
                border-radius: var(--radius-lg);
                padding: var(--space-2) var(--space-4);
                cursor: pointer;
                font-size: 1rem;
                font-weight: 600;
                transition: all 0.2s ease;
                min-width: 40px;
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            
            .btn-close:hover {
                background: var(--danger-600);
                transform: scale(1.05);
            }
            
            /* Form */
            .form-group {
                margin: var(--space-4) 0;
            }
            
            .form-group label {
                display: block;
                margin-bottom: var(--space-2);
                font-weight: 600;
                color: var(--gray-700);
                font-size: 0.875rem;
            }
            
            .form-group input,
            .form-group select,
            .form-group textarea {
                width: 100%;
                padding: var(--space-4);
                border: 1px solid var(--gray-300);
                border-radius: var(--radius-lg);
                font-size: 0.875rem;
                font-family: inherit;
                background: white;
                transition: all 0.2s ease;
            }
            
            .form-group input:focus,
            .form-group select:focus,
            .form-group textarea:focus {
                outline: none;
                border-color: var(--primary-500);
                box-shadow: 0 0 0 3px var(--primary-100);
            }
            
            .form-buttons {
                display: flex;
                justify-content: flex-end;
                gap: var(--space-4);
                margin-top: var(--space-8);
                padding-top: var(--space-6);
                border-top: 1px solid var(--gray-200);
            }
            
            /* Alert */
            .alert {
                padding: var(--space-4) var(--space-6);
                border-radius: var(--radius-lg);
                margin: var(--space-4) 0;
                display: flex;
                align-items: center;
                gap: var(--space-3);
                font-weight: 500;
            }
            
            .alert-success {
                background: var(--success-100);
                color: var(--success-700);
                border: 1px solid var(--success-200);
            }
            
            .alert-danger {
                background: var(--danger-100);
                color: var(--danger-700);
                border: 1px solid var(--danger-200);
            }
            
            .alert-warning {
                background: var(--warning-100);
                color: var(--warning-700);
                border: 1px solid var(--warning-200);
            }
            
            /* Loading Animation */
            .spinner {
                width: 24px;
                height: 24px;
                border: 3px solid var(--gray-200);
                border-top: 3px solid var(--primary-500);
                border-radius: 50%;
                animation: spin 1s linear infinite;
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            /* Responsive */
            @media (max-width: 768px) {
                .container {
                    padding: var(--space-4);
                }
                
                .header {
                    padding: var(--space-6);
                }
                
                .header h1 {
                    font-size: 2rem;
                }
                
                .nav-tabs {
                    flex-direction: column;
                }
                
                .modal-content {
                    margin: var(--space-4) auto;
                    padding: var(--space-6);
                }
                
                .form-buttons {
                    flex-direction: column;
                }
                
                table {
                    font-size: 0.75rem;
                }
                
                th, td {
                    padding: var(--space-2);
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <!-- Header -->
            <header class="header">
                <h1>
                    <span>⚙️</span>
                    Configurações do Sistema
                </h1>
                <p>Gerencie classificações, planos de contas e itens hierárquicos</p>
                <a href="/" class="btn btn-primary">
                    <span>🏠</span>
                    Voltar ao Sistema
                </a>
            </header>
            
            <!-- Navigation Tabs -->
            <nav class="nav-tabs">
                <button class="nav-tab active" onclick="abrirTab(event, 'visao-geral')">
                    <span>👁️</span>
                    Visão Geral
                </button>
                <button class="nav-tab" onclick="abrirTab(event, 'classificacoes')">
                    <span>📁</span>
                    Classificações
                </button>
                <button class="nav-tab" onclick="abrirTab(event, 'planos-contas')">
                    <span>📊</span>
                    Planos de Contas
                </button>
                <button class="nav-tab" onclick="abrirTab(event, 'itens')">
                    <span>📝</span>
                    Itens
                </button>
            </nav>
            
            <!-- Tab: Visão Geral -->
            <div id="visao-geral" class="tab-content active">
                <div class="config-card">
                    <h3>
                        <span>🔍</span>
                        Estrutura Hierárquica Atual
                    </h3>
                    <div id="estrutura-hierarquica">
                        <div style="text-align: center; padding: var(--space-8); color: var(--gray-600);">
                            <div class="spinner" style="margin: 0 auto var(--space-4);"></div>
                            Carregando estrutura...
                        </div>
                    </div>
                    <div style="margin-top: var(--space-6);">
                        <button onclick="carregarEstrutura()" class="btn btn-secondary">
                            <span>🔄</span>
                            Atualizar Estrutura
                        </button>
                    </div>
                </div>

                <!-- Utilitários do Sistema -->
                <div class="config-card">
                    <h3>
                        <span>🛠️</span>
                        Utilitários do Sistema
                    </h3>
                    
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: var(--space-4); margin-bottom: var(--space-6);">
                        <!-- Exportar/Importar -->
                        <div style="background: var(--success-50); border: 1px solid var(--success-200); border-radius: var(--radius-xl); padding: var(--space-4);">
                            <h4 style="color: var(--success-700); margin-bottom: var(--space-3); display: flex; align-items: center; gap: var(--space-2);">
                                <span>📤</span>
                                Backup & Restore
                            </h4>
                            <p style="font-size: 0.875rem; color: var(--gray-600); margin-bottom: var(--space-4);">
                                Faça backup ou restaure suas configurações
                            </p>
                            <div style="display: flex; gap: var(--space-2);">
                                <button onclick="exportarConfiguracoes()" class="btn btn-success" style="font-size: 0.75rem; padding: var(--space-2) var(--space-3);">
                                    <span>📤</span>
                                    Exportar
                                </button>
                                <button onclick="importarConfiguracoes()" class="btn btn-secondary" style="font-size: 0.75rem; padding: var(--space-2) var(--space-3);">
                                    <span>📥</span>
                                    Importar
                                </button>
                            </div>
                        </div>
                        
                        <!-- Validação -->
                        <div style="background: var(--primary-50); border: 1px solid var(--primary-200); border-radius: var(--radius-xl); padding: var(--space-4);">
                            <h4 style="color: var(--primary-700); margin-bottom: var(--space-3); display: flex; align-items: center; gap: var(--space-2);">
                                <span>🔍</span>
                                Validação & Análise
                            </h4>
                            <p style="font-size: 0.875rem; color: var(--gray-600); margin-bottom: var(--space-4);">
                                Verifique a integridade das configurações
                            </p>
                            <div style="display: flex; gap: var(--space-2);">
                                <button onclick="validarConfiguracoes()" class="btn btn-primary" style="font-size: 0.75rem; padding: var(--space-2) var(--space-3);">
                                    <span>✅</span>
                                    Validar
                                </button>
                                <button onclick="obterEstatisticas()" class="btn btn-secondary" style="font-size: 0.75rem; padding: var(--space-2) var(--space-3);">
                                    <span>📊</span>
                                    Stats
                                </button>
                            </div>
                        </div>
                        
                        <!-- Reset -->
                        <div style="background: var(--warning-50); border: 1px solid var(--warning-200); border-radius: var(--radius-xl); padding: var(--space-4);">
                            <h4 style="color: var(--warning-700); margin-bottom: var(--space-3); display: flex; align-items: center; gap: var(--space-2);">
                                <span>🔄</span>
                                Reset & Limpeza
                            </h4>
                            <p style="font-size: 0.875rem; color: var(--gray-600); margin-bottom: var(--space-4);">
                                Restaurar configurações padrão
                            </p>
                            <div style="display: flex; gap: var(--space-2);">
                                <button onclick="resetarConfiguracoes()" class="btn btn-warning" style="font-size: 0.75rem; padding: var(--space-2) var(--space-3);">
                                    <span>🔄</span>
                                    Reset
                                </button>
                            </div>
                        </div>
                        
                        <!-- Informações -->
                        <div style="background: var(--slate-50); border: 1px solid var(--slate-200); border-radius: var(--radius-xl); padding: var(--space-4);">
                            <h4 style="color: var(--slate-700); margin-bottom: var(--space-3); display: flex; align-items: center; gap: var(--space-2);">
                                <span>ℹ️</span>
                                Informações
                            </h4>
                            <p style="font-size: 0.875rem; color: var(--gray-600); margin-bottom: var(--space-4);">
                                Sistema de configurações v2.0
                            </p>
                            <div style="display: flex; gap: var(--space-2);">
                                <a href="/docs" class="btn btn-secondary" style="font-size: 0.75rem; padding: var(--space-2) var(--space-3);">
                                    <span>📚</span>
                                    Ajuda
                                </a>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Quick Stats -->
                    <div style="background: linear-gradient(135deg, var(--gray-50), var(--gray-100)); border-radius: var(--radius-xl); padding: var(--space-4); margin-top: var(--space-4);">
                        <h4 style="color: var(--gray-800); margin-bottom: var(--space-4); display: flex; align-items: center; gap: var(--space-2);">
                            <span>⚡</span>
                            Status Rápido
                        </h4>
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: var(--space-4);" id="quick-stats">
                            <div style="text-align: center;">
                                <div style="font-size: 1.5rem; font-weight: 700; color: var(--primary-600);" id="quick-classificacoes">0</div>
                                <div style="font-size: 0.75rem; color: var(--gray-600);">Classificações</div>
                            </div>
                            <div style="text-align: center;">
                                <div style="font-size: 1.5rem; font-weight: 700; color: var(--success-600);" id="quick-planos">0</div>
                                <div style="font-size: 0.75rem; color: var(--gray-600);">Planos</div>
                            </div>
                            <div style="text-align: center;">
                                <div style="font-size: 1.5rem; font-weight: 700; color: var(--warning-600);" id="quick-itens">0</div>
                                <div style="font-size: 0.75rem; color: var(--gray-600);">Itens</div>
                            </div>
                            <div style="text-align: center;">
                                <div style="font-size: 1.5rem; font-weight: 700; color: var(--slate-600);" id="quick-transacoes">0</div>
                                <div style="font-size: 0.75rem; color: var(--gray-600);">Em Uso</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Tab: Classificações -->
            <div id="classificacoes" class="tab-content">
                <div class="config-card">
                    <h3>
                        <span>📁</span>
                        Gerenciar Classificações
                    </h3>
                    <div style="margin-bottom: var(--space-6);">
                        <button onclick="abrirModalClassificacao()" class="btn btn-success">
                            <span>➕</span>
                            Nova Classificação
                        </button>
                    </div>
                    
                    <div class="table-container">
                        <table id="tabela-classificacoes">
                            <thead>
                                <tr>
                                    <th>Nome da Classificação</th>
                                    <th>Planos de Contas</th>
                                    <th>Total de Itens</th>
                                    <th>Transações</th>
                                    <th>Ações</th>
                                </tr>
                            </thead>
                            <tbody id="tbody-classificacoes">
                                <tr>
                                    <td colspan="5" style="text-align: center; padding: var(--space-8); color: var(--gray-600);">
                                        Carregando classificações...
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            
            <!-- Tab: Planos de Contas -->
            <div id="planos-contas" class="tab-content">
                <div class="config-card">
                    <h3>
                        <span>📊</span>
                        Gerenciar Planos de Contas
                    </h3>
                    <div style="margin-bottom: var(--space-6);">
                        <button onclick="abrirModalPlanoContas()" class="btn btn-success">
                            <span>➕</span>
                            Novo Plano de Contas
                        </button>
                    </div>
                    
                    <div class="table-container">
                        <table id="tabela-planos">
                            <thead>
                                <tr>
                                    <th>Classificação</th>
                                    <th>Nome do Plano</th>
                                    <th>Itens</th>
                                    <th>Ações</th>
                                </tr>
                            </thead>
                            <tbody id="tbody-planos">
                                <tr>
                                    <td colspan="4" style="text-align: center; padding: var(--space-8); color: var(--gray-600);">
                                        Carregando planos de contas...
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            
            <!-- Tab: Itens -->
            <div id="itens" class="tab-content">
                <div class="config-card">
                    <h3>
                        <span>📝</span>
                        Gerenciar Itens
                    </h3>
                    <div style="margin-bottom: var(--space-6);">
                        <button onclick="abrirModalItem()" class="btn btn-success">
                            <span>➕</span>
                            Novo Item
                        </button>
                    </div>
                    
                    <div class="table-container">
                        <table id="tabela-itens">
                            <thead>
                                <tr>
                                    <th>Classificação</th>
                                    <th>Plano de Contas</th>
                                    <th>Nome do Item</th>
                                    <th>Ações</th>
                                </tr>
                            </thead>
                            <tbody id="tbody-itens">
                                <tr>
                                    <td colspan="4" style="text-align: center; padding: var(--space-8); color: var(--gray-600);">
                                        Carregando itens...
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Modals -->
        <!-- Modal: Classificação -->
        <div id="modal-classificacao" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h3>
                        <span>📁</span>
                        <span id="modal-classificacao-titulo">Nova Classificação</span>
                    </h3>
                    <button class="btn-close" onclick="fecharModal('modal-classificacao')">✕</button>
                </div>
                
                <form id="form-classificacao">
                    <input type="hidden" id="classificacao-acao" value="criar">
                    <input type="hidden" id="classificacao-nome-antigo">
                    
                    <div class="form-group">
                        <label for="classificacao-nome">Nome da Classificação <span style="color: var(--danger-500);">*</span></label>
                        <input type="text" id="classificacao-nome" required placeholder="Ex: CUSTOS AAI, RECEITA INVESTIMENTOS...">
                    </div>
                    
                    <div class="form-buttons">
                        <button type="button" onclick="fecharModal('modal-classificacao')" class="btn btn-secondary">
                            <span>✕</span>
                            Cancelar
                        </button>
                        <button type="submit" class="btn btn-success">
                            <span>✅</span>
                            Salvar Classificação
                        </button>
                    </div>
                </form>
            </div>
        </div>
        
        <!-- Modal: Plano de Contas -->
        <div id="modal-plano-contas" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h3>
                        <span>📊</span>
                        <span id="modal-plano-titulo">Novo Plano de Contas</span>
                    </h3>
                    <button class="btn-close" onclick="fecharModal('modal-plano-contas')">✕</button>
                </div>
                
                <form id="form-plano-contas">
                    <input type="hidden" id="plano-acao" value="criar">
                    <input type="hidden" id="plano-nome-antigo">
                    
                    <div class="form-group">
                        <label for="plano-classificacao">Classificação <span style="color: var(--danger-500);">*</span></label>
                        <select id="plano-classificacao" required>
                            <option value="">Selecione uma classificação...</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label for="plano-nome">Nome do Plano de Contas <span style="color: var(--danger-500);">*</span></label>
                        <input type="text" id="plano-nome" required placeholder="Ex: Advogados, E-mail 360, Relatórios...">
                    </div>
                    
                    <div class="form-buttons">
                        <button type="button" onclick="fecharModal('modal-plano-contas')" class="btn btn-secondary">
                            <span>✕</span>
                            Cancelar
                        </button>
                        <button type="submit" class="btn btn-success">
                            <span>✅</span>
                            Salvar Plano
                        </button>
                    </div>
                </form>
            </div>
        </div>
        
        <!-- Modal: Item -->
        <div id="modal-item" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h3>
                        <span>📝</span>
                        <span id="modal-item-titulo">Novo Item</span>
                    </h3>
                    <button class="btn-close" onclick="fecharModal('modal-item')">✕</button>
                </div>
                
                <form id="form-item">
                    <input type="hidden" id="item-acao" value="criar">
                    <input type="hidden" id="item-nome-antigo">
                    
                    <div class="form-group">
                        <label for="item-classificacao">Classificação <span style="color: var(--danger-500);">*</span></label>
                        <select id="item-classificacao" onchange="atualizarPlanosItem()" required>
                            <option value="">Selecione uma classificação...</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label for="item-plano-contas">Plano de Contas <span style="color: var(--danger-500);">*</span></label>
                        <select id="item-plano-contas" required disabled>
                            <option value="">Selecione uma classificação primeiro...</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label for="item-nome">Nome do Item <span style="color: var(--danger-500);">*</span></label>
                        <input type="text" id="item-nome" required placeholder="Ex: Veritas, BHS AXTER, Link Solution...">
                    </div>
                    
                    <div class="form-buttons">
                        <button type="button" onclick="fecharModal('modal-item')" class="btn btn-secondary">
                            <span>✕</span>
                            Cancelar
                        </button>
                        <button type="submit" class="btn btn-success">
                            <span>✅</span>
                            Salvar Item
                        </button>
                    </div>
                </form>
            </div>
        </div>
        
        <!-- Modal: Confirmação de Exclusão -->
        <div id="modal-confirmacao" class="modal">
            <div class="modal-content" style="max-width: 500px;">
                <div class="modal-header">
                    <h3>
                        <span>⚠️</span>
                        Confirmar Exclusão
                    </h3>
                    <button class="btn-close" onclick="fecharModal('modal-confirmacao')">✕</button>
                </div>
                
                <div style="margin-bottom: var(--space-8);">
                    <div class="alert alert-warning">
                        <span>⚠️</span>
                        <div>
                            <strong>Atenção!</strong><br>
                            <span id="confirmacao-mensagem">Esta ação não pode ser desfeita.</span>
                        </div>
                    </div>
                </div>
                
                <div class="form-buttons">
                    <button type="button" onclick="fecharModal('modal-confirmacao')" class="btn btn-secondary">
                        <span>✕</span>
                        Cancelar
                    </button>
                    <button type="button" onclick="confirmarExclusao()" class="btn btn-danger">
                        <span>🗑️</span>
                        Sim, Excluir
                    </button>
                </div>
            </div>
        </div>
        
        <script>
        // Variáveis globais
        let classificacoesData = {};
        let transacoesData = [];
        let excluindoItem = null;

        // Navegação entre tabs
        function abrirTab(event, tabName) {
            // Remover active de todas as tabs
            document.querySelectorAll('.nav-tab').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            
            // Ativar tab selecionada
            event.target.classList.add('active');
            document.getElementById(tabName).classList.add('active');
            
            // Carregar dados específicos da tab
            switch(tabName) {
                case 'visao-geral':
                    carregarEstrutura();
                    break;
                case 'classificacoes':
                    carregarClassificacoes();
                    break;
                case 'planos-contas':
                    carregarPlanosContas();
                    break;
                case 'itens':
                    carregarItens();
                    break;
            }
        }

        // Carregar dados das classificações com cache
        async function carregarDados(forceReload = false) {
        // Se já carregou e não é force reload, usar cache
        if (Object.keys(classificacoesData).length > 0 && !forceReload) {
        return;
    }
    
    try {
        const [classificacoesResponse, transacoesResponse] = await Promise.all([
            fetch('/api/classificacoes'),
            fetch('/api/transacoes')
        ]);
        
        if (classificacoesResponse.ok) {
            const classificacoesResult = await classificacoesResponse.json();
            classificacoesData = classificacoesResult.classificacoes;
        }
        
        if (transacoesResponse.ok) {
            const transacoesResult = await transacoesResponse.json();
            transacoesData = transacoesResult.transacoes;
        }
    } catch (error) {
        console.error('Erro ao carregar dados:', error);
        mostrarAlerta('Erro ao carregar dados do sistema', 'danger');
    }
}

        // Carregar estrutura hierárquica
        async function carregarEstrutura() {
            const container = document.getElementById('estrutura-hierarquica');
            container.innerHTML = '<div style="text-align: center; padding: var(--space-8); color: var(--gray-600);"><div class="spinner" style="margin: 0 auto var(--space-4);"></div>Carregando estrutura...</div>';
            
            await carregarDados();
            
            let html = '';
            
            if (Object.keys(classificacoesData).length === 0) {
                html = '<div style="text-align: center; padding: var(--space-8); color: var(--gray-600);">📁 Nenhuma classificação configurada ainda</div>';
            } else {
                Object.entries(classificacoesData).forEach(([classificacao, planos]) => {
                    const totalPlanos = Object.keys(planos).length;
                    const totalItens = Object.values(planos).flat().length;
                    
                    html += `
                        <div class="hierarchy-item">
                            <div class="hierarchy-header" onclick="toggleHierarchy('${classificacao}')">
                                <div>
                                    <span>📁</span>
                                    <strong>${classificacao}</strong>
                                    <span style="margin-left: var(--space-2); opacity: 0.8; font-size: 0.875rem;">
                                        ${totalPlanos} plano${totalPlanos !== 1 ? 's' : ''} • ${totalItens} iten${totalItens !== 1 ? 's' : ''}
                                    </span>
                                </div>
                                <span id="toggle-${classificacao}">▼</span>
                            </div>
                            <div class="hierarchy-content" id="content-${classificacao}">
                    `;
                    
                    if (totalPlanos === 0) {
                        html += '<div style="text-align: center; padding: var(--space-4); color: var(--gray-600);">Nenhum plano de contas configurado</div>';
                    } else {
                        Object.entries(planos).forEach(([plano, itens]) => {
                            html += `
                                <div class="plano-item">
                                    <div class="plano-header">
                                        <div class="plano-title">
                                            <span>📊</span>
                                            ${plano}
                                        </div>
                                        <span style="font-size: 0.875rem; color: var(--gray-600);">
                                            ${itens.length} iten${itens.length !== 1 ? 's' : ''}
                                        </span>
                                    </div>
                            `;
                            
                            if (itens.length === 0) {
                                html += '<div style="font-size: 0.875rem; color: var(--gray-500); font-style: italic;">Nenhum item configurado</div>';
                            } else {
                                html += '<div class="items-list">';
                                itens.forEach(item => {
                                    html += `<span class="item-tag">📝 ${item}</span>`;
                                });
                                html += '</div>';
                            }
                            
                            html += '</div>';
                        });
                    }
                    
                    html += `
                            </div>
                        </div>
                    `;
                });
            }
            
            container.innerHTML = html;
            atualizarQuickStats();
        }
        
        
        
        // Quick Stats
        function atualizarQuickStats() {
            const totalClassificacoes = Object.keys(classificacoesData).length;
            const totalPlanos = Object.values(classificacoesData).reduce((acc, planos) => acc + Object.keys(planos).length, 0);
            const totalItens = Object.values(classificacoesData).reduce((acc, planos) => 
                acc + Object.values(planos).reduce((acc2, itens) => acc2 + itens.length, 0), 0);
            
            const transacoesComConfiguracoes = transacoesData.filter(t => 
                t.status === 'CONCILIADO' && t.classificacao && t.plano_contas && t.item
            ).length;
            
            const elementoClassificacoes = document.getElementById('quick-classificacoes');
            const elementoPlanos = document.getElementById('quick-planos');
            const elementoItens = document.getElementById('quick-itens');
            const elementoTransacoes = document.getElementById('quick-transacoes');
            
            if (elementoClassificacoes) elementoClassificacoes.textContent = totalClassificacoes;
            if (elementoPlanos) elementoPlanos.textContent = totalPlanos;
            if (elementoItens) elementoItens.textContent = totalItens;
            if (elementoTransacoes) elementoTransacoes.textContent = transacoesComConfiguracoes;
        }

        // Toggle hierarchy visibility
        function toggleHierarchy(classificacao) {
            const content = document.getElementById(`content-${classificacao}`);
            const toggle = document.getElementById(`toggle-${classificacao}`);
            
            if (content.classList.contains('collapsed')) {
                content.classList.remove('collapsed');
                toggle.textContent = '▼';
            } else {
                content.classList.add('collapsed');
                toggle.textContent = '▶';
            }
        }

        // Carregar classificações na tabela
        async function carregarClassificacoes() {
            const tbody = document.getElementById('tbody-classificacoes');
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: var(--space-8); color: var(--gray-600);">Carregando...</td></tr>';
            
            await carregarDados();
            
            let html = '';
            
            if (Object.keys(classificacoesData).length === 0) {
                html = '<tr><td colspan="5" style="text-align: center; padding: var(--space-8); color: var(--gray-600);">📁 Nenhuma classificação cadastrada</td></tr>';
            } else {
                Object.entries(classificacoesData).forEach(([classificacao, planos]) => {
                    const totalPlanos = Object.keys(planos).length;
                    const totalItens = Object.values(planos).flat().length;
                    const transacoesUsando = transacoesData.filter(t => t.classificacao === classificacao).length;
                    
                    html += `
                        <tr>
                            <td><strong>${classificacao}</strong></td>
                            <td>${totalPlanos}</td>
                            <td>${totalItens}</td>
                            <td>
                                <span style="color: ${transacoesUsando > 0 ? 'var(--success-600)' : 'var(--gray-500)'}; font-weight: 600;">
                                    ${transacoesUsando}
                                </span>
                            </td>
                            <td>
                                <button onclick="editarClassificacao('${classificacao}')" class="btn btn-warning" style="margin-right: var(--space-2);">
                                    <span>✏️</span>
                                    Editar
                                </button>
                                <button onclick="excluirClassificacao('${classificacao}', ${transacoesUsando})" class="btn btn-danger">
                                    <span>🗑️</span>
                                    Excluir
                                </button>
                            </td>
                        </tr>
                    `;
                });
            }
            
            tbody.innerHTML = html;
        }

        // Carregar planos de contas na tabela
        async function carregarPlanosContas() {
            const tbody = document.getElementById('tbody-planos');
            tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; padding: var(--space-8); color: var(--gray-600);">Carregando...</td></tr>';
            
            await carregarDados();
            
            let html = '';
            let totalPlanos = 0;
            
            Object.entries(classificacoesData).forEach(([classificacao, planos]) => {
                Object.entries(planos).forEach(([plano, itens]) => {
                    totalPlanos++;
                    html += `
                        <tr>
                            <td><strong>${classificacao}</strong></td>
                            <td>${plano}</td>
                            <td>${itens.length} iten${itens.length !== 1 ? 's' : ''}</td>
                            <td>
                                <button onclick="editarPlanoContas('${classificacao}', '${plano}')" class="btn btn-warning" style="margin-right: var(--space-2);">
                                    <span>✏️</span>
                                    Editar
                                </button>
                                <button onclick="excluirPlanoContas('${classificacao}', '${plano}')" class="btn btn-danger">
                                    <span>🗑️</span>
                                    Excluir
                                </button>
                            </td>
                        </tr>
                    `;
                });
            });
            
            if (totalPlanos === 0) {
                html = '<tr><td colspan="4" style="text-align: center; padding: var(--space-8); color: var(--gray-600);">📊 Nenhum plano de contas cadastrado</td></tr>';
            }
            
            tbody.innerHTML = html;
        }

        // Carregar itens na tabela
        async function carregarItens() {
            const tbody = document.getElementById('tbody-itens');
            tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; padding: var(--space-8); color: var(--gray-600);">Carregando...</td></tr>';
            
            await carregarDados();
            
            let html = '';
            let totalItens = 0;
            
            Object.entries(classificacoesData).forEach(([classificacao, planos]) => {
                Object.entries(planos).forEach(([plano, itens]) => {
                    itens.forEach(item => {
                        totalItens++;
                        html += `
                            <tr>
                                <td><strong>${classificacao}</strong></td>
                                <td>${plano}</td>
                                <td>${item}</td>
                                <td>
                                    <button onclick="editarItem('${classificacao}', '${plano}', '${item}')" class="btn btn-warning" style="margin-right: var(--space-2);">
                                        <span>✏️</span>
                                        Editar
                                    </button>
                                    <button onclick="excluirItem('${classificacao}', '${plano}', '${item}')" class="btn btn-danger">
                                        <span>🗑️</span>
                                        Excluir
                                    </button>
                                </td>
                            </tr>
                        `;
                    });
                });
            });
            
            if (totalItens === 0) {
                html = '<tr><td colspan="4" style="text-align: center; padding: var(--space-8); color: var(--gray-600);">📝 Nenhum item cadastrado</td></tr>';
            }
            
            tbody.innerHTML = html;
        }

        // Modals
        function abrirModalClassificacao(nomeClassificacao = null) {
            const modal = document.getElementById('modal-classificacao');
            const titulo = document.getElementById('modal-classificacao-titulo');
            const acao = document.getElementById('classificacao-acao');
            const nome = document.getElementById('classificacao-nome');
            const nomeAntigo = document.getElementById('classificacao-nome-antigo');
            
            if (nomeClassificacao) {
                titulo.textContent = 'Editar Classificação';
                acao.value = 'editar';
                nome.value = nomeClassificacao;
                nomeAntigo.value = nomeClassificacao;
            } else {
                titulo.textContent = 'Nova Classificação';
                acao.value = 'criar';
                nome.value = '';
                nomeAntigo.value = '';
            }
            
            modal.style.display = 'block';
            document.body.style.overflow = 'hidden';
            nome.focus();
        }

        function abrirModalPlanoContas(classificacao = null, plano = null) {
            const modal = document.getElementById('modal-plano-contas');
            const titulo = document.getElementById('modal-plano-titulo');
            const acao = document.getElementById('plano-acao');
            const selectClassificacao = document.getElementById('plano-classificacao');
            const inputNome = document.getElementById('plano-nome');
            const nomeAntigo = document.getElementById('plano-nome-antigo');
            
            // Preencher select de classificações
            selectClassificacao.innerHTML = '<option value="">Selecione uma classificação...</option>';
            Object.keys(classificacoesData).forEach(classif => {
                selectClassificacao.innerHTML += `<option value="${classif}">${classif}</option>`;
            });
            
            if (classificacao && plano) {
                titulo.textContent = 'Editar Plano de Contas';
                acao.value = 'editar';
                selectClassificacao.value = classificacao;
                inputNome.value = plano;
                nomeAntigo.value = plano;
            } else {
                titulo.textContent = 'Novo Plano de Contas';
                acao.value = 'criar';
                selectClassificacao.value = '';
                inputNome.value = '';
                nomeAntigo.value = '';
            }
            
            modal.style.display = 'block';
            document.body.style.overflow = 'hidden';
            inputNome.focus();
        }

        function abrirModalItem(classificacao = null, plano = null, item = null) {
            const modal = document.getElementById('modal-item');
            const titulo = document.getElementById('modal-item-titulo');
            const acao = document.getElementById('item-acao');
            const selectClassificacao = document.getElementById('item-classificacao');
            const selectPlano = document.getElementById('item-plano-contas');
            const inputNome = document.getElementById('item-nome');
            const nomeAntigo = document.getElementById('item-nome-antigo');
            
            // Preencher select de classificações
            selectClassificacao.innerHTML = '<option value="">Selecione uma classificação...</option>';
            Object.keys(classificacoesData).forEach(classif => {
                selectClassificacao.innerHTML += `<option value="${classif}">${classif}</option>`;
            });
            
            if (classificacao && plano && item) {
                titulo.textContent = 'Editar Item';
                acao.value = 'editar';
                selectClassificacao.value = classificacao;
                atualizarPlanosItem();
                selectPlano.value = plano;
                inputNome.value = item;
                nomeAntigo.value = item;
            } else {
                titulo.textContent = 'Novo Item';
                acao.value = 'criar';
                selectClassificacao.value = '';
                selectPlano.innerHTML = '<option value="">Selecione uma classificação primeiro...</option>';
                selectPlano.disabled = true;
                inputNome.value = '';
                nomeAntigo.value = '';
            }
            
            modal.style.display = 'block';
            document.body.style.overflow = 'hidden';
            inputNome.focus();
        }

        function atualizarPlanosItem() {
            const classificacao = document.getElementById('item-classificacao').value;
            const selectPlano = document.getElementById('item-plano-contas');
            
            if (classificacao && classificacoesData[classificacao]) {
                selectPlano.disabled = false;
                selectPlano.innerHTML = '<option value="">Selecione um plano de contas...</option>';
                
                Object.keys(classificacoesData[classificacao]).forEach(plano => {
                    selectPlano.innerHTML += `<option value="${plano}">${plano}</option>`;
                });
            } else {
                selectPlano.disabled = true;
                selectPlano.innerHTML = '<option value="">Selecione uma classificação primeiro...</option>';
            }
        }

        function fecharModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = 'auto';
        
        // Reset específico para modal de confirmação
        if (modalId === 'modal-confirmacao') {
            excluindoItem = null;
            
            // Restaurar botão se estiver com loading
            const btnConfirmar = modal.querySelector('.btn-danger');
            if (btnConfirmar && btnConfirmar.disabled) {
                btnConfirmar.innerHTML = '<span>🗑️</span> Sim, Excluir';
                btnConfirmar.disabled = false;
            }
        }
        
        // Reset formulários
        const forms = modal.querySelectorAll('form');
        forms.forEach(form => {
            if (form && typeof form.reset === 'function') {
                form.reset();
            }
        });
    }
}

        // Funções de edição
        function editarClassificacao(nome) {
            abrirModalClassificacao(nome);
        }

        function editarPlanoContas(classificacao, plano) {
            abrirModalPlanoContas(classificacao, plano);
        }

        function editarItem(classificacao, plano, item) {
            abrirModalItem(classificacao, plano, item);
        }

        // Funções de exclusão
        function excluirClassificacao(nome, transacoesUsando) {
            excluindoItem = {
                tipo: 'classificacao',
                nome: nome,
                transacoes: transacoesUsando
            };
            
            const mensagem = transacoesUsando > 0 
                ? `Você está prestes a excluir a classificação "${nome}". Esta classificação está sendo usada por ${transacoesUsando} transação${transacoesUsando !== 1 ? 'ões' : ''}. A exclusão não será permitida.`
                : `Você está prestes a excluir a classificação "${nome}" e todos os seus planos de contas e itens.`;
            
            document.getElementById('confirmacao-mensagem').innerHTML = mensagem;
            document.getElementById('modal-confirmacao').style.display = 'block';
            document.body.style.overflow = 'hidden';
        }

        function excluirPlanoContas(classificacao, plano) {
            const transacoesUsando = transacoesData.filter(t => 
                t.classificacao === classificacao && t.plano_contas === plano
            ).length;
            
            excluindoItem = {
                tipo: 'plano',
                classificacao: classificacao,
                plano: plano,
                transacoes: transacoesUsando
            };
            
            const mensagem = transacoesUsando > 0 
                ? `Você está prestes a excluir o plano de contas "${plano}" da classificação "${classificacao}". Este plano está sendo usado por ${transacoesUsando} transação${transacoesUsando !== 1 ? 'ões' : ''}. A exclusão não será permitida.`
                : `Você está prestes a excluir o plano de contas "${plano}" da classificação "${classificacao}" e todos os seus itens.`;
            
            document.getElementById('confirmacao-mensagem').innerHTML = mensagem;
            document.getElementById('modal-confirmacao').style.display = 'block';
            document.body.style.overflow = 'hidden';
        }

        function excluirItem(classificacao, plano, item) {
            const transacoesUsando = transacoesData.filter(t => 
                t.classificacao === classificacao && t.plano_contas === plano && t.item === item
            ).length;
            
                excluindoItem = {
            tipo: 'item',
            classificacao: classificacao,
            plano: plano,
            item: item,
            transacoes: transacoesUsando
        };
        
        const mensagem = transacoesUsando > 0 
            ? `Você está prestes a excluir o item "${item}" do plano "${plano}". Este item está sendo usado por ${transacoesUsando} transação${transacoesUsando !== 1 ? 'ões' : ''}. A exclusão não será permitida.`
            : `Você está prestes a excluir o item "${item}" do plano "${plano}".`;
        
        const mensagemElement = document.getElementById('confirmacao-mensagem');
        if (mensagemElement) {  // VERIFICAR SE ELEMENTO EXISTS
            mensagemElement.innerHTML = mensagem;
    }
    
    const modalElement = document.getElementById('modal-confirmacao');
    if (modalElement) {  // VERIFICAR SE MODAL EXISTS
        modalElement.style.display = 'block';
        document.body.style.overflow = 'hidden';
    }
}

        async function confirmarExclusao() {
    if (!excluindoItem) {
        fecharModal('modal-confirmacao');
        return;
    }
    
    // Verificar se pode excluir (se tem transações)
    if (excluindoItem.transacoes > 0) {
        mostrarAlerta('Não é possível excluir item que está em uso por transações', 'danger');
        fecharModal('modal-confirmacao');
        excluindoItem = null;
        return;
    }
    
    // Mostrar loading no botão
    const btnConfirmar = document.querySelector('#modal-confirmacao .btn-danger');
    const textoOriginal = btnConfirmar.innerHTML;
    btnConfirmar.innerHTML = '<div class="spinner" style="width: 16px; height: 16px; margin: 0 auto;"></div>';
    btnConfirmar.disabled = true;
    
    try {
        let response;
        let url;
        
        // Construir URL da API baseado no tipo
        switch (excluindoItem.tipo) {
            case 'classificacao':
                url = `/api/classificacoes/${encodeURIComponent(excluindoItem.nome)}`;
                break;
            case 'plano':
                url = `/api/planos-contas/${encodeURIComponent(excluindoItem.classificacao)}/${encodeURIComponent(excluindoItem.plano)}`;
                break;
            case 'item':
                url = `/api/itens/${encodeURIComponent(excluindoItem.classificacao)}/${encodeURIComponent(excluindoItem.plano)}/${encodeURIComponent(excluindoItem.item)}`;
                break;
        }
        
        response = await fetch(url, { method: 'DELETE' });
        
        if (response.ok) {
            const result = await response.json();
            mostrarAlerta(result.message || 'Item excluído com sucesso!', 'success');
            
            // Atualizar interface dinamicamente
            atualizarInterfaceAposExclusao();
        } else {
            const error = await response.json();
            mostrarAlerta(error.detail || 'Erro ao excluir', 'danger');
        }
        
    } catch (error) {
        console.error('Erro ao excluir:', error);
        mostrarAlerta('Erro de conexão: ' + error.message, 'danger');
    } finally {
        // Restaurar botão e fechar modal sempre
        btnConfirmar.innerHTML = textoOriginal;
        btnConfirmar.disabled = false;
        fecharModal('modal-confirmacao');
        excluindoItem = null;
    }
}

// Nova função para atualizar interface dinamicamente após exclusão
async function atualizarInterfaceAposExclusao() {
    if (!excluindoItem) return;
    
    const { tipo, classificacao, plano, item, nome } = excluindoItem;
    
    // Atualizar dados locais primeiro (mais rápido)
    switch (tipo) {
        case 'classificacao':
            delete classificacoesData[nome];
            break;
        case 'plano':
            if (classificacoesData[classificacao]) {
                delete classificacoesData[classificacao][plano];
            }
            break;
        case 'item':
            if (classificacoesData[classificacao] && classificacoesData[classificacao][plano]) {
                const index = classificacoesData[classificacao][plano].indexOf(item);
                if (index > -1) {
                    classificacoesData[classificacao][plano].splice(index, 1);
                }
            }
            break;
    }
    
    // Atualizar interface específica da tab ativa
    const tabAtiva = document.querySelector('.tab-content.active');
    if (tabAtiva) {
        const tabId = tabAtiva.id;
        
        setTimeout(() => {
            switch (tabId) {
                case 'visao-geral':
                    if (typeof carregarEstrutura === 'function') carregarEstrutura();
                    break;
                case 'classificacoes':
                    if (typeof carregarClassificacoes === 'function') carregarClassificacoes();
                    break;
                case 'planos-contas':
                    if (typeof carregarPlanosContas === 'function') carregarPlanosContas();
                    break;
                case 'itens':
                    if (typeof carregarItens === 'function') carregarItens();
                    break;
            }
        }, 100);
    }
}

        // Submissão de formulários
        document.getElementById('form-classificacao').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const acao = document.getElementById('classificacao-acao').value;
            const nome = document.getElementById('classificacao-nome').value.trim();
            const nomeAntigo = document.getElementById('classificacao-nome-antigo').value;
            
            if (!nome) {
                mostrarAlerta('Nome da classificação é obrigatório', 'danger');
                return;
            }
            
            try {
                let response;
                
                if (acao === 'criar') {
                    response = await fetch('/api/classificacoes', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({nome: nome})
                    });
                } else {
                    response = await fetch('/api/classificacoes', {
                        method: 'PUT',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            nome_antigo: nomeAntigo,
                            nome_novo: nome
                        })
                    });
                }
                
                if (response.ok) {
                    const result = await response.json();
                    mostrarAlerta(result.message, 'success');
                    fecharModal('modal-classificacao');
                    await carregarDados(true);
                    atualizarInterfaceAposOperacao();
                } else {
                    const error = await response.json();
                    mostrarAlerta(error.detail || 'Erro ao salvar classificação', 'danger');
                }
                
            } catch (error) {
                console.error('Erro ao salvar classificação:', error);
                mostrarAlerta('Erro ao salvar: ' + error.message, 'danger');
            }
        });

        document.getElementById('form-plano-contas').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const acao = document.getElementById('plano-acao').value;
            const classificacao = document.getElementById('plano-classificacao').value;
            const nome = document.getElementById('plano-nome').value.trim();
            const nomeAntigo = document.getElementById('plano-nome-antigo').value;
            
            if (!classificacao) {
                mostrarAlerta('Classificação é obrigatória', 'danger');
                return;
            }
            
            if (!nome) {
                mostrarAlerta('Nome do plano de contas é obrigatório', 'danger');
                return;
            }
            
            try {
                let response;
                
                if (acao === 'criar') {
                    response = await fetch('/api/planos-contas', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            classificacao: classificacao,
                            nome: nome
                        })
                    });
                } else {
                    response = await fetch('/api/planos-contas', {
                        method: 'PUT',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            classificacao: classificacao,
                            nome_antigo: nomeAntigo,
                            nome_novo: nome
                        })
                    });
                }
                
                if (response.ok) {
                    const result = await response.json();
                    mostrarAlerta(result.message, 'success');
                    fecharModal('modal-plano-contas');
                    await carregarDados(true);
                    atualizarInterfaceAposOperacao();
                } else {
                    const error = await response.json();
                    mostrarAlerta(error.detail || 'Erro ao salvar plano de contas', 'danger');
                }
                
            } catch (error) {
                console.error('Erro ao salvar plano de contas:', error);
                mostrarAlerta('Erro ao salvar: ' + error.message, 'danger');
            }
        });

        document.getElementById('form-item').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const acao = document.getElementById('item-acao').value;
            const classificacao = document.getElementById('item-classificacao').value;
            const planoContas = document.getElementById('item-plano-contas').value;
            const nome = document.getElementById('item-nome').value.trim();
            const nomeAntigo = document.getElementById('item-nome-antigo').value;
            
            if (!classificacao) {
                mostrarAlerta('Classificação é obrigatória', 'danger');
                return;
            }
            
            if (!planoContas) {
                mostrarAlerta('Plano de contas é obrigatório', 'danger');
                return;
            }
            
            if (!nome) {
                mostrarAlerta('Nome do item é obrigatório', 'danger');
                return;
            }
            
            try {
                let response;
                
                if (acao === 'criar') {
                    response = await fetch('/api/itens', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            classificacao: classificacao,
                            plano_contas: planoContas,
                            nome: nome
                        })
                    });
                } else {
                    response = await fetch('/api/itens', {
                        method: 'PUT',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            classificacao: classificacao,
                            plano_contas: planoContas,
                            nome_antigo: nomeAntigo,
                            nome_novo: nome
                        })
                    });
                }
                
                if (response.ok) {
                    const result = await response.json();
                    mostrarAlerta(result.message, 'success');
                    fecharModal('modal-item');
                    await carregarDados(true);
                    atualizarInterfaceAposOperacao();
                } else {
                    const error = await response.json();
                    mostrarAlerta(error.detail || 'Erro ao salvar item', 'danger');
                }
                
            } catch (error) {
                console.error('Erro ao salvar item:', error);
                mostrarAlerta('Erro ao salvar: ' + error.message, 'danger');
            }
        });
        function atualizarInterfaceAposOperacao() {
        const tabId = document.querySelector('.tab-content.active')?.id;
        if (tabId === 'classificacoes') carregarClassificacoes();
        else if (tabId === 'planos-contas') carregarPlanosContas();
        else if (tabId === 'itens') carregarItens();
        else if (tabId === 'visao-geral') carregarEstrutura();
        atualizarQuickStats();
    }


        // Funções utilitárias
        async function exportarConfiguracoes() {
            try {
                const response = await fetch('/api/configuracoes/export');
                if (response.ok) {
                    const data = await response.json();
                    
                    const blob = new Blob([JSON.stringify(data.data, null, 2)], {
                        type: 'application/json'
                    });
                    
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `configuracoes_conciliacao_${new Date().toISOString().split('T')[0]}.json`;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                    
                    mostrarAlerta('Configurações exportadas com sucesso!', 'success');
                } else {
                    mostrarAlerta('Erro ao exportar configurações', 'danger');
                }
            } catch (error) {
                console.error('Erro ao exportar:', error);
                mostrarAlerta('Erro ao exportar: ' + error.message, 'danger');
            }
        }

        function importarConfiguracoes() {
            const input = document.createElement('input');
            input.type = 'file';
            input.accept = '.json';
            input.style.display = 'none';
            
            input.addEventListener('change', async function(e) {
                const file = e.target.files[0];
                if (!file) return;
                
                try {
                    const text = await file.text();
                    const data = JSON.parse(text);
                    
                    if (!data.classificacoes || typeof data.classificacoes !== 'object') {
                        throw new Error('Arquivo de configuração inválido');
                    }
                    
                    if (!confirm('⚠️ ATENÇÃO: Isso substituirá TODAS as configurações atuais! Tem certeza?')) {
                        return;
                    }
                    
                    const response = await fetch('/api/configuracoes/import', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(data)
                    });
                    
                    if (response.ok) {
                        const result = await response.json();
                        mostrarAlerta(`Configurações importadas: ${result.imported_count.classificacoes} classificações, ${result.imported_count.planos} planos, ${result.imported_count.itens} itens`, 'success');
                        
                        await carregarDados();
                        carregarEstrutura();
                    } else {
                        const error = await response.json();
                        mostrarAlerta(error.detail || 'Erro ao importar configurações', 'danger');
                    }
                    
                } catch (error) {
                    console.error('Erro ao importar:', error);
                    mostrarAlerta('Erro ao processar arquivo: ' + error.message, 'danger');
                }
                
                document.body.removeChild(input);
            });
            
            document.body.appendChild(input);
            input.click();
        }

        async function resetarConfiguracoes() {
            if (!confirm('⚠️ ATENÇÃO: Isso apagará TODAS as configurações personalizadas! Tem certeza?')) {
                return;
            }
            
            if (!confirm('🚨 CONFIRMAÇÃO FINAL: Você realmente quer resetar para as configurações padrão?')) {
                return;
            }
            
            try {
                const response = await fetch('/api/configuracoes/reset', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'}
                });
                
                if (response.ok) {
                    const result = await response.json();
                    mostrarAlerta(`Configurações resetadas: ${result.restored_count.classificacoes} classificações, ${result.restored_count.planos} planos, ${result.restored_count.itens} itens`, 'success');
                    await carregarDados();
                    carregarEstrutura();
                } else {
                    const error = await response.json();
                    mostrarAlerta(error.detail || 'Erro ao resetar', 'danger');
                }
                
            } catch (error) {
                console.error('Erro ao resetar:', error);
                mostrarAlerta('Erro ao resetar configurações: ' + error.message, 'danger');
            }
        }

        async function validarConfiguracoes() {
            await carregarDados();
            
            let problemas = [];
            let totalClassificacoes = 0;
            let totalPlanos = 0;
            let totalItens = 0;
            
            Object.entries(classificacoesData).forEach(([classificacao, planos]) => {
                totalClassificacoes++;
                
                if (typeof planos !== 'object') {
                    problemas.push(`❌ Classificação "${classificacao}" tem estrutura inválida`);
                    return;
                }
                
                Object.entries(planos).forEach(([plano, itens]) => {
                    totalPlanos++;
                    
                    if (!Array.isArray(itens)) {
                        problemas.push(`❌ Plano "${plano}" em "${classificacao}" tem estrutura inválida`);
                        return;
                    }
                    
                    totalItens += itens.length;
                    
                    const itensUnicos = [...new Set(itens)];
                    if (itensUnicos.length !== itens.length) {
                        problemas.push(`⚠️ Plano "${plano}" em "${classificacao}" tem itens duplicados`);
                    }
                    
                    const itensVazios = itens.filter(item => !item || item.trim() === '');
                    if (itensVazios.length > 0) {
                        problemas.push(`❌ Plano "${plano}" em "${classificacao}" tem ${itensVazios.length} item(ns) vazio(s)`);
                    }
                });
            });
            
            if (problemas.length === 0) {
                mostrarAlerta(`✅ Configurações válidas! ${totalClassificacoes} classificações, ${totalPlanos} planos, ${totalItens} itens - nenhum problema encontrado.`, 'success');
            } else {
                let mensagem = `⚠️ Encontrados ${problemas.length} problema(s):\\n\\n`;
                mensagem += problemas.slice(0, 5).join('\\n');
                if (problemas.length > 5) {
                    mensagem += `\\n... e mais ${problemas.length - 5} problema(s)`;
                }
                
                mostrarAlerta(mensagem, 'warning');
            }
        }

        async function obterEstatisticas() {
            try {
                const response = await fetch('/api/configuracoes/stats');
                if (response.ok) {
                    const result = await response.json();
                    const stats = result.stats;
                    
                    let mensagem = `📊 ESTATÍSTICAS:\\n\\n`;
                    mensagem += `📁 Classificações: ${stats.total_classificacoes} (${stats.classificacoes_usadas} em uso - ${stats.percentual_uso_classificacoes}%)\\n`;
                    mensagem += `📊 Planos: ${stats.total_planos} (${stats.planos_usados} em uso - ${stats.percentual_uso_planos}%)\\n`;
                    mensagem += `📝 Itens: ${stats.total_itens} (${stats.itens_usados} em uso - ${stats.percentual_uso_itens}%)`;
                    
                    mostrarAlerta(mensagem, 'success');
                }
            } catch (error) {
                mostrarAlerta('Erro ao obter estatísticas: ' + error.message, 'danger');
            }
        }

        // Event listeners para modais
        document.addEventListener('click', function(event) {
            if (event.target.classList.contains('modal')) {
                fecharModal(event.target.id);
            }
        });

        document.addEventListener('keydown', function(event) {
            if (event.key === 'Escape') {
                const modaisAbertos = document.querySelectorAll('.modal');
                modaisAbertos.forEach(modal => {
                    if (modal.style.display === 'block') {
                        fecharModal(modal.id);
                    }
                });
            }
        });

        // Função para mostrar alertas
        function mostrarAlerta(mensagem, tipo) {
            const alertasExistentes = document.querySelectorAll('.alert');
            alertasExistentes.forEach(alerta => alerta.remove());
            
            const alerta = document.createElement('div');
            alerta.className = `alert alert-${tipo}`;
            alerta.innerHTML = `
                <span>${tipo === 'success' ? '✅' : tipo === 'danger' ? '❌' : '⚠️'}</span>
                <span>${mensagem}</span>
            `;
            
            const container = document.querySelector('.container');
            container.insertBefore(alerta, container.firstChild);
            
            setTimeout(() => {
                if (alerta.parentNode) {
                    alerta.remove();
                }
            }, 5000);
            
            window.scrollTo({top: 0, behavior: 'smooth'});
        }

        // Inicializar página otimizada
        window.onload = function() {
        // Carregar dados uma vez no início
        carregarDados().then(() => {
        carregarEstrutura();
    });
};
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# ====================================
# APIs PARA ESTRUTURA NORMALIZADA
# ====================================

@app.get("/api/classificacoes")
async def obter_classificacoes():
    """Obter classificações com cache otimizado"""
    try:
        if not supabase:
            raise HTTPException(status_code=500, detail="Banco não configurado")
        
        # Verificar cache primeiro
        cached_data = cache.get('estrutura', 'classificacoes')
        if cached_data:
            logger.info("✅ Usando classificações do cache")
            return cached_data
        
        logger.info("🔄 Cache miss - consultando banco...")
        
                
        # Buscar dados com menos queries
        classifs = supabase.admin_client.table("classificacoes").select("id,nome").eq("ativo", True).execute()
        planos = supabase.admin_client.table("planos_contas").select("id,nome,classificacao_id").eq("ativo", True).execute()
        itens = supabase.admin_client.table("itens").select("nome,plano_contas_id").eq("ativo", True).execute()
        
        # Construir estrutura
        estrutura = {}
        
        # Indexar planos por classificação
        planos_por_classif = {}
        for plano in planos.data:
            classif_id = plano['classificacao_id']
            if classif_id not in planos_por_classif:
                planos_por_classif[classif_id] = []
            planos_por_classif[classif_id].append(plano)
        
        # Indexar itens por plano
        itens_por_plano = {}
        for item in itens.data:
            plano_id = item['plano_contas_id']
            if plano_id not in itens_por_plano:
                itens_por_plano[plano_id] = []
            itens_por_plano[plano_id].append(item['nome'])
        
        # Montar estrutura final
        for classif in classifs.data:
            classif_nome = classif['nome']
            classif_id = classif['id']
            estrutura[classif_nome] = {}
            
            if classif_id in planos_por_classif:
                for plano in planos_por_classif[classif_id]:
                    plano_nome = plano['nome']
                    plano_id = plano['id']
                    estrutura[classif_nome][plano_nome] = itens_por_plano.get(plano_id, [])
        
        response_data = {
            'success': True,
            'classificacoes': estrutura,
            'totals': {
                'classificacoes': len(estrutura),
                'planos': sum(len(p) for p in estrutura.values()),
                'itens': sum(len(i) for p in estrutura.values() for i in p.values())
            }
        }
        
        # Armazenar no cache por 1 hora
        cache.set('estrutura', response_data, 'classificacoes')
        
        logger.info(f"✅ Estrutura carregada: {len(estrutura)} classificações")
        
        return response_data
        
    except Exception as e:
        logger.error(f"❌ ERRO ao obter classificações: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
    
@app.get("/api/classificacoes/debug")
async def debug_classificacoes():
    """API para debug das classificações"""
    try:
        if not supabase:
            return {"erro": "Supabase não configurado"}
        
        # Contar registros em cada tabela
        classifs = supabase.admin_client.table("classificacoes").select("id,nome,ativo").execute()
        planos = supabase.admin_client.table("planos_contas").select("id,nome,ativo,classificacao_id").execute()
        itens = supabase.admin_client.table("itens").select("id,nome,ativo,plano_contas_id").execute()
        
        # Contar ativos
        classifs_ativas = [c for c in classifs.data if c.get('ativo', True)]
        planos_ativos = [p for p in planos.data if p.get('ativo', True)]
        itens_ativos = [i for i in itens.data if i.get('ativo', True)]
        
        return {
            "debug_info": {
                "classificacoes": {
                    "total": len(classifs.data),
                    "ativas": len(classifs_ativas),
                    "inativas": len(classifs.data) - len(classifs_ativas),
                    "exemplos": classifs_ativas[:3]
                },
                "planos_contas": {
                    "total": len(planos.data),
                    "ativos": len(planos_ativos),
                    "inativos": len(planos.data) - len(planos_ativos),
                    "exemplos": planos_ativos[:3]
                },
                "itens": {
                    "total": len(itens.data),
                    "ativos": len(itens_ativos),
                    "inativos": len(itens.data) - len(itens_ativos),
                    "exemplos": itens_ativos[:3]
                }
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Erro no debug: {str(e)}")
        return {"erro": str(e)} 

@app.post("/api/classificacoes")
async def criar_classificacao_normalizada(dados: ClassificacaoRequest):
    """Criar classificação na estrutura normalizada"""
    try:
        if not supabase:
            raise HTTPException(status_code=500, detail="Banco não configurado")
        
        # Buscar usuário admin para created_by
        admin_result = supabase.admin_client.table("usuarios").select("id").eq("cargo", "admin").limit(1).execute()
        admin_id = admin_result.data[0]["id"] if admin_result.data else None
        
        # Criar classificação
        result = supabase.admin_client.table("classificacoes").insert({
            "nome": dados.nome,
            "created_by": admin_id,
            "ativo": True
        }).execute()
        
        if result.data:
            logger.info(f"✅ Classificação criada: {dados.nome}")   
            cache.invalidate_pattern('*', 'classificacoes')
            return {'success': True, 'message': 'Classificação criada com sucesso'}
        else:
            raise HTTPException(status_code=500, detail="Erro ao criar classificação")
            
    except Exception as e:
        logger.error(f"❌ Erro ao criar classificação: {str(e)}")
        if "duplicate key" in str(e).lower() or "unique" in str(e).lower():
            raise HTTPException(status_code=400, detail="Classificação já existe")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

@app.put("/api/classificacoes")
async def atualizar_classificacao_normalizada(dados: UpdateClassificacaoRequest):
    """Atualizar classificação na estrutura normalizada"""
    try:
        if not supabase:
            raise HTTPException(status_code=500, detail="Banco não configurado")
        
        # Buscar classificação pelo nome antigo
        result = supabase.admin_client.table("classificacoes").select("id").eq("nome", dados.nome_antigo).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Classificação não encontrada")
        
        classif_id = result.data[0]["id"]
        
        # Atualizar nome
        update_result = supabase.admin_client.table("classificacoes").update({
            "nome": dados.nome_novo
        }).eq("id", classif_id).execute()
        
        if update_result.data:
            logger.info(f"✅ Classificação atualizada: {dados.nome_antigo} -> {dados.nome_novo}")
            cache.invalidate_pattern('*', 'classificacoes')
            return {'success': True, 'message': 'Classificação atualizada com sucesso'}
        else:
            raise HTTPException(status_code=500, detail="Erro ao atualizar classificação")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar classificação: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

@app.delete("/api/classificacoes/{nome}")
async def excluir_classificacao_normalizada(nome: str):
    """Excluir classificação da estrutura normalizada"""
    try:
        if not supabase:
            raise HTTPException(status_code=500, detail="Banco não configurado")
        
        # Buscar classificação
        result = supabase.admin_client.table("classificacoes").select("id").eq("nome", nome).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Classificação não encontrada")
        
        classif_id = result.data[0]["id"]
        
        # Verificar se há transações usando esta classificação
        transacoes_usando = supabase.admin_client.table("transacoes").select("id").eq("classificacao_id", classif_id).execute()
        
        if transacoes_usando.data:
            raise HTTPException(
                status_code=400, 
                detail=f"Não é possível excluir. Há {len(transacoes_usando.data)} transações usando esta classificação."
            )
        
        # Excluir (CASCADE vai excluir planos e itens automaticamente)
        delete_result = supabase.admin_client.table("classificacoes").delete().eq("id", classif_id).execute()
        
        if delete_result.data:
            logger.info(f"✅ Classificação excluída: {nome}")
            cache.invalidate_pattern('*', 'classificacoes')
            return {'success': True, 'message': 'Classificação excluída com sucesso'}
        else:
            raise HTTPException(status_code=500, detail="Erro ao excluir classificação")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao excluir classificação: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

@app.post("/api/planos-contas")
async def criar_plano_contas_normalizado(dados: PlanoContasRequest):
    """Criar plano de contas na estrutura normalizada"""
    try:
        if not supabase:
            raise HTTPException(status_code=500, detail="Banco não configurado")
        
        # Buscar ID da classificação
        classif_result = supabase.admin_client.table("classificacoes").select("id").eq("nome", dados.classificacao).execute()
        if not classif_result.data:
            raise HTTPException(status_code=404, detail="Classificação não encontrada")
        
        classif_id = classif_result.data[0]["id"]
        
        # Buscar usuário admin  
        admin_result = supabase.admin_client.table("usuarios").select("id").eq("cargo", "admin").limit(1).execute()
        admin_id = admin_result.data[0]["id"] if admin_result.data else None
        
        # Criar plano de contas
        result = supabase.admin_client.table("planos_contas").insert({
            "classificacao_id": classif_id,
            "nome": dados.nome,
            "created_by": admin_id,
            "ativo": True
        }).execute()
        
        if result.data:
            logger.info(f"✅ Plano criado: {dados.nome} em {dados.classificacao}")
            cache.invalidate_pattern('*', 'classificacoes')
            return {'success': True, 'message': 'Plano de contas criado com sucesso'}
        else:
            raise HTTPException(status_code=500, detail="Erro ao criar plano de contas")
            
    except Exception as e:
        logger.error(f"❌ Erro ao criar plano: {str(e)}")
        if "duplicate key" in str(e).lower() or "unique" in str(e).lower():
            raise HTTPException(status_code=400, detail="Plano de contas já existe nesta classificação")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

@app.put("/api/planos-contas")
async def atualizar_plano_contas_normalizado(dados: UpdatePlanoContasRequest):
    """Atualizar plano de contas na estrutura normalizada"""
    try:
        if not supabase:
            raise HTTPException(status_code=500, detail="Banco não configurado")
        
        # Buscar ID da classificação
        classif_result = supabase.admin_client.table("classificacoes").select("id").eq("nome", dados.classificacao).execute()
        if not classif_result.data:
            raise HTTPException(status_code=404, detail="Classificação não encontrada")
        
        classif_id = classif_result.data[0]["id"]
        
        # Buscar plano de contas pelo nome antigo
        plano_result = supabase.admin_client.table("planos_contas").select("id").eq("classificacao_id", classif_id).eq("nome", dados.nome_antigo).execute()
        if not plano_result.data:
            raise HTTPException(status_code=404, detail="Plano de contas não encontrado")
        
        plano_id = plano_result.data[0]["id"]
        
        # Atualizar nome
        update_result = supabase.admin_client.table("planos_contas").update({
            "nome": dados.nome_novo
        }).eq("id", plano_id).execute()
        
        if update_result.data:
            logger.info(f"✅ Plano atualizado: {dados.nome_antigo} -> {dados.nome_novo}")
            cache.invalidate_pattern('*', 'classificacoes')
            return {'success': True, 'message': 'Plano de contas atualizado com sucesso'}
        else:
            raise HTTPException(status_code=500, detail="Erro ao atualizar plano de contas")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar plano: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

@app.delete("/api/planos-contas/{classificacao}/{plano}")
async def excluir_plano_contas_normalizado(classificacao: str, plano: str):
    """Excluir plano de contas da estrutura normalizada"""
    try:
        if not supabase:
            raise HTTPException(status_code=500, detail="Banco não configurado")
        
        # Buscar IDs
        classif_result = supabase.admin_client.table("classificacoes").select("id").eq("nome", classificacao).execute()
        if not classif_result.data:
            raise HTTPException(status_code=404, detail="Classificação não encontrada")
        
        classif_id = classif_result.data[0]["id"]
        
        plano_result = supabase.admin_client.table("planos_contas").select("id").eq("classificacao_id", classif_id).eq("nome", plano).execute()
        if not plano_result.data:
            raise HTTPException(status_code=404, detail="Plano de contas não encontrado")
        
        plano_id = plano_result.data[0]["id"]
        
        # Verificar se há transações usando este plano
        transacoes_usando = supabase.admin_client.table("transacoes").select("id").eq("plano_contas_id", plano_id).execute()
        
        if transacoes_usando.data:
            raise HTTPException(
                status_code=400, 
                detail=f"Não é possível excluir. Há {len(transacoes_usando.data)} transações usando este plano de contas."
            )
        
        # Excluir
        delete_result = supabase.admin_client.table("planos_contas").delete().eq("id", plano_id).execute()
        
        if delete_result.data:
            logger.info(f"✅ Plano excluído: {plano} de {classificacao}")
            cache.invalidate_pattern('*', 'classificacoes')
            return {'success': True, 'message': 'Plano de contas excluído com sucesso'}
        else:
            raise HTTPException(status_code=500, detail="Erro ao excluir plano de contas")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao excluir plano: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

@app.post("/api/itens")
async def criar_item_normalizado(dados: ItemRequest):
    """Criar item na estrutura normalizada"""
    try:
        if not supabase:
            raise HTTPException(status_code=500, detail="Banco não configurado")
        
        # Buscar IDs da classificação e plano
        classif_result = supabase.admin_client.table("classificacoes").select("id").eq("nome", dados.classificacao).execute()
        if not classif_result.data:
            raise HTTPException(status_code=404, detail="Classificação não encontrada")
        
        classif_id = classif_result.data[0]["id"]
        
        plano_result = supabase.admin_client.table("planos_contas").select("id").eq("classificacao_id", classif_id).eq("nome", dados.plano_contas).execute()
        if not plano_result.data:
            raise HTTPException(status_code=404, detail="Plano de contas não encontrado")
        
        plano_id = plano_result.data[0]["id"]
        
        # Buscar usuário admin
        admin_result = supabase.admin_client.table("usuarios").select("id").eq("cargo", "admin").limit(1).execute()
        admin_id = admin_result.data[0]["id"] if admin_result.data else None
        
        # Criar item
        result = supabase.admin_client.table("itens").insert({
            "plano_contas_id": plano_id,
            "nome": dados.nome,
            "created_by": admin_id,
            "ativo": True
        }).execute()
        
        if result.data:
            logger.info(f"✅ Item criado: {dados.nome} em {dados.classificacao}/{dados.plano_contas}")
            cache.invalidate_pattern('*', 'classificacoes')
            return {'success': True, 'message': 'Item criado com sucesso'}
        else:
            raise HTTPException(status_code=500, detail="Erro ao criar item")
            
    except Exception as e:
        logger.error(f"❌ Erro ao criar item: {str(e)}")
        if "duplicate key" in str(e).lower() or "unique" in str(e).lower():
            raise HTTPException(status_code=400, detail="Item já existe neste plano de contas")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

@app.put("/api/itens")
async def atualizar_item_normalizado(dados: UpdateItemRequest):
    """Atualizar item na estrutura normalizada"""
    try:
        if not supabase:
            raise HTTPException(status_code=500, detail="Banco não configurado")
        
        # Buscar IDs
        classif_result = supabase.admin_client.table("classificacoes").select("id").eq("nome", dados.classificacao).execute()
        if not classif_result.data:
            raise HTTPException(status_code=404, detail="Classificação não encontrada")
        
        classif_id = classif_result.data[0]["id"]
        
        plano_result = supabase.admin_client.table("planos_contas").select("id").eq("classificacao_id", classif_id).eq("nome", dados.plano_contas).execute()
        if not plano_result.data:
            raise HTTPException(status_code=404, detail="Plano de contas não encontrado")
        
        plano_id = plano_result.data[0]["id"]
        
        # Buscar item pelo nome antigo
        item_result = supabase.admin_client.table("itens").select("id").eq("plano_contas_id", plano_id).eq("nome", dados.nome_antigo).execute()
        if not item_result.data:
            raise HTTPException(status_code=404, detail="Item não encontrado")
        
        item_id = item_result.data[0]["id"]
        
        # Atualizar nome
        update_result = supabase.admin_client.table("itens").update({
            "nome": dados.nome_novo
        }).eq("id", item_id).execute()
        
        if update_result.data:
            logger.info(f"✅ Item atualizado: {dados.nome_antigo} -> {dados.nome_novo}")
            cache.invalidate_pattern('*', 'classificacoes')
            return {'success': True, 'message': 'Item atualizado com sucesso'}
        else:
            raise HTTPException(status_code=500, detail="Erro ao atualizar item")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar item: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

@app.delete("/api/itens/{classificacao}/{plano}/{item}")
async def excluir_item_normalizado(classificacao: str, plano: str, item: str):
    """Excluir item da estrutura normalizada"""
    try:
        if not supabase:
            raise HTTPException(status_code=500, detail="Banco não configurado")
        
        # Buscar IDs
        classif_result = supabase.admin_client.table("classificacoes").select("id").eq("nome", classificacao).execute()
        if not classif_result.data:
            raise HTTPException(status_code=404, detail="Classificação não encontrada")
        
        classif_id = classif_result.data[0]["id"]
        
        plano_result = supabase.admin_client.table("planos_contas").select("id").eq("classificacao_id", classif_id).eq("nome", plano).execute()
        if not plano_result.data:
            raise HTTPException(status_code=404, detail="Plano de contas não encontrado")
        
        plano_id = plano_result.data[0]["id"]
        
        item_result = supabase.admin_client.table("itens").select("id").eq("plano_contas_id", plano_id).eq("nome", item).execute()
        if not item_result.data:
            raise HTTPException(status_code=404, detail="Item não encontrado")
        
        item_id = item_result.data[0]["id"]
        
        # Verificar se há transações usando este item
        transacoes_usando = supabase.admin_client.table("transacoes").select("id").eq("item_id", item_id).execute()
        
        if transacoes_usando.data:
            raise HTTPException(
                status_code=400, 
                detail=f"Não é possível excluir. Há {len(transacoes_usando.data)} transações usando este item."
            )
        
        # Excluir
        delete_result = supabase.admin_client.table("itens").delete().eq("id", item_id).execute()
        
        if delete_result.data:
            logger.info(f"✅ Item excluído: {item} de {classificacao}/{plano}")
            cache.invalidate_pattern('*', 'classificacoes')
            return {'success': True, 'message': 'Item excluído com sucesso'}
        else:
            raise HTTPException(status_code=500, detail="Erro ao excluir item")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao excluir item: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

# FIM DAS APIs PARA ESTRUTURA NORMALIZADA

# API para resetar configurações para o padrão
@app.post("/api/configuracoes/reset")
async def resetar_configuracoes():
    """Resetar configurações para o padrão do sistema"""
    global classificacoes
        
    # Fazer backup das configurações atuais
    backup_classificacoes = classificacoes.copy()
    
    try:
        # Restaurar classificações padrão originais do sistema
        classificacoes_padrao = {
            'CUSTOS AAI': {
                'Advogados': ['Veritas'],
                'E-mail 360': ['BHS AXTER'],
                'Gravador de voz': ['Link Solution'],
                'Relatórios': ['BDM', 'IR', 'IR TRADE', 'Lemit', 'OPLAB', 'Quantum'],
                'Taxa fiscalização CVM': ['0'],
                'Treinamento Assessores': ['Prova FEBRABAN']
            },
            'DESPESA COM MARKETING': {
                'Agência de Mktg': ['0'],
                'Almoço com clientes': ['Clientes Daniel', 'Clientes Leandro'],
                'Associação Comercial': ['ACIP'],
                'Brindes Assessores': ['Thera Day'],
                'Brindes Clientes': ['Cliente Unimed'],
                'Cartões de Visita': ['0'],
                'Eventos': ['Bar', 'Bônus HH', 'Buffet', 'Caixas', 'Camisetas Beacth', 'Champanheira', 'Evento Silvia', 'Fisio', 'Garçom', 'Hotel Rafi', 'Manobrista', 'Mesas', 'Mesas e taças', 'Mulheres / Taças /Toalhas', 'Musico', 'Play Tennis / Promoter', 'Projetor', 'Promoter', 'Queijos', 'Som', 'Sorvete', 'Toalhas beach tennis', 'Utensilíos', 'Vinhos'],
                'Eventos Interno Thera': ['Camisetas', 'Camisetas Thera Day', 'Fotográfo', 'Som', 'Thera Day - Chopp', 'Thera Day - Iphone', 'Thera Day - Notebook', 'Thera Day - Placas', 'Thera Day - Projetor', 'Thera Day - Relógio', 'Van Campinas', 'Van RP', 'Vila Dei Colori'],
                'Facebook Ads': ['0'],
                'Google Ads': ['0'],
                'Materiais Institucionais': ['Brochuras'],
                'Outras Despesas Mktg': ['Campanha Patrocinada', 'Lembrança dia das mães'],
                'Patrocínios': ['Ajuda Unimed', 'Alphaville', 'Araraquarense', 'Associação Comercial', 'Fundesport', 'Play Tennis'],
                'Site e E-mail Mktg': ['0']
            },
            'DESPESA COM RH': {
                'Assessor Comercial': ['Bonificação - CFA - 2s.2024', 'Bonificação CFA - Panthera - 2s.2024', 'Bônus', 'Bônus ', 'Bônus Cluster A', 'Bônus Cluster B', 'Fixo', 'Gestor', 'Piso', 'Variável'],
                'Assessor de Produtos': ['Bonificação - CFA - 2s.2024', 'Bônus', 'Bônus ', 'Fixo', 'Variável'],
                'Assistente Operacional': ['Bonificação - CFA - 2s.2024', 'Bônus', 'Fixo', 'Reembolso - Prova Ancord', 'Variável'],
                'CLTs': ['Férias', 'Recisão', 'Salário', 'Vale alimentação', 'Vale Transporte'],
                'Diretores': ['Bonificação - CFA - 2s.2024', 'Fixo'],
                'Operador de Mesa': ['Bonificação - CFA - 2s.2024', 'Variável'],
                'Plano de Saúde': ['Bradesco', 'CLT\'s', 'José Rafael e Thiago Menezes', 'Luiz Toloi (Unimed)', 'Variável', 'Livia Benassi', 'Parceiro Pedro (Willian Nascimento)']
            },
            'DESPESAS FINANCEIRAS': {
                'Imposto Retroativo': ['0'],
                'Outros Valores': ['Patrick', 'Thiago Menezes','0']
            },
            'DESPESAS OPERACIONAIS': {
                'Aluguel': ['Arenco', 'IPTU', 'Nova Camp', 'Pereira Alvim', 'Ribeirão Imóveis'],
                'Cartuchos': ['0'],
                'Condomínio': ['0'],
                'Conta de água': ['0'],
                'Contabilidade': ['Audiplan', 'Certificação Digital'],
                'Emissor de notas': ['Site Notas'],
                'CPFL / Energia': ['0'],
                'Estacionamento': ['0'],
                'Faxineira': ['Jeni', 'Maria Brasileira', 'Nil'],
                'Internet': ['Alcans', 'Algar', 'NET', 'Vivo'],
                'Materiais de escritório': ['0', 'Café', 'Computador', 'Fita', 'Fone', 'Lampadas', 'Maquina de café', 'Teclado e Mouse'],
                'Materiais de limpeza': ['0'],
                'Outras Despesas': ['Estorno ', 'Renovação Seguro', 'Seguro Incêndio', 'ZOOM'],
                'Serviços de Manutenção': ['0', 'Chaves', 'Cortina', 'Limpeza Pisos'],
                'Supermercados': ['0'],
                'Tarifas bancárias': ['0', 'Pacote Serviços', 'Tarifa Avulso Pix'],
                'Tecnico Informática': ['0'],
                'Telefone': ['Algar', 'Celulares Claro', 'Directcall', 'DIRECTCALL BRASIL'],
                'Uber': ['0'],
                'Viagens': ['Arthur / 2 Dias XP', 'Bruno Yudi', 'Guilherme Rossetti', 'José Rafael', 'José Rafael (Passagem Aérea)', 'José Rafael e Luiz Toloi (B2B Experience)', 'Lucas Lima', 'Luciano Mudesto']
            },
            'IMPOSTOS': {
                'COFINS': ['0'],
                'CSLL': ['0', '10', '11', '12'],
                'FGTS': ['0'],
                'GPS': ['0'],
                'IRPJ': ['0', '10', '11', '12'],
                'IRPJ ADICIONAL': ['0'],
                'ISS': ['0'],
                'PIS': ['0']
            },
            'RECEITA INVESTIMENTOS': {
                'Asset': ['0'],
                'BM&F': ['0'],
                'Bovespa': ['0'],
                'Bovespa FIIs': ['0'],
                'BTC': ['0'],
                'Campanha Fundos Imobiliários': ['0'],
                'Campanha RV': ['0'],
                'Campanhas': ['0'],
                'Clearthrough': ['COE', 'Renda Fixa', 'RF'],
                'COE': ['0'],
                'Desconto de Transferência de Clientes': ['0'],
                'Enquadramento RLP': ['0'],
                'Erro Operacional': ['0'],
                'Fee Fixo': ['0'],
                'Internacional': ['0'],
                'Oferta RF': ['0'],
                'Outros Valores': ['0'],
                'Produtos Estruturados': ['0'],
                'Renda Fixa': ['0'],
                'Secundário FIIs': ['0']
            },
            'RECEITA OUTROS PRODUTOS': {
                'Câmbio XP': ['0', 'Crédito Reserva'],
                'Campanhas PJ2': ['0'],
                'Câmbio': ['Mercado Internacional'],
                'Previdência': ['Previdência XP'],
                'Conta Global': ['0'],
                'Crédito': ['0', 'FMB4', 'Franq'],
                'Crédito Colaterizado': ['0'],
                'IAXP': ['0'],
                'Mercado Internacional': ['0'],
                'Outras Receitas': ['0'],
                'Previdência - Co-corretagem': ['0'],
                'RV': ['Previdência XP'],
                'Seguro de vida': ['0', 'MetLife', 'Mongeral', 'Previdência', 'Prudential'],
                'Taxa de Performance': ['0']
            }
        }
        
        # Aplicar configurações padrão
        classificacoes = classificacoes_padrao
        
        logger.info("Configurações resetadas para o padrão do sistema")
        
        # Contar elementos
        total_classificacoes = len(classificacoes)
        total_planos = sum(len(planos) for planos in classificacoes.values())
        total_itens = sum(len(itens) for planos in classificacoes.values() for itens in planos.values())
        
        return {
            'success': True,
            'message': 'Configurações resetadas para o padrão do sistema com sucesso',
            'restored_count': {
                'classificacoes': total_classificacoes,
                'planos': total_planos,
                'itens': total_itens
            }
        }
        
    except Exception as e:
        # Restaurar backup em caso de erro
        classificacoes = backup_classificacoes
        logger.error(f"Erro ao resetar configurações: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao resetar configurações: {str(e)}"
        )
    
# ROTAS DE AUTENTICAÇÃO - ADICIONAR ANTES DO if __name__
# ===============================================
@app.post("/api/auth/login")
async def login(dados: LoginRequest):
    """Login do usuário com senha individual"""
    try:
        logger.info(f"🔍 Tentativa de login: {dados.email}")
        
        if not supabase:
            logger.error("❌ Supabase não configurado")
            raise HTTPException(status_code=500, detail="Supabase não configurado")
        
        logger.info("✅ Supabase configurado, procurando usuário...")
        
        # Buscar usuário na tabela (incluindo senha_hash)
        user_result = supabase.admin_client.table("usuarios").select("*").eq("email", dados.email).execute()
        logger.info(f"🔍 Usuário encontrado na tabela: {len(user_result.data) > 0}")
        
        if not user_result.data:
            logger.error(f"❌ Usuário {dados.email} não encontrado")
            raise HTTPException(status_code=401, detail="Email ou senha incorretos")
        
        user_profile = user_result.data[0]
        logger.info(f"✅ Perfil encontrado: {user_profile['nome']} ({user_profile['cargo']})")
        
        # Verificar se usuário está ativo
        if not user_profile.get('ativo', True):
            logger.error(f"❌ Usuário {dados.email} está desativado")
            raise HTTPException(status_code=401, detail="Usuário desativado")
        
        # ===== CORREÇÃO: VERIFICAR SENHA INDIVIDUAL =====
        senha_hash = user_profile.get('senha_hash')
        
        if not senha_hash:
            # Usuário antigo sem senha hash - REJEITAR LOGIN
            logger.error(f"❌ Usuário {dados.email} não tem senha configurada")
            raise HTTPException(status_code=401, detail="Usuário sem senha configurada. Contate o administrador.")
        
        # Verificar senha hash individual
        logger.info("🔐 Verificando senha individual com hash...")
        if not verify_password(dados.password, senha_hash):
            logger.error(f"❌ Senha incorreta para {dados.email}")
            raise HTTPException(status_code=401, detail="Email ou senha incorretos")
        
        logger.info("✅ Senha verificada com sucesso!")
        
        # Criar token fake temporário
        import uuid
        fake_token = f"token_{uuid.uuid4()}"
        
        # Resposta de sucesso
        response = {
            "access_token": fake_token,
            "token_type": "bearer", 
            "expires_in": 3600,
            "user": {
                "id": user_profile["id"],
                "nome": user_profile["nome"],
                "email": user_profile["email"],
                "cargo": user_profile["cargo"],
                "ativo": user_profile["ativo"],
                "created_at": user_profile["created_at"]
            }
        }
        
        logger.info(f"✅ Login realizado com sucesso: {dados.email}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ ERRO DETALHADO: {str(e)}")
        logger.error(f"❌ TIPO DO ERRO: {type(e)}")
        import traceback
        logger.error(f"❌ TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

@app.post("/api/auth/logout")
async def logout(user: dict = Depends(get_current_user)):
    """Logout do usuário"""
    try:
        await supabase.sign_out()
        logger.info(f"✅ Logout: {user['email']}")
        return {"message": "Logout realizado com sucesso"}
    except Exception as e:
        logger.error(f"❌ Erro no logout: {str(e)}")
        raise HTTPException(status_code=500, detail="Erro no logout")

@app.get("/api/auth/me")
async def obter_perfil(user: dict = Depends(get_current_user)):
    """Obter dados do usuário atual"""
    return UsuarioResponse(**user)

@app.get("/api/auth/verify")
async def verificar_token(user: dict = Depends(get_current_user)):
    """Verificar se token é válido"""
    return {
        "valid": True,
        "user_id": user["id"],
        "cargo": user["cargo"],
        "nome": user["nome"]
    }

@app.get("/login")
async def login_page():
    """Página de login"""
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Login - Sistema de Conciliação</title>
        <style>
            body { font-family: Arial, sans-serif; background: #f5f5f5; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
            .login-container { background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); width: 100%; max-width: 400px; }
            .logo { text-align: center; margin-bottom: 2rem; }
            .logo h1 { color: #333; margin-bottom: 0.5rem; }
            .form-group { margin-bottom: 1rem; }
            .form-group label { display: block; margin-bottom: 0.5rem; font-weight: bold; color: #333; }
            .form-group input { width: 100%; padding: 0.75rem; border: 1px solid #ddd; border-radius: 4px; font-size: 1rem; box-sizing: border-box; }
            .btn { width: 100%; padding: 0.75rem; background: #007bff; color: white; border: none; border-radius: 4px; font-size: 1rem; cursor: pointer; margin-bottom: 1rem; }
            .btn:hover { background: #0056b3; }
            .alert { padding: 0.75rem; border-radius: 4px; margin-bottom: 1rem; font-size: 0.875rem; }
            .alert-error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
            .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        </style>
    </head>
    <body>
        <div class="login-container">
            <div class="logo">
                <h1>🏦 Sistema de Conciliação</h1>
                <p>Faça login para continuar</p>
            </div>
            
            <div id="alert-container"></div>
            
            <form id="login-form">
                <div class="form-group">
                    <label for="email">Email</label>
                    <input type="email" id="email" required placeholder="Digite seu email">
                </div>
                
                <div class="form-group">
                    <label for="password">Senha</label>
                    <input type="password" id="password" required placeholder="Digite sua senha">
                </div>
                
                <button type="submit" class="btn" id="login-btn">
                    Entrar
                </button>
            </form>
        </div>
        
        <script>
            function showAlert(message, type = 'error') {
                const container = document.getElementById('alert-container');
                container.innerHTML = `<div class="alert alert-${type}">${message}</div>`;
            }
            
            function setLoading(loading) {
                const btn = document.getElementById('login-btn');
                btn.disabled = loading;
                btn.innerHTML = loading ? 'Entrando...' : 'Entrar';
            }
            
            document.getElementById('login-form').addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const email = document.getElementById('email').value;
                const password = document.getElementById('password').value;
                
                setLoading(true);
                
                try {
                    const response = await fetch('/api/auth/login', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({email, password})
                    });
                    
                    if (response.ok) {
                        const data = await response.json();
                        
                        // Salvar token
                        localStorage.setItem('access_token', data.access_token);
                        localStorage.setItem('user', JSON.stringify(data.user));
                        
                        showAlert('Login realizado com sucesso! Redirecionando...', 'success');
                        
                        setTimeout(() => {
                            window.location.href = '/';
                        }, 1000);
                        
                    } else {
                        const error = await response.json();
                        showAlert(error.detail || 'Login falhou');
                    }
                    
                } catch (error) {
                    showAlert('Erro de conexão: ' + error.message);
                } finally {
                    setLoading(false);
                }
            });
            
            // Se já está logado, redirecionar
            if (localStorage.getItem('access_token')) {
                window.location.href = '/';
            }
        </script>
    </body>
    </html>
    """)    
# === GESTÃO DE USUÁRIOS (APENAS ADMINS) ===

@app.get("/usuarios")
async def pagina_usuarios():
    """Página de gestão de usuários - verificação via JS"""
    html_content = """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Gestão de Usuários</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            body { font-family: 'Inter', Arial, sans-serif; margin: 0; padding: 60px 0 0 0; background: #f8fafc; }
            
            /* Loading Screen */
            #loading { 
                display: flex; 
                justify-content: center; 
                align-items: center; 
                min-height: 100vh; 
                flex-direction: column; 
                gap: 1rem;
                font-size: 1.2rem; 
                color: #6b7280;
            }
            
            .spinner { 
                width: 40px; 
                height: 40px; 
                border: 4px solid #e5e7eb; 
                border-top: 4px solid #3b82f6; 
                border-radius: 50%; 
                animation: spin 1s linear infinite; 
            }
            
            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
            
            /* App Content */
            #app { display: none; }
            
            .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }
            
            .header { background: white; border-radius: 12px; padding: 2rem; margin-bottom: 2rem; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .header h1 { margin: 0 0 0.5rem 0; color: #1f2937; display: flex; align-items: center; gap: 0.75rem; }
            .header p { margin: 0; color: #6b7280; }
            
            .actions { display: flex; gap: 1rem; margin-bottom: 2rem; flex-wrap: wrap; }
            .btn { display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.75rem 1.5rem; border: none; border-radius: 8px; font-weight: 600; text-decoration: none; cursor: pointer; transition: all 0.2s; }
            .btn-primary { background: #3b82f6; color: white; }
            .btn-primary:hover { background: #2563eb; }
            .btn-success { background: #22c55e; color: white; }
            .btn-success:hover { background: #16a34a; }
            .btn-secondary { background: #6b7280; color: white; }
            .btn-secondary:hover { background: #4b5563; }
            .btn-danger { background: #ef4444; color: white; }
            .btn-danger:hover { background: #dc2626; }
            
            .card { background: white; border-radius: 12px; padding: 2rem; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            
            table { width: 100%; border-collapse: collapse; }
            th, td { padding: 1rem; text-align: left; border-bottom: 1px solid #e5e7eb; }
            th { background: #f9fafb; font-weight: 600; color: #374151; }
            tr:hover { background: #f9fafb; }
            
            .status-badge { padding: 0.25rem 0.75rem; border-radius: 6px; font-size: 0.875rem; font-weight: 600; }
            .status-ativo { background: #dcfce7; color: #166534; }
            .status-inativo { background: #fee2e2; color: #991b1b; }
            
            .cargo-badge { padding: 0.25rem 0.75rem; border-radius: 6px; font-size: 0.875rem; font-weight: 600; }
            .cargo-admin { background: #fef3c7; color: #92400e; }
            .cargo-supervisor { background: #dbeafe; color: #1e40af; }
            .cargo-operador { background: #f3e8ff; color: #7c3aed; }
            
            /* Modal */
            .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1000; }
            .modal-content { position: relative; background: white; margin: 5% auto; padding: 2rem; border-radius: 12px; width: 90%; max-width: 500px; }
            .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; }
            .modal-header h3 { margin: 0; display: flex; align-items: center; gap: 0.75rem; }
            .btn-close { background: #ef4444; color: white; border: none; border-radius: 6px; padding: 0.5rem; cursor: pointer; width: 40px; height: 40px; }
            
            .form-group { margin-bottom: 1.5rem; }
            .form-group label { display: block; margin-bottom: 0.5rem; font-weight: 600; color: #374151; }
            .form-group input, .form-group select { width: 100%; padding: 0.75rem; border: 1px solid #d1d5db; border-radius: 8px; font-size: 1rem; box-sizing: border-box; }
            .form-group input:focus, .form-group select:focus { outline: none; border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,0.1); }
            
            .form-buttons { display: flex; justify-content: flex-end; gap: 1rem; margin-top: 2rem; }
            
            .alert { padding: 1rem; border-radius: 8px; margin-bottom: 1rem; }
            .alert-success { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
            .alert-danger { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
            
            /* Erro de permissão */
            .error-container { 
                display: none; 
                text-align: center; 
                padding: 4rem 2rem; 
                background: white; 
                border-radius: 12px; 
                margin: 2rem auto; 
                max-width: 500px; 
                box-shadow: 0 2px 4px rgba(0,0,0,0.1); 
            }
        </style>
    </head>
    <body>
        <!-- Loading Screen -->
        <div id="loading">
            <div class="spinner"></div>
            <div>🔄 Verificando permissões...</div>
        </div>
        
        <!-- Erro de Permissão -->
        <div id="erro-permissao" class="error-container">
            <h2 style="color: #ef4444; margin-bottom: 1rem;">🚫 Acesso Negado</h2>
            <p style="color: #6b7280; margin-bottom: 2rem;">Apenas administradores podem acessar esta página.</p>
            <a href="/" class="btn btn-primary">🏠 Voltar ao Sistema</a>
        </div>
        
        <!-- App Content -->
        <div id="app">
            <div class="container">
                <div class="header">
                    <h1>👥 Gestão de Usuários</h1>
                    <p>Cadastre e gerencie usuários do sistema de conciliação</p>
                </div>
                
                <div class="actions">
                    <button onclick="abrirModalNovoUsuario()" class="btn btn-success">
                        ➕ Novo Usuário
                    </button>
                    <a href="/" class="btn btn-secondary">
                        🏠 Voltar ao Sistema
                    </a>
                </div>
                
                <div class="card">
                    <h3 style="margin-top: 0;">📋 Usuários Cadastrados</h3>
                    
                    <table id="tabela-usuarios">
                        <thead>
                            <tr>
                                <th>Nome</th>
                                <th>Email</th>
                                <th>Cargo</th>
                                <th>Status</th>
                                <th>Criado em</th>
                                <th>Ações</th>
                            </tr>
                        </thead>
                        <tbody id="tbody-usuarios">
                            <tr>
                                <td colspan="6" style="text-align: center; padding: 2rem; color: #6b7280;">
                                    Carregando usuários...
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <!-- Modal Novo Usuário -->
        <div id="modal-novo-usuario" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h3>➕ Novo Usuário</h3>
                    <button class="btn-close" onclick="fecharModal()">✕</button>
                </div>
                
                <div id="alert-container"></div>
                
                <form id="form-novo-usuario">
                    <div class="form-group">
                        <label>Nome Completo *</label>
                        <input type="text" id="nome" required placeholder="Ex: João Silva">
                    </div>
                    
                    <div class="form-group">
                        <label>Email *</label>
                        <input type="email" id="email" required placeholder="Ex: joao@empresa.com">
                    </div>
                    
                    <div class="form-group">
                        <label>Senha *</label>
                        <input type="password" id="senha" required placeholder="Mínimo 6 caracteres">
                    </div>
                    
                    <div class="form-group">
                        <label>Cargo *</label>
                        <select id="cargo" required>
                            <option value="">Selecione o cargo...</option>
                            <option value="operador">Operador</option>
                            <option value="supervisor">Supervisor</option>
                            <option value="admin">Administrador</option>
                        </select>
                    </div>
                    
                    <div class="form-buttons">
                        <button type="button" onclick="fecharModal()" class="btn btn-secondary">
                            Cancelar
                        </button>
                        <button type="submit" class="btn btn-success">
                            💾 Criar Usuário
                        </button>
                    </div>
                </form>
            </div>
        </div>
        
        <script>
        let usuarios = [];
        
        // Verificar autenticação e permissões
        async function checkAuth() {
            console.log('🔍 Verificando autenticação...');
            
            const token = localStorage.getItem('access_token');
            const userData = localStorage.getItem('user');
            
            if (!token || !userData) {
                console.log('❌ Sem token/dados, redirecionando para login');
                window.location.href = '/login';
                return;
            }
            
            try {
                const user = JSON.parse(userData);
                console.log('✅ Usuário encontrado:', user);
                
                // Verificar se é admin
                if (user.cargo !== 'admin') {
                    console.log('❌ Usuário não é admin:', user.cargo);
                    document.getElementById('loading').style.display = 'none';
                    document.getElementById('erro-permissao').style.display = 'block';
                    return;
                }
                
                console.log('✅ Usuário é admin, carregando interface...');
                
                // Mostrar app e carregar usuários
                document.getElementById('loading').style.display = 'none';
                document.getElementById('app').style.display = 'block';
                
                // Carregar lista de usuários
                carregarUsuarios();
                
            } catch (error) {
                console.error('❌ Erro ao processar dados do usuário:', error);
                localStorage.removeItem('access_token');
                localStorage.removeItem('user');
                window.location.href = '/login';
            }
        }
        
        async function carregarUsuarios() {
    try {
        console.log('🔄 Carregando usuários...');
        
        // REMOVER O HEADER DE AUTHORIZATION
        const response = await fetch('/api/usuarios');
        
        console.log('📨 Response status:', response.status);
        
        if (response.ok) {
            const data = await response.json();
            console.log('✅ Dados recebidos:', data);
            usuarios = data.usuarios;
            renderizarUsuarios();
        } else {
            const errorText = await response.text();
            console.error('❌ Erro response:', response.status, errorText);
            mostrarAlerta('Erro ao carregar usuários: ' + response.status, 'danger');
        }
    } catch (error) {
        console.error('❌ Erro de conexão:', error);
        mostrarAlerta('Erro de conexão: ' + error.message, 'danger');
    }
}
        
        function renderizarUsuarios() {
            const tbody = document.getElementById('tbody-usuarios');
            
            if (usuarios.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 2rem; color: #6b7280;">Nenhum usuário encontrado</td></tr>';
                return;
            }
            
            tbody.innerHTML = usuarios.map(user => {
                const dataFormatada = new Date(user.created_at).toLocaleDateString('pt-BR');
                const statusClass = user.ativo ? 'status-ativo' : 'status-inativo';
                const statusText = user.ativo ? 'Ativo' : 'Inativo';
                const cargoClass = `cargo-${user.cargo}`;
                const cargoText = user.cargo.charAt(0).toUpperCase() + user.cargo.slice(1);
                
                return `
                    <tr>
                        <td><strong>${user.nome}</strong></td>
                        <td>${user.email}</td>
                        <td><span class="cargo-badge ${cargoClass}">${cargoText}</span></td>
                        <td><span class="status-badge ${statusClass}">${statusText}</span></td>
                        <td>${dataFormatada}</td>
                        <td>
                            <button onclick="toggleUsuario('${user.id}', ${user.ativo})" class="btn ${user.ativo ? 'btn-danger' : 'btn-success'}" style="font-size: 0.875rem; padding: 0.5rem 1rem;">
                                ${user.ativo ? '🚫 Desativar' : '✅ Ativar'}
                            </button>
                        </td>
                    </tr>
                `;
            }).join('');
        }
        
        function abrirModalNovoUsuario() {
            document.getElementById('modal-novo-usuario').style.display = 'block';
            document.getElementById('form-novo-usuario').reset();
            document.getElementById('alert-container').innerHTML = '';
        }
        
        function fecharModal() {
            document.getElementById('modal-novo-usuario').style.display = 'none';
        }
        
        document.getElementById('form-novo-usuario').addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const dados = {
        nome: document.getElementById('nome').value.trim(),
        email: document.getElementById('email').value.trim(),
        senha: document.getElementById('senha').value,
        cargo: document.getElementById('cargo').value
    };
    
    console.log('📤 Enviando dados:', dados);
    
    if (!dados.nome || !dados.email || !dados.senha || !dados.cargo) {
        mostrarAlerta('Todos os campos são obrigatórios', 'danger');
        return;
    }
    
    if (dados.senha.length < 6) {
        mostrarAlerta('Senha deve ter pelo menos 6 caracteres', 'danger');
        return;
    }
    
    try {
        console.log('🔄 Fazendo requisição para criar usuário...');
        
        // REMOVER O HEADER DE AUTHORIZATION
        const response = await fetch('/api/usuarios', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
                // REMOVIDO: 'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(dados)
        });
        
        console.log('📨 Response status:', response.status);
        
        if (response.ok) {
            const result = await response.json();
            console.log('✅ Usuário criado:', result);
            mostrarAlerta('Usuário criado com sucesso!', 'success');
            fecharModal();
            carregarUsuarios();
        } else {
            const error = await response.json();
            console.error('❌ Erro na resposta:', error);
            mostrarAlerta(error.detail || 'Erro ao criar usuário', 'danger');
        }
        
    } catch (error) {
        console.error('❌ Erro na requisição:', error);
        mostrarAlerta('Erro de conexão: ' + error.message, 'danger');
    }
});
        
        async function toggleUsuario(userId, ativoAtual) {
            const acao = ativoAtual ? 'desativar' : 'ativar';
            
            if (!confirm(`Deseja ${acao} este usuário?`)) {
                return;
            }
            
            try {
                const token = localStorage.getItem('access_token');
                const response = await fetch(`/api/usuarios/${userId}/toggle`, {
                    method: 'PATCH',
                    headers: {'Authorization': `Bearer ${token}`}
                });
                
                if (response.ok) {
                    mostrarAlerta(`Usuário ${acao === 'ativar' ? 'ativado' : 'desativado'} com sucesso!`, 'success');
                    carregarUsuarios();
                } else {
                    const error = await response.json();
                    mostrarAlerta(error.detail || `Erro ao ${acao} usuário`, 'danger');
                }
                
            } catch (error) {
                mostrarAlerta('Erro de conexão: ' + error.message, 'danger');
            }
        }
        
        function mostrarAlerta(mensagem, tipo) {
            const container = document.getElementById('alert-container');
            container.innerHTML = `<div class="alert alert-${tipo}">${mensagem}</div>`;
            setTimeout(() => {
                container.innerHTML = '';
            }, 5000);
        }
        
        // Fechar modal clicando fora
        document.addEventListener('click', function(event) {
            const modal = document.getElementById('modal-novo-usuario');
            if (event.target === modal) {
                fecharModal();
            }
        });
        
        // Verificar auth ao carregar
        checkAuth();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/api/usuarios")
async def criar_usuario(dados: dict):
    """Criar novo usuário com senha real - versão única"""
    try:
        logger.info(f"🔍 Recebida solicitação para criar usuário: {dados.get('email', 'N/A')}")
        
        if not supabase:
            logger.error("❌ Supabase não configurado")
            raise HTTPException(status_code=500, detail="Supabase não configurado")
            
        # Validações básicas
        if not all(key in dados for key in ['nome', 'email', 'senha', 'cargo']):
            logger.error("❌ Campos obrigatórios faltando")
            raise HTTPException(status_code=400, detail="Todos os campos são obrigatórios")
        
        if len(dados['senha']) < 6:
            logger.error("❌ Senha muito curta")
            raise HTTPException(status_code=400, detail="Senha deve ter pelo menos 6 caracteres")
        
        if dados['cargo'] not in ['operador', 'supervisor', 'admin']:
            logger.error(f"❌ Cargo inválido: {dados['cargo']}")
            raise HTTPException(status_code=400, detail="Cargo inválido")
        
        logger.info("✅ Validações básicas OK")
        
        # Verificar se email já existe
        logger.info("🔍 Verificando se email já existe...")
        existing = supabase.admin_client.table("usuarios").select("email").eq("email", dados['email']).execute()
        if existing.data:
            logger.error(f"❌ Email já existe: {dados['email']}")
            raise HTTPException(status_code=400, detail="Email já está em uso")
        
        logger.info("✅ Email disponível")
        
        # Hash da senha
        logger.info("🔐 Criando hash da senha...")
        senha_hash = hash_password(dados['senha'])
        logger.info("✅ Hash da senha criado")
        
        # Inserir usuário com senha hash
        logger.info("💾 Inserindo usuário no banco...")
        user_data = {
            "nome": dados['nome'].strip(),
            "email": dados['email'].strip().lower(),
            "senha_hash": senha_hash,
            "cargo": dados['cargo'],
            "ativo": True,
            "created_at": datetime.now().isoformat()
        }
        
        result = supabase.admin_client.table("usuarios").insert(user_data).execute()
        
        if not result.data:
            logger.error("❌ Falha ao inserir usuário - sem dados retornados")
            raise HTTPException(status_code=500, detail="Erro ao criar usuário no banco")
        
        created_user = result.data[0]
        logger.info(f"✅ Usuário criado com sucesso! ID: {created_user.get('id', 'N/A')}")
        
        return {
            'success': True,
            'message': 'Usuário criado com sucesso',
            'user_id': created_user.get('id'),
            'user': {
                'id': created_user.get('id'),
                'nome': created_user.get('nome'),
                'email': created_user.get('email'),
                'cargo': created_user.get('cargo'),
                'ativo': created_user.get('ativo'),
                'created_at': created_user.get('created_at')
            }
        }
        
    except HTTPException as e:
        logger.error(f"❌ HTTPException: {e.detail}")
        raise
    except Exception as e:
        logger.error(f"❌ ERRO CRÍTICO ao criar usuário: {str(e)}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@app.get("/api/usuarios")
async def listar_usuarios():
    """Listar todos os usuários"""
    try:
        logger.info("🔍 Listando usuários...")
        
        if not supabase:
            logger.error("❌ Supabase não configurado")
            raise HTTPException(status_code=500, detail="Supabase não configurado")
        
        # Buscar todos os usuários na tabela
        result = supabase.admin_client.table("usuarios").select("*").order("created_at", desc=True).execute()
        
        logger.info(f"✅ Query executada, encontrados: {len(result.data)} usuários")
        
        usuarios = []
        for user in result.data:
            usuarios.append({
                "id": user["id"],
                "nome": user["nome"],
                "email": user["email"],
                "cargo": user["cargo"],
                "ativo": user["ativo"],
                "created_at": user["created_at"],
                "updated_at": user.get("updated_at")
            })
        
        return {
            'success': True,
            'usuarios': usuarios,
            'total': len(usuarios)
        }
        
    except Exception as e:
        logger.error(f"❌ ERRO ao listar usuários: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@app.patch("/api/usuarios/{user_id}/toggle")
async def toggle_usuario(user_id: str):
    """Ativar/desativar usuário - versão corrigida"""
    try:
        logger.info(f"🔄 Tentando alterar status do usuário: {user_id}")
        
        if not supabase:
            raise HTTPException(status_code=500, detail="Supabase não configurado")
            
        # Buscar usuário atual
        result = supabase.admin_client.table("usuarios").select("*").eq("id", user_id).execute()
        logger.info(f"🔍 Usuário encontrado: {len(result.data) > 0}")
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
        usuario = result.data[0]
        novo_status = not usuario['ativo']
        
        logger.info(f"🔄 Alterando status de {usuario['ativo']} para {novo_status}")
        
        # Atualizar status
        update_result = supabase.admin_client.table("usuarios").update({
            "ativo": novo_status,
            "updated_at": datetime.now().isoformat()
        }).eq("id", user_id).execute()
        
        logger.info(f"💾 Update result: {len(update_result.data) > 0}")
        
        acao = "ativado" if novo_status else "desativado"
        logger.info(f"✅ Usuário {acao}: {usuario['email']}")
        
        return {
            'success': True,
            'message': f'Usuário {acao} com sucesso',
            'novo_status': novo_status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao alterar status do usuário: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

# FIM DAS ROTAS DE USUÁRIOS

# ===== APIS DE GESTÃO DE USUÁRIOS - ADICIONAR ANTES DO if __name__ =====

@app.get("/api/usuarios/count")
async def contar_usuarios():
    """Contar usuários no sistema"""
    try:
        if not supabase:
            return {'total_usuarios': 0, 'tem_usuarios': False}
            
        result = supabase.admin_client.table("usuarios").select("id", count="exact").execute()
        total = result.count if result.count is not None else 0
        
        logger.info(f"✅ Total de usuários no sistema: {total}")
        
        return {
            'total_usuarios': total,
            'tem_usuarios': total > 0
        }
    except Exception as e:
        logger.error(f"❌ Erro ao contar usuários: {str(e)}")
        return {'total_usuarios': 0, 'tem_usuarios': False}

@app.get("/api/usuarios")
async def listar_usuarios():
    """Listar todos os usuários - SEM autenticação"""
    try:
        logger.info("🔍 Tentando listar usuários...")
        
        if not supabase:
            logger.error("❌ Supabase não configurado")
            raise HTTPException(status_code=500, detail="Supabase não configurado")
        
        logger.info("✅ Supabase OK, consultando tabela usuarios...")
        
        # Buscar todos os usuários na tabela
        result = supabase.admin_client.table("usuarios").select("*").order("created_at", desc=True).execute()
        
        logger.info(f"✅ Query executada, encontrados: {len(result.data)} usuários")
        
        usuarios = []
        for user in result.data:
            usuarios.append({
                "id": user["id"],
                "nome": user["nome"],
                "email": user["email"],
                "cargo": user["cargo"],
                "ativo": user["ativo"],
                "created_at": user["created_at"],
                "updated_at": user.get("updated_at")
            })
        
        logger.info(f"✅ Usuários processados com sucesso: {len(usuarios)}")
        
        return {
            'success': True,
            'usuarios': usuarios,
            'total': len(usuarios)
        }
        
    except Exception as e:
        logger.error(f"❌ ERRO DETALHADO ao listar usuários: {str(e)}")
        logger.error(f"❌ Tipo do erro: {type(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
    
@app.get("/api/usuarios/init-admin")
async def criar_admin_inicial():
    """Criar usuário admin inicial se não existir - GET"""
    try:
        if not supabase:
            return {'success': False, 'message': 'Supabase não configurado'}
            
        # Verificar se já existe admin
        result = supabase.admin_client.table("usuarios").select("id").eq("cargo", "admin").execute()
        
        if result.data:
            return {
                'success': False,
                'message': 'Já existe um administrador no sistema',
                'admin_exists': True,
                'total_admins': len(result.data)
            }
        
        # Criar admin padrão
        admin_result = supabase.admin_client.table("usuarios").insert({
            "nome": 'Administrador Sistema',
            "email": 'admin@conciliacao.com',
            "cargo": 'admin',
            "ativo": True,
            "created_at": datetime.now().isoformat()
        }).execute()
        
        logger.info(f"✅ Admin inicial criado: admin@conciliacao.com")
        
        return {
            'success': True,
            'message': 'Administrador inicial criado com sucesso',
            'admin_email': 'admin@conciliacao.com'
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao criar admin inicial: {str(e)}")
        return {'success': False, 'message': f'Erro: {str(e)}'}




@app.post("/api/usuarios/init-admin")
async def criar_admin_inicial():
    """Criar usuário admin inicial se não existir"""
    try:
        if not supabase:
            return {'success': False, 'message': 'Supabase não configurado'}
            
        # Verificar se já existe admin
        result = supabase.admin_client.table("usuarios").select("id").eq("cargo", "admin").execute()
        
        if result.data:
            return {
                'success': False,
                'message': 'Já existe um administrador no sistema',
                'admin_exists': True
            }
        
        # Criar admin padrão
        admin_result = supabase.admin_client.table("usuarios").insert({
            "nome": 'Administrador Sistema',
            "email": 'admin@conciliacao.com',
            "cargo": 'admin',
            "ativo": True,
            "created_at": datetime.now().isoformat()
        }).execute()
        
        logger.info(f"✅ Admin inicial criado: admin@conciliacao.com")
        
        return {
            'success': True,
            'message': 'Administrador inicial criado com sucesso',
            'admin_email': 'admin@conciliacao.com'
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao criar admin inicial: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

# FIM DAS APIS DE USUÁRIOS
@app.get("/health")
async def health_check():
    """Health check simples para monitoramento"""
    try:
        if supabase:
            # Teste rápido do banco
            result = supabase.admin_client.table("usuarios").select("id").limit(1).execute()
            return {
                "status": "ok",
                "database": "connected",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        else:
            return {"status": "error", "database": "not_configured"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
