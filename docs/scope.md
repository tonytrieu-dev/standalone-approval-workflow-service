# Scope: What Was Built and What Was Not

## What Was Built

### Core State Machine

The approval lifecycle is `PENDING → APPROVED | REJECTED | TIMED_OUT`. Every endpoint enforces valid transitions. You can't approve something already rejected, reject something that timed out, or accidentally overwrite a resolved workflow. Getting these transitions right was the main focus of v1.

### Four API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /workflows` | Create an approval request; returns `workflow_id` and `expires_at` |
| `GET /workflows/{id}` | Poll for status; applies lazy timeout inline |
| `POST /workflows/{id}/approve` | Human approves; idempotent on re-approval |
| `POST /workflows/{id}/reject` | Human rejects; idempotent on re-rejection |

These four cover the full loop: an agent creates a request, polls until there's an answer, and a human makes the call.

### In-Memory Store with a Swappable Interface

`WorkflowStore` only exposes `create`, `get`, and `update`. Nothing outside `store.py` touches the underlying dict. Replacing it with a real database later is a one-file change and nothing in the endpoint logic needs to change.

### Lazy Timeout

Rather than running a background sweeper, expiry is checked inline whenever a record is accessed. If it's past `expires_at` and still `PENDING`, it flips to `TIMED_OUT` on the spot. Less infrastructure, same result.

### Test Suite (10 tests)

Every endpoint, every terminal state, every error path, and the idempotency behavior are covered. Tests use FastAPI's `TestClient` which runs the whole app in-process with no server needed. The store gets wiped between tests so nothing bleeds through.

### Agent Demo (`agent_demo.py`)

The submission requirement was a functional service. `agent_demo.py` is a voluntary addition. It simulates a client of the service: an autonomous process running a task, hitting a sensitive step, pausing for approval, and either continuing or aborting based on the decision. It's not production code. It's just there to make the full loop runnable without having to construct every curl command manually. Run the service in one terminal, the demo in a second, and approve or reject from a third.

### Project Scaffolding

`pyproject.toml`, `requirements.txt`, `__init__.py` files, and a README with curl examples. `uv sync` and everything is ready to run.

---

## What Was Not Built

### Notifications (Email / Slack / Webhook)

Skipped. The right delivery mechanism depends on the deployment environment and committing to one before that's known would probably mean choosing the wrong one. The stub belongs in `app/services/notifier.py` called right after workflow creation. The honest tradeoff: without notifications, every approval request times out because no one knows it's waiting. This is the biggest gap and the first thing to fix before real usage.

### List / Dashboard Endpoint

No `GET /workflows`. An agent only needs its own `workflow_id` and there's no UI yet that would need to list them. Building pagination, filtering, and auth scoping before there's something to use them felt premature.

### Auth

The service assumes it sits behind something that already handles identity, like an API gateway or an internal network. Picking an auth mechanism before knowing the deployment topology would likely mean picking the wrong one, and it's orthogonal to whether the state machine is correct anyway.

### Persistent Storage

The in-memory store is intentional for v1. Adding a database before the core logic is validated means debugging two things at once. The store interface makes it a straightforward swap when the time comes. The real limitation is that a restart loses everything in-flight, which is the second thing to fix after notifications.

### Background Expiry Sweep

Replaced by lazy timeout. The only case where this falls short is if something external needs a callback at the exact moment of expiry rather than on the next access. That requirement doesn't exist yet.

### Webhook Callbacks for Agents

Agents poll rather than receive a push. A push model would require storing callback URLs, retry logic, TLS, and delivery tracking. Polling avoids all of that and works fine for agents already waiting in a loop.

### `request_id` Deduplication on Create

If an agent's `POST /workflows` times out and it retries, the service creates two separate records. The fix is a caller-supplied `request_id` for deduplication, but that needs a unique index and therefore a real database. Deferred until persistence is in place.

### Admin / Escalation Endpoints

No bulk expiry, reassignment, or escalation to a secondary approver. Those belong in v2 once the basic loop is running in production.

---

## The Decision Rule

If a feature doesn't affect whether the state machine is correct, and it requires committing to infrastructure or deployment decisions that aren't settled yet, it got deferred. What's here is the smallest thing that works end-to-end.

What to add next, in order:

1. **Notifications**: Without them, timeouts are the default outcome not the edge case
2. **Persistent storage**: A restart loses everything in-flight right now
3. **`request_id` deduplication**: Depends on storage, needed before agents run in production
4. **Auth**: Before anything is exposed outside localhost
