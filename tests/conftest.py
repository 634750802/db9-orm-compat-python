import os
import pytest

DSN = os.environ.get("PG_DSN", "postgresql://localhost:5433/postgres")


def get_dsn():
    return DSN


@pytest.fixture(scope="session")
def dsn():
    return DSN
