from __future__ import annotations

import math
import threading
from collections import OrderedDict
from collections.abc import Callable
from functools import wraps
from inspect import Parameter, Signature, signature
from typing import Any, NamedTuple, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


class CacheInfo(NamedTuple):
    hits: int
    misses: int
    maxsize: int
    currsize: int


def _freeze_float(value: float) -> tuple[type, str, float]:
    """Encode float values while preserving signed zero and NaN/Infinity signs."""
    if math.isnan(value):
        return (float, "nan", math.copysign(1.0, value))
    if math.isinf(value):
        return (float, "inf", math.copysign(1.0, value))
    return (float, value.hex(), 0.0)


def _freeze(value: Any, active: set[int] | None = None) -> Any:
    """Create a hashable, type-sensitive key, or raise TypeError if unsupported."""
    if value is None:
        return (type(None),)
    if type(value) is bool:
        return (bool, value)
    if type(value) is int:
        return (int, value)
    if type(value) is float:
        return _freeze_float(value)
    if type(value) is complex:
        return (complex, _freeze_float(value.real), _freeze_float(value.imag))
    if type(value) is str or type(value) is bytes:
        return (type(value), value)

    if active is None:
        active = set()
    if isinstance(value, (tuple, list, dict, set, frozenset)):
        identity = id(value)
        if identity in active:
            raise TypeError("recursive values cannot be memoized")
        active.add(identity)
        try:
            if isinstance(value, dict):
                contents = tuple(
                    (_freeze(key, active), _freeze(item, active))
                    for key, item in value.items()
                )
            else:
                contents = tuple(_freeze(item, active) for item in value)
        finally:
            active.remove(identity)
        return (type(value), contents)

    try:
        hash(value)
    except TypeError:
        raise
    return (type(value), value)


def _make_key(
    func_signature: Signature | None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    if func_signature is None:
        return (
            tuple(_freeze(value) for value in args),
            tuple((name, _freeze(value)) for name, value in kwargs.items()),
        )

    bound = func_signature.bind(*args, **kwargs)
    bound.apply_defaults()
    values = []
    for name, parameter in func_signature.parameters.items():
        value = bound.arguments[name]
        if parameter.kind is Parameter.VAR_KEYWORD:
            frozen = tuple((key, _freeze(item)) for key, item in value.items())
        else:
            frozen = _freeze(value)
        values.append((name, frozen))
    return tuple(values)


def memoize(max_size: int = 256) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Cache results for pure, repeated function calls with LRU eviction."""
    if isinstance(max_size, bool) or not isinstance(max_size, int) or max_size < 1:
        raise ValueError("max_size must be a positive integer")

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        cache: OrderedDict[tuple[Any, ...], R] = OrderedDict()
        lock = threading.RLock()
        try:
            func_signature = signature(func)
        except (TypeError, ValueError):
            func_signature = None
        hits = 0
        misses = 0

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            nonlocal hits, misses
            try:
                key = _make_key(func_signature, args, kwargs)
                hash(key)
            except TypeError:
                key = None

            with lock:
                if key is not None and key in cache:
                    cache.move_to_end(key)
                    hits += 1
                    return cache[key]
                misses += 1

            value = func(*args, **kwargs)
            if key is not None:
                with lock:
                    if key not in cache:
                        if len(cache) >= max_size:
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
                return CacheInfo(hits, misses, max_size, len(cache))

        wrapper.clear = clear  # type: ignore[attr-defined]
        wrapper.cache_clear = clear  # type: ignore[attr-defined]
        wrapper.cache_info = cache_info  # type: ignore[attr-defined]
        return wrapper

    return decorator
