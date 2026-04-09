import unittest
from bson import ObjectId
from fastapi.encoders import jsonable_encoder
from ..models import Organization, QuestionSet
from ..main import app


class PyObjectIdValidationTestCase(unittest.TestCase):
    """Tests for PyObjectId validation via model_validate()"""

    def test_model_validate_from_string(self):
        """PyObjectId accepts a valid hex string via model_validate"""
        hex_str = "507f1f77bcf86cd799439011"
        org = Organization.model_validate({"_id": hex_str, "name": "Test Org"})
        self.assertIsInstance(org.id, ObjectId)
        self.assertEqual(str(org.id), hex_str)

    def test_model_validate_from_objectid(self):
        """PyObjectId accepts an ObjectId instance via model_validate"""
        oid = ObjectId("507f1f77bcf86cd799439011")
        org = Organization.model_validate({"_id": oid, "name": "Test Org"})
        self.assertIsInstance(org.id, ObjectId)
        self.assertEqual(org.id, oid)

    def test_model_validate_invalid_string_raises(self):
        """PyObjectId rejects invalid strings"""
        with self.assertRaises(Exception):
            Organization.model_validate({"_id": "not-valid", "name": "Test Org"})

    def test_default_factory_generates_valid_objectid(self):
        """Field(default_factory=PyObjectId) produces a valid ObjectId"""
        org = Organization(name="Test Org")
        self.assertIsInstance(org.id, ObjectId)
        self.assertTrue(ObjectId.is_valid(str(org.id)))

    def test_nested_questionset_id_from_string(self):
        """Nested QuestionSet._id validates from string"""
        hex_str = "507f1f77bcf86cd799439011"
        qs = QuestionSet.model_validate(
            {
                "_id": hex_str,
                "questions": [],
                "max_questions_allowed_to_attempt": 1,
            }
        )
        self.assertIsInstance(qs.id, ObjectId)
        self.assertEqual(str(qs.id), hex_str)


class PyObjectIdSerializationTestCase(unittest.TestCase):
    """Tests for PyObjectId JSON serialization"""

    def test_json_serialization_produces_string(self):
        """model_dump_json() serializes PyObjectId as a string"""
        hex_str = "507f1f77bcf86cd799439011"
        org = Organization.model_validate({"_id": hex_str, "name": "Test Org"})
        json_str = org.model_dump_json()
        self.assertIn(f'"{hex_str}"', json_str)

    def test_model_dump_json_mode_produces_string(self):
        """model_dump(mode='json') produces string id values"""
        hex_str = "507f1f77bcf86cd799439011"
        org = Organization.model_validate({"_id": hex_str, "name": "Test Org"})
        data = org.model_dump(mode="json")
        self.assertIsInstance(data["id"], str)
        self.assertEqual(data["id"], hex_str)

    def test_jsonable_encoder_produces_string_id(self):
        """jsonable_encoder() produces string _id (preserves v1 behavior)"""
        hex_str = "507f1f77bcf86cd799439011"
        org = Organization.model_validate({"_id": hex_str, "name": "Test Org"})
        encoded = jsonable_encoder(org)
        self.assertIn("_id", encoded)
        self.assertIsInstance(encoded["_id"], str)
        self.assertEqual(encoded["_id"], hex_str)

    def test_jsonable_encoder_nested_questionset_id(self):
        """jsonable_encoder() serializes nested QuestionSet._id as string"""
        qs_hex = "507f1f77bcf86cd799439011"
        q_hex = "607f1f77bcf86cd799439012"
        qs = QuestionSet.model_validate(
            {
                "_id": qs_hex,
                "questions": [
                    {
                        "_id": q_hex,
                        "text": "Test question",
                        "type": "single-choice",
                    }
                ],
                "max_questions_allowed_to_attempt": 1,
            }
        )
        encoded = jsonable_encoder(qs)
        self.assertIsInstance(encoded["_id"], str)
        self.assertEqual(encoded["_id"], qs_hex)
        self.assertIsInstance(encoded["questions"][0]["_id"], str)
        self.assertEqual(encoded["questions"][0]["_id"], q_hex)


class PyObjectIdOpenAPITestCase(unittest.TestCase):
    """Tests for PyObjectId OpenAPI schema output"""

    @classmethod
    def setUpClass(cls):
        cls.schema = app.openapi()

    def _get_model_id_schema(self, model_name):
        """Helper to extract the _id property schema for a model"""
        model_schema = self.schema["components"]["schemas"].get(model_name, {})
        return model_schema.get("properties", {}).get("_id", {})

    def test_organization_id_is_string_in_openapi(self):
        id_schema = self._get_model_id_schema("Organization")
        self.assertEqual(id_schema.get("type"), "string")

    def test_question_id_is_string_in_openapi(self):
        id_schema = self._get_model_id_schema("Question")
        self.assertEqual(id_schema.get("type"), "string")

    def test_session_id_is_string_in_openapi(self):
        id_schema = self._get_model_id_schema("Session")
        self.assertEqual(id_schema.get("type"), "string")

    def test_questionset_id_is_string_in_openapi(self):
        id_schema = self._get_model_id_schema("QuestionSet")
        self.assertEqual(id_schema.get("type"), "string")

    def test_session_answer_id_is_string_in_openapi(self):
        id_schema = self._get_model_id_schema("SessionAnswer")
        self.assertEqual(id_schema.get("type"), "string")
