# **Title**

Concurrent session control in QE backend.

# **Description**

Allow multiple sessions for analysis while enforcing a single active/writable session per user+quiz.

# **Author**

Surya

# **Context & Problem Description**

- Frontend always calls create session on mount; refresh/tab/device forks a new session.
- Backend creates a new session once any meaningful event exists in the last session.
- Session answer updates do not guard against stale/parallel sessions.
- ETL picks latest session by _id, so newer parallel sessions override correct ones.
- Requirement: allow multiple sessions for analysis, but only one active/writable session per user+quiz.

# **Solution(s)**

- Enforce a single active session with explicit takeover.
    - Identify clients with client_id (device/browser) and optional tab_id (tab).
    - Use heartbeat to detect stale sessions.
    - Reject writes from superseded sessions.
- Rejected for now: allow multi-device writes and reconcile conflicts.
    - Too risky; conflicts are hard to resolve and break ETL correctness.

# **Implementation / Tech Specs**

**Quiz Backend**

- Add session fields:
    - client_id: string
    - tab_id: string (optional)
    - last_heartbeat_at: datetime (or reuse updated_at)
    - status: "active" | "superseded"
    - superseded_by: session_id (optional)
- Define active session as last_heartbeat_at within T seconds.
    - Heartbeat uses existing dummy-event updates (from fix/session-timing-fields).
- Create session: POST `/sessions`
    - Input: user_id, quiz_id, omr_mode, client_id, optional tab_id.
    - Logic:
        1) Find latest session for user+quiz.
        2) If latest is active and not ended:
            - If client_id (and tab_id if used) matches: return existing session (200).
            - If mismatch: return 409 with active session details.
        3) If stale: create new session and mark old as superseded.
        4) If has_quiz_ended is true: return the latest session in read-only mode; do not create a new session.
- Takeover: POST `/sessions/{id}/takeover` (or param on create)
    - Requires explicit confirmation from UI.
    - Marks existing active session as superseded and activates new session.
    - Enforce cooldown to avoid ping-pong.
- Update session / session_answers
    - Reject writes if status is superseded or has_quiz_ended is true.
    - Return 409 with active_session_id or superseded_by for UI guidance.

**Quiz Frontend**

- Generate and persist client_id (localStorage or cookie).
- Optionally generate tab_id (sessionStorage) if blocking multi-tab.
- Send client_id (and tab_id) on create and update calls.
- Handle 409 responses with modal:
    - Title: "Session active elsewhere"
    - Body: "This quiz is active in another tab or device. You can keep it there, or take over here."
    - Actions:
        - "Keep it there": close modal, keep this view read-only, show banner "Session active elsewhere. Close this tab or take over."
        - "Take over here": call takeover endpoint, then retry create/update. If takeover fails, stay read-only.
- If session is superseded, switch to read-only and prompt refresh.
    - Show banner "This session is no longer active. Refresh to continue."
    - Disable input and prevent further writes.

**Scenario table**

| **Scenario** | **Server decision** | **Client behavior** |
| --- | --- | --- |
| Refresh same tab (same client_id + same tab_id) | Return existing session (200) | Continue seamlessly; no new session |
| New tab same browser | If using tab_id: return 409 "active in another tab" | Show "Active in another tab. Take over or close other tab" |
| New tab same browser (client_id only, no tab_id) | Return existing session (200) | Both tabs write same session (no fork, but still concurrent UI) |
| Laptop + mobile (active on laptop) | Return 409 with active session info | Show "Active elsewhere. Resume there or take over here" |
| Laptop crashed (no heartbeat > T) | Create new session; mark old abandoned/superseded | Resume on new session automatically |
| Different student using same user_id while active | Return 409; optionally require OTP | Block unless stale or explicit takeover is allowed |
| Two devices keep taking over | Enforce cooldown + require explicit confirm | Show "Recent takeover detected; try again later" |

The last scenarios we will ignore for now -- referring to the tug-of-war takeover.

- Take over does not close the other tab/device; it invalidates it. Next API call from the old session gets rejected (read-only mode message).

**Backwards compatibility**

- Old clients without client_id should still be allowed to create/update sessions.
- Existing sessions without new fields should be treated as active unless has_quiz_ended is true.
- On first write from a new client, backfill missing fields (client_id/status/last_heartbeat_at).
- ETL should treat missing status as "not superseded".

**ETL Flow**

- Select the latest session where status != superseded and has_quiz_ended == true.
- If no ended session exists, prefer active session for in-progress reporting.

# **Status**

`🔃PROPOSED`

#
`[positive]` Prevents parallel session overwrites and improves data integrity and ETL correctness. Clear client UX for active-session conflicts and takeovers.

`[negative]` Added API complexity and client handling for 409 responses. Requires additional session fields and heartbeat tracking.
