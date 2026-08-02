import pytest

from .base import _assert_safe_test_database


@pytest.mark.parametrize(
    "uri",
    [
        "mongodb://localhost:27017",
        "mongodb://127.0.0.1:27017",
        "mongodb://[::1]:27017",
    ],
)
def test_allows_local_mongodb(uri):
    _assert_safe_test_database(uri)


def test_rejects_non_local_mongodb():
    with pytest.raises(RuntimeError, match="Refusing to reset a non-local MongoDB"):
        _assert_safe_test_database("mongodb://production.example.com:27017")
