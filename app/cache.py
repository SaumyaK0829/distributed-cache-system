import redis
import json
from typing import Optional, Any
from app.config import settings

class CacheManager:
    """Redis cache manager with hit/miss statistics tracking"""
    
    def __init__(self):
        """Initialize Redis connection and stats counters"""
        self.redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            decode_responses=True
        )
        self.default_ttl = settings.cache_ttl
        
        # Stats counters
        self.total_requests = 0
        self.cache_hits = 0
        self.cache_misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache and track hit/miss"""
        try:
            self.total_requests += 1
            value = self.redis_client.get(key)
            
            if value:
                self.cache_hits += 1
                return json.loads(value)
            
            self.cache_misses += 1
            return None
        except Exception as e:
            print(f"Cache get error: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with optional TTL"""
        try:
            ttl = ttl or self.default_ttl
            serialized_value = json.dumps(value)
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
    
    def get_stats(self) -> dict:
        """
        Return cache performance statistics.
        Hit rate = hits / total requests * 100
        """
        hit_rate = (
            round((self.cache_hits / self.total_requests) * 100, 2)
            if self.total_requests > 0
            else 0.0
        )
        miss_rate = (
            round((self.cache_misses / self.total_requests) * 100, 2)
            if self.total_requests > 0
            else 0.0
        )
        
        return {
            "total_requests": self.total_requests,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate_percent": hit_rate,
            "miss_rate_percent": miss_rate,
            "cached_keys": len(self.redis_client.keys("*")),
        }
    
    def clear_all(self) -> bool:
        """Clear all cache"""
        try:
            self.redis_client.flushdb()
            return True
        except Exception as e:
            print(f"Cache clear error: {e}")
            return False

# Global cache instance
cache = CacheManager()