<!-- Canonical copy. quiz-frontend/CONTEXT.md symlinks here (../quiz-backend/CONTEXT.md). -->

# Quiz Engine

A mobile-friendly quiz and assessment platform built by Avanti Fellows, serving students in Indian government schools. The backend (FastAPI/Python) and frontend (Vue 3/TypeScript) live in separate repos (`quiz-backend`, `quiz-frontend`) and share this domain context.

## Language

### Core Entities

**Quiz**:
The top-level container for an assessment, homework, or form. Holds settings (time limit, shuffle, navigation mode) and one or more **QuestionSets**.
_Avoid_: Test, exam

**QuestionSet**:
A logical section within a **Quiz** (e.g., "Section A — Physics"). Groups **Questions** and defines a default **MarkingScheme**. Questions are embedded, not shared across quizzes.
_Avoid_: Question pool, question bank

**Question**:
An individual item a student answers. Has a type (single-choice, multi-choice, numerical, subjective, matrix-match, and variants), optional correct answer, and optional **MarkingScheme** override.

**Session**:
One user's attempt at one **Quiz**. Identified by `user_id` + `quiz_id`. Tracks lifecycle events, time, shuffled question order, and completion state.
_Avoid_: Attempt, submission

**SessionAnswer**:
One user's response to one **Question** within a **Session**. Tracks the answer value, visited flag, time spent, and marked-for-review state.
_Avoid_: Response, submission

**Organization**:
A lightweight tenant. Owns an API key used to authenticate quiz access. Avanti Fellows is the only tenant today, but the model supports multiple NGOs sharing the platform.
_Avoid_: Tenant, account

### Quiz Behavior

**QuizType**:
Controls how the frontend behaves. Four values: `assessment` (timed, scored at end), `homework` (untimed, immediate feedback per question), `form` (data collection, no grading), `omr-assessment` (legacy — equivalent to `assessment` with OMR mode forced on; exists to support older data, may be cleaned up).
_Avoid_: Quiz mode

**TestFormat**:
Pure metadata label on a **Quiz** (e.g., `full_syllabus_test`, `part_test`, `chapter_test`). No code branches on this value — it is for display and categorization only.

**OMR Mode**:
A display mode, not a quiz type. Renders all questions on a single scrollable page (bubble-sheet style) instead of one-at-a-time. Can be enabled via the `?omrMode` URL param on any assessment, or forced by the `omr-assessment` **QuizType**. Homework cannot use OMR mode.
_Avoid_: OMR type

**Form**:
A side feature that reuses the quiz engine for data collection (surveys, questionnaires). No grading, no correct answers, no scores. Has a separate URL endpoint (`/form/{id}`) primarily for cleaner URLs; the backend logic also skips answer-hiding since there's nothing to protect.

### Scoring

**MarkingScheme**:
Defines marks awarded for correct, wrong, and skipped answers, plus optional partial-marking rules. Can be set at **QuestionSet** level (default for all questions in the set) or **Question** level (overrides the set). In practice, all questions within a set share the same scheme.

**Graded**:
A boolean on **Question**. Ungraded questions accept any answer without correctness evaluation (e.g., survey questions within an assessment).

**Force Correct**:
A backend-only scoring override on **Question**. When enabled, the student receives full marks regardless of their actual answer. The frontend has no knowledge of this flag.

**Partial Marking**:
For multi-choice and matrix-match questions. If a student selects a correct subset of answers, they receive partial credit based on rules mapping number-of-correct-selections to marks.

### Session Lifecycle

**Event**:
A timestamped lifecycle marker appended to a **Session**'s event log. Four types: `start-quiz`, `resume-quiz`, `end-quiz`, and `dummy-event`.

**Dummy Event**:
A periodic heartbeat sent by the frontend every ~20 seconds. Syncs time-spent data and checks remaining time. The name is a placeholder that stuck — it's functionally a heartbeat/time-sync.
_Avoid_: Heartbeat (in code — the enum value is `dummy-event`)

### Performance

**Question Bucketing**:
A lazy-loading optimization. Questions are fetched in buckets of 10. On quiz load, only the first bucket has full details; the rest are stubs loaded on demand as the student navigates. The backend shuffles question order within blocks of 10 to preserve bucket boundaries — this is a cross-repo coupling (backend `subset_size = 10`, frontend `bucketSize = 10`).
_Avoid_: Pagination (it's block-based, not offset-based in the traditional sense)

### External Systems

**Portal**:
The external authentication system that manages user identity and generates quiz URLs. The quiz engine receives an opaque `user_id` and does not manage users itself.

**CMS**:
The external content management system that creates questions and quizzes. The `source` and `source_id` fields on **Quiz** and **Question** link back to it.

**Next Step**:
A post-quiz redirect configured per **Quiz** via `next_step_url` metadata. Sends students to another quiz, an external URL, or any configured destination after completion.

## Relationships

- A **Quiz** contains one or more **QuestionSets**
- A **QuestionSet** contains one or more **Questions** (embedded, not shared across quizzes)
- A **Session** belongs to exactly one **Quiz** and one user
- A **Session** contains one **SessionAnswer** per **Question** in the quiz
- An **Organization** authenticates access to quizzes via its API key
- A **MarkingScheme** is defined on a **QuestionSet** and optionally overridden per **Question**
- **QuizType** determines frontend behavior; **TestFormat** is display-only metadata
- **OMR Mode** switches the frontend between single-question and all-questions-on-page rendering

## Example dialogue

> **Dev:** "A student opens a **Quiz** link. What happens?"
> **Domain expert:** "The **Portal** authenticates them via the `apiKey`. The frontend fetches the **Quiz**, creates a **Session**, and loads the first bucket of **Questions**. As the student navigates past question 10, the next bucket is lazy-loaded."

> **Dev:** "What if a **Question** in an assessment turns out to be wrong after students have already taken it?"
> **Domain expert:** "Set **Force Correct** on that **Question**. Every student gets full marks for it — the frontend doesn't even know, it only affects backend scoring."

> **Dev:** "Can I make a **Form** timed?"
> **Domain expert:** "Technically yes — the data model supports `time_limit` on any **Quiz**. But forms are for data collection; timing doesn't make domain sense."

> **Dev:** "Why does the shuffle only randomize within blocks of 10?"
> **Domain expert:** "Because of **Question Bucketing**. The frontend lazy-loads questions in groups of 10. If we shuffled freely, the bucket boundaries would break — a question from position 25 might end up at position 3, but the frontend would try to fetch it from the wrong bucket."

## Flagged ambiguities

- **`omr-assessment`** is listed as a **QuizType** but is functionally `assessment` + OMR mode. It exists to support older quiz data. May be consolidated in the future.
- **`dummy-event`** is a misleading name for what is actually a heartbeat/time-sync event. Renaming is a breaking change (stored in existing session documents).
- **Form endpoint** (`/form`) was created for cleaner URLs, but the backend logic has diverged — it never hides answers, unlike `/quiz`. This divergence is intentional given forms have no concept of correct answers to protect.
- **Dual-backend switching** (`?new_backend`, `VUE_APP_BACKEND_ECS`) was developed on a feature branch during the Lambda-to-ECS migration but never merged. The frontend CLAUDE.md and project-context.md still reference it — these docs are stale.
- **S3 bucket names** (`question-set-player`, `question-set-player-staging`) use the old project name. Should be renamed to match "Quiz Engine" / "quiz-frontend" for consistency.
