# Distributed Cache System

A production-ready distributed caching system built with **FastAPI**, **Redis**, and **PostgreSQL**, implementing the **Cache-Aside pattern** with full Docker containerization.

## Architecture
```
Client → FastAPI App → Redis Cache (fast)
                     ↓ (cache miss)
                   PostgreSQL (persistent)
```

## Cache-Aside Pattern
1. Request comes in for data
2. Check Redis first → if found, return instantly ⚡ (cache hit)
3. If not found → fetch from PostgreSQL (cache miss)
4. Store result in Redis for next time
5. Return data to client

## Tech Stack
| Technology | Purpose |
|------------|---------|
| FastAPI | REST API framework |
| Redis | In-memory cache (TTL: 5 mins) |
| PostgreSQL | Persistent database |
| SQLAlchemy | ORM for database queries |
| Docker | Containerization |
| Docker Compose | Multi-container orchestration |

## Project Structure
```
distributed_cache_system/
├── app/
│   ├── main.py        # FastAPI routes (Cache-Aside logic)
│   ├── cache.py       # Redis cache manager
│   ├── database.py    # PostgreSQL models & session
│   └── config.py      # Environment configuration
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Getting Started

### Prerequisites
- Docker & Docker Compose

### Run the project
```bash
git clone https://github.com/SaumyaK0829/distributed-cache-system.git
cd distributed-cache-system
docker-compose up --build
```

### API Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| POST | `/users/` | Create a user |
| GET | `/users/{id}` | Get user (Cache-Aside) |
| DELETE | `/users/{id}` | Delete user + invalidate cache |

### Interactive Docs
Visit `http://localhost:8000/docs` for Swagger UI

## Key Concepts Demonstrated
- **Cache-Aside pattern** — lazy loading data into cache
- **Cache invalidation** — deleting stale cache on write/delete
- **TTL (Time-To-Live)** — automatic cache expiry after 5 minutes
- **Docker networking** — services communicating via container names
- **Health checks** — ensuring Postgres is ready before app starts
- **Dependency injection** — FastAPI's `Depends()` for DB sessions