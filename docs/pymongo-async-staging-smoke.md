# PyMongo Async — Staging Smoke Checklist

Post-deployment validation for the PyMongo Async migration. Run these checks against the **testing** environment before promoting to production.

**Base URL:** `https://quiz-backend-testing.avantifellows.org`

---

## Prerequisites

- ECS task is running and healthy (ALB target group shows healthy targets)
- `MONGO_AUTH_CREDENTIALS` and `MONGO_DB_NAME` are set in the ECS task definition via Terraform

---

## 1. Health check (no DB)

```bash
curl -s https://quiz-backend-testing.avantifellows.org/health
```

**Expected:** `{"status":"healthy"}`

> **Note:** `/health` does not touch the database. It only confirms the FastAPI process is running and reachable through the ALB. A passing health check does **not** verify database connectivity.

---

## 2. Fail-fast lifespan behavior

The app lifespan runs `await _client.admin.command("ping")` at startup. If `MONGO_AUTH_CREDENTIALS` is invalid, DNS is unreachable, or the Atlas cluster is down, the ECS task will **fail to start** rather than serving requests that silently error on every DB call.

**How to verify:** If the task is running and healthy (step 1 passes), the lifespan ping succeeded.

---

## 3. Create organization (DB write + read)

```bash
curl -s -X POST https://quiz-backend-testing.avantifellows.org/organizations/ \
  -H "Content-Type: application/json" \
  -d '{"name": "Smoke Test Org"}'
```

**Expected:** 200 response with `name`, `key`, and `_id` fields. Save the `key` value for step 4.

---

## 4. Authenticate organization (DB read)

```bash
curl -s https://quiz-backend-testing.avantifellows.org/organizations/authenticate/{api_key}
```

Replace `{api_key}` with the `key` from step 3.

**Expected:** 200 response with the organization document.

---

## 5. Create quiz with questions (DB write, insert_many)

```bash
curl -s -X POST https://quiz-backend-testing.avantifellows.org/quiz \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Smoke Test Quiz",
    "question_sets": [
      {
        "questions": [
          {
            "text": "What is 2+2?",
            "type": "single-choice",
            "options": [
              {"text": "3"},
              {"text": "4"},
              {"text": "5"},
              {"text": "6"}
            ],
            "correct_answer": [1]
          }
        ]
      }
    ]
  }'
```

**Expected:** 200 response with `quiz_id`. Save it for step 6.

---

## 6. Create session (DB write + aggregation)

```bash
curl -s -X POST https://quiz-backend-testing.avantifellows.org/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "quiz_id": "{quiz_id}",
    "user_id": "smoke-test-user"
  }'
```

Replace `{quiz_id}` with the value from step 5.

**Expected:** 200 response with `session_id` and `session_answers`. Save `session_id` for step 7.

---

## 7. Submit answer (DB update)

```bash
curl -s -X PATCH https://quiz-backend-testing.avantifellows.org/session_answers/{session_id}/0 \
  -H "Content-Type: application/json" \
  -d '{
    "answer": [1],
    "visited": true,
    "time_spent": 5.0
  }'
```

Replace `{session_id}` with the value from step 6.

**Expected:** 200 response confirming the answer was recorded.

---

## Summary

| Step | Operation | DB pattern verified |
|------|-----------|-------------------|
| 1 | Health check | None (no DB) |
| 2 | Lifespan ping | `admin.command("ping")` at startup |
| 3 | Create org | `insert_one`, `find_one` |
| 4 | Auth org | `find_one` |
| 5 | Create quiz | `insert_one`, `insert_many`, `aggregate` |
| 6 | Create session | `insert_one`, `find_one`, `aggregate`, `find` |
| 7 | Submit answer | `update_one`, `find_one`, `aggregate` |

If all steps return expected responses, the async migration is working correctly in staging.
