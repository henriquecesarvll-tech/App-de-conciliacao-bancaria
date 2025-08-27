from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import pandas as pd
import io
import uuid
import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from loguru import logger

# Configurar logs
os.makedirs("logs", exist_ok=True)
logger.add("logs/app.log", rotation="1 day", level="INFO")

# Criar app FastAPI
app = FastAPI(
    title="Sistema de Conciliação Bancária",
    description="Upload e processamento de extratos AAI e EDUCA",
    version="2.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Armazenamento em memória
extratos_data = []
transacoes_data = []

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
        'Outros Valores': ['Patrick', 'Thiago Menezes']
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

class ConciliacaoLoteRequest(BaseModel):
    transacao_ids: List[str]

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
                    'created_at': datetime.now().isoformat()
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

@app.on_event("startup")
async def startup():
    """Inicializar aplicação"""
    logger.info("🚀 Iniciando Sistema de Conciliação Bancária...")
    logger.info("✅ Sistema iniciado com sucesso!")

@app.get("/")
async def root():
    """Página inicial"""
    html_content = """
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
                    <button onclick="limparDados()" class="btn btn-danger">
                        <span>🗑️</span>
                        Limpar Dados
                    </button>
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
        
        async function limparDados() {
            if (confirm('⚠️ ATENÇÃO: Isso vai apagar TODOS os dados do sistema! Tem certeza?')) {
                try {
                    const response = await fetch('/limpar-dados', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'}
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        alert(`✅ Dados limpos! ${result.transacoes_removidas} transações removidas.`);
                        atualizarStats();
                    } else {
                        alert('❌ Erro ao limpar dados');
                    }
                } catch (error) {
                    alert('❌ Erro: ' + error.message);
                }
            }
        }
        
        window.onload = atualizarStats;
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/upload-extrato")
async def upload_extrato(file: UploadFile = File(...), banco: str = Form(...)):
    """Upload e processamento de extrato bancário"""
    
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
        
        # Salvar transações
        transacoes_data.extend(transacoes)
        logger.info(f"Total de transações no sistema: {len(transacoes_data)}")
        
        # Registrar extrato
        extrato = {
            'id': str(uuid.uuid4()),
            'banco': banco,
            'arquivo': file.filename,
            'total_transacoes': len(transacoes),
            'processado_em': datetime.now().isoformat(),
            'status': 'PROCESSADO'
        }
        extratos_data.append(extrato)
        
        logger.info(f"Extrato {banco} processado com sucesso: {len(transacoes)} transações")
        
        # Calcular estatísticas CORRETAS
        valor_total = sum(t['valor'] for t in transacoes)
        creditos = [t for t in transacoes if t['valor'] > 0]
        debitos = [t for t in transacoes if t['valor'] < 0]
        
        # Retornar página de sucesso
        html_sucesso = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Upload Concluído</title>
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
            <style>
                :root {{
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
                }}
                
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                
                body {{
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background: linear-gradient(135deg, var(--primary-50) 0%, var(--primary-100) 100%);
                    min-height: 100vh;
                    color: var(--gray-900);
                    line-height: 1.6;
                    padding: var(--space-6);
                }}
                
                .container {{
                    max-width: 900px;
                    margin: 0 auto;
                }}
                
                /* Success Card */
                .success-card {{
                    background: white;
                    border-radius: var(--radius-2xl);
                    padding: var(--space-10);
                    box-shadow: var(--shadow-xl);
                    border: 1px solid var(--gray-100);
                    text-align: center;
                }}
                
                .success-icon {{
                    font-size: 4rem;
                    display: block;
                    margin-bottom: var(--space-6);
                }}
                
                h1 {{
                    font-size: 2.5rem;
                    font-weight: 700;
                    color: var(--gray-900);
                    margin-bottom: var(--space-8);
                    letter-spacing: -0.025em;
                }}
                
                /* Success Info Box */
                .success-info {{
                    background: var(--success-50);
                    border: 1px solid var(--success-100);
                    border-radius: var(--radius-xl);
                    padding: var(--space-6);
                    margin-bottom: var(--space-8);
                }}
                
                .success-info h3 {{
                    font-size: 1.25rem;
                    font-weight: 600;
                    color: var(--success-600);
                    margin-bottom: var(--space-4);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: var(--space-2);
                }}
                
                .success-info p {{
                    color: var(--gray-700);
                    margin: var(--space-2) 0;
                }}
                
                .success-info p strong {{
                    font-weight: 600;
                    color: var(--gray-800);
                }}
                
                /* Stats Section */
                .stats-section {{
                    margin: var(--space-10) 0;
                }}
                
                .stats-section h3 {{
                    font-size: 1.5rem;
                    font-weight: 600;
                    color: var(--gray-900);
                    margin-bottom: var(--space-6);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: var(--space-3);
                }}
                
                .stats-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: var(--space-6);
                    margin-bottom: var(--space-8);
                }}
                
                .stat-card {{
                    background: white;
                    border: 1px solid var(--gray-200);
                    border-radius: var(--radius-xl);
                    padding: var(--space-6);
                    text-align: center;
                    box-shadow: var(--shadow-md);
                    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
                }}
                
                .stat-card:hover {{
                    transform: translateY(-2px);
                    box-shadow: var(--shadow-lg);
                }}
                
                .stat-number {{
                    font-size: 2.5rem;
                    font-weight: 700;
                    margin-bottom: var(--space-2);
                    display: block;
                }}
                
                .stat-label {{
                    font-size: 0.875rem;
                    color: var(--gray-600);
                    font-weight: 500;
                }}
                
                /* Details Box */
                .details-box {{
                    background: var(--gray-50);
                    border: 1px solid var(--gray-200);
                    border-radius: var(--radius-xl);
                    padding: var(--space-6);
                    margin-bottom: var(--space-8);
                }}
                
                .details-box h4 {{
                    font-size: 1.125rem;
                    font-weight: 600;
                    color: var(--gray-800);
                    margin-bottom: var(--space-4);
                    display: flex;
                    align-items: center;
                    gap: var(--space-2);
                }}
                
                .details-box p {{
                    color: var(--gray-700);
                    margin: var(--space-2) 0;
                    font-size: 0.875rem;
                }}
                
                .details-box p strong {{
                    font-weight: 600;
                    color: var(--gray-900);
                }}
                
                /* Actions Section */
                .actions-section {{
                    margin: var(--space-10) 0;
                }}
                
                .actions-section h3 {{
                    font-size: 1.5rem;
                    font-weight: 600;
                    color: var(--gray-900);
                    margin-bottom: var(--space-6);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: var(--space-3);
                }}
                
                .actions {{
                    display: flex;
                    flex-wrap: wrap;
                    gap: var(--space-4);
                    justify-content: center;
                    margin-bottom: var(--space-8);
                }}
                
                /* Buttons */
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
                
                .btn-success {{
                    background: var(--success-600);
                    color: white;
                }}
                
                .btn-success:hover {{
                    background: var(--success-700);
                    transform: translateY(-1px);
                    box-shadow: var(--shadow-md);
                }}
                
                .btn-warning {{
                    background: var(--warning-500);
                    color: white;
                }}
                
                .btn-warning:hover {{
                    background: var(--warning-600);
                    transform: translateY(-1px);
                    box-shadow: var(--shadow-md);
                }}
                
                /* Tip Box */
                .tip-box {{
                    background: var(--warning-50);
                    border: 1px solid var(--warning-100);
                    border-radius: var(--radius-xl);
                    padding: var(--space-6);
                    margin-top: var(--space-8);
                }}
                
                .tip-box p {{
                    color: var(--gray-700);
                    font-size: 0.875rem;
                    margin: 0;
                }}
                
                .tip-box p strong {{
                    color: var(--warning-600);
                    font-weight: 600;
                }}
                
                /* Responsive */
                @media (max-width: 768px) {{
                    body {{
                        padding: var(--space-4);
                    }}
                    
                    .success-card {{
                        padding: var(--space-6);
                    }}
                    
                    h1 {{
                        font-size: 2rem;
                    }}
                    
                    .success-icon {{
                        font-size: 3rem;
                    }}
                    
                    .stats-grid {{
                        grid-template-columns: repeat(2, 1fr);
                        gap: var(--space-4);
                    }}
                    
                    .actions {{
                        flex-direction: column;
                        align-items: stretch;
                    }}
                    
                    .btn {{
                        justify-content: center;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success-card">
                    <span class="success-icon">✅</span>
                    <h1>Upload Concluído com Sucesso!</h1>
                    
                    <div class="success-info">
                        <h3>
                            <span>🎉</span>
                            Extrato {banco} Processado
                        </h3>
                        <p><strong>Arquivo:</strong> {file.filename}</p>
                        <p><strong>Status:</strong> Processado com sucesso</p>
                        <p><strong>Data/Hora:</strong> {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}</p>
                    </div>
                    
                    <div class="stats-section">
                        <h3>
                            <span>📊</span>
                            Estatísticas do Processamento
                        </h3>
                        <div class="stats-grid">
                            <div class="stat-card">
                                <span class="stat-number" style="color: var(--primary-600);">{len(transacoes)}</span>
                                <span class="stat-label">Total de Transações</span>
                            </div>
                            <div class="stat-card">
                                <span class="stat-number" style="color: var(--success-600);">{len(creditos)}</span>
                                <span class="stat-label">Entradas (+)</span>
                            </div>
                            <div class="stat-card">
                                <span class="stat-number" style="color: var(--danger-500);">{len(debitos)}</span>
                                <span class="stat-label">Saídas (-)</span>
                            </div>
                            <div class="stat-card">
                                <span class="stat-number" style="color: {'var(--success-600)' if valor_total >= 0 else 'var(--danger-500)'};">
                                    R$ {valor_total:,.2f}
                                </span>
                                <span class="stat-label">Soma Total (Valor R$)</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="details-box">
                        <h4>
                            <span>📋</span>
                            Detalhes do Cálculo
                        </h4>
                        <p><strong>Entradas:</strong> {len(creditos)} transações = R$ {sum(t['valor'] for t in creditos):,.2f}</p>
                        <p><strong>Saídas:</strong> {len(debitos)} transações = R$ {sum(t['valor'] for t in debitos):,.2f}</p>
                        <p><strong>Total:</strong> R$ {valor_total:,.2f}</p>
                    </div>
                    
                    <div class="actions-section">
                        <h3>
                            <span>🎯</span>
                            Próximos Passos
                        </h3>
                        <div class="actions">
                            <a href="/pendentes" class="btn btn-warning">
                                <span>📋</span>
                                Ver Transações Pendentes ({len(transacoes)})
                            </a>
                            <a href="/" class="btn btn-primary">
                                <span>🏠</span>
                                Voltar ao Início
                            </a>
                            <a href="/relatorios" class="btn btn-success">
                                <span>📊</span>
                                Ver Relatórios
                            </a>
                        </div>
                    </div>
                    
                    <div class="tip-box">
                        <p><strong>💡 Dica:</strong> Agora você pode ir em "Conciliações Pendentes" para classificar as {len(transacoes)} transações importadas do banco {banco}.</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_sucesso)
        
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
                
                <div style="margin-top: 20px; padding: 15px; background: #d1ecf1; border-radius: 8px;">
                    <h4>💡 Dicas para resolver:</h4>
                    <ul>
                        <li>Verifique se o arquivo é um Excel válido (.xlsx ou .xls)</li>
                        <li>Certifique-se que tem as colunas: Data, Histórico, Documento, Valor (R$), Saldo (R$)</li>
                        <li>Verifique se não há caracteres especiais no nome do arquivo</li>
                    </ul>
                </div>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_erro, status_code=400)

@app.get("/pendentes")
async def listar_pendentes():
    """Listar transações pendentes de conciliação"""
    pendentes = [t for t in transacoes_data if t['status'] == 'PENDENTE']
    
    # Criar HTML com design moderno
    html_content = """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Conciliações Pendentes</title>
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
            }
            
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: var(--gray-50);
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
            }
            
            .header-content h1 {
                font-size: 2rem;
                font-weight: 700;
                color: var(--gray-900);
                margin-bottom: var(--space-2);
                display: flex;
                align-items: center;
                gap: var(--space-3);
            }
            
            .header-content p {
                color: var(--gray-600);
                font-size: 1rem;
            }
            
            /* Filters */
            .filters {
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
            }
            
            .filter-group {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            
            .filter-group label {
                font-size: 0.875rem;
                font-weight: 600;
                color: var(--gray-700);
            }
            
            /* Table Container */
            .table-container {
                background: white;
                border-radius: var(--radius-2xl);
                overflow: hidden;
                box-shadow: var(--shadow-lg);
                border: 1px solid var(--gray-200);
            }
            
            table {
                width: 100%;
                border-collapse: collapse;
            }
            
            th {
                background: var(--primary-600);
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
            
            /* Buttons */
            .btn {
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
            
            /* Status */
            .status-pendente {
                background: var(--warning-100);
                color: var(--warning-600);
                padding: var(--space-1) var(--space-3);
                border-radius: var(--radius-md);
                font-size: 0.75rem;
                font-weight: 600;
                letter-spacing: 0.025em;
            }
            
            /* Values */
            .valor-positivo {
                color: var(--success-600);
                font-weight: 700;
            }
            
            .valor-negativo {
                color: var(--danger-500);
                font-weight: 700;
            }
            
            /* Form Elements */
            select, input {
                padding: var(--space-3);
                border: 1px solid var(--gray-300);
                border-radius: var(--radius-md);
                font-size: 0.875rem;
                font-family: inherit;
                background: white;
                transition: all 0.2s ease;
            }
            
            select:focus, input:focus {
                outline: none;
                border-color: var(--primary-500);
                box-shadow: 0 0 0 3px var(--primary-100);
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
                max-width: 900px;
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
            }
            
            .btn-close:hover {
                background: var(--danger-600);
                transform: scale(1.05);
            }
            
            /* Form */
            .form-row {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-6);
                margin: var(--space-6) 0;
            }
            
            .form-group {
                margin: var(--space-4) 0;
            }
            
            .form-group.full-width {
                grid-column: 1 / -1;
            }
            
            .form-group label {
                display: block;
                margin-bottom: var(--space-2);
                font-weight: 600;
                color: var(--gray-700);
                font-size: 0.875rem;
            }
            
            .form-group select,
            .form-group input,
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
            
            .form-group select:focus,
            .form-group input:focus,
            .form-group textarea:focus {
                outline: none;
                border-color: var(--primary-500);
                box-shadow: 0 0 0 3px var(--primary-100);
            }
            
            .form-group textarea {
                height: 100px;
                resize: vertical;
            }
            
            .form-group select:disabled,
            .form-group input:disabled,
            .form-group input:read-only {
                background-color: var(--primary-50);
                border-color: var(--primary-200);
            }
            
            .auto-filled {
                background-color: var(--primary-50) !important;
                border-color: var(--primary-200) !important;
            }
            
            .required {
                color: var(--danger-500);
            }
            
            /* Form Buttons */
            .form-buttons {
                display: flex;
                justify-content: flex-end;
                gap: var(--space-4);
                margin-top: var(--space-8);
                padding-top: var(--space-6);
                border-top: 1px solid var(--gray-200);
            }
            
            .btn-cancel {
                background: var(--gray-600);
                color: white;
                padding: var(--space-3) var(--space-6);
            }
            
            .btn-cancel:hover {
                background: var(--gray-700);
            }
            
            .btn-save {
                background: var(--success-600);
                color: white;
                padding: var(--space-3) var(--space-6);
            }
            
            .btn-save:hover {
                background: var(--success-700);
            }
            
            /* Responsive */
            @media (max-width: 768px) {
                .container {
                    padding: var(--space-4);
                }
                
                .header {
                    flex-direction: column;
                    align-items: stretch;
                    text-align: center;
                }
                
                .filters {
                    flex-direction: column;
                    align-items: stretch;
                }
                
                .filter-group {
                    width: 100%;
                }
                
                .form-row {
                    grid-template-columns: 1fr;
                    gap: var(--space-4);
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
                <div class="header-content">
                    <h1>
                        <span>📋</span>
                        Conciliações Pendentes
                    </h1>
                    <p>Total de """ + str(len(pendentes)) + """ transações aguardando conciliação</p>
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

    for transacao in pendentes:
        valor_class = "valor-positivo" if transacao['valor'] >= 0 else "valor-negativo"
        html_content += f"""
                        <tr data-banco="{transacao['banco']}" data-tipo="{transacao['tipo_transacao']}" data-historico="{transacao['historico'].lower()}">
                            <td><input type="checkbox" class="select-transacao" value="{transacao['id']}"></td>
                            <td><strong>{transacao['banco']}</strong></td>
                            <td>{transacao['data']}</td>
                            <td title="{transacao['historico']}">{transacao['historico'][:60]}{'...' if len(transacao['historico']) > 60 else ''}</td>
                            <td>{transacao['tipo_transacao']}</td>
                            <td class="{valor_class}">R$ {transacao['valor']:,.2f}</td>
                            <td><span class="status-pendente">PENDENTE</span></td>
                            <td>
                                <button class="btn btn-primary" onclick="abrirModalConciliacao('{transacao['id']}')">
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
        
        <!-- Modal de Conciliação -->
        <div id="modal-conciliacao" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h3>
                        <span>🔖</span>
                        Conciliar Transação
                    </h3>
                    <button class="btn-close" onclick="fecharModal()">✕</button>
                </div>
                
                <form id="form-conciliacao">
                    <input type="hidden" id="transacao-id">
                    
                    <!-- Seção 1: Hierarquia de Classificação -->
                    <div style="margin-bottom: var(--space-8);">
                        <h4 style="font-size: 1.125rem; font-weight: 600; color: var(--gray-800); margin-bottom: var(--space-4); padding-bottom: var(--space-2); border-bottom: 1px solid var(--gray-200);">📊 Classificação Hierárquica</h4>
                        
                        <div class="form-row">
                            <div class="form-group">
                                <label>1. Classificação <span class="required">*</span></label>
                                <select id="classificacao" onchange="atualizarPlanoContas()" required>
                                    <option value="">Selecionar classificação...</option>""" + \
                                    ''.join([f'<option value="{classif}">{classif}</option>' for classif in classificacoes.keys()]) + """
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
                    <div style="margin-bottom: var(--space-8);">
                        <h4 style="font-size: 1.125rem; font-weight: 600; color: var(--gray-800); margin-bottom: var(--space-4); padding-bottom: var(--space-2); border-bottom: 1px solid var(--gray-200);">💳 Informações de Pagamento</h4>
                        
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
                                <label>Banco <small style="color: var(--gray-500);">(Automático)</small></label>
                                <select id="banco-origem" class="auto-filled" disabled>
                                    <option value="AAI">AAI</option>
                                    <option value="EDUCAÇÃO">EDUCAÇÃO</option>
                                </select>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Seção 3: Detalhes da Transação -->
                    <div style="margin-bottom: var(--space-8);">
                        <h4 style="font-size: 1.125rem; font-weight: 600; color: var(--gray-800); margin-bottom: var(--space-4); padding-bottom: var(--space-2); border-bottom: 1px solid var(--gray-200);">📝 Detalhes da Transação</h4>
                        
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
                        <button type="button" onclick="fecharModal()" class="btn btn-cancel">
                            <span>✕</span>
                            Cancelar
                        </button>
                        <button type="button" onclick="salvarConciliacao()" class="btn btn-save">
                            <span>✅</span>
                            Conciliar Transação
                        </button>
                    </div>
                </form>
            </div>
        </div>
        
        <script>
        // Dados das classificações para JavaScript
        const classificacoesData = """ + json.dumps(classificacoes) + """;
        
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
        
        function abrirModalConciliacao(transacaoId) {
            console.log('Abrindo modal para:', transacaoId);
            
            // Buscar dados da transação
            fetch('/api/transacoes')
                .then(response => response.json())
                .then(data => {
                    const transacao = data.transacoes.find(t => t.id === transacaoId);
                    if (transacao) {
                        preencherModal(transacao);
                    }
                })
                .catch(error => console.error('Erro ao buscar transação:', error));
            
            document.getElementById('transacao-id').value = transacaoId;
            document.getElementById('modal-conciliacao').style.display = 'block';
            document.body.style.overflow = 'hidden'; // Prevent scroll
        }
        
        function preencherModal(transacao) {
            // Preencher campos autopreenchidos
            
            // Forma de pagamento
            const formaPagamentoSelect = document.getElementById('forma-pagamento');
            formaPagamentoSelect.value = transacao.forma_pagamento || 'Outros';
            
            // Banco origem
            const bancoSelect = document.getElementById('banco-origem');
            bancoSelect.value = transacao.banco_origem || transacao.banco;
            
            // Formatar e preencher data de pagamento (sempre da transação)
            let dataPagamento = transacao.data_pagamento || transacao.data;
            if (dataPagamento) {
                // Se a data estiver em formato brasileiro (dd/mm/yyyy), converter para yyyy-mm-dd
                if (dataPagamento.includes('/')) {
                    const parts = dataPagamento.split('/');
                    if (parts.length === 3) {
                        // Assumir dd/mm/yyyy
                        dataPagamento = `${parts[2]}-${parts[1].padStart(2, '0')}-${parts[0].padStart(2, '0')}`;
                    }
                } else if (dataPagamento.includes('-') && dataPagamento.length === 10) {
                    // Já está no formato correto yyyy-mm-dd
                    dataPagamento = dataPagamento;
                }
                document.getElementById('data-pagamento').value = dataPagamento;
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
            
            if (classificacao && classificacoesData[classificacao]) {
                planoContasSelect.disabled = false;
                
                // Adicionar opções do plano de contas
                Object.keys(classificacoesData[classificacao]).forEach(plano => {
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
            
            if (classificacao && planoContas && classificacoesData[classificacao] && classificacoesData[classificacao][planoContas]) {
                itemSelect.disabled = false;
                
                // Adicionar opções dos itens
                classificacoesData[classificacao][planoContas].forEach(item => {
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
            document.body.style.overflow = 'auto'; // Restore scroll
            
            // Resetar apenas campos editáveis (não os automáticos)
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
        }
        
        async function salvarConciliacao() {
            console.log('Iniciando salvamento da conciliacao...');
            
            // Coletar todos os dados
            const dados = {
                transacao_id: document.getElementById('transacao-id').value,
                classificacao: document.getElementById('classificacao').value,
                plano_contas: document.getElementById('plano-contas').value,
                item: document.getElementById('item').value,
                forma_pagamento: document.getElementById('forma-pagamento').value,
                banco_origem: document.getElementById('banco-origem').value,
                centro_custo: document.getElementById('centro-custo').value,
                nome_recebedor: document.getElementById('nome-recebedor').value,
                data_pagamento: document.getElementById('data-pagamento').value,
                data_referencia: document.getElementById('data-referencia').value,
                observacoes: document.getElementById('observacoes').value
            };
            
            console.log('Dados coletados:', dados);
            
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
            
            // Data de pagamento sempre será preenchida automaticamente, então não precisa validar
            
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
        
        console.log('Sistema carregado com sucesso!');
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

@app.get("/conciliados")
def listar_conciliados():
    """Listar transações já conciliadas"""
    conciliados = [t for t in transacoes_data if t['status'] == 'CONCILIADO']
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
                /* Design System - Colors */
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
                --gray-600: #4b5563;
                --gray-700: #374151;
                --gray-800: #1f2937;
                --gray-900: #111827;
                
                --space-2: 0.5rem;
                --space-3: 0.75rem;
                --space-4: 1rem;
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
            }}
            
            .container {{
                max-width: 1600px;
                margin: 0 auto;
                padding: var(--space-6);
            }}
            
            /* Header */
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
            
            /* Stats Summary */
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
            
            /* Table Container */
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
            
            /* Values */
            .valor-positivo {{
                color: var(--success-600);
                font-weight: 700;
            }}
            
            .valor-negativo {{
                color: var(--danger-500);
                font-weight: 700;
            }}
            
            /* Status */
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
            
            /* Button */
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
            }}
        </style>
    </head>
    <body>
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
                        <span class="stat-number">R$ {sum(t['valor'] for t in conciliados):,.2f}</span>
                        <span class="stat-label">Valor Total Processado</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-number">{len([t for t in conciliados if t['valor'] > 0])}</span>
                        <span class="stat-label">Entradas (+)</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-number">{len([t for t in conciliados if t['valor'] < 0])}</span>
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

    for transacao in conciliados:
        valor_class = "valor-positivo" if transacao['valor'] >= 0 else "valor-negativo"
        data_conciliacao = transacao.get('conciliado_em', '').split('T')[0] if transacao.get('conciliado_em') else ''
        data_referencia = transacao.get('data_referencia', '-') if transacao.get('data_referencia') else '-'
        
        html_content += f"""
                        <tr>
                            <td><strong>{transacao['banco']}</strong></td>
                            <td style="white-space: nowrap;">{transacao['data']}</td>
                            <td title="{transacao['historico']}" style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{transacao['historico'][:40]}{'...' if len(transacao['historico']) > 40 else ''}</td>
                            <td class="{valor_class}" style="white-space: nowrap;">R$ {transacao['valor']:,.2f}</td>
                            <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis;">{transacao.get('classificacao', '-')}</td>
                            <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis;">{transacao.get('plano_contas', '-')}</td>
                            <td style="max-width: 120px; overflow: hidden; text-overflow: ellipsis;">{transacao.get('item', '-')}</td>
                            <td>{transacao.get('forma_pagamento', '-')}</td>
                            <td>{transacao.get('centro_custo', '-')}</td>
                            <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis;" title="{transacao.get('nome_recebedor', '-')}">{transacao.get('nome_recebedor', '-')[:20]}{'...' if len(transacao.get('nome_recebedor', '')) > 20 else ''}</td>
                            <td style="white-space: nowrap;">{data_referencia}</td>
                            <td><span class="status-conciliado">CONCILIADO</span></td>
                            <td style="white-space: nowrap;">{data_conciliacao}</td>
                        </tr>"""

    html_content += """
                    </tbody>
                </table>
            </section>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

@app.get("/debug")
async def debug_info():
    """Informações de debug"""
    return {
        'total_transacoes': len(transacoes_data),
        'total_extratos': len(extratos_data),
        'transacoes_sample': transacoes_data[:3] if transacoes_data else [],
        'extratos_sample': extratos_data[:3] if extratos_data else []
    }

@app.post("/limpar-dados")
async def limpar_dados():
    """Limpar todos os dados do sistema"""
    global transacoes_data, extratos_data
    
    count_transacoes = len(transacoes_data)
    count_extratos = len(extratos_data)
    
    transacoes_data.clear()
    extratos_data.clear()
    
    logger.info(f"Dados limpos: {count_transacoes} transações e {count_extratos} extratos removidos")
    
    return {
        'success': True,
        'message': 'Todos os dados foram limpos com sucesso!',
        'transacoes_removidas': count_transacoes,
        'extratos_removidos': count_extratos
    }

@app.get("/api/stats")
async def get_stats():
    """Obter estatísticas do sistema"""
    total_transacoes = len(transacoes_data)
    pendentes = len([t for t in transacoes_data if t['status'] == 'PENDENTE'])
    conciliados = len([t for t in transacoes_data if t['status'] == 'CONCILIADO'])
    valor_total = sum(t['valor'] for t in transacoes_data)
    
    return {
        'total_transacoes': total_transacoes,
        'pendentes': pendentes,
        'conciliados': conciliados,
        'valor_total': valor_total
    }

@app.post("/api/conciliar")
async def conciliar_transacao(dados: ConciliacaoRequest):
    """Conciliar uma transação individual"""
    logger.info(f"Recebida solicitação de conciliação: {dados}")
    
    # Encontrar transação
    transacao = next((t for t in transacoes_data if t['id'] == dados.transacao_id), None)
    if not transacao:
        logger.error(f"Transação não encontrada: {dados.transacao_id}")
        raise HTTPException(status_code=404, detail="Transação não encontrada")
    
    # Verificar se já está conciliada
    if transacao['status'] == 'CONCILIADO':
        logger.warning(f"Transação já conciliada: {dados.transacao_id}")
        raise HTTPException(status_code=400, detail="Transação já está conciliada")
    
    # Atualizar dados da transação
    transacao.update({
        'status': 'CONCILIADO',
        'classificacao': dados.classificacao,
        'plano_contas': dados.plano_contas,
        'item': dados.item,
        'forma_pagamento': dados.forma_pagamento,
        'banco_origem': dados.banco_origem,
        'centro_custo': dados.centro_custo,
        'nome_recebedor': dados.nome_recebedor,
        'data_pagamento': dados.data_pagamento,
        'data_referencia': dados.data_referencia,
        'observacoes': dados.observacoes,
        'conciliado_em': datetime.now().isoformat(),
        'conciliado_por': 'Sistema'
    })
    
    logger.info(f"Transação {dados.transacao_id} conciliada com sucesso")
    
    return {'success': True, 'message': 'Transação conciliada com sucesso'}

@app.post("/api/conciliar-lote")
async def conciliar_lote(dados: ConciliacaoLoteRequest):
    """Conciliar múltiplas transações em lote"""
    logger.info(f"Recebida solicitação de conciliação em lote: {len(dados.transacao_ids)} transações")
    
    conciliadas = 0
    erros = []
    
    for transacao_id in dados.transacao_ids:
        transacao = next((t for t in transacoes_data if t['id'] == transacao_id), None)
        if transacao and transacao['status'] == 'PENDENTE':
            transacao.update({
                'status': 'CONCILIADO',
                'conciliado_em': datetime.now().isoformat(),
                'conciliado_por': 'Sistema (Lote)'
            })
            conciliadas += 1
        elif not transacao:
            erros.append(f"Transação {transacao_id} não encontrada")
        elif transacao['status'] == 'CONCILIADO':
            erros.append(f"Transação {transacao_id} já estava conciliada")
    
    logger.info(f"Conciliação em lote concluída: {conciliadas} conciliadas, {len(erros)} erros")
    
    if erros:
        logger.warning(f"Erros na conciliação em lote: {erros}")
    
    return {
        'success': True, 
        'message': f'{conciliadas} transações conciliadas com sucesso',
        'total_conciliadas': conciliadas,
        'erros': erros
    }

@app.get("/api/transacoes")
async def listar_transacoes(status: Optional[str] = None, banco: Optional[str] = None):
    """API para listar transações com filtros"""
    filtradas = transacoes_data
    
    if status:
        filtradas = [t for t in filtradas if t['status'] == status]
    
    if banco:
        filtradas = [t for t in filtradas if t['banco'] == banco]
    
    return {
        'success': True,
        'transacoes': filtradas,
        'total': len(filtradas)
    }

@app.get("/relatorios")
async def relatorios():
    """Página de relatórios aprimorada"""
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
                /* Enhanced Color System */
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
                
                --purple-50: #faf5ff;
                --purple-500: #a855f7;
                --purple-600: #9333ea;
                
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
                background: linear-gradient(135deg, var(--primary-50) 0%, var(--purple-50) 50%, var(--emerald-50) 100%);
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
                background: linear-gradient(135deg, var(--primary-600), var(--purple-600), var(--emerald-600));
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
            
            .stat-card.purple {
                background: linear-gradient(135deg, var(--purple-500), var(--purple-600));
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
                background: linear-gradient(90deg, var(--emerald-500), var(--primary-500), var(--purple-500));
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
                
                <div class="stat-card purple">
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
        
        async function carregarPorClassificacao() {
            const container = document.getElementById('por-classificacao');
            container.innerHTML = '<div class="loading"><div class="spinner"></div>Carregando...</div>';
            
            try {
                const response = await fetch('/api/transacoes');
                const data = await response.json();
                
                const porClassificacao = {};
                data.transacoes.forEach(t => {
                    const classif = t.classificacao || 'Não Classificado';
                    if (!porClassificacao[classif]) porClassificacao[classif] = {total: 0, valor: 0};
                    porClassificacao[classif].total++;
                    porClassificacao[classif].valor += t.valor;
                });
                
                setTimeout(() => {
                    let html = '';
                    
                    if (Object.keys(porClassificacao).length === 0) {
                        html = '<div style="text-align: center; color: var(--gray-600); padding: var(--space-8);">📊 Nenhuma classificação disponível</div>';
                    } else {
                        const sorted = Object.entries(porClassificacao)
                            .sort(([,a], [,b]) => b.total - a.total)
                            .slice(0, 10);
                        
                        const maxTotal = sorted.length > 0 ? sorted[0][1].total : 1;
                        
                        html += '<div class="chart-container">';
                        
                        sorted.forEach(([classif, info]) => {
                            const barWidth = (info.total / maxTotal) * 100;
                            const truncatedClassif = classif.length > 20 ? classif.substring(0, 20) + '...' : classif;
                            
                            html += `
                                <div class="chart-item">
                                    <div class="chart-label" title="${classif}">📋 ${truncatedClassif}</div>
                                    <div class="chart-bar-container">
                                        <div class="chart-bar-fill" style="width: ${barWidth}%"></div>
                                    </div>
                                    <div class="chart-value">${info.total}</div>
                                </div>
                            `;
                        });
                        
                        html += '</div>';
                        
                        sorted.slice(0, 5).forEach(([classif, info]) => {
                            html += `
                                <div class="data-item">
                                    <div class="data-item-label">
                                        <span>💼</span>
                                        ${classif.length > 25 ? classif.substring(0, 25) + '...' : classif}
                                    </div>
                                    <div class="data-item-value primary">
                                        ${info.total} transação${info.total !== 1 ? 'ões' : ''}
                                    </div>
                                </div>
                            `;
                        });
                    }
                    
                    container.innerHTML = html;
                    container.classList.add('loaded');
                }, 1000);
                
            } catch (error) {
                setTimeout(() => {
                    container.innerHTML = '<div style="color: var(--rose-500); text-align: center;">❌ Erro ao carregar classificações</div>';
                }, 1000);
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)