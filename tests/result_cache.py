"""Result caches that a test session may release without discarding compiled models."""

import gc
from functools import lru_cache
from weakref import WeakSet

_CACHES = WeakSet()


def result_cache(maxsize=None):
    """Register an LRU result cache; its normal lifetime and size stay unchanged."""

    def decorate(function):
        cached = lru_cache(maxsize=maxsize)(function)
        _CACHES.add(cached)
        return cached

    return decorate


def clear_result_caches():
    """Release registered results, including cycles, and return the entry count."""
    caches = tuple(_CACHES)
    entries = sum(cached.cache_info().currsize for cached in caches)
    for cached in caches:
        cached.cache_clear()
    if entries:
        gc.collect()
    return entries
