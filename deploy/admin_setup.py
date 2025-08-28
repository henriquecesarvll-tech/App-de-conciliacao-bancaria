# admin_setup.py - Criar admin diretamente no banco
import os
import uuid
from datetime import datetime

# Definir variáveis diretamente
os.environ['SUPABASE_URL'] = 'https://hifukfkwmhgmkirgjvqf.supabase.co'
os.environ['SUPABASE_ANON_KEY'] = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhpZnVrZmt3bWhnbWtpcmdqdnFmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTM3MTM4NTYsImV4cCI6MjA2OTI4OTg1Nn0.Z3qUNcYaghxDB9X79T5uG5vC9EifgKJJBVqQMwag19U'
os.environ['SUPABASE_SERVICE_KEY'] = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhpZnVrZmt3bWhnbWtpcmdqdnFmIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1MzcxMzg1NiwiZXhwIjoyMDY5Mjg5ODU2fQ.OHLG3n48Y3NZN2cQ2z1Qbi0eiMB79eFYl85PXD35loc'
os.environ['JWT_SECRET'] = 'minha-chave-jwt-super-secreta-123456789'

from supabase_client import SupabaseClient

def criar_admin_direto():
    """Criar admin diretamente na tabela usuarios"""
    try:
        print("🚀 Configurando admin diretamente no banco...")
        
        supabase = SupabaseClient()
        admin_client = supabase.admin_client
        
        # Verificar se já existe admin
        print("🔍 Verificando admins existentes...")
        result = admin_client.table("usuarios").select("*").eq("cargo", "admin").execute()
        
        if result.data:
            print(f"✅ Admin já existe: {result.data[0]['nome']} ({result.data[0]['email']})")
            return True
        
        print("👤 Criando admin diretamente na tabela...")
        
        # Gerar UUID fake para admin (normalmente viria do auth)
        admin_id = str(uuid.uuid4())
        admin_email = "admin@conciliacao.com"
        admin_nome = "Administrador Sistema"
        
        # Inserir diretamente na tabela usuarios (usando admin_client para bypassar RLS)
        admin_data = {
            "id": admin_id,
            "nome": admin_nome,
            "email": admin_email,
            "cargo": "admin",
            "ativo": True,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        result = admin_client.table("usuarios").insert(admin_data).execute()
        
        if result.data:
            print("✅ Admin criado com sucesso na tabela!")
            print(f"📋 ID: {admin_id}")
            print(f"📋 Nome: {admin_nome}")
            print(f"📋 Email: {admin_email}")
            print(f"📋 Cargo: admin")
            print()
            print("⚠️  IMPORTANTE:")
            print("   - Este admin foi criado apenas na tabela 'usuarios'")
            print("   - Para fazer login, você precisará implementar auth customizado")
            print("   - Ou criar o usuário no Supabase Auth Dashboard manualmente")
            print()
            print("💡 PRÓXIMOS PASSOS:")
            print("   1. Ir ao Supabase Dashboard → Authentication → Users")
            print(f"   2. Criar usuário manualmente: {admin_email}")
            print("   3. Copiar o UUID gerado pelo Auth")
            print(f"   4. Atualizar tabela usuarios com o UUID correto")
            
            return True
        else:
            print("❌ Falha ao inserir admin na tabela")
            return False
            
    except Exception as e:
        print(f"❌ Erro: {str(e)}")
        return False

def migrar_dados_basicos():
    """Migrar algumas classificações básicas para teste"""
    try:
        print("\n📁 Migrando dados de exemplo...")
        
        supabase = SupabaseClient()
        admin_client = supabase.admin_client
        
        # Classificações básicas
        classificacoes_exemplo = [
            {"nome": "RECEITAS", "descricao": "Receitas do sistema"},
            {"nome": "DESPESAS", "descricao": "Despesas do sistema"},
            {"nome": "TRANSFERÊNCIAS", "descricao": "Transferências entre contas"}
        ]
        
        for classif in classificacoes_exemplo:
            # Verificar se já existe
            existing = admin_client.table("classificacoes").select("*").eq("nome", classif["nome"]).execute()
            
            if not existing.data:
                result = admin_client.table("classificacoes").insert(classif).execute()
                if result.data:
                    print(f"✅ Classificação criada: {classif['nome']}")
                else:
                    print(f"❌ Erro ao criar: {classif['nome']}")
            else:
                print(f"⏭️  Já existe: {classif['nome']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Erro na migração: {str(e)}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("🔧 SETUP INICIAL DO SISTEMA")
    print("=" * 60)
    
    # Criar admin
    if criar_admin_direto():
        # Migrar dados básicos
        migrar_dados_basicos()
        
        print("\n" + "=" * 60)
        print("🎉 SETUP CONCLUÍDO!")
        print("=" * 60)
        print("✅ Admin criado na tabela usuarios")
        print("✅ Classificações básicas criadas")
        print("✅ Sistema pronto para uso básico")
        print()
        print("🚀 PRÓXIMO PASSO: Configurar autenticação no seu app.py")
        
    else:
        print("\n❌ Falha no setup")