from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

try:
    import redis as redis_lib
except ImportError:  # pragma: no cover
    redis_lib = None


class RateLimiter:
    """Sliding window por clave. Redis si hay URL; si no, memoria de proceso."""

    def __init__(self, redis_url: str = "") -> None:
        self._memory: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()
        self._redis = None
        if redis_url and redis_lib is not None:
            try:
                client = redis_lib.Redis.from_url(redis_url, socket_connect_timeout=0.4)
                client.ping()
                self._redis = client
            except Exception:
                self._redis = None

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "memory"

    def hit(self, key_id: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
        if self._redis is not None:
            return self._hit_redis(key_id, limit, window_seconds)
        return self._hit_memory(key_id, limit, window_seconds)

    def _hit_memory(self, key_id: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.time()
        with self._lock:
            bucket = self._memory[key_id]
            cutoff = now - window_seconds
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False, 0
            bucket.append(now)
            return True, limit - len(bucket)

    def _hit_redis(self, key_id: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        redis_key = f"paracite:rl:{key_id}"
        now = time.time()
        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(redis_key, 0, now - window_seconds)
        pipe.zcard(redis_key)
        pipe.zadd(redis_key, {str(now): now})
        pipe.expire(redis_key, window_seconds)
        _, count, _, _ = pipe.execute()
        if count >= limit:
            self._redis.zrem(redis_key, str(now))
            return False, 0
        remaining = max(0, limit - int(count) - 1)
        return True, remaining
