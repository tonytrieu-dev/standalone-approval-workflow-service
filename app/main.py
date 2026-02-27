import uuid
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException

from app.models import (
    CreateWorkflowRequest,
    CreateWorkflowResponse,
    ReviewRequest,
    WorkflowDetailResponse,
    WorkflowRecord,
    WorkflowStatus,
)
from app.store import store

app = FastAPI(title="Standalone Approval Workflow Service")


def not_found_error(workflow_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")


def to_detail_response(record: WorkflowRecord) -> WorkflowDetailResponse:
    return WorkflowDetailResponse(
        workflow_id=record.workflow_id,
        action=record.action,
        requested_by=record.requested_by,
        context=record.context,
        status=record.status,
        created_at=record.created_at,
        expires_at=record.expires_at,
        resolved_at=record.resolved_at,
        resolved_by=record.resolved_by,
    )


def apply_lazy_timeout(record: WorkflowRecord) -> WorkflowRecord:
    if record.status == WorkflowStatus.PENDING and datetime.now(timezone.utc) > record.expires_at:
        record = store.update(record.workflow_id, status=WorkflowStatus.TIMED_OUT)
    return record


def fetch_and_timeout(workflow_id: str) -> WorkflowRecord:
    record = store.get(workflow_id)
    if record is None:
        raise not_found_error(workflow_id)
    return apply_lazy_timeout(record)


def resolve_workflow(workflow_id: str, target_status: WorkflowStatus, reviewed_by: str) -> WorkflowDetailResponse:
    record = fetch_and_timeout(workflow_id)

    if record.status == target_status:
        return to_detail_response(record)

    if record.status != WorkflowStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail={"error": "workflow already resolved", "current_status": record.status},
        )

    record = store.update(
        workflow_id,
        status=target_status,
        resolved_at=datetime.now(timezone.utc),
        resolved_by=reviewed_by,
    )
    return to_detail_response(record)


@app.post("/v1/workflows", response_model=CreateWorkflowResponse, status_code=201)
def create_workflow(workflow_request: CreateWorkflowRequest) -> CreateWorkflowResponse:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=workflow_request.timeout_minutes)

    record = WorkflowRecord(
        workflow_id=str(uuid.uuid4()),
        action=workflow_request.action,
        requested_by=workflow_request.requested_by,
        context=workflow_request.context,
        status=WorkflowStatus.PENDING,
        created_at=now,
        expires_at=expires_at,
    )
    store.create(record)
    return CreateWorkflowResponse(
        workflow_id=record.workflow_id,
        status=record.status,
        expires_at=record.expires_at,
    )


@app.get("/v1/workflows/{workflow_id}", response_model=WorkflowDetailResponse)
def get_workflow(workflow_id: str) -> WorkflowDetailResponse:
    record = fetch_and_timeout(workflow_id)
    return to_detail_response(record)


@app.post("/v1/workflows/{workflow_id}/approve", response_model=WorkflowDetailResponse)
def approve_workflow(workflow_id: str, review_request: ReviewRequest) -> WorkflowDetailResponse:
    return resolve_workflow(workflow_id, WorkflowStatus.APPROVED, review_request.reviewed_by)


@app.post("/v1/workflows/{workflow_id}/reject", response_model=WorkflowDetailResponse)
def reject_workflow(workflow_id: str, review_request: ReviewRequest) -> WorkflowDetailResponse:
    return resolve_workflow(workflow_id, WorkflowStatus.REJECTED, review_request.reviewed_by)
