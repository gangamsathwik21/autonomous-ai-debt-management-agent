import pytest

import backend.database as database


@pytest.fixture
def test_database(tmp_path, monkeypatch):
    """
    Creates an isolated temporary SQLite database for each test.
    The project's actual customers.db is never modified.
    """
    test_db_path = tmp_path / "test_customers.db"

    monkeypatch.setattr(
        database,
        "DATABASE_PATH",
        str(test_db_path)
    )

    database.initialize_database()

    return database