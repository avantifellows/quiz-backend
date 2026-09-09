import os
import unittest

from settings import Settings


class TestSettings(unittest.TestCase):
    def test_no_mongo_fields_on_settings(self):
        """Settings must not contain Mongo fields; those belong in MongoSettings."""
        for field_name in Settings.model_fields:
            self.assertFalse(
                field_name.startswith("mongo_"),
                f"Settings.{field_name} starts with 'mongo_' — move it to MongoSettings",
            )


class TestLifespanTeardown(unittest.TestCase):
    """Verify that lifespan shutdown closes the async app client."""

    def test_lifespan_closes_async_client(self):
        os.environ["MONGO_DB_NAME"] = "quiz_test"
        import database
        from main import create_app
        from fastapi.testclient import TestClient

        app = create_app()
        with TestClient(app):
            # During lifespan, the client should be initialized
            self.assertIsNotNone(database._client)

        # After exiting the context, close_db() should have set _client to None
        self.assertIsNone(database._client)
