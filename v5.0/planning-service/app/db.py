from contextlib import contextmanager
from typing import Any, Sequence

import psycopg
from psycopg.rows import dict_row

from app.config import settings


@contextmanager
def get_db():
    conn = psycopg.connect(settings.database_url, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()


def execute_parameterized(conn: psycopg.Connection, query: str, params: Sequence[Any] | None = None):
    """
    Enforce parameterized SQL execution pattern for safety.
    """
    if params is None:
        params = ()
    if "%s" not in query and len(params) > 0:
        raise ValueError("Parameterized query expected %s placeholders for supplied params.")
    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur
