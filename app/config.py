from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    """Application configuration settings — reads from .env file"""
    
    # API Settings
    app_name: str = "Distributed Cache System"
    debug: bool = True
    
    # Redis Configuration
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    cache_ttl: int = 300
    
    # PostgreSQL Configuration
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "admin"
    postgres_password: str = "admin123"
    postgres_db: str = "cachedb"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache()
def get_settings() -> Settings:
    """
    Cache the settings object so .env is only read once.
    lru_cache = Least Recently Used cache — Python's built-in memoization
    """
    return Settings()

# Global settings instance
settings = get_settings()