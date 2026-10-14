from __future__ import annotations

import threading
from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def memoize(max_size: int = 256) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Cache results for pure, repeated function calls.

    This is the highest-impact, lowest-effort change for any read-heavy workflow:
    it removes redundant computation without changing call semantics.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        cache: dict[tuple[Any, ...], R] = {}
        lock = threading.RLock()

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            key = (args, tuple(sorted(kwargs.items())))
            with lock:
                if key in cache:
                    return cache[key]

            value = func(*args, **kwargs)
            with lock:
                if len(cache) >= max_size:
                    cache.clear()
                cache[key] = value
            return value

        wrapper.clear = lambda: cache.clear()  # type: ignore[attr-defined]
        return wrapper

    return decorator
