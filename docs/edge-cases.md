# Edge Cases: Handled and Not Yet Handled

## Handled

### Conflicting Decisions
Trying to approve a workflow that was already rejected (or vice versa) returns `409` with the current status in the body. The caller knows exactly what happened and what state the workflow is in.

### Approving Twice
Approving an already-approved workflow returns `200` unchanged. This covers the network retry case where the first request went through but the client never got the response. Returning an error on a retry would make this API unnecessarily painful to call reliably.

### Approving After Timeout
The timeout check runs before the approval logic. So if someone clicks approve on an expired workflow, it gets marked `TIMED_OUT` first, then the handler sees it's no longer `PENDING` and returns `409`. The reviewer gets a real error rather than a silent success the agent would never see.

### Unknown Workflow ID
Any request with a `workflow_id` that doesn't exist returns `404`. Covers typos, stale links, wrong environment. All four endpoints share the same lookup helper.

### Zero-Minute Timeout
`timeout_minutes=0` creates a record with `expires_at` already in the past. The first GET (or approve/reject) immediately marks it `TIMED_OUT`. This is also how the tests verify timeout behavior without mocking the clock or actually waiting.

### Negative Timeout
`timeout_minutes` has a `ge=0` Pydantic validator. Negative values are rejected with 422 before anything gets created. `0` is intentionally allowed as "expires immediately".

### Timeout Check on Approve/Reject, Not Just GET
The lazy timeout runs at the top of the approve and reject handlers, not only on GET. Even if an agent skips polling and a human goes straight to approve after expiry, the timeout still fires. There's no way to sneak a decision through on an expired workflow.

---

## Not Yet Handled

### Two People Deciding at the Same Time
If two approvers submit at the exact same moment, both reads see `PENDING`, both proceed, and whichever write lands last wins. The fix is a conditional write like `UPDATE ... WHERE status = 'PENDING'` so only one succeeds. Not a concern with a single in-process dict, but it will be the first thing to break when moving to a real database with concurrent requests.

### Agent Retry Creates a Duplicate Request
If an agent's `POST /workflows` call times out and it retries, it gets a brand new `workflow_id` even though the first request went through. The agent will only ever poll the new one. The fix is a caller-supplied `request_id` the service checks before creating anything. Needs a database to implement properly, so it's deferred.

### Anyone Can Approve Anything
`reviewed_by` is a free-text string that gets recorded but never validated. Anyone with a `workflow_id` can approve or reject it. UUIDs aren't guessable but they're not secret either. The real fix is auth middleware and an approver allowlist on the workflow record.

### Huge Context Payloads
The `context` field accepts any JSON object with no size limit. An agent could send megabytes of stack traces or log data and it would all get stored in memory without complaint. A size validator on the Pydantic model or a body size cap at the gateway level would handle this.

### Memory Never Gets Freed
Every workflow lives in the dict forever regardless of its status. For a low-volume internal tool that's probably fine for a while, but it's a slow leak. A database with a retention policy or a periodic cleanup job would solve it.

### Slow Poll Interval Near Expiry
If an agent polls every 60 seconds and the timeout window is 2 minutes, it might only check once or twice before the window closes. Nothing in the API enforces a sensible poll rate. A good rule of thumb is polling at `timeout_minutes / 10` seconds with a floor of 5 seconds, but that should be documented in the API reference once one exists.

### Agent Crashes and Never Polls
If the agent that created a workflow dies and never comes back, the record just sits as `PENDING` indefinitely even after expiry. A human trying to approve it would get a 409 after lazy timeout, but nobody gets notified the request is orphaned. A background sweep that fires a cancellation callback when a workflow goes silent past its expiry would handle this, but that's a v2 problem.

### Clock Skew Across Multiple Instances
Not an issue now since the in-memory store can't be shared across instances. But on multiple machines, each using its own `datetime.now()` for expiry checks, the same workflow could be `PENDING` on one box and `TIMED_OUT` on another depending on which handles the request. Using the database server's clock for all time comparisons is the standard fix.
