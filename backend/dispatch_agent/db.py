import sqlite3

from dispatch_agent.config import DB_PATH


def connect(path=DB_PATH):
    """Open the provider database read-only, with rows accessible by column name."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn
