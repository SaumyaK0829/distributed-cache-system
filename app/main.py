from fastapi import FastAPI, HTTPException, Depends, Request, Response
from sqlalchemy.orm import Session
from app.database import get_db, init_db, User
from app.cache import cache
from app.metrics import track_request, update_cache_metrics
from pydantic import BaseModel
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import time

# Rate limiter — uses client IP address to track requests
limiter = Limiter(key_func=get_remote_address)

# Initialize FastAPI app
app = FastAPI(title="Distributed Cache System")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Pydantic model for creating a user
class UserCreate(BaseModel):
    username: str
    email: str

@app.on_event("startup")
def startup():
    """Initialize database tables when app starts"""
    init_db()

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Track request count and latency for every request"""
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    track_request(
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code,
        duration=duration
    )
    return response

@app.get("/")
def root():
    """Health check endpoint"""
    return {"message": "Distributed Cache System is running!"}

@app.get("/metrics")
def metrics():
    """Prometheus scrapes this endpoint every 15 seconds"""
    stats = cache.get_stats()
    update_cache_metrics(
        hit_rate=stats["hit_rate_percent"],
        total_keys=stats["cached_keys"]
    )
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/cache/stats")
def get_cache_stats():
    """Returns cache performance metrics"""
    return cache.get_stats()

@app.get("/users/")
@limiter.limit("10/minute")
def get_users(request: Request, skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    """
    Get all users with pagination.
    skip = how many records to skip (offset)
    limit = how many records to return (page size)
    Rate limited to 10 requests per minute per IP
    """
    cache_key = f"users:skip={skip}:limit={limit}"
    cached_users = cache.get(cache_key)
    if cached_users:
        return {"source": "cache", "users": cached_users, "skip": skip, "limit": limit}
    users = db.query(User).offset(skip).limit(limit).all()
    users_data = [
        {"id": u.id, "username": u.username, "email": u.email}
        for u in users
    ]
    cache.set(cache_key, users_data)
    return {"source": "database", "users": users_data, "skip": skip, "limit": limit}

@app.post("/users/")
@limiter.limit("5/minute")
def create_user(request: Request, user: UserCreate, db: Session = Depends(get_db)):
    """
    Create a new user in PostgreSQL
    Rate limited to 5 requests per minute per IP
    """
    existing = db.query(User).filter(User.username == user.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    new_user = User(username=user.username, email=user.email)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    cache.delete(f"user:{new_user.id}")
    return {"message": "User created", "user_id": new_user.id}

@app.get("/users/{user_id}")
@limiter.limit("10/minute")
def get_user(request: Request, user_id: int, db: Session = Depends(get_db)):
    """
    Get user by ID — implements Cache-Aside pattern
    Rate limited to 10 requests per minute per IP
    """
    cache_key = f"user:{user_id}"
    cached_user = cache.get(cache_key)
    if cached_user:
        return {"source": "cache", "user": cached_user}
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user_data = {"id": user.id, "username": user.username, "email": user.email}
    cache.set(cache_key, user_data)
    return {"source": "database", "user": user_data}

@app.delete("/users/{user_id}")
@limiter.limit("5/minute")
def delete_user(request: Request, user_id: int, db: Session = Depends(get_db)):
    """
    Delete user from PostgreSQL and cache
    Rate limited to 5 requests per minute per IP
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    cache.delete(f"user:{user_id}")
    return {"message": f"User {user_id} deleted"}

# What's happening here:

# GET /users/{id} — this is the Cache-Aside pattern in action. Notice the "source" field in the response — it tells you whether data came from cache or database. First call returns "database", second call returns "cache" ⚡
# POST /users/ — writes to Postgres and invalidates the cache
# DELETE /users/ — deletes from both Postgres AND cache (consistency!)
# Depends(get_db) — FastAPI's dependency injection, automatically handles DB session lifecycle