"""Backend registry.

Built-in backends are referenced by import path and only imported when needed,
so ``import mco`` never imports a runtime. Third-party backends can be added
with :func:`register_backend` or through the ``mco.backends`` entry-point group::

    [project.entry-points."mco.backends"]
    my-runtime = "my_package.backend:MyBackend"
"""
from __future__ import annotations

from importlib import import_module
from importlib.metadata import entry_points
import threading
from typing import Optional

from ..errors import BackendUnavailableError, UnsupportedFormatError
from ..formats import ModelFile
from .base import Backend, BackendModel, BackendSession

__all__ = [
    "Backend",
    "BackendModel",
    "BackendSession",
    "register_backend",
    "get_backend",
    "available_backends",
    "select_backend",
]

_BUILTIN = {
    "marco-kgpack": "mco.backends.marco:MarcoKgpackBackend",
    "mco-native": "mco.backends.native:NativeMcoBackend",
}
_registered: dict[str, type[Backend]] = {}
_instances: dict[str, Backend] = {}
_lock = threading.Lock()
_entry_points_loaded = False


def register_backend(backend: type[Backend], *, replace: bool = False) -> type[Backend]:
    """Register a backend class. Usable as a decorator."""
    if not (isinstance(backend, type) and issubclass(backend, Backend)):
        raise TypeError("register_backend() expects a Backend subclass")
    name = getattr(backend, "name", None)
    if not isinstance(name, str) or not name:
        raise TypeError("a Backend subclass must define a non-empty 'name'")
    with _lock:
        if not replace and (name in _registered or name in _BUILTIN):
            raise ValueError(f"backend {name!r} is already registered")
        _registered[name] = backend
        _instances.pop(name, None)
    return backend


def _load_entry_points() -> None:
    global _entry_points_loaded
    if _entry_points_loaded:
        return
    _entry_points_loaded = True
    for ep in entry_points(group="mco.backends"):
        if ep.name in _BUILTIN or ep.name in _registered:
            continue
        try:
            cls = ep.load()
        except Exception:  # a broken third-party plugin must not break mco
            continue
        if isinstance(cls, type) and issubclass(cls, Backend):
            _registered.setdefault(ep.name, cls)


def _names() -> list[str]:
    _load_entry_points()
    return list(_BUILTIN) + [n for n in _registered if n not in _BUILTIN]


def get_backend(name: str) -> Backend:
    """Return the (cached) backend instance registered under ``name``."""
    with _lock:
        if name in _instances:
            return _instances[name]
    _load_entry_points()
    if name in _registered:
        cls = _registered[name]
    elif name in _BUILTIN:
        module, _, attr = _BUILTIN[name].partition(":")
        cls = getattr(import_module(module), attr)
    else:
        raise BackendUnavailableError(f"unknown backend {name!r}; known: {', '.join(_names())}")
    with _lock:
        return _instances.setdefault(name, cls())


def available_backends() -> dict[str, tuple[bool, str]]:
    """``{name: (usable, reason)}`` for every known backend."""
    return {name: get_backend(name).availability() for name in _names()}


def select_backend(file: ModelFile, name: Optional[str] = None) -> Backend:
    """Choose the backend that will run ``file``.

    An explicit ``name`` wins. Otherwise the backend recorded in the model's
    manifest is preferred, then the highest-priority backend that accepts it.
    """
    if name is not None:
        backend = get_backend(name)
        if not backend.accepts(file):
            raise UnsupportedFormatError(f"backend {name!r} cannot open {file.kind} files")
        return backend
    recorded = (file.manifest.get("runtime") or {}).get("backend") if file.manifest else None
    candidates = [get_backend(n) for n in _names()]
    if recorded:
        candidates.sort(key=lambda b: b.name != recorded)
    accepting = [b for b in candidates if b.accepts(file)]
    if not accepting:
        raise UnsupportedFormatError(f"no installed backend can open {file.kind} files")
    if not recorded:
        accepting.sort(key=lambda b: -b.priority)
    return accepting[0]
