import os
from typing import List
from dotenv import load_dotenv

# Carregar variáveis do .env
load_dotenv()

class Settings:
    # Supabase
    SUPABASE_URL = os.getenv('SUPABASE_URL')
    SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY') 
    SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    
    # App
    SECRET_KEY = os.getenv('SECRET_KEY', 'change-me-in-production')
    ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
    DEBUG = os.getenv('DEBUG', 'true').lower() == 'true'
    
    # CORS
    ALLOWED_ORIGINS = [
        "http://localhost:3000",
        "http://localhost:8000", 
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000"
    ]
    
    # Upload
    MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', '52428800'))
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'uploads')

settings = Settings()

# Validar configurações
def validate_config():
    required = ['SUPABASE_URL', 'SUPABASE_ANON_KEY', 'SUPABASE_SERVICE_ROLE_KEY']
    missing = [key for key in required if not getattr(settings, key)]
    
    if missing:
        raise Exception(f"Configurações obrigatórias não encontradas: {missing}")
    
    print("✅ Configurações validadas com sucesso!")
    return True