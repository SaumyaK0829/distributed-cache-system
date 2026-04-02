import pytest
from unittest.mock import MagicMock, patch
from app.cache import CacheManager

@pytest.fixture
def cache_manager():
    """Create a CacheManager with a mocked Redis client"""
    with patch('app.cache.redis.Redis') as mock_redis:
        mock_redis.return_value = MagicMock()
        manager = CacheManager()
        return manager

def test_cache_hit(cache_manager):
    """Test that cache returns value when key exists"""
    # Simulate Redis returning a value
    cache_manager.redis_client.get.return_value = '{"id": 1, "username": "saumya"}'
    
    result = cache_manager.get("user:1")
    
    assert result == {"id": 1, "username": "saumya"}
    assert cache_manager.cache_hits == 1
    assert cache_manager.cache_misses == 0

def test_cache_miss(cache_manager):
    """Test that cache returns None when key doesn't exist"""
    # Simulate Redis returning nothing
    cache_manager.redis_client.get.return_value = None
    
    result = cache_manager.get("user:999")
    
    assert result is None
    assert cache_manager.cache_hits == 0
    assert cache_manager.cache_misses == 1

def test_cache_set(cache_manager):
    """Test that cache stores value correctly"""
    result = cache_manager.set("user:1", {"id": 1, "username": "saumya"})
    
    assert result == True
    assert cache_manager.redis_client.setex.called

def test_cache_delete(cache_manager):
    """Test that cache deletes key correctly"""
    result = cache_manager.delete("user:1")
    
    assert result == True
    assert cache_manager.redis_client.delete.called

def test_cache_stats(cache_manager):
    """Test that stats are calculated correctly"""
    # Simulate 3 requests: 2 hits, 1 miss
    cache_manager.cache_hits = 2
    cache_manager.cache_misses = 1
    cache_manager.total_requests = 3
    cache_manager.redis_client.keys.return_value = ["user:1", "user:2"]
    
    stats = cache_manager.get_stats()
    
    assert stats["total_requests"] == 3
    assert stats["cache_hits"] == 2
    assert stats["cache_misses"] == 1
    assert stats["hit_rate_percent"] == 66.67
    assert stats["cached_keys"] == 2

def test_hit_rate_zero_requests(cache_manager):
    """Test hit rate when no requests have been made"""
    cache_manager.redis_client.keys.return_value = []
    stats = cache_manager.get_stats()
    
    assert stats["hit_rate_percent"] == 0.0
    assert stats["total_requests"] == 0