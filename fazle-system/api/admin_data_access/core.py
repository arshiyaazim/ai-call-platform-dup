# ============================================================
# Admin Data Access — Core connection management
# Reuses the shared pool from database.py
# ============================================================
import logging
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

logger = logging.getLogger("fazle-api")

# Import the shared pool from database.py to avoid duplicate connections
from database import _pool

psycopg2.extras.register_uuid()


@contextmanager
def get_conn():
    """Get a connection from the shared pool."""
    conn = _pool.getconn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)


@contextmanager
def get_dict_cursor(conn=None):
    """Get a RealDictCursor, optionally from an existing connection."""
    if conn is not None:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
    else:
        with get_conn() as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                yield cur
                c.commit()
