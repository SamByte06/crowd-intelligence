"""
Database engine, session, and base model setup using SQLAlchemy.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

# Create engine with SQLite-specific optimizations
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    connect_args["timeout"] = 15.0
    try:
        import os
        raw_path = settings.DATABASE_URL.replace("sqlite:///", "").lstrip("/")
        if raw_path and not raw_path.startswith(":memory:"):
            # Ensure folder exists
            dir_name = os.path.dirname(os.path.abspath(raw_path if os.name == 'nt' else "/" + raw_path))
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
    except Exception:
        pass

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=settings.DEBUG,
    pool_pre_ping=True,
)

# Enable WAL mode and foreign keys for SQLite
if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that provides a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Called on application startup."""
    import app.models  # noqa: F401 — ensure models are imported before create_all
    Base.metadata.create_all(bind=engine)
