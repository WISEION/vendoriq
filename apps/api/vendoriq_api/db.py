"""Engine, session factory and the unit of work.

One request is one transaction. The route handler never commits: it calls services on a
:class:`UnitOfWork`, and the dependency commits once the handler returns without raising.
That is what makes "every mutation writes an audit event" enforceable — the audit row and
the change it describes are the same transaction, so neither can exist without the other.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from types import TracebackType

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Lazily-built engine so importing the package never opens a connection."""
    settings = get_settings()
    return create_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_pre_ping=True,
        future=True,
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


class UnitOfWork:
    """A session plus the identity performing the work.

    Services take a ``UnitOfWork`` rather than a bare ``Session`` because every mutating
    service call needs the actor for the audit row, and threading the actor through each
    signature separately is how one of them ends up forgetting it.
    """

    def __init__(self, session: Session, actor_id: object | None = None) -> None:
        self.session = session
        #: ``uuid.UUID | None`` — NULL for anonymous and machine-initiated writes.
        self.actor_id = actor_id

    def flush(self) -> None:
        self.session.flush()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def __enter__(self) -> UnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a session; the request handler owns the transaction."""
    with get_sessionmaker()() as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transaction scope for scripts, the seed CLI and the worker jobs."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
