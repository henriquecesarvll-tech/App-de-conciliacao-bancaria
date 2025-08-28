# sync_admin.py - Versão simplificada e funcional
import os
from datetime import datetime

# Definir variáveis diretamente
os.environ['SUPABASE_URL'] = 'https://hifukfkwmhgmkirgjvqf.supabase.co'
os.environ['SUPABASE_SERVICE_KEY'] = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhpZnVrZmt3bWhnbWtpcmdqdnFmIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1MzcxMzg1NiwiZXhwIjoyMDY5Mjg5ODU2fQ.OHLG3n48Y3NZN2cQ2z1Qbi0eiMB79eFYl85PXD35loc'

from supabase import create_client

def sincronizar_admin(admin_uuid):
    """Criar perfil para usuário admin usando UUID fornecido"""
    try:
        print(f"🔄 Sincronizando admin com UUID: {admin_uuid}")
        
        client = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])
        
        # Verificar se já existe perfil
        print("🔍 Verificando se perfil já existe...")
        existing = client.table("usuarios").select("*").eq("id", admin_uuid).execute()
        
        if existing.data:
            print(f"✅ Perfil já existe: {existing.data[0]['nome']} ({existing.data[0]['email']})")
            print(f"📋 Cargo: {existing.data[0]['cargo']}")
            return True
        
        # Criar perfil
        print("👤 Criando perfil na tabela usuarios...")
        
        admin_data = {
            "id": admin_uuid,  # UUID copiado do Dashboard
            "nome": "Administrador Sistema",
            "email": "admin@conciliacao.com",
            "cargo": "admin",
            "ativo": True,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        result = client.table("usuarios").insert(admin_data).execute()
        
        if result.data:
            print("✅ Perfil admin criado com sucesso!")
            print(f"📋 ID: {admin_uuid}")
            print(f"📋 Nome: Administrador Sistema")
            print(f"📋 Email: admin@conciliacao.com")
            print(f"📋 Cargo: admin")
            return True
        else:
            print("❌ Falha ao criar perfil")
            print(f"Erro: {result}")
            return False
            
    except Exception as e:
        print(f"❌ Erro: {str(e)}")
        return False

def criar_classificacoes_exemplo():
    """Criar algumas classificações para teste"""
    try:
        print("\n📁 Criando classificações de exemplo...")
        
        client = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])
        
        classificacoes = [
            {"nome": "RECEITAS", "descricao": "Receitas operacionais"},
            {"nome": "DESPESAS", "descricao": "Despesas operacionais"},
            {"nome": "TRANSFERÊNCIAS", "descricao": "Transferências entre contas"},
            {"nome": "INVESTIMENTOS", "descricao": "Aplicações e investimentos"}
        ]
        
        for classif in classificacoes:
            # Verificar se já existe
            existing = client.table("classificacoes").select("*").eq("nome", classif["nome"]).execute()
            
            if not existing.data:
                result = client.table("classificacoes").insert(classif).execute()
                if result.data:
                    print(f"✅ Criado: {classif['nome']}")
                else:
                    print(f"❌ Erro ao criar: {classif['nome']}")
            else:
                print(f"⏭️  Já existe: {classif['nome']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Erro na criação de classificações: {str(e)}")
        return False

def testar_sistema():
    """Testar se tudo está funcionando"""
    try:
        print("\n🧪 Testando sistema...")
        
        client = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])
        
        # Contar registros
        usuarios = client.table("usuarios").select("*", count="exact").execute()
        classificacoes = client.table("classificacoes").select("*", count="exact").execute()
        centros_custo = client.table("centros_custo").select("*", count="exact").execute()
        
        print(f"📊 ESTATÍSTICAS DO SISTEMA:")
        print(f"   👥 Usuários: {usuarios.count}")
        print(f"   📁 Classificações: {classificacoes.count}")
        print(f"   🏢 Centros de Custo: {centros_custo.count}")
        
        if usuarios.data:
            print(f"\n👥 USUÁRIOS:")
            for user in usuarios.data:
                print(f"   🔹 {user['nome']} ({user['email']}) - {user['cargo']}")
        
        if classificacoes.data:
            print(f"\n📁 CLASSIFICAÇÕES:")
            for classif in classificacoes.data:
                print(f"   🔹 {classif['nome']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Erro no teste: {str(e)}")
        return False

if __name__ == "__main__":
    print("=" * 70)
    print("🔄 SINCRONIZAÇÃO DO ADMIN")
    print("=" * 70)
    print()
    print("📝 INSTRUÇÕES:")
    print("1. Vá ao Supabase Dashboard:")
    print("   → https://hifukfkwmhgmkirgjvqf.supabase.co")
    print("2. Authentication → Users → Add user")
    print("3. Email: admin@conciliacao.com")
    print("4. Password: admin123")
    print("5. ✅ Marcar 'Auto Confirm User'")
    print("6. Create user")
    print("7. COPIAR o UUID gerado")
    print()
    
    # Solicitar UUID
    admin_uuid = input("📋 Cole aqui o UUID do admin criado no Dashboard: ").strip()
    
    if not admin_uuid:
        print("❌ UUID não fornecido!")
        exit(1)
    
    print(f"\n🚀 Iniciando sincronização com UUID: {admin_uuid}")
    
    # Executar sincronização
    if sincronizar_admin(admin_uuid):
        print("\n✅ Admin sincronizado com sucesso!")
        
        # Criar dados de exemplo
        if criar_classificacoes_exemplo():
            print("\n✅ Classificações criadas!")
        
        # Testar sistema
        testar_sistema()
        
        print("\n" + "=" * 70)
        print("🎉 CONFIGURAÇÃO CONCLUÍDA!")
        print("=" * 70)
        print("✅ Admin configurado e funcional")
        print("✅ Dados básicos criados")
        print("✅ Sistema pronto para integração")
        print()
        print("🚀 PRÓXIMO PASSO:")
        print("   Integrar autenticação com seu main.py")
        
    else:
        print("\n❌ Falha na sincronização")
        print("💡 Verifique se o UUID está correto")