import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.store import store


@pytest.fixture(autouse=True)
def clear_store():
    store._data.clear()
    yield
    store._data.clear()


client = TestClient(app)


def create_workflow(**overrides) -> dict:
    payload = {
        "action": "terminate-ec2-instance",
        "requested_by": "agent-1",
        "context": {"instance_id": "i-abc123"},
        "timeout_minutes": 30,
        **overrides,
    }
    response = client.post("/v1/workflows", json=payload)
    assert response.status_code == 201
    return response.json()


def test_create_workflow():
    created_workflow = create_workflow()
    assert "workflow_id" in created_workflow
    assert created_workflow["status"] == "PENDING"
    assert "expires_at" in created_workflow


def test_get_pending_workflow():
    created_workflow = create_workflow()
    workflow_id = created_workflow["workflow_id"]

    get_response = client.get(f"/v1/workflows/{workflow_id}")
    assert get_response.status_code == 200
    fetched_workflow = get_response.json()
    assert fetched_workflow["workflow_id"] == workflow_id
    assert fetched_workflow["status"] == "PENDING"
    assert fetched_workflow["action"] == "terminate-ec2-instance"
    assert fetched_workflow["requested_by"] == "agent-1"
    assert fetched_workflow["resolved_at"] is None
    assert fetched_workflow["resolved_by"] is None


def test_workflow_can_be_approved():
    workflow_id = create_workflow()["workflow_id"]

    approve_response = client.post(f"/v1/workflows/{workflow_id}/approve", json={"reviewed_by": "alice"})
    assert approve_response.status_code == 200
    approved_workflow = approve_response.json()
    assert approved_workflow["status"] == "APPROVED"
    assert approved_workflow["resolved_by"] == "alice"
    assert approved_workflow["resolved_at"] is not None


def test_workflow_can_be_rejected():
    workflow_id = create_workflow()["workflow_id"]

    reject_response = client.post(f"/v1/workflows/{workflow_id}/reject", json={"reviewed_by": "bob"})
    assert reject_response.status_code == 200
    rejected_workflow = reject_response.json()
    assert rejected_workflow["status"] == "REJECTED"
    assert rejected_workflow["resolved_by"] == "bob"
    assert rejected_workflow["resolved_at"] is not None


def test_double_approve_is_idempotent():
    workflow_id = create_workflow()["workflow_id"]

    first_approved_response = client.post(f"/v1/workflows/{workflow_id}/approve", json={"reviewed_by": "alice"})
    assert first_approved_response.status_code == 200
    assert first_approved_response.json()["status"] == "APPROVED"

    second_approved_response = client.post(f"/v1/workflows/{workflow_id}/approve", json={"reviewed_by": "alice"})
    assert second_approved_response.status_code == 200
    assert second_approved_response.json()["status"] == "APPROVED"


def test_approve_after_reject_returns_conflict():
    workflow_id = create_workflow()["workflow_id"]

    client.post(f"/v1/workflows/{workflow_id}/reject", json={"reviewed_by": "bob"})

    approve_after_reject_response = client.post(f"/v1/workflows/{workflow_id}/approve", json={"reviewed_by": "alice"})
    assert approve_after_reject_response.status_code == 409
    conflict_detail = approve_after_reject_response.json()["detail"]
    assert conflict_detail["error"] == "workflow already resolved"
    assert conflict_detail["current_status"] == "REJECTED"


def test_expired_workflow_is_timed_out():
    workflow_id = create_workflow(timeout_minutes=0)["workflow_id"]

    get_response = client.get(f"/v1/workflows/{workflow_id}")
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "TIMED_OUT"


def test_approve_after_timeout_returns_conflict():
    workflow_id = create_workflow(timeout_minutes=0)["workflow_id"]

    client.get(f"/v1/workflows/{workflow_id}")

    approve_after_timeout_response = client.post(f"/v1/workflows/{workflow_id}/approve", json={"reviewed_by": "alice"})
    assert approve_after_timeout_response.status_code == 409
    conflict_detail = approve_after_timeout_response.json()["detail"]
    assert conflict_detail["error"] == "workflow already resolved"
    assert conflict_detail["current_status"] == "TIMED_OUT"


def test_unknown_workflow_returns_404():
    get_response = client.get("/v1/workflows/does-not-exist")
    assert get_response.status_code == 404


def test_negative_timeout_minutes_returns_422():
    create_response = client.post("/v1/workflows", json={
        "action": "terminate-ec2-instance",
        "requested_by": "agent-1",
        "timeout_minutes": -1,
    })
    assert create_response.status_code == 422
