import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://virtue:virtuepass@postgres:5432/virtue")

# NullPool: create a fresh connection per session, close it immediately on session.close().
# This eliminates all connection-state pollution between requests (stale transactions,
# idle-in-transaction locks, pool exhaustion). The 1-3ms TCP overhead per request is
# negligible compared to 25s LLM calls.
# statement_timeout=30s: PostgreSQL kills any query that hangs >30s (e.g. lock waits),
# preventing the silent 5-minute nginx-timeout hang caused by an indefinite lock wait.
engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,
    connect_args={"options": "-c statement_timeout=30000"}  # 30s query timeout
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

