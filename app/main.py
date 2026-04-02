from fastapi import FastAPI, HTTPException, Depends, Request, Response
from sqlalchemy.orm import Session
from app.database import get_db, init_db, User, SessionLocal
from app.cache import cache
from app.metrics import track_request, update_cache_metrics
from pydantic import BaseModel
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import time
import redis as redis_client

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Direct Redis connection for distributed locking
redis_conn = redis_client.Redis(
    host="redis",
    port=6379,
    db=0,
    decode_responses=True
)

# Initialize FastAPI app
app = FastAPI(title="Distributed Cache System")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Pydantic model for creating a user
class UserCreate(BaseModel):
    username: str
    email: str

# ============================================================
# DISTRIBUTED LOCKING
# ============================================================
class DistributedLock:
    """
    Prevents cache stampede — when cache expires and thousands
    of requests simultaneously hit the database.
    Only ONE request gets the lock and fetches from DB.
    All others wait and then read from cache.

    Real world analogy: Like a single key to a room.
    Only one person can enter at a time. Others wait outside.
    """
    def __init__(self, lock_name: str, expire: int = 10):
        self.lock_name = f"lock:{lock_name}"
        self.expire = expire

    def acquire(self) -> bool:
        """Try to acquire lock — returns True if successful"""
        # SET key value NX EX = set only if not exists, with expiry
        # This is atomic in Redis — no race conditions
        result = redis_conn.set(
            self.lock_name,
            "locked",
            nx=True,      # Only set if key doesn't exist
            ex=self.expire # Auto-expire after N seconds
        )
        return result is True

    def release(self):
        """Release the lock"""
        redis_conn.delete(self.lock_name)

# ============================================================
# CACHE WARMING
# ============================================================
def warm_cache():
    """
    Pre-load the first page of users into cache on startup.
    Solves the 'cold start' problem.
    """
    try:
        db = SessionLocal()
        users = db.query(User).limit(10).all()
        if users:
            users_data = [
                {"id": u.id, "username": u.username, "email": u.email}
                for u in users
            ]
            cache.set("users:skip=0:limit=10", users_data)
            for user in users:
                user_data = {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email
                }
                cache.set(f"user:{user.id}", user_data)
            print(f"Cache warmed with {len(users)} users ✅")
        else:
            print("No users to warm cache with")
        db.close()
    except Exception as e:
        print(f"Cache warming failed: {e}")

@app.on_event("startup")
def startup():
    init_db()
    warm_cache()

# ============================================================
# MIDDLEWARE
# ============================================================
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

# ============================================================
# ROUTES
# ============================================================
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
    Rate limited to 10 requests per minute per IP.
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
    Write-Through Cache pattern:
    1. Write to PostgreSQL
    2. IMMEDIATELY write to Redis cache too
    3. Both are always in sync

    Difference from Cache-Aside:
    - Cache-Aside: writes only to DB, cache is populated lazily on next read
    - Write-Through: writes to BOTH DB and cache simultaneously
    This means cache is ALWAYS up to date after a write.
    """
    existing = db.query(User).filter(User.username == user.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    # Step 1: Write to PostgreSQL
    new_user = User(username=user.username, email=user.email)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Step 2: Write-Through — immediately write to cache too
    user_data = {
        "id": new_user.id,
        "username": new_user.username,
        "email": new_user.email
    }
    cache.set(f"user:{new_user.id}", user_data)

    return {
        "message": "User created",
        "user_id": new_user.id,
        "cache_strategy": "write-through"
    }

@app.get("/users/{user_id}")
@limiter.limit("10/minute")
def get_user(request: Request, user_id: int, db: Session = Depends(get_db)):
    """
    Get user by ID with Cache-Aside pattern + Distributed Locking.

    Distributed Lock prevents cache stampede:
    - Cache expires → 1000 requests come in simultaneously
    - Without lock: all 1000 hit the database at once 💥
    - With lock: only 1 request fetches from DB, others wait
      and then read from cache ✅
    """
    cache_key = f"user:{user_id}"

    # Step 1: Check cache first
    cached_user = cache.get(cache_key)
    if cached_user:
        return {"source": "cache", "user": cached_user}

    # Step 2: Cache miss — acquire distributed lock
    lock = DistributedLock(f"fetch_user_{user_id}")

    if lock.acquire():
        try:
            # Step 3: Double-check cache (another request might have
            # populated it while we were acquiring the lock)
            cached_user = cache.get(cache_key)
            if cached_user:
                return {"source": "cache_after_lock", "user": cached_user}

            # Step 4: Fetch from database
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # Step 5: Store in cache
            user_data = {
                "id": user.id,
                "username": user.username,
                "email": user.email
            }
            cache.set(cache_key, user_data)
            return {"source": "database", "user": user_data}

        finally:
            # Always release lock even if an error occurs
            lock.release()
    else:
        # Could not acquire lock — another request is fetching
        # Wait briefly and read from cache
        time.sleep(0.1)
        cached_user = cache.get(cache_key)
        if cached_user:
            return {"source": "cache_after_wait", "user": cached_user}

        # Fallback to database if cache still empty
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {"source": "database_fallback", "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email
        }}

@app.delete("/users/{user_id}")
@limiter.limit("5/minute")
def delete_user(request: Request, user_id: int, db: Session = Depends(get_db)):
    """Delete user from PostgreSQL and cache"""
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