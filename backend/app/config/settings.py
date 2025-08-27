from pydantic import BaseSettings
from typing import List
import os

class Settings(BaseSettings):
    # Database
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-key-123")
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "jwt-secret-key")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # App
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    PORT: int = int(os.getenv("PORT", 8000))
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "https://sistema-conciliacao-bancaria-production.up.railway.app",
        "https://*.railway.app",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
    ]
    
    class Config:
        env_file = ".env"

def get_settings() -> Settings:
    return Settings()
