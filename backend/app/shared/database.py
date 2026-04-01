from contextlib import contextmanager
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from shared.config import db_settings

engine = create_engine(db_settings.url, pool_pre_ping=True)
_SessionFactory = sessionmaker(bind=engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
