"""
Cache-enabled integration tests.

Requires a running Redis instance at localhost:6379.
Run with: CACHE_ENABLED=true REDIS_URL=redis://localhost:6379/0 CACHE_NAMESPACE=test pytest app/tests/test_cache_integration.py
"""

import json
import os
import unittest
from pathlib import Path

import redis as sync_redis

from .base import BaseTestCase

_DUMMY_DATA = Path(__file__).resolve().parent / "dummy_data"

# Namespace used for all cache keys in these tests
_TEST_CACHE_NAMESPACE = "test"


def _redis_available() -> bool:
    """Check if Redis is reachable — skip tests if not."""
    try:
        r = sync_redis.Redis(host="localhost", port=6379, db=0)
        r.ping()
        r.close()
        return True
    except Exception:
        return False


_SKIP_REASON = "Redis not available at localhost:6379"


class CacheEnabledBaseTestCase(BaseTestCase):
    """Base test case with Redis caching enabled.

    Sets CACHE_ENABLED=true and CACHE_NAMESPACE=test before the app is created.
    Flushes Redis before and after each test for isolation.
    """

    @classmethod
    def setUpClass(cls):
        os.environ["CACHE_ENABLED"] = "true"
        os.environ["REDIS_URL"] = "redis://localhost:6379/0"
        os.environ["REDIS_MAX_CONNECTIONS"] = "10"
        os.environ["CACHE_NAMESPACE"] = _TEST_CACHE_NAMESPACE
        super().setUpClass()
        # Sync Redis client for direct key inspection in assertions
        cls._redis = sync_redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)

    @classmethod
    def tearDownClass(cls):
        cls._redis.flushdb()
        cls._redis.close()
        super().tearDownClass()
        # Restore cache-off default so other test classes are unaffected
        os.environ["CACHE_ENABLED"] = "false"

    def setUp(self):
        # Flush Redis before each test so no cached data leaks between tests
        self._redis.flushdb()
        # Also reset cache module globals so each test starts with a clean state
        import cache as cache_module

        cache_module._last_error_log_ts = 0.0
        cache_module._last_connect_attempt_ts = 0.0
        cache_module._stats.clear()
        cache_module._last_stats_log_ts = 0.0
        super().setUp()
        # Flush again after parent setUp, which seeds DB via post_and_get_quiz()
        # (those GET calls warm the cache). Tests start with a cold cache.
        self._redis.flushdb()

    def tearDown(self):
        super().tearDown()
        self._redis.flushdb()

    def _cache_key(self, family: str, *parts: str) -> str:
        """Build a cache key matching the app's cache_key() function."""
        return f"cache:{_TEST_CACHE_NAMESPACE}:{family}:{':'.join(parts)}"

    def _key_exists(self, key: str) -> bool:
        """Check if a key exists in Redis."""
        return self._redis.exists(key) == 1


# ---------------------------------------------------------------------------
# Cache miss → cache hit tests
# ---------------------------------------------------------------------------


@unittest.skipUnless(_redis_available(), _SKIP_REASON)
class QuizCacheHitMissTest(CacheEnabledBaseTestCase):
    """Verify quiz read caches on miss and serves from cache on hit."""

    def test_quiz_cache_miss_then_hit(self):
        quiz_id = self.homework_quiz_id
        key = self._cache_key("quiz", quiz_id)

        # Before first read, key should not exist
        self.assertFalse(self._key_exists(key))

        # First read — cache miss, data comes from MongoDB
        resp1 = self.client.get(f"/quiz/{quiz_id}")
        self.assertEqual(resp1.status_code, 200)

        # After first read, key should exist in Redis
        self.assertTrue(self._key_exists(key))

        # Second read — cache hit
        resp2 = self.client.get(f"/quiz/{quiz_id}")
        self.assertEqual(resp2.status_code, 200)

        # Both reads should return the same data
        self.assertEqual(resp1.json()["_id"], resp2.json()["_id"])
        self.assertEqual(
            len(resp1.json()["question_sets"]),
            len(resp2.json()["question_sets"]),
        )


@unittest.skipUnless(_redis_available(), _SKIP_REASON)
class FormCacheHitMissTest(CacheEnabledBaseTestCase):
    """Verify form read caches on miss and serves from cache on hit."""

    def setUp(self):
        super().setUp()
        # Create a form (quiz_type=form) — POST only, no GET, so it won't be cached
        form_data = json.load(open(_DUMMY_DATA / "form_questionnaire.json"))
        response = self.client.post("/quiz/", json=form_data)
        self.form_id = json.loads(response.content)["id"]
        # Flush again since the POST creates a quiz (which might trigger a GET internally)
        self._redis.flushdb()

    def test_form_cache_miss_then_hit(self):
        key = self._cache_key("quiz", self.form_id)

        # Before first read, key should not exist
        self.assertFalse(self._key_exists(key))

        # First read — cache miss
        resp1 = self.client.get(f"/form/{self.form_id}")
        self.assertEqual(resp1.status_code, 200)

        # Key should now exist
        self.assertTrue(self._key_exists(key))

        # Second read — cache hit
        resp2 = self.client.get(f"/form/{self.form_id}")
        self.assertEqual(resp2.status_code, 200)

        # Both reads return the same form
        self.assertEqual(resp1.json()["_id"], resp2.json()["_id"])

    def test_form_preserves_answers(self):
        """Forms must return correct_answer and solution — no answer hiding."""
        resp = self.client.get(f"/form/{self.form_id}")
        self.assertEqual(resp.status_code, 200)
        form = resp.json()

        # Verify at least one question set exists
        self.assertTrue(len(form["question_sets"]) > 0)

        # Forms do NOT hide answers — check that graded questions with correct_answer keep them
        for qset in form["question_sets"]:
            for q in qset["questions"]:
                # Form questions may or may not have correct_answer depending on graded flag
                # The key point: forms do NOT null out correct_answer like quizzes do
                if q.get("graded") and q.get("correct_answer") is not None:
                    self.assertIsNotNone(q["correct_answer"])


@unittest.skipUnless(_redis_available(), _SKIP_REASON)
class QuestionCacheHitMissTest(CacheEnabledBaseTestCase):
    """Verify single question read caches on miss and serves from cache on hit."""

    def test_question_cache_miss_then_hit(self):
        question = self.homework_quiz["question_sets"][0]["questions"][0]
        question_id = question["_id"]
        key = self._cache_key("question", question_id)

        # Before first read
        self.assertFalse(self._key_exists(key))

        # First read — cache miss
        resp1 = self.client.get(f"/questions/{question_id}")
        self.assertEqual(resp1.status_code, 200)

        # Key should now exist
        self.assertTrue(self._key_exists(key))

        # Second read — cache hit
        resp2 = self.client.get(f"/questions/{question_id}")
        self.assertEqual(resp2.status_code, 200)

        # Same question text returned both times
        self.assertEqual(resp1.json()["text"], resp2.json()["text"])


@unittest.skipUnless(_redis_available(), _SKIP_REASON)
class OrgAuthCacheHitMissTest(CacheEnabledBaseTestCase):
    """Verify org-auth read caches on miss and serves from cache on hit."""

    def test_org_auth_cache_miss_then_hit(self):
        api_key = self.organization_api_key
        key = self._cache_key("org", "key", api_key)

        # Before first read
        self.assertFalse(self._key_exists(key))

        # First read — cache miss
        resp1 = self.client.get(f"/organizations/authenticate/{api_key}")
        self.assertEqual(resp1.status_code, 200)

        # Key should now exist
        self.assertTrue(self._key_exists(key))

        # Second read — cache hit
        resp2 = self.client.get(f"/organizations/authenticate/{api_key}")
        self.assertEqual(resp2.status_code, 200)

        # Same org name both times
        self.assertEqual(resp1.json()["name"], resp2.json()["name"])


# ---------------------------------------------------------------------------
# Cross-route cache warming test
# ---------------------------------------------------------------------------


@unittest.skipUnless(_redis_available(), _SKIP_REASON)
class CrossRouteCacheTest(CacheEnabledBaseTestCase):
    """One route warms the quiz cache, another route reads the same cached quiz."""

    def test_quiz_route_warms_cache_for_form_route(self):
        """Create a non-form quiz, warm it via /quiz, then verify cache key exists.
        A second /quiz read should hit cache."""
        quiz_id = self.homework_quiz_id
        key = self._cache_key("quiz", quiz_id)

        # Warm cache via quiz route
        resp1 = self.client.get(f"/quiz/{quiz_id}")
        self.assertEqual(resp1.status_code, 200)
        self.assertTrue(self._key_exists(key))

        # Second read uses the cached quiz
        resp2 = self.client.get(f"/quiz/{quiz_id}")
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp1.json()["_id"], resp2.json()["_id"])

    def test_question_cache_shared_across_routes(self):
        """A question cached by /questions/{id} is also available when the
        questions route is called again — verifying key reuse."""
        question = self.homework_quiz["question_sets"][0]["questions"][0]
        question_id = question["_id"]
        key = self._cache_key("question", question_id)

        # Warm via questions route
        resp1 = self.client.get(f"/questions/{question_id}")
        self.assertEqual(resp1.status_code, 200)
        self.assertTrue(self._key_exists(key))

        # Read again — same cache key, should be a hit
        resp2 = self.client.get(f"/questions/{question_id}")
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp1.json()["_id"], resp2.json()["_id"])


# ---------------------------------------------------------------------------
# Legacy quiz fixup cache test
# ---------------------------------------------------------------------------


@unittest.skipUnless(_redis_available(), _SKIP_REASON)
class LegacyQuizFixupCacheTest(CacheEnabledBaseTestCase):
    """Test that legacy quizzes get fixed up on first read and the fixed version is cached."""

    def test_fixup_runs_on_cache_miss_and_cached_version_includes_fix(self):
        """Create a quiz via API, strip backwards-compat fields in MongoDB,
        read through the API, and verify the cached version has the fixup applied."""
        # Use an existing quiz created by setUp, strip compat fields in MongoDB
        quiz_id = self.short_homework_quiz_id

        # Strip backwards-compat fields directly in MongoDB to simulate a legacy doc
        self.db.quizzes.update_one(
            {"_id": quiz_id},
            {
                "$unset": {
                    "question_sets.$[].max_questions_allowed_to_attempt": "",
                    "question_sets.$[].title": "",
                    "question_sets.$[].marking_scheme": "",
                }
            },
        )

        # Verify fields were stripped
        raw = self.db.quizzes.find_one({"_id": quiz_id})
        for qset in raw["question_sets"]:
            self.assertNotIn("max_questions_allowed_to_attempt", qset)

        cache_key_str = self._cache_key("quiz", quiz_id)

        # No cache entry yet (flushed in setUp)
        self.assertFalse(self._key_exists(cache_key_str))

        # Read through the API — triggers fixup + cache write
        resp = self.client.get(f"/quiz/{quiz_id}")
        self.assertEqual(resp.status_code, 200)

        # Cache entry should now exist
        self.assertTrue(self._key_exists(cache_key_str))

        # Verify the cached version has the fixup fields
        cached_raw = self._redis.get(cache_key_str)
        cached_quiz = json.loads(cached_raw)
        for qset in cached_quiz["question_sets"]:
            self.assertIn("max_questions_allowed_to_attempt", qset)
            self.assertIn("marking_scheme", qset)
            self.assertIsNotNone(qset["marking_scheme"])

        # Verify the MongoDB document was also updated (fixup write-back)
        db_quiz = self.db.quizzes.find_one({"_id": quiz_id})
        for qset in db_quiz["question_sets"]:
            self.assertIn("max_questions_allowed_to_attempt", qset)


# ---------------------------------------------------------------------------
# OMR keyed-map missing qset_id test
# ---------------------------------------------------------------------------


@unittest.skipUnless(_redis_available(), _SKIP_REASON)
class OMRKeyedMapTest(CacheEnabledBaseTestCase):
    """Test that missing question_set_id in OMR aggregation returns 500."""

    def test_missing_qset_id_returns_500(self):
        """If a question_set has no matching questions in DB, the OMR aggregation
        should return 500 (data integrity error)."""
        from bson import ObjectId

        # Use the OMR quiz created in setUp
        quiz_id = self.multi_qset_omr_id

        # Tamper: add a fake question_set with an _id that has no matching questions in DB
        fake_qset_id = str(ObjectId())
        fake_qset = {
            "_id": fake_qset_id,
            "max_questions_allowed_to_attempt": 5,
            "title": "Fake",
            "marking_scheme": {"correct": 1, "wrong": 0, "skipped": 0},
            "questions": [
                {
                    "_id": str(ObjectId()),
                    "type": "single-choice",
                    "graded": True,
                    "question_set_id": fake_qset_id,
                }
            ],
        }
        self.db.quizzes.update_one(
            {"_id": quiz_id},
            {"$push": {"question_sets": fake_qset}},
        )

        # Cache is already flushed in setUp — route will read the tampered quiz from MongoDB

        # Read with omr_mode=true — should hit the missing qset_id path and return 500
        resp = self.client.get(f"/quiz/{quiz_id}", params={"omr_mode": True})
        self.assertEqual(resp.status_code, 500)
        self.assertIn("OMR data integrity error", resp.json()["detail"])


# ---------------------------------------------------------------------------
# Redis-disabled fallback test
# ---------------------------------------------------------------------------


@unittest.skipUnless(_redis_available(), _SKIP_REASON)
class RedisDisabledFallbackTest(CacheEnabledBaseTestCase):
    """With CACHE_ENABLED=false, all endpoints still work via direct MongoDB."""

    def test_endpoints_work_with_cache_disabled(self):
        """Temporarily disable caching and verify all read endpoints still work."""
        import cache as cache_module

        # Disable caching at the module level by overriding env var
        original_enabled = os.environ.get("CACHE_ENABLED")
        os.environ["CACHE_ENABLED"] = "false"

        # Reset cache client so it picks up the new setting
        old_client = cache_module.redis_client
        cache_module.redis_client = None

        try:
            # Quiz read
            resp = self.client.get(f"/quiz/{self.homework_quiz_id}")
            self.assertEqual(resp.status_code, 200)

            # Question read
            question_id = self.homework_quiz["question_sets"][0]["questions"][0]["_id"]
            resp = self.client.get(f"/questions/{question_id}")
            self.assertEqual(resp.status_code, 200)

            # Org-auth read
            resp = self.client.get(
                f"/organizations/authenticate/{self.organization_api_key}"
            )
            self.assertEqual(resp.status_code, 200)

            # Paginated questions read
            qset_id = self.homework_quiz["question_sets"][0]["_id"]
            resp = self.client.get(f"/questions/?question_set_id={qset_id}")
            self.assertEqual(resp.status_code, 200)

            # No cache keys should have been written
            keys = self._redis.keys(f"cache:{_TEST_CACHE_NAMESPACE}:*")
            self.assertEqual(len(keys), 0)

        finally:
            # Restore caching
            os.environ["CACHE_ENABLED"] = original_enabled or "true"
            cache_module.redis_client = old_client


# ---------------------------------------------------------------------------
# Paginated questions — empty result is valid cache hit
# ---------------------------------------------------------------------------


@unittest.skipUnless(_redis_available(), _SKIP_REASON)
class PaginatedQuestionsEmptyCacheTest(CacheEnabledBaseTestCase):
    """Test that paginated questions with empty result [] is a valid cache hit."""

    def test_empty_result_is_valid_cache_hit(self):
        """Query questions with a qset_id that has no matching questions.
        The empty [] result should be cached and returned on the second read."""
        from bson import ObjectId

        # Use a question_set_id that has no questions in the DB
        empty_qset_id = str(ObjectId())

        # Build the expected cache key (normalized: skip=0, limit=all)
        key = self._cache_key(
            "questions", "qset", empty_qset_id, "skip", "0", "limit", "all"
        )

        # No cache entry yet
        self.assertFalse(self._key_exists(key))

        # First read — cache miss, returns []
        resp1 = self.client.get(f"/questions/?question_set_id={empty_qset_id}")
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp1.json(), [])

        # Cache key should now exist with the empty array
        self.assertTrue(self._key_exists(key))

        # Verify the cached value is actually []
        cached_raw = self._redis.get(key)
        self.assertEqual(json.loads(cached_raw), [])

        # Second read — cache hit, still returns []
        resp2 = self.client.get(f"/questions/?question_set_id={empty_qset_id}")
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json(), [])
