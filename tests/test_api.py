import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    """Create test client"""
    with TestClient(app) as c:
        yield c

def test_root_endpoint(client):
    """Test health check endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Distributed Cache System is running!"}

def test_cache_stats_endpoint(client):
    """Test cache stats endpoint returns correct structure"""
    response = client.get("/cache/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_requests" in data
    assert "cache_hits" in data
    assert "cache_misses" in data
    assert "hit_rate_percent" in data

def test_get_user_not_found(client):
    """Test that 404 is returned for non-existent user"""
    response = client.get("/users/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"

def test_get_users_pagination(client):
    """Test pagination parameters are accepted"""
    response = client.get("/users/?skip=0&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert "users" in data
    assert "skip" in data
    assert "limit" in data
    assert data["skip"] == 0
    assert data["limit"] == 5