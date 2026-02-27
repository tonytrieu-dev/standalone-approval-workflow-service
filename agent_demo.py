"""
Demo agent that simulates an autonomous process hitting a sensitive step.
"""

import time
import httpx

BASE_URL = "http://localhost:8000"
POLL_INTERVAL_SECONDS = 5


def request_approval(action: str, context: dict) -> str:
    response = httpx.post(f"{BASE_URL}/v1/workflows", json={
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
    while True:
        response = httpx.get(f"{BASE_URL}/v1/workflows/{workflow_id}")
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

    print("\n[agent] Step 1: Checking existing resources... done")
    print("[agent] Step 2: Validating config... done")

    print("\n[agent] Step 3: About to terminate EC2 instance i-abc123.")
    print("[agent] This requires human approval. Pausing...")

    workflow_id = request_approval(
        action="Terminate EC2 instance i-abc123",
        context={"instance_id": "i-abc123", "region": "us-west-1"},
    )

    status = poll_until_decided(workflow_id)

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
