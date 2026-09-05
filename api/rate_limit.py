"""
Minimal in-memory rate limiter for Block 5.
Single-process only — sufficient for today's sprint. Swap for a
Redis-backed limiter before running multiple app instances.
"""
import time
import threading
from collections import defaultdict, deque

_lock = threading.Lock()
_hits = defaultdict(deque)

def is_rate_limited(key: str, max_attempts: int, window_seconds: int) -> bool:
    """
    Sliding-window check. Returns True if `key` has already made
    `max_attempts` or more calls within the last `window_seconds`.
    Records this call as an attempt regardless of outcome.
    """
    now = time.time()
    with _lock:
        q = _hits[key]
        while q and now - q[0] > window_seconds:
            q.popleft()
        if len(q) >= max_attempts:
            return True
        q.append(now)
        return False

def reset_key(key: str):
    """Test/debug helper: clear rate-limit history for a key."""
    with _lock:
        _hits.pop(key, None)