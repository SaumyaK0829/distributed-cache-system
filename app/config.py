from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application configuration settings"""
    
    # API Settings
    app_name: str = "Distributed Cache System"
    debug: bool = True
    
    # Redis Configuration
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    cache_ttl: int = 300  # Cache time-to-live in seconds (5 minutes)
    
    # PostgreSQL Configuration
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "admin"
    postgres_password: str = "admin123"
    postgres_db: str = "cachedb"
    
    class Config:
        env_file = ".env"

# Create a global settings instance
settings = Settings()