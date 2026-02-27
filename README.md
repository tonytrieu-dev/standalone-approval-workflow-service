# Standalone Approval Workflow Service

A standalone human-in-the-loop approval workflow service for AI agent platforms. When automated agents reach sensitive operations (terminating cloud resources, resetting credentials, etc.), they pause execution and request human approval before proceeding.

## Overview

The service implements a **pause-and-resume** pattern:

1. Agent calls `POST /v1/workflows` with a description of the action needing approval
2. Service persists the request and returns a `workflow_id`
3. Agent polls `GET /v1/workflows/{id}` for status changes
4. A human approver calls `POST /v1/workflows/{id}/approve` or `POST /v1/workflows/{id}/reject`
5. Agent resumes or halts based on the decision; requests expire after a configurable timeout

## Quick Start

1. Install dependencies: `uv sync`
2. Run the server: `uv run uvicorn app.main:app --reload`
3. Run tests: `uv run pytest tests/ -v`

## Demo Agent

`agent_demo.py` simulates an autonomous agent hitting a sensitive step and pausing for human approval.

```bash
# Terminal 1 — start the service
uv run uvicorn app.main:app --reload

# Terminal 2 — run the agent
uv run python agent_demo.py
```

The agent prints the `workflow_id` and polls every 5 seconds. In a third terminal, approve or reject:

```bash
# Terminal 3 — approve
curl -X POST http://localhost:8000/v1/workflows/<id>/approve -H "Content-Type: application/json" -d "{\"reviewed_by\": \"tony\"}"

# Terminal 3 — or reject
curl -X POST http://localhost:8000/v1/workflows/<id>/reject -H "Content-Type: application/json" -d "{\"reviewed_by\": \"tony\"}"
```

The demo uses a 5-minute timeout. If no one responds, the agent prints `TIMED_OUT` and aborts.

## API Reference

### Create a workflow approval request

```bash
curl -X POST http://localhost:8000/v1/workflows -H "Content-Type: application/json" -d "{\"action\": \"terminate EC2 instance i-abc123\", \"requested_by\": \"infra-agent\", \"context\": {\"instance_id\": \"i-abc123\", \"region\": \"us-east-1\"}, \"timeout_minutes\": 30}"
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
curl http://localhost:8000/v1/workflows/{workflow_id}
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
curl -X POST http://localhost:8000/v1/workflows/{workflow_id}/approve -H "Content-Type: application/json" -d "{\"reviewed_by\": \"alice\"}"
```

### Reject

```bash
curl -X POST http://localhost:8000/v1/workflows/{workflow_id}/reject -H "Content-Type: application/json" -d "{\"reviewed_by\": \"alice\"}"
```

Both approve and reject return the full workflow detail response (same shape as `GET /v1/workflows/{id}`).

**Error response (409)** — returned when the workflow is already resolved (e.g. already approved, rejected, or timed out):
```json
{
  "detail": {
    "error": "workflow already resolved",
    "current_status": "TIMED_OUT"
  }
}
```

## Further Reading

- [`docs/design-decisions.md`](docs/design-decisions.md) — architectural choices and rationale
- [`docs/edge-cases.md`](docs/edge-cases.md) — handled and unhandled edge cases
- [`docs/scope.md`](docs/scope.md) — what was built, what was deferred, and why
