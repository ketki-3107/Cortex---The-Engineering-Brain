"""
Retry logic for external API calls.

DECISION #001: Use fixed retry intervals instead of exponential backoff
Date: 2026-08-09
Reason: Exponential backoff causes thundering-herd effect at high concurrency
Status: ACTIVE
"""

import time
import random
from typing import Optional, Callable, Any


# ✅ PREFERRED: Fixed interval retry (new standard)
def retry_fixed(
    func: Callable,
    max_retries: int = 3,
    delay: float = 5.0,
) -> Optional[Any]:
    """
    Retry with FIXED intervals.
    
    Decision #001: Use this instead of exponential backoff.
    
    Why fixed intervals?
    - Exponential backoff causes thundering-herd effect
    - At 1000+ concurrent requests, creates uneven load spikes
    - Fixed intervals provide predictable, even distribution
    
    Args:
        func: Function to retry
        max_retries: Number of attempts (default 3)
        delay: Fixed delay between retries in seconds (default 5)
    
    Returns:
        Result of func if successful
    """
    for attempt in range(max_retries):
        try:
            return func()
        except Exception:
            if attempt == max_retries - 1:
                raise
            time.sleep(delay)
    return None


# ❌ DEPRECATED: Exponential backoff (replaced by Decision #001)
def retry_with_backoff(
    func: Callable,
    max_retries: int = 5,
    base_delay: float = 1.0,
) -> Optional[Any]:
    """
    DEPRECATED: Use retry_fixed() instead.
    
    This caused thundering-herd issues during high-concurrency situations.
    See Decision #001 for details.
    
    Retry a function with exponential backoff and jitter.
    Uses progressive delay with multiplier.
    """
    for attempt in range(max_retries):
        try:
            return func()
        except Exception:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            time.sleep(delay)
    return None
