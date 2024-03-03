from enum import Enum


class CacheKeys(Enum):
    # to cache information for a particular organization
    ORG_ = "org_"

    # to cache information for a particular question with question_id
    QUESTION_ = "question_"

    # to cache a slice of the questions in a question set. The slice is defined by the skip and limit
    QUESTIONS_IN_QSET_ = "questions_in_qset_"
    _SKIP_ = "_skip_"
    _LIMIT_ = "_limit_"

    # to cache the quiz data for a particular quiz with quiz_id
    QUIZ_ = "quiz_"

    # to cache a particular session with session_id
    SESSION_ = "session_"

    # to cache the session_ids which were created in cache, and need to be inserted to db
    SESSION_ID_TO_INSERT_ = "session_id_to_insert_"

    # to cache the session_ids which were updated in cache, and need to be updated in db
    SESSION_ID_TO_UPDATE_ = "session_id_to_update_"

    # to cache the two latest session_ids for a user-quiz combo
    PREVIOUS_TWO_SESSION_IDS_ = "previous_two_session_ids_"

    # a key used as a lock. This lock is activated when a write back from cache to db is in progress.
    # When the lock is active, the webserver will not respond to any incoming requests.
    # When the write back succeeds or fails, the lock is deactivated.
    WRITE_BACK_LOCK = "write_back_lock"
