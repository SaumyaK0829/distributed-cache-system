import redis
import json
from typing import Optional, Any
from app.config import settings

class CacheManager:
    """Redis cache manager for fast data access"""
    
    def __init__(self):
        """Initialize Redis connection"""
        self.redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            decode_responses=True  # Automatically decode bytes to strings
        )
        self.default_ttl = settings.cache_ttl
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        try:
            value = self.redis_client.get(key)
            if value:
                return json.loads(value)  # Convert JSON string back to Python object
            return None
        except Exception as e:
            print(f"Cache get error: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with optional TTL (time-to-live)"""
        try:
            ttl = ttl or self.default_ttl
            serialized_value = json.dumps(value)  # Convert Python object to JSON string
            self.redis_client.setex(key, ttl, serialized_value)
            return True
        except Exception as e:
            print(f"Cache set error: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        try:
            self.redis_client.delete(key)
            return True
        except Exception as e:
            print(f"Cache delete error: {e}")
            return False
    
    def clear_all(self) -> bool:
        """Clear all cache (use carefully!)"""
        try:
            self.redis_client.flushdb()
            return True
        except Exception as e:
            print(f"Cache clear error: {e}")
            return False

# Create global cache instance
cache = CacheManager()