# approval-workflow-service

A standalone human-in-the-loop approval service for AI agent platforms. When automated agents reach sensitive operations (terminating cloud resources, resetting credentials, etc.), they pause execution and request human approval before proceeding.

## Overview

The service implements a **pause-and-resume** pattern:

1. Agent calls `POST /workflows` with a description of the action needing approval
2. Service persists the request and returns a `workflow_id`
3. Agent polls `GET /workflows/{id}` for status changes
4. A human approver calls `POST /workflows/{id}/approve` or `POST /workflows/{id}/reject`
5. Agent resumes or halts based on the decision; requests expire after a configurable timeout

## Demo Agent

`agent_demo.py` simulates an autonomous agent hitting a sensitive step and pausing for human approval.

```bash
# Terminal 1 — start the service
uv run uvicorn app.main:app --reload

# Terminal 2 — run the agent
uv run python agent_demo.py
```

The agent prints the `workflow_id` and polls every 3 seconds. In a third terminal, approve or reject:

```bash
curl -X POST http://localhost:8000/workflows/<id>/approve \
  -H "Content-Type: application/json" \
  -d '{"reviewed_by": "alice"}'
```

The demo uses a 5-minute timeout — if no one responds, the agent prints `TIMED_OUT` and aborts.

## Running Locally

```bash
# Install dependencies
uv sync

# Start the server
uv run uvicorn app.main:app --reload

# Run tests
uv run pytest tests/ -v
```

## API Reference

### Create a workflow approval request

```bash
curl -X POST http://localhost:8000/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "action": "terminate EC2 instance i-abc123",
    "requested_by": "infra-agent",
    "context": {"instance_id": "i-abc123", "region": "us-east-1"},
    "timeout_minutes": 30
  }'
```

**Request fields:**
- `action` (string, required) — human-readable description of the action needing approval
- `requested_by` (string, required) — identifier of the requesting agent
- `context` (object, optional, default `{}`) — arbitrary metadata for the approver
- `timeout_minutes` (int, optional, default `30`) — how long to wait for a human decision

**Response (201):**
```json
{
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "PENDING",
  "expires_at": "2026-02-24T16:00:00Z"
}
```

### Poll for status

```bash
curl http://localhost:8000/workflows/{workflow_id}
```

**Response (200):**
```json
{
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
  "action": "terminate EC2 instance i-abc123",
  "requested_by": "infra-agent",
  "context": {"instance_id": "i-abc123", "region": "us-east-1"},
  "status": "PENDING",
  "created_at": "2026-02-24T15:00:00Z",
  "expires_at": "2026-02-24T16:00:00Z",
  "resolved_at": null,
  "resolved_by": null
}
```

Returns 404 if the `workflow_id` does not exist.

### Approve

```bash
curl -X POST http://localhost:8000/workflows/{workflow_id}/approve \
  -H "Content-Type: application/json" \
  -d '{"reviewed_by": "alice"}'
```

### Reject

```bash
curl -X POST http://localhost:8000/workflows/{workflow_id}/reject \
  -H "Content-Type: application/json" \
  -d '{"reviewed_by": "alice"}'
```

Both approve and reject return the full workflow detail response (same shape as `GET /workflows/{id}`).

**Error response (409)** — returned when the workflow is already resolved (e.g. already approved, rejected, or timed out):
```json
{
  "detail": {
    "error": "workflow already resolved",
    "current_status": "TIMED_OUT"
  }
}
```

## Architecture Notes

- **In-memory store**: The current implementation uses a dict-backed store. Swap `app/store.py` for a SQLAlchemy-backed implementation for persistence across restarts.
- **Lazy timeout**: Expired requests are marked `TIMED_OUT` on first read rather than via a background sweep, keeping the implementation simple. The timeout check runs on `GET`, approve, and reject — preventing race conditions where a reviewer acts on a request that expired moments earlier.
- **Idempotency**: Approving an already-approved workflow (same decision) returns 200. Conflicting decisions (approve after reject, or any action after timeout) return 409 with a `current_status` field indicating the actual state.
- **Statuses**: `PENDING` → `APPROVED` | `REJECTED` | `TIMED_OUT`
