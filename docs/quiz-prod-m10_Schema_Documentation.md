# quiz-prod-m10 Schema Documentation

### questions Collection

Individual question definitions with metadata and marking schemes. This collection stores all questions that can be used in quizzes, forms, and assessments.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_id` | String | Yes | Unique identifier (ObjectId as string) for the question |
| `text` | String | Yes | The question text/content that students will see |
| `type` | String | Yes | Question type from enum: "single-choice", "multi-choice", "subjective", "numerical-integer", "numerical-float", "matrix-match", "matrix-rating", "matrix-numerical" |
| `instructions` | String | No | Additional instructions for the question (nullable) |
| `image` | Object | No | Question image with URL and alt text (nullable) |
| `image.url` | String | No | URL of the question image |
| `image.alt_text` | String | No | Alternative text for accessibility |
| `options` | Array | Yes | Answer options for multiple choice questions |
| `options[].text` | String | Yes | Text content of the option |
| `options[].image` | Object | No | Image associated with the option (nullable) |
| `max_char_limit` | Number | No | Character limit for subjective/text answers (nullable) |
| `matrix_size` | Array | No | Size dimensions for matrix match questions (nullable) |
| `matrix_rows` | Array | No | Row labels for matrix rating/numerical questions (nullable) |
| `correct_answer` | Union | No | Correct answer - can be Array[int], Array[str], float, int, dict, or null |
| `graded` | Boolean | Yes | Whether this question contributes to scoring (true) or is just for data collection (false) |
| `marking_scheme` | Object | No | Question-specific marking scheme (nullable) - overrides question set marking |
| `marking_scheme.correct` | Number | No | Points awarded for correct answer |
| `marking_scheme.wrong` | Number | No | Points deducted for wrong answer |
| `marking_scheme.skipped` | Number | No | Points for skipped/unanswered question |
| `marking_scheme.partial` | Array | No | Partial credit rules for multi-choice questions |
| `solution` | Array | Yes | Step-by-step solution explanation (empty array if none) |
| `metadata` | Object | No | Question metadata including grade, subject, chapter, topic, difficulty, etc. (nullable) |
| `source` | String | No | Source system that created this question (nullable) |
| `source_id` | String | No | ID in the source system (nullable) |
| `question_set_id` | String | Yes | ID of the question set this question belongs to |

### organization Collection

Organization data for frontend authentication. This collection stores organization information and API keys used for client-side access validation.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_id` | String | Yes | Unique identifier (ObjectId as string) for the organization |
| `name` | String | Yes | Organization name (e.g., "Avanti Fellows") |
| `key` | String | Yes | API key for organization authentication (auto-generated random string) |

### marking_presets Collection

Predefined marking schemes for different exam types. This collection stores standardized marking schemes that can be reused across multiple quizzes.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_id` | String | Yes | Unique identifier (ObjectId as string) for the marking preset |
| `name` | String | Yes | Preset name (e.g., "JEE_ADVANCED_2023_MULTI_ANSWER") |
| `marking_scheme` | Object | Yes | Marking scheme configuration |
| `marking_scheme.correct` | Number | Yes | Points awarded for correct answer |
| `marking_scheme.wrong` | Number | Yes | Points deducted for wrong answer |
| `marking_scheme.skipped` | Number | Yes | Points for skipped/unanswered question |
| `marking_scheme.partial` | Array | No | Partial credit rules for complex scoring |
| `marking_scheme.partial[].conditions` | Array | No | Conditions that must be met for partial credit |
| `marking_scheme.partial[].conditions[].num_correct_selected` | Number | No | Number of correct options that must be selected |
| `marking_scheme.partial[].marks` | Number | No | Marks awarded when conditions are met |

### sessions Collection

User quiz sessions containing answers and progress.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_id` | String | Yes | Unique identifier (ObjectId as string) for the session |
| `user_id` | String | Yes | User identifier who is taking the quiz |
| `quiz_id` | String | Yes | Quiz identifier being attempted |
| `omr_mode` | Boolean | No | Whether the quiz is in OMR (Optical Mark Recognition) mode (default: false) |
| `created_at` | DateTime | Yes | Timestamp when session was created |
| `events` | Array | Yes | Array of session events (start-quiz, resume-quiz, end-quiz, dummy-event) |
| `events[].event_type` | String | Yes | Type of event from EventType enum |
| `events[].created_at` | DateTime | Yes | When the event occurred |
| `events[].updated_at` | DateTime | Yes | When the event was last updated |
| `has_quiz_ended` | Boolean | Yes | Whether the quiz session has been completed |
| `question_order` | Array | Yes | Randomized order of questions for this session (array of indices) |
| `metrics` | Object | No | Session performance metrics (populated when quiz ends) |
| `is_first` | Boolean | Yes | Whether this is the user's first attempt at this quiz |
| `session_answers` | Array | Yes | Array of user's answers to questions |
| `session_answers[]._id` | String | Yes | Answer identifier (ObjectId as string) |
| `session_answers[].question_id` | String | Yes | Question identifier being answered |
| `session_answers[].answer` | Union | No | User's answer - can be Array[int], Array[str], float, int, str, dict, or null |
| `session_answers[].visited` | Boolean | No | Whether the user has visited this question |
| `session_answers[].time_spent` | Number | No | Time spent on this question in seconds |
| `session_answers[].marked_for_review` | Boolean | No | Whether the question is marked for review |
| `session_answers[].created_at` | DateTime | Yes | When the answer was created |
| `session_answers[].updated_at` | DateTime | Yes | When the answer was last updated |
| `time_remaining` | Number | No | Time remaining in the quiz (in seconds) |

### quizzes Collection

Complete quiz definitions with question sets and configuration. This collection stores the full quiz structure including all questions, settings, and metadata.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_id` | String | Yes | Unique identifier (ObjectId as string) for the quiz |
| `title` | String | No | Quiz title (nullable) |
| `question_sets` | Array | Yes | Array of question sets that make up the quiz |
| `question_sets[]._id` | String | Yes | Question set identifier (ObjectId as string) |
| `question_sets[].questions` | Array | Yes | **Question objects** (see questions collection schema for full structure) |
| `question_sets[].title` | String | No | Question set title (nullable) |
| `question_sets[].description` | String | No | Question set description (nullable) |
| `question_sets[].max_questions_allowed_to_attempt` | Number | Yes | Maximum number of questions user can attempt in this set |
| `question_sets[].marking_scheme` | Object | No | Question set marking scheme (nullable) - overrides individual question marking |
| `question_sets[].marking_scheme.correct` | Number | No | Points for correct answer |
| `question_sets[].marking_scheme.wrong` | Number | No | Points for wrong answer |
| `question_sets[].marking_scheme.skipped` | Number | No | Points for skipped answer |
| `question_sets[].marking_scheme.partial` | Array | No | Partial credit rules |
| `max_marks` | Number | Yes | Maximum possible marks for the entire quiz |
| `num_graded_questions` | Number | Yes | Total number of graded questions in the quiz |
| `shuffle` | Boolean | Yes | Whether to shuffle question order (default: false) |
| `num_attempts_allowed` | Number | Yes | Number of attempts allowed per user (default: 1) |
| `time_limit` | Object | No | Time limit configuration (nullable) |
| `time_limit.min` | Number | No | Minimum time limit in minutes |
| `time_limit.max` | Number | No | Maximum time limit in minutes |
| `review_immediate` | Boolean | No | Whether to show answers immediately after quiz ends (default: true) |
| `display_solution` | Boolean | No | Whether to display solutions after quiz ends (default: true) |
| `show_scores` | Boolean | No | Whether to show scores after quiz ends (default: true) |
| `navigation_mode` | String | Yes | Navigation mode from NavigationMode enum ("linear", "non-linear") |
| `instructions` | String | No | General quiz instructions (nullable) |
| `language` | String | Yes | Quiz language from QuizLanguage enum ("en", "hi") |
| `metadata` | Object | No | Quiz metadata (nullable) |
| `metadata.quiz_type` | String | No | Type of quiz from QuizType enum ("assessment", "homework", "omr-assessment", "form") |
| `metadata.test_format` | String | No | Test format from TestFormat enum ("full_syllabus_test", "major_test", "part_test", etc.) |
| `metadata.grade` | String | No | Target grade level |
| `metadata.subject` | String | No | Subject area |
| `metadata.chapter` | String | No | Chapter name (nullable) |
| `metadata.topic` | String | No | Topic name (nullable) |
| `metadata.source` | String | No | Source system that created this quiz (nullable) |
| `metadata.source_id` | String | No | ID in the source system (nullable) |
| `metadata.session_end_time` | String | No | Session end time in format "%Y-%m-%d %I:%M:%S %p" (nullable) |
| `metadata.next_step_url` | String | No | URL to redirect to after quiz completion (nullable) |
| `metadata.next_step_text` | String | No | Text to display on next step button (nullable) |
| `metadata.next_step_autostart` | Boolean | No | Whether next step should auto-start (default: false) |

**Note**: The `question_sets[].questions[]` array contains full question objects with the same structure as defined in the `questions` collection. See the questions collection schema above for complete field definitions.

---

## Data Types

### Common Types
- **ObjectId**: MongoDB ObjectId (represented as string in some collections)
- **String**: Text data
- **Number**: Numeric data (integers and floats)
- **Boolean**: True/false values
- **Array**: List of items
- **Object**: Nested object structure
- **DateTime**: ISO format datetime strings
- **Union**: Multiple possible types (e.g., answerType can be Array[int], Array[str], float, int, str, dict, or null)
- **null**: Null value (indicates optional fields)

### Special Types
- **Date of Birth Object**: Contains `month`, `day`, and `year` fields for student enrollment
- **Image Object**: Contains `url` and `alt_text` fields for accessibility
- **Marking Scheme Object**: Contains scoring configuration with correct/wrong/skipped points and partial credit rules
- **Metadata Object**: Contains additional contextual information (grade, subject, chapter, topic, etc.)
- **Time Limit Object**: Contains `min` and `max` fields for quiz time constraints
- **Event Object**: Contains `event_type`, `created_at`, and `updated_at` for session tracking

### Enums and Constants

#### QuestionType Enum
- `single-choice`: Single correct answer selection
- `multi-choice`: Multiple correct answer selection
- `subjective`: Open-ended text response
- `numerical-integer`: Integer numerical answer
- `numerical-float`: Decimal numerical answer
- `matrix-match`: Matrix matching questions
- `matrix-rating`: Matrix rating questions
- `matrix-numerical`: Matrix numerical questions

#### QuizType Enum
- `assessment`: Formal assessment/test
- `homework`: Homework assignment
- `omr-assessment`: OMR (Optical Mark Recognition) assessment
- `form`: Data collection form

#### NavigationMode Enum
- `linear`: Sequential question navigation
- `non-linear`: Free navigation between questions

#### QuizLanguage Enum
- `en`: English
- `hi`: Hindi

#### EventType Enum
- `start-quiz`: Quiz session started
- `resume-quiz`: Quiz session resumed
- `end-quiz`: Quiz session ended
- `dummy-event`: Placeholder event
