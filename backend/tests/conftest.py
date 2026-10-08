import pytest

from dispatch_agent.db import connect


@pytest.fixture(scope="session")
def conn():
    conn = connect()
    yield conn
    conn.close()
