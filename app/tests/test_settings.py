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
