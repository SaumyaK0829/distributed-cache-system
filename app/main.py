from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db, init_db, User
from app.cache import cache
from pydantic import BaseModel

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

@app.get("/")
def root():
    """Health check endpoint"""
    return {"message": "Distributed Cache System is running!"}

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