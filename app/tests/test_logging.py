import logging
import unittest
from unittest.mock import patch

from .base import BaseTestCase, SessionsBaseTestCase
from logger_config import ISTFormatter, _log_level, setup_logger
from routers import organizations, session_answers, sessions
from schemas import EventType

LOGGER = "quizenginelogger"


def _messages(cm, level=None):
    return [r.getMessage() for r in cm.records if level is None or r.levelno == level]


class LoggerConfigTestCase(unittest.TestCase):
    def test_log_level_defaults_to_info(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(_log_level(), logging.INFO)

    def test_log_level_from_env(self):
        for value, expected in [
            ("DEBUG", logging.DEBUG),
            ("warning", logging.WARNING),
            (" error ", logging.ERROR),
            ("nonsense", logging.INFO),
        ]:
            with patch.dict("os.environ", {"LOG_LEVEL": value}):
                self.assertEqual(_log_level(), expected, value)

    def test_formatter_keeps_records_on_one_line(self):
        formatter = ISTFormatter(fmt="%(message)s")
        record = logging.LogRecord(
            LOGGER, logging.INFO, __file__, 1, "a\nforged\r\nline", None, None
        )
        self.assertEqual(formatter.format(record), "a\\nforged\\r\\nline")

    def test_format_has_no_duplicate_call_trace(self):
        formatter = setup_logger().handlers[0].formatter
        self.assertNotIn("call_trace", formatter._fmt)


class RequestLoggingTestCase(BaseTestCase):
    def test_one_line_per_request_without_headers(self):
        with self.assertLogs(LOGGER, level=logging.DEBUG) as cm:
            self.client.get(
                f"/quiz/{self.short_homework_quiz['_id']}",
                headers={"x-forwarded-for": "203.0.113.7", "user-agent": "probe/1.0"},
            )
        request_lines = [m for m in _messages(cm) if m.startswith("rid=")]
        self.assertEqual(len(request_lines), 1, request_lines)
        line = request_lines[0]
        self.assertIn("path=/quiz/", line)
        self.assertIn("method=GET", line)
        self.assertIn("status_code=200", line)
        self.assertIn("completed_in=", line)
        joined = "\n".join(_messages(cm))
        self.assertNotIn("headers=", joined)
        self.assertNotIn("203.0.113.7", joined)
        self.assertNotIn("probe/1.0", joined)

    def test_health_checks_are_not_logged(self):
        with self.assertNoLogs(LOGGER, level=logging.DEBUG):
            response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)


class ApiKeyLoggingTestCase(BaseTestCase):
    def test_api_keys_never_logged(self):
        with self.assertLogs(LOGGER, level=logging.DEBUG) as cm:
            created = self.client.post(
                organizations.router.prefix + "/", json={"name": "Log Test Org"}
            ).json()
            new_key = created["key"]
            self.client.get(f"{organizations.router.prefix}/authenticate/{new_key}")
            self.client.get(
                f"{organizations.router.prefix}/authenticate/{self.organization_api_key}"
            )
            self.client.get(
                f"{organizations.router.prefix}/authenticate/NotARealKeyAtAll1234"
            )
        joined = "\n".join(_messages(cm))
        for secret in (new_key, self.organization_api_key, "NotARealKeyAtAll1234"):
            self.assertNotIn(secret, joined)
        # the failed lookup is still visible, just masked, and the request line redacts the key
        self.assertIn("Failed to authenticate API key: NotA…(len=20)", joined)
        self.assertIn("path=/organizations/authenticate/<redacted>", joined)


class HotPathLoggingTestCase(SessionsBaseTestCase):
    def test_answer_update_details_are_debug_only(self):
        session_id = self.homework_session["_id"]
        with self.assertLogs(LOGGER, level=logging.DEBUG) as cm:
            response = self.client.patch(
                f"{session_answers.router.prefix}/{session_id}/0",
                json={"answer": [0, 1], "time_spent": 14},
            )
        self.assertEqual(response.status_code, 200)
        info = _messages(cm, logging.INFO)
        # at INFO only the single request line remains
        self.assertEqual(len(info), 1, info)
        self.assertTrue(info[0].startswith("rid="))
        debug = _messages(cm, logging.DEBUG)
        self.assertTrue(any("Updating session answer" in m for m in debug))
        self.assertTrue(any("Updated session answer" in m for m in debug))

    def test_heartbeat_events_debug_real_events_info(self):
        session_id = self.homework_session["_id"]
        url = f"{sessions.router.prefix}/{session_id}"

        with self.assertLogs(LOGGER, level=logging.DEBUG) as start_cm:
            self.client.patch(url, json={"event": EventType.start_quiz.value})
        self.assertTrue(
            any(
                "Updating session with id" in m
                for m in _messages(start_cm, logging.INFO)
            )
        )

        with self.assertLogs(LOGGER, level=logging.DEBUG) as dummy_cm:
            response = self.client.patch(
                url, json={"event": EventType.dummy_event.value}
            )
        self.assertEqual(response.status_code, 200)
        info = [
            m for m in _messages(dummy_cm, logging.INFO) if not m.startswith("rid=")
        ]
        self.assertEqual(info, [])
        debug = _messages(dummy_cm, logging.DEBUG)
        self.assertTrue(any("Updating session with id" in m for m in debug))
        self.assertTrue(any("Updated session with id" in m for m in debug))
