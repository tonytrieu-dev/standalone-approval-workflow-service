# Design Decisions

## Problem and Approach

AI agents need a way to stop, ask a human for permission, and then continue (or not) based on the answer. I focused on getting that loop right before anything else.

---

## Core Architectural Choices

### Polling Instead of Webhooks

Agents poll `GET /workflows/{id}` to check for a decision rather than waiting for a callback. A few reasons I went this direction:

- Agents are already sitting in a wait loop, so polling fits naturally
- Webhooks require the agent to expose a callback URL, which adds infrastructure I don't need yet
- If an agent crashes and restarts, it can resume polling with the same `workflow_id` with nothing lost

The tradeoff is the agent might be a few seconds late to notice a decision, but human approval takes minutes at minimum so that doesn't matter in practice.

You can see this in `agent_demo.py`. The agent polls every 3 seconds and reacts the moment a decision comes back. The service doesn't need to know anything about the agent for that to work.

### Lazy Timeout

The status only flips to `TIMED_OUT` when something actually touches the record: a GET, an approve, or a reject. Nothing happens at the moment of expiry. The alternative is a background sweeper running on a schedule, which means managing a separate process, handling crashes, and avoiding double-processing. That's a lot of complexity for a problem the polling model already solves naturally, since the agent is always the one to discover the timeout anyway.

### In-Memory Store

The store is a Python dict, but nothing outside `store.py` ever touches it directly. Everything goes through `create`, `get`, and `update`. That boundary means swapping in a real database later is a one-file change.

I didn't start with SQLite because I didn't want to debug two things at once. If a test fails with a dict, it's a logic bug. Nothing to misconfigure.

The other reason is there are no real users yet. Losing in-flight approvals on a restart is a real limitation, but it's not worth solving until someone is actually depending on it.

### Idempotency on Approve/Reject

Approving an already-approved workflow returns 200. Approving a rejected one returns 409.

This difference is intentional. A double-approve is almost always a network retry where the first response got lost. Returning success makes the operation idempotent and retry-safe. Approving after rejection is a true state conflict, so 409 signals the issue with the current status in the response body.

### Pydantic for API, Dataclass for Storage

Request and response shapes use Pydantic. The internal `WorkflowRecord` is a plain dataclass. Pydantic validation belongs at the boundary where untrusted input comes in. Inside the service it's just known-good data being passed around, so a dataclass is enough. `dataclasses.replace()` keeps updates immutable, which makes the logic easier to reason about.

---

## Tools and Stack

| Choice | Rationale |
|--------|-----------|
| **REST over GraphQL** | Four endpoints with clear resource semantics. GraphQL adds a schema layer and dependency that isn't justified at this scale. |
| **FastAPI** | Routing, validation, and automatic OpenAPI docs with minimal boilerplate. |
| **uv** | Much faster than pip and handles both the virtualenv and script running. One tool instead of several. |
| **pytest + TestClient** | Runs the full app in-process. No server to spin up, tests finish in under 2 seconds. |
| **Python dataclasses** | No dependencies, immutable updates with `replace()`. |
| **No database** | Deferred. The store interface makes it a one-file change when needed. |
| **No auth** | Assumed to sit behind an API gateway or internal network for now. |

---

## What Was Left Out

- **Notifications**: Can't pick email vs. Slack vs. webhook without knowing the deployment environment. Biggest practical gap.
- **List endpoint**: No `GET /workflows`. An agent only needs its own ID. A dashboard can come later when there's actually a UI to build for.
- **Background expiry sweep**: Replaced by lazy timeout. Only becomes necessary if something external needs a callback at the moment of expiry.
- **Auth**: Deferred until the deployment topology is clearer.
- **Distributed locking**: Not relevant while the store is a single in-process dict.

---

## What Gets Built Next

In order of priority:

1. **Notifications**: Without them, every request times out because no one knows it's waiting
2. **Persistent storage**: A restart loses everything in-flight right now
3. **`request_id` on create**: Needed for safe agent retries, but requires a real database first
4. **Auth**: Before anything is exposed outside localhost
