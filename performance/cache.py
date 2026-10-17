from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def memoize(max_size: int = 256) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Cache results for pure, repeated function calls with LRU eviction."""
    if max_size < 1:
        raise ValueError("max_size must be at least 1")

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        cache: OrderedDict[tuple[Any, ...], R] = OrderedDict()
        lock = threading.RLock()

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            key = (args, tuple(sorted(kwargs.items())))
            with lock:
                if key in cache:
                    cache.move_to_end(key)
                    return cache[key]

            value = func(*args, **kwargs)
            with lock:
                if key not in cache and len(cache) >= max_size:
                    cache.popitem(last=False)
                cache[key] = value
                cache.move_to_end(key)
            return value

        def clear() -> None:
            with lock:
                cache.clear()

        wrapper.clear = clear  # type: ignore[attr-defined]
        return wrapper

    return decorator
