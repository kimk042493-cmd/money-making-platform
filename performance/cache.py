from __future__ import annotations

import inspect
import struct
import threading
from collections import OrderedDict, namedtuple
from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")
CacheInfo = namedtuple("CacheInfo", ["hits", "misses", "maxsize", "currsize"])
_UNCACHEABLE = object()


def _freeze(value: Any, seen: set[int] | None = None) -> Any:
    """Convert nested Python data into a hashable, stable representation."""
    value_type = type(value)
    if value is None or value_type in (str, bytes, bool, int):
        return (value_type, value)
    if value_type is float:
        return (float, struct.pack(">d", value))
    if value_type is complex:
        return (complex, struct.pack(">dd", value.real, value.imag))
    if value_type in (list, tuple):
        return _freeze_sequence(value, seen)
    if value_type is dict:
        active = seen if seen is not None else set()
        identity = id(value)
        if identity in active:
            return _UNCACHEABLE
        active.add(identity)
        try:
            items = tuple(
                (_freeze(key, active), _freeze(item, active))
                for key, item in value.items()
            )
        finally:
            active.remove(identity)
        if any(key is _UNCACHEABLE or item is _UNCACHEABLE for key, item in items):
            return _UNCACHEABLE
        return (dict, items)
    if value_type in (set, frozenset):
        active = seen if seen is not None else set()
        identity = id(value)
        if identity in active:
            return _UNCACHEABLE
        active.add(identity)
        try:
            items = tuple(_freeze(item, active) for item in value)
        finally:
            active.remove(identity)
        if any(item is _UNCACHEABLE for item in items):
            return _UNCACHEABLE
        items = frozenset(items)
        return (value_type, items)
    try:
        hash(value)
    except TypeError:
        return _UNCACHEABLE
    return (value_type, value)


def _freeze_sequence(value: list[Any] | tuple[Any, ...], seen: set[int] | None) -> Any:
    active = seen if seen is not None else set()
    identity = id(value)
    if identity in active:
        return _UNCACHEABLE
    active.add(identity)
    try:
        items = tuple(_freeze(item, active) for item in value)
    finally:
        active.remove(identity)
    if any(item is _UNCACHEABLE for item in items):
        return _UNCACHEABLE
    return (type(value), items)


def memoize(max_size: int = 256) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Cache results for pure, repeated function calls with LRU eviction."""
    if isinstance(max_size, bool) or not isinstance(max_size, int) or max_size < 1:
        raise ValueError("max_size must be at least 1")

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        cache: OrderedDict[tuple[Any, ...], R] = OrderedDict()
        lock = threading.RLock()
        hits = 0
        misses = 0
        try:
            signature = inspect.signature(func)
        except (TypeError, ValueError):
            signature = None

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            nonlocal hits, misses
            if signature is not None:
                bound = signature.bind(*args, **kwargs)
                bound.apply_defaults()
                frozen_arguments = tuple(
                    (name, _freeze(value)) for name, value in bound.arguments.items()
                )
                if any(value is _UNCACHEABLE for _, value in frozen_arguments):
                    return func(*args, **kwargs)
                key = frozen_arguments
            else:
                frozen_args = _freeze(args)
                normalized_kwargs = tuple(kwargs.items())
                frozen_kwargs = _freeze(normalized_kwargs)
                if frozen_args is _UNCACHEABLE or frozen_kwargs is _UNCACHEABLE:
                    return func(*args, **kwargs)
                key = (frozen_args, frozen_kwargs)

            with lock:
                if key in cache:
                    cache.move_to_end(key)
                    hits += 1
                    return cache[key]
                misses += 1

            value = func(*args, **kwargs)
            with lock:
                if key not in cache and len(cache) >= max_size:
                    cache.popitem(last=False)
                cache[key] = value
                cache.move_to_end(key)
            return value

        def clear() -> None:
            nonlocal hits, misses
            with lock:
                cache.clear()
                hits = 0
                misses = 0

        def cache_info() -> CacheInfo:
            with lock:
                return CacheInfo(
                    hits=hits, misses=misses, maxsize=max_size, currsize=len(cache)
                )

        wrapper.clear = clear  # type: ignore[attr-defined]
        wrapper.cache_clear = clear  # type: ignore[attr-defined]
        wrapper.cache_info = cache_info  # type: ignore[attr-defined]
        return wrapper

    return decorator
