# PR #142 staging test results — 2026-09-17

**Result: do not enable caching yet.** Functional checks passed, but a controlled
Redis stall delayed a quiz request for 14.133 seconds. This fails the planned
five-second request deadline. The request eventually returned 200 and recovered;
it did not promptly fall back to MongoDB.

## Scope and deployed version

Only `quiz-backend-testing` in `ap-south-1` was changed. No production resources or
production configuration files were changed during this test run.

- PR head tested: `ac4234882e5581dcae46733a473c9fd5ee2ba9c2`.
- Deployed PR merge image: `9c7f3186da59a4e2920b3d6d9e544a9d669f6d23`.
- Staging revisions: 120 existing backend; 121 Redis installed/cache off;
  122 cache on; cache-disabled rollback initiated after the failed fault test.
- One ECS task, 1 vCPU, 2 GiB; same backend image throughout.
- Redis 7.2.5, nonessential sidecar, 64 MiB LRU cache, 128 MiB container limit.
- Namespace `pr142-staging-validation`; Redis pool limit 10 per backend worker.

The full Terraform plan contained an unrelated Cloudflare page-rule change. It
was not applied. Targeted saved plans were inspected and applied with changes
limited to the testing ECS task definition and service. Existing application
environment values were verified unchanged; the backend image was pinned.

The user's accepted freshness contract is unchanged: quiz/settings data can stay
stale until its one-hour TTL expires; organization authentication has a five-minute
TTL. Immediate invalidation was not required for this run.

## Passed

- Cache-off and cache-on timed quiz/homework flows, each with 63 HTTP requests:
  creation, loading, single/batch answers, heartbeat time updates, reopening with
  saved answers, resume, submission, known scoring, preflight and homework reveal.
- Normal answer-hidden reads remain hidden after answer-enabled reads, and vice
  versa, for quizzes and individual questions.
- Paginated question IDs/order/counts and answer hiding; cached empty lists.
- Full-page forms and normal/OMR mode isolation, including questions beyond the
  initial ten-question subset.
- Multi-set OMR option counts match full question data.
- Organization authentication returns the same result cold and warm.
- Actual Redis hit counters increased; quiz, question, question-list, organization
  and OMR cache entries were observed. TTLs were positive and within their intended
  one-hour/five-minute limits.
- A patched title stayed stale while cached, then refreshed from MongoDB after
  shortening only its fixture key's TTL and letting it expire. This verifies the
  expiry/refill mechanism, not a full one-hour soak.
- Malformed cached JSON fell back to MongoDB without an HTTP failure.
- Legacy fixture fields were repaired in MongoDB and subsequent reads agreed;
  `display_solution=false` remained respected.
- Deliberately invalid fixture indices/missing IDs and a synthetic broken OMR set
  returned the expected 400/404/500 errors. These were intentional negative tests.

All writes used synthetic test fixtures with tracked IDs. The destructive local
integration-test harness was not run against staging.

## Initial performance screen

Same one-task configuration, two fixed synthetic quizzes, 20 concurrent clients,
100 ms pacing per client and 60 seconds per mode, from the same local runner:

| Metric | Cache off | Cache on |
| --- | ---: | ---: |
| Successful requests | 5,543 | 5,602 |
| Unexpected errors | 0 | 0 |
| Requests/second | 92.38 | 93.37 |
| p50 | 93.86 ms | 90.49 ms |
| p95 | 253.45 ms | 254.47 ms |
| p99 | 371.72 ms | 451.06 ms |

A Redis snapshot after the tests showed 5,685 hits and 28 misses, around 1.42 MB
used memory and zero evictions. These counters include functional traffic as well
as the cache-on screen; they are not an isolated load-test hit-rate measurement.

This small screen does **not** demonstrate increased capacity or a significant
latency improvement. MongoDB read reduction was not directly measured. The longer,
repeated load matrix was stopped at the failed reliability gate; no production
capacity conclusions should be drawn.

## Failed reliability gate

Using ECS Exec on the staging backend, issue a finite `CLIENT PAUSE 15000 ALL`
against its local Redis, then request an already warmed quiz. No persistent Redis
configuration was changed; the pause ends automatically.

Observed: HTTP 200 after **14.133 seconds**. The next request succeeded normally.
The application waited for Redis to resume instead of reaching MongoDB promptly.

`app/cache.py` constructs its Redis client without explicit socket/connect timeouts,
and startup awaits Redis ping. Add bounded connection and command deadlines and
review retry behavior, then rerun the stalled-command and unavailable-startup
checks. Exception handling alone does not bound request latency.

## Not completed / remaining

Because the reliability gate failed, cache enablement is not signed off. The
multi-task/restart matrix, eviction pressure, unavailable-at-startup case, sidecar
termination/reconnect test, full one-hour soak, and sustained repeated load matrix
remain pending. A finite Redis pause is not equivalent to testing every failure
mode.

The earlier GitHub deployment job failed during verification because its IAM user
lacks `ecs:ListTasks` for staging. The image had deployed successfully. ECS state,
image, Redis and application behavior were verified directly for this run. The
workflow permission issue still needs a staging-scoped fix; no shared IAM policy
was modified here.

## Final state

Staging revision 123 has caching disabled and retains the tested #142 image and
healthy Redis sidecar. Verified existing sessions remain readable and a new
session can start, save an answer and submit after rollback. The replacement
Redis contains zero keys in the test namespace.

Exact-ID cleanup removed 9 synthetic sessions, 202 questions, 8 quizzes and 2
organizations. The old cache-on task drained; its ephemeral Redis was replaced.
No shared database collections or Redis databases were flushed.

Next: bound Redis connection/command waiting and retries, then rerun failure
checks before the deferred load/multi-task tests.
