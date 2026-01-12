import unittest
from datetime import datetime, timedelta

from ..routers.sessions import compute_total_time_spent_like_etl
from ..schemas import EventType


class SessionTimingUnitTests(unittest.TestCase):
    def test_compute_total_time_spent_returns_none_if_not_ended(self):
        t0 = datetime(2026, 1, 1, 12, 0, 0)
        events = [
            {
                "event_type": EventType.start_quiz,
                "created_at": t0,
                "updated_at": t0,
            }
        ]
        assert compute_total_time_spent_like_etl(events, has_quiz_ended=False) is None

    def test_compute_total_time_spent_returns_none_if_no_events(self):
        assert compute_total_time_spent_like_etl([], has_quiz_ended=True) is None

    def test_compute_total_time_spent_basic_dummy_then_end(self):
        """
        Timeline:
        - start at t0
        - dummy window from t1..t2
        - end at t3
        ETL math should sum to (t3 - t0) seconds.
        """
        t0 = datetime(2026, 1, 1, 12, 0, 0)
        t1 = t0 + timedelta(seconds=10)
        t2 = t0 + timedelta(seconds=40)  # dummy extended to here
        t3 = t0 + timedelta(seconds=55)  # end

        events = [
            {"event_type": EventType.start_quiz, "created_at": t0, "updated_at": t0},
            {"event_type": EventType.dummy_event, "created_at": t1, "updated_at": t2},
            {"event_type": EventType.end_quiz, "created_at": t3, "updated_at": t3},
        ]

        assert compute_total_time_spent_like_etl(events, has_quiz_ended=True) == 55

    def test_compute_total_time_spent_multiple_dummies(self):
        """
        Two dummy windows before end. This validates the loop logic doesn't crash and
        returns a sensible int.
        """
        t0 = datetime(2026, 1, 1, 12, 0, 0)
        t1 = t0 + timedelta(seconds=5)
        t2 = t0 + timedelta(seconds=15)
        t3 = t0 + timedelta(seconds=20)
        t4 = t0 + timedelta(seconds=35)
        t5 = t0 + timedelta(seconds=40)

        events = [
            {"event_type": EventType.start_quiz, "created_at": t0, "updated_at": t0},
            {"event_type": EventType.dummy_event, "created_at": t1, "updated_at": t2},
            {"event_type": EventType.dummy_event, "created_at": t3, "updated_at": t4},
            {"event_type": EventType.end_quiz, "created_at": t5, "updated_at": t5},
        ]

        out = compute_total_time_spent_like_etl(events, has_quiz_ended=True)
        assert isinstance(out, int)
        assert out == 40
