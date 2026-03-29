from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator


_AUDIT_ID: ContextVar[str] = ContextVar("audit_id", default="")
_RUN_ID: ContextVar[str] = ContextVar("run_id", default="")


def current_audit_id() -> str:
    return _AUDIT_ID.get()


def current_run_id() -> str:
    return _RUN_ID.get()


@contextmanager
def bind_audit_context(audit_id: str = "", run_id: str = "") -> Iterator[None]:
    audit_token = _AUDIT_ID.set(str(audit_id or "").strip())
    run_token = _RUN_ID.set(str(run_id or "").strip())
    try:
        yield
    finally:
        _AUDIT_ID.reset(audit_token)
        _RUN_ID.reset(run_token)
