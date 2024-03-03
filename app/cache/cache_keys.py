from enum import Enum

class CacheKeys(Enum):
  ORG_ = "org_"
  QUESTION_ = "question_"
  QUESTIONS_IN_QSET_ = "questions_in_qset_"
  _SKIP_ = "_skip_"
  _LIMIT_ = "_limit_"
  QUIZ_ = "quiz_"
  SESSION_ = "session_"
  SESSION_ID_TO_INSERT_ = "session_id_to_insert_"
  SESSION_ID_TO_UPDATE_ = "session_id_to_update_"
  PREVIOUS_TWO_SESSION_IDS_ = "previous_two_session_ids_"
  WRITE_BACK_LOCK = "write_back_lock"