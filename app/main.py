from fastapi import FastAPI, HTTPException, Depends, Request, Response
from sqlalchemy.orm import Session
from app.database import get_db, init_db, User
from app.cache import cache
from app.metrics import track_request, update_cache_metrics
from pydantic import BaseModel
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
import time

# Initialize FastAPI app
app = FastAPI(title="Distributed Cache System")

# Pydantic model for creating a user (request body validation)
class UserCreate(BaseModel):
    username: str
    email: str

@app.on_event("startup")
def startup():
    """Initialize database tables when app starts"""
    init_db()

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """
    Middleware runs on EVERY request automatically.
    We use it to track request count and latency.
    Think of it like a toll booth — every request passes through it.
    """
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
    """
    Prometheus scrapes this endpoint every 15 seconds.
    Returns all metrics in Prometheus text format.
    This is how Prometheus knows what's happening in our app.
    """
    stats = cache.get_stats()
    update_cache_metrics(
        hit_rate=stats["hit_rate_percent"],
        total_keys=stats["cached_keys"]
    )
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/cache/stats")
def get_cache_stats():
    """
    Returns cache performance metrics.
    Hit rate tells you how effective your cache is.
    A good hit rate is > 80% in production.
    """
    return cache.get_stats()

@app.get("/users/")
def get_users(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    """
    Get all users with pagination.
    skip = how many records to skip (offset)
    limit = how many records to return (page size)

    Example: skip=0, limit=10 → page 1
             skip=10, limit=10 → page 2
             skip=20, limit=10 → page 3
    """
    cache_key = f"users:skip={skip}:limit={limit}"

    # Check cache first
    cached_users = cache.get(cache_key)
    if cached_users:
        return {"source": "cache", "users": cached_users, "skip": skip, "limit": limit}

    # Cache miss — fetch from PostgreSQL
    users = db.query(User).offset(skip).limit(limit).all()
    users_data = [
        {"id": u.id, "username": u.username, "email": u.email}
        for u in users
    ]

    # Store in cache
    cache.set(cache_key, users_data)

    return {"source": "database", "users": users_data, "skip": skip, "limit": limit}

@app.post("/users/")
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    """
    Create a new user in PostgreSQL
    and invalidate cache so fresh data is fetched next time
    """
    # Check if user already exists
    existing = db.query(User).filter(User.username == user.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    # Save to PostgreSQL
    new_user = User(username=user.username, email=user.email)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Invalidate cache for this user (so stale data isn't returned)
    cache.delete(f"user:{new_user.id}")

    return {"message": "User created", "user_id": new_user.id}

@app.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    """
    Get user by ID — implements Cache-Aside pattern:
    1. Check Redis first
    2. If not found, fetch from PostgreSQL
    3. Store in Redis for next time
    """
    cache_key = f"user:{user_id}"

    # Step 1: Check cache
    cached_user = cache.get(cache_key)
    if cached_user:
        return {"source": "cache", "user": cached_user}

    # Step 2: Cache miss — fetch from PostgreSQL
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Step 3: Store in cache for next time
    user_data = {"id": user.id, "username": user.username, "email": user.email}
    cache.set(cache_key, user_data)

    return {"source": "database", "user": user_data}

@app.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    """
    Delete user from PostgreSQL and remove from cache
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Delete from PostgreSQL
    db.delete(user)
    db.commit()

    # Delete from cache too (very important!)
    cache.delete(f"user:{user_id}")

    return {"message": f"User {user_id} deleted"}

# What's happening here:

# GET /users/{id} — this is the Cache-Aside pattern in action. Notice the "source" field in the response — it tells you whether data came from cache or database. First call returns "database", second call returns "cache" ⚡
# POST /users/ — writes to Postgres and invalidates the cache
# DELETE /users/ — deletes from both Postgres AND cache (consistency!)
# Depends(get_db) — FastAPI's dependency injection, automatically handles DB session lifecycle