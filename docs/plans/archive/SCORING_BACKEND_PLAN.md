description
Backend scoring as the single source of truth, computed on end-quiz and returned to the frontend.

author [surya]

context & problem description
- Frontend currently computes score at end-quiz and sends metrics to backend.
- In poor network conditions, some answers are not synced before end-quiz.
- Result: frontend score (stored in metrics) mismatches backend/ETL recomputation.
- Requirement: backend should be the source of truth for score computation, without major model changes.
- Homework quizzes must still show correct answers immediately (frontend still needs question data).

solution(s) [with rejected ones too]
- Accepted: recompute metrics on backend only at end-quiz.
  - Frontend stops sending metrics, sends a final batch of answers, then reads server metrics.
  - Backend ignores client metrics and stores server-computed metrics.
  - Return metrics in end-quiz response to avoid extra GET.
- Rejected: incremental per-answer scoring on backend.
  - Higher complexity and cost; not needed if UI only needs end-quiz score.
- Rejected: keep frontend scoring and "trust" last known metrics.
  - Does not fix mismatches from missing answers.

implementation spec
Backend (quiz-backend)
- Add scoring helper (e.g., app/services/scoring.py) to compute SessionMetrics:
  - Inputs: session, quiz (question_sets), session_answers.
  - Output: SessionMetrics (qset_metrics + totals).
  - Use question_set.marking_scheme (ETL-aligned).
  - Logic mirrors frontend and ETL mapping in etl-data-flow/flows/quizzes/lambda_function.py.
- Update PATCH /sessions/{session_id} (app/routers/sessions.py):
  - On end-quiz: ignore incoming metrics, recompute and store metrics, set has_quiz_ended.
  - If has_quiz_ended is already true, skip recomputation.
  - Return computed metrics in response for end-quiz.
- No schema changes required if SessionResponse already includes metrics.
- Form quizzes: compute basic counts only (num_answered/num_skipped), avoid scoring.

Frontend (quiz-frontend)
- Remove client-side score computation and metrics payload generation.
- Stop sending metrics in SessionAPIService.updateSession.
- Before end-quiz, send a final batch of answers via update-multiple-answers (send all answers once).
  - If batch fails, block end-quiz and show retry toast.
- After end-quiz succeeds:
  - Use metrics from end-quiz response; fallback to GET /sessions/{id} if response omits metrics.
  - Map backend metrics to UI state for Scorecard.
  - Show a "computing score" state while waiting.
  - Keep answer-evaluation helpers only where needed for immediate feedback UI (homework), not for scoring.

Scoring rules (must match frontend)
- Answer evaluation:
  - invalid format for choice/matrix-match (number) => answered, incorrect
  - numerical-integer: exact match; numerical-float: tolerance 0.05
  - multi-choice/matrix-match: subset counts as partially correct when partial marking exists
  - subjective/matrix-subjective: non-empty response counts as correct
  - ungraded: valid=false; do not contribute to counts
- Marks:
  - correct/wrong/skipped from question_set.marking_scheme
  - partial marks via marking_scheme.partial rules (num_correct_selected)
- Counts:
  - per-qset: num_answered, num_skipped, num_correct, num_wrong, num_partially_correct, num_marked_for_review
  - totals: sum across qsets
  - attempt_rate = num_answered / max_questions_allowed_to_attempt
  - accuracy_rate = (num_correct + 0.5 * num_partially_correct) / num_answered
- Optional + ungraded:
  - max_questions_allowed_to_attempt is reduced by ungraded questions, like current frontend logic.

Backward compatibility
- Old clients may send metrics; backend ignores and overwrites with server-computed values.
- Sessions without metrics remain valid; metrics are computed only on end-quiz.
- Review flows (has_quiz_ended true) should use stored metrics; if metrics are missing, compute once on-demand and persist.
- ETL remains the analytics source of truth; session metrics are for UI only.

status [proposed]

consequences [positive and negative and neutral]
positive
- Eliminates score mismatches from missing answer sync.
- Centralizes scoring logic on backend, aligned with ETL.
- Simplifies frontend scoring logic and reduces client trust.

negative
- End-quiz request may take longer due to server computation.
- Requires additional backend code and tests to mirror frontend logic.

neutral
- Homework immediate feedback remains frontend-only and unchanged.
- ETL flow continues to recompute independently.
