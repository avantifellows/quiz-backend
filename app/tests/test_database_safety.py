import pytest

from .base import _assert_safe_test_database, _guard_db_name


@pytest.mark.parametrize(
    "uri",
    [
        "mongodb://localhost:27017",
        "mongodb://127.0.0.1:27017",
        "mongodb://[::1]:27017",
    ],
)
def test_allows_local_mongodb(uri, monkeypatch):
    monkeypatch.setenv("ALLOW_TEST_DATABASE_RESET", "1")
    _assert_safe_test_database(uri)


def test_requires_explicit_database_reset_opt_in(monkeypatch):
    monkeypatch.delenv("ALLOW_TEST_DATABASE_RESET", raising=False)
    with pytest.raises(RuntimeError, match="ALLOW_TEST_DATABASE_RESET=1"):
        _assert_safe_test_database("mongodb://localhost:27017")


def test_rejects_non_local_mongodb(monkeypatch):
    monkeypatch.setenv("ALLOW_TEST_DATABASE_RESET", "1")
    with pytest.raises(RuntimeError, match="Refusing to reset a non-local MongoDB"):
        _assert_safe_test_database("mongodb://production.example.com:27017")


def test_rejects_production_database_name():
    with pytest.raises(RuntimeError, match="production 'quiz' database"):
        _guard_db_name("quiz")
