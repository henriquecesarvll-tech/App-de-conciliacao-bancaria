# migrator_direto.py - Versão melhorada
import asyncio
import logging
import os

# Definir variáveis diretamente
os.environ['SUPABASE_URL'] = 'https://hifukfkwmhgmkirgjvqf.supabase.co'
os.environ['SUPABASE_ANON_KEY'] = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhpZnVrZmt3bWhnbWtpcmdqdnFmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTM3MTM4NTYsImV4cCI6MjA2OTI4OTg1Nn0.Z3qUNcYaghxDB9X79T5uG5vC9EifgKJJBVqQMwag19U'
os.environ['SUPABASE_SERVICE_KEY'] = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhpZnVrZmt3bWhnbWtpcmdqdnFmIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1MzcxMzg1NiwiZXhwIjoyMDY5Mjg5ODU2fQ.OHLG3n48Y3NZN2cQ2z1Qbi0eiMB79eFYl85PXD35loc'
os.environ['JWT_SECRET'] = 'minha-chave-jwt-super-secreta-123456789'

from supabase_client import SupabaseClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def criar_admin():
    """Criar usuário admin"""
    try:
        print("🚀 Iniciando criação do admin...")
        
        supabase = SupabaseClient()
        admin_client = supabase.admin_client
        
        print("✅ Cliente Supabase conectado!")
        
        # Verificar se já existe admin
        print("🔍 Verificando se admin já existe...")
        result = admin_client.table("usuarios").select("*").eq("cargo", "admin").execute()
        
        if result.data:
            print(f"✅ Admin já existe: {result.data[0]['nome']} ({result.data[0]['email']})")
            print("🎉 Migração concluída - Admin já configurado!")
            return
        
        print("👤 Admin não existe, criando novo...")
        
        # Criar admin
        admin_email = "admin@conciliacao.com"
        admin_senha = "admin123"
        admin_nome = "Administrador Sistema"
        
        print(f"📧 Criando usuário: {admin_email}")
        
        try:
            # Tentar criar com timeout maior
            auth_result = await asyncio.wait_for(
                supabase.sign_up(
                    email=admin_email,
                    password=admin_senha,
                    metadata={"nome": admin_nome, "cargo": "admin"}
                ),
                timeout=30.0  # 30 segundos de timeout
            )
            
            if auth_result.user:
                print(f"✅ Usuário criado no Auth: {auth_result.user.id}")
                
                # Criar perfil
                await supabase.create_user_profile(
                    user_id=auth_result.user.id,
                    nome=admin_nome,
                    email=admin_email,
                    cargo="admin"
                )
                
                print(f"✅ Admin criado com sucesso!")
                print(f"📋 Email: {admin_email}")
                print(f"📋 Senha: {admin_senha}")
                print("⚠️  ALTERE A SENHA EM PRODUÇÃO!")
            else:
                print("❌ Falha ao criar usuário no Auth")
                
        except asyncio.TimeoutError:
            print("⏰ Timeout ao criar usuário - pode ser problema de rede")
            print("💡 Tente novamente ou verifique a conexão")
        except Exception as e:
            if "already registered" in str(e).lower():
                print("✅ Usuário já existe no Auth, vamos criar só o perfil")
                # Aqui você pode tentar fazer login para obter o ID
            else:
                print(f"❌ Erro ao criar usuário: {str(e)}")
        
    except Exception as e:
        print(f"❌ Erro geral: {str(e)}")

async def testar_conexao():
    """Testar conexão com Supabase"""
    try:
        print("🧪 Testando conexão com Supabase...")
        
        supabase = SupabaseClient()
        
        # Testar query simples
        result = supabase.admin_client.table("centros_custo").select("nome").limit(1).execute()
        
        if result.data:
            print(f"✅ Conexão OK! Exemplo de dados: {result.data}")
        else:
            print("✅ Conexão OK! Tabela vazia mas conectou.")
            
        return True
        
    except Exception as e:
        print(f"❌ Erro na conexão: {str(e)}")
        return False

if __name__ == "__main__":
    # Primeiro testar conexão
    print("=" * 50)
    print("🧪 TESTE DE CONEXÃO")
    print("=" * 50)
    
    if asyncio.run(testar_conexao()):
        print("\n" + "=" * 50)
        print("👤 CRIAÇÃO DO ADMIN")
        print("=" * 50)
        asyncio.run(criar_admin())
    else:
        print("💥 Falha na conexão - não prosseguindo")