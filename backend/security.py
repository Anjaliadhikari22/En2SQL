"""
Basic security helpers for En2SQL.

En2SQL is local-first. By default, prompts and database data are not sent to
external AI services. Optional Llama support should run locally and should
receive only minimal metadata, never actual database records.
"""

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
except Exception:  # pragma: no cover - fallback for environments before install
    Limiter = None
    get_remote_address = None


class _NoOpLimiter:
    def limit(self, _rule: str):
        def decorator(fn):
            return fn
        return decorator


def create_limiter(app):
    """Create a Flask-Limiter instance, or a no-op fallback if unavailable."""
    if Limiter is None:
        return _NoOpLimiter()
    return Limiter(
        get_remote_address,
        app=app,
        default_limits=[],
        storage_uri="memory://",
    )
