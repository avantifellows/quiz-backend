# PR #142 staging test plan — Local Redis caching

Prepared 2026-09-17 for `redis-caching` at `9d1d5d0`, based on `main` at `ed0ea69`.
Target: https://quiz-backend-testing.avantifellows.org
Status: plan only; the tests below have not yet been executed for #142.

## Objective and release gate

Prove that caching preserves quiz behavior, actually reduces repeated MongoDB reads, and recovers safely when Redis is unavailable. Functional checks alone do not establish a capacity improvement.

Pass requires all correctness cases below, cache-hit evidence for every cache family, bounded Redis failure behavior, successful recovery/rollback, and repeatable performance results. The user accepts up to one hour of stale quiz/settings data (five minutes for organization authentication). Verify refresh after expiry; do not require immediate invalidation. Answer leakage, scores inconsistent with the cached version, lost answers, or indefinite startup/request hangs block enabling caching. Report failed or unavailable checks explicitly.

## Findings that shape the plan

- The latest registered testing task definition inspected is revision 119, image `ed0ea69`, with only the backend container and no cache settings. Verify the actual service/task revision again before execution.
- The normal deployment workflow replaces the backend image in the existing task definition. It does not apply Terraform or add the Redis sidecar. An image-only deployment is insufficient to exercise this PR's cache.
- The PR adds one Redis sidecar per ECS task: nonessential, 128 MiB container limit, 64 MiB cache, `allkeys-lru`. Cache defaults to disabled. Pools default to 10 Redis connections per worker; quiz/question/OMR entries use a 3,600-second TTL; organization authentication uses 300 seconds.
- There is no cache invalidation. Quiz PATCH and CMS updates write MongoDB but do not clear cached quiz/question data. Even supported settings such as `shuffle`, `show_scores`, and `review_immediate` need explicit freshness checks. A code comment permitting settings edits is not evidence that they stay fresh.
- Redis initialization is awaited at startup. No explicit socket/connect timeout is configured in `app/cache.py`. Test both connection refusal and a connection that stalls; exception handling alone does not prove prompt fallback.
- Existing cache integration tests flush Redis and the test harness clears its MongoDB database. Do not point that harness at staging. Use dedicated HTTP fixtures and exact-ID cleanup.

## 1. Setup, baseline, and deployment

1. Record service/task revision, backend image SHA, desired task count, worker count, resource limits, MongoDB target, and relevant cache settings. Keep credentials out of reports. Save the known-good task definition for rollback.
2. Establish access to each Redis sidecar through ECS Exec or equivalent restricted access. Do not expose Redis publicly. Without per-task cache inspection, report hit/TTL/eviction tests as blocked rather than inferring success from HTTP 200s.
3. Create uniquely tagged synthetic fixtures: timed assessment, homework, form, multi-set OMR, mixed question types, and an organization. Include more than 10 questions per set to exercise full-question hydration, varied option counts, correct answers, solutions, and known scores. Track every created ID and cache key.
4. Capture a baseline on #141/current main before changing the image. Use only these fixtures.
5. Install the testing Redis sidecar and cache settings through a reviewed, testing-only task-definition/Terraform change. Review any Terraform plan for unrelated changes; do not apply production changes. Confirm total task resource capacity and Redis health.
6. Deploy #142 with `CACHE_ENABLED=false`; verify the exact image/commit on running tasks and repeat the functional baseline.
7. Enable `CACHE_ENABLED=true`, `REDIS_URL=redis://localhost:6379/0`, `REDIS_MAX_CONNECTIONS=10`, and a unique run namespace such as `pr142-staging-<run-id>`. Wait for a stable rollout. Verify the sidecar is healthy and cache keys appear after reads.

## 2. Functional and cache test matrix

Run the primary flows with cache off, cold, and warm. Compare normalized response bodies and scores; ignore only generated IDs/timestamps and intentionally changing timing values.

| Case | Steps and expected evidence |
| --- | --- |
| Quiz and form caching | Read `/quiz/{id}` and `/form/{id}` twice. Verify first-miss/second-hit evidence and identical content. Wrong quiz/form route must still return 404. |
| Single question and organization | Repeat `/questions/{id}` and organization authentication. Verify `question` and `org` keys/hits and stable results; invalid credentials and missing IDs retain expected errors. Do not log organization API keys. |
| Paginated questions | Vary question-set ID, skip, and limit; compare IDs/order/counts against cache-off results. Verify separate page keys, equivalent default/zero paging, and cached empty lists. |
| Full-question rendering | Alternate regular and `single_page_mode=true` reads on quizzes/forms with >10 questions. Full text/options must remain complete, and regular responses must retain their intended shape. Verify full-set `questions` keys. |
| Answer/solution isolation | Alternate `include_answers=true` and false in both orders for quiz, individual question, and paginated routes. Normal responses must hide answers; answer-enabled responses retain them. Repeat with `display_solution=false`. Inspect canonical cache data without copying answer payloads into general logs. |
| OMR | Multi-set fixtures with varied option counts, numerical/subjective questions, and >10 questions per set. Alternate normal/OMR/full-page modes. Verify keyed set mapping, correct placeholder counts, and `omr_options` hits. Use a deliberately broken synthetic set to verify the expected integrity error. |
| Session lifecycle | Start, save a single answer, batch-save, heartbeat with time updates, reopen/resume, and submit. Verify persistence, timing, expected scores, preflight state, and homework reveal rules. Repeat while other requests warm/hide quiz and question answers. Session state must stay fresh in MongoDB. |
| Concurrent users | Run independent synthetic users on one quiz. Verify no answer/session cross-contamination, correct scores, and no lost writes. Include simultaneous cold-cache reads to detect duplicate-load spikes. |
| Legacy documents | Remove compatibility fields only from a tracked synthetic quiz. First read must repair MongoDB and cache the repaired document; subsequent reads must agree. Do not run the repository-wide backfill against staging. |
| TTL | Inspect new keys: positive TTL <=3,600 seconds (<=300 for organization authentication). Shorten TTL only for tracked fixture keys, let them expire, and verify MongoDB refill plus restored TTL. Confirm unrelated keys are untouched. |
| Mutable settings — accepted TTL | Warm a quiz, PATCH its title/shuffle/show_scores/review_immediate, then GET it and create a fresh session. Compare to MongoDB and cache-off behavior. Repeat per task. Old settings within the TTL are accepted. After expiry/refill, settings must match MongoDB on every tested task. |
| Content edits | On a disposable fixture only, warm quiz/question/list/OMR keys, update content/answer key through supported paths, and compare display, scoring, and reveal. Record the no-invalidation limitation and how immutable publishing is enforced. The user accepts the one-hour freshness window; record that scoring may use the cached key during that window. |

## 3. Failure, memory, and multi-task checks

- **Disabled mode:** Redis can be absent and all primary routes still work. No keys for the test namespace should be written.
- **Redis unavailable at startup:** use a controlled testing task with a refused endpoint, then a stalled endpoint. The backend must start and serve MongoDB-backed requests within a bounded deadline. Proposed gate: startup healthy within 60 seconds and affected individual requests within 5 seconds, not an indefinite wait.
- **Redis loss during traffic:** interrupt only the test sidecar, continue quiz reads/writes, and restore it. Verify no lost answers, unexpected 5xx, or score changes; observe connection retries/recovery. Reconnect attempts are throttled for five seconds when there is no client, so measure recovery rather than expecting immediate reconnection.
- **Invalid cached JSON:** corrupt one tracked fixture key and verify fallback and eventual cache repair without affecting other records.
- **Memory pressure/eviction:** on an isolated test task, generate disposable namespaced keys until the configured LRU eviction occurs. Record Redis memory/evictions, backend latency, and task health; verify evicted fixture keys refill. No unbounded fill or shared Redis flush.
- **Multiple tasks/cold restart:** run two testing tasks if capacity permits. Prove each independent sidecar can warm, and that restarted tasks begin cold without functional errors. Recheck settings consistency across both; record any test skipped if only one task can be exercised.
- **Rollback:** roll back to cache-disabled #142 and then, if needed, the recorded #141 task definition. Existing test sessions must still read/save/submit. Restore task count and configuration after fault experiments.

## 4. Before/after load comparison

Use the same task resources/count, MongoDB tier, fixture mix, request pacing, and load-generator location. Separate these modes: #141 baseline; #142 cache-off; #142 cold-cache; #142 warm-cache. Avoid competing workloads during measurement and record any that remain.

Start with 5, 20, then 50 concurrent synthetic users. At each level use a one-minute warmup and three-minute measurement; repeat the highest safe level three times per mode. These are initial staging test levels, not a claim about production capacity. Stop if unexpected 5xx exceed 1% for 30 seconds, p95 exceeds twice baseline for a minute, or resource saturation threatens service stability.

Use two workloads:
1. Repeated quiz/question/form/organization reads across a fixed fixture set, including full-page and OMR reads.
2. Realistic start/read/answer/heartbeat/resume/submit flows with unique users. Keep answer writes in this mix: Redis does not remove those database writes.

Capture throughput, p50/p95/p99, timeouts/5xx, ECS CPU/memory/restarts, MongoDB read operations/connections/latency, Redis hits/misses/evictions/memory, and per-family `event=cache_stats` logs. These logs aggregate per process and emit on traffic after about 60 seconds; they are not request-level proof by themselves.

Proposed acceptance: zero unexpected functional errors; #142 cache-off and mixed-flow p95 no more than 10% worse than #141; warmed repeated reads show a high stable hit rate (target >=90%) and lower MongoDB read work at equal throughput, with a repeatable latency or throughput improvement. Investigate measurement noise; do not promise a fixed capacity gain or extrapolate 50 users to production load.

## 5. Evidence and cleanup

Record pass/fail/blocked for each case, tested image SHA/task revisions, config mode, fixture IDs, expected/actual response summaries, cache/TTL evidence, metrics, and relevant sanitized logs. Distinguish expected negative-test errors from failures.

Delete only tracked test organizations, quizzes, questions, sessions, and exact Redis fixture keys on each task. Never run `FLUSHDB`, `FLUSHALL`, or broad collection deletion. Keep the report and restore temporary load/fault settings. Leave cache enabled only if correctness, freshness, failure, and performance gates pass; otherwise leave the verified disabled/baseline configuration and list the required fixes.
