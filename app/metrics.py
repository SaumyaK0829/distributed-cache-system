from prometheus_client import Counter, Histogram, Gauge
import time

# Counter — tracks total number of times something happened
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

# Histogram — tracks how long requests take
REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['endpoint']
)

# Gauge — tracks a value that goes up and down
CACHE_HIT_RATE = Gauge(
    'cache_hit_rate_percent',
    'Current cache hit rate percentage'
)

CACHE_KEYS_TOTAL = Gauge(
    'cache_keys_total',
    'Total number of keys in cache'
)

def track_request(method: str, endpoint: str, status_code: int, duration: float):
    """Record metrics for each request"""
    REQUEST_COUNT.labels(
        method=method,
        endpoint=endpoint,
        status_code=status_code
    ).inc()
    
    REQUEST_LATENCY.labels(endpoint=endpoint).observe(duration)

def update_cache_metrics(hit_rate: float, total_keys: int):
    """Update cache performance gauges"""
    CACHE_HIT_RATE.set(hit_rate)
    CACHE_KEYS_TOTAL.set(total_keys)