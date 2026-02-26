"""
Demo agent that simulates an autonomous process hitting a sensitive step.

HOW TO RUN:
  Terminal 1 — start the approval service:
    uv run uvicorn app.main:app --reload

  Terminal 2 — run this script:
    uv run python agent_demo.py

The agent will pause and wait for you to approve or reject in Terminal 3:
  Approve:  curl -X POST http://localhost:8000/workflows/<id>/approve -H "Content-Type: application/json" -d '{"reviewed_by": "tony"}'
  Reject:   curl -X POST http://localhost:8000/workflows/<id>/reject  -H "Content-Type: application/json" -d '{"reviewed_by": "tony"}'
"""

import time
import httpx

BASE_URL = "http://localhost:8000"
POLL_INTERVAL_SECONDS = 3


def request_approval(action: str, context: dict) -> str:
    """Ask the approval service for human sign-off. Returns the workflow_id."""
    response = httpx.post(f"{BASE_URL}/workflows", json={
        "action": action,
        "requested_by": "demo-agent",
        "context": context,
        "timeout_minutes": 5,
    })
    response.raise_for_status()
    workflow_id = response.json()["workflow_id"]
    print(f"\n[agent] Approval requested. Workflow ID: {workflow_id}")
    print(f"[agent] Waiting for a human to approve or reject...\n")
    return workflow_id


def poll_until_decided(workflow_id: str) -> str:
    """Poll every few seconds until the workflow is no longer PENDING. Returns the final status."""
    while True:
        response = httpx.get(f"{BASE_URL}/workflows/{workflow_id}")
        response.raise_for_status()
        status = response.json()["status"]

        if status != "PENDING":
            return status

        print(f"[agent] Still waiting... (status: {status})")
        time.sleep(POLL_INTERVAL_SECONDS)


def run():
    print("=" * 50)
    print("[agent] Starting task: provision new cloud environment")
    print("=" * 50)

    # Step 1 — safe work, no approval needed
    print("\n[agent] Step 1: Checking existing resources... done")
    print("[agent] Step 2: Validating config... done")

    # Step 2 — sensitive action, must pause and ask for approval
    print("\n[agent] Step 3: About to terminate EC2 instance i-abc123.")
    print("[agent] This requires human approval. Pausing...")

    workflow_id = request_approval(
        action="Terminate EC2 instance i-abc123",
        context={"instance_id": "i-abc123", "region": "us-west-1"},
    )

    # Step 3 — wait for a human to decide
    status = poll_until_decided(workflow_id)

    # Step 4 — resume or stop based on the decision
    print(f"\n[agent] Decision received: {status}")

    if status == "APPROVED":
        print("[agent] Approved. Terminating instance i-abc123...")
        print("[agent] Instance terminated. Task complete.")
    elif status == "REJECTED":
        print("[agent] Rejected. Skipping termination. Task aborted.")
    elif status == "TIMED_OUT":
        print("[agent] No one responded in time. Task aborted.")

    print()


if __name__ == "__main__":
    run()
