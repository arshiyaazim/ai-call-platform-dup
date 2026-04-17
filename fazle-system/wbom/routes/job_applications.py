# ============================================================
# WBOM — Job Applications Routes
# Full CRUD for recruitment pipeline
# ============================================================
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from database import insert_row, get_row, update_row, delete_row, list_rows, audit_log, count_rows
from models import JobApplicationCreate, JobApplicationUpdate, JobApplicationResponse
from response import api_response, api_single
from openapi_models import ApplicationListResponse, SingleEnvelope

router = APIRouter(prefix="/job-applications", tags=["job_applications"])


@router.post("", status_code=201)
def create_application(data: JobApplicationCreate):
    row = insert_row("wbom_job_applications", data.model_dump(exclude_none=True))
    audit_log("job_application.created", actor=data.source or "system",
              entity_type="job_application", entity_id=row.get("application_id"),
              payload={"applicant": data.applicant_name, "position": data.position})
    return api_single(row, entity="applications")


@router.get("", response_model=ApplicationListResponse)
def list_applications(
    status: Optional[str] = None,
    position: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    filters = {}
    if status:
        filters["status"] = status
    if position:
        filters["position"] = position
    rows = list_rows("wbom_job_applications", filters=filters, limit=limit, offset=offset)
    total = count_rows("wbom_job_applications", filters if filters else None)
    return api_response(rows, entity="applications", total=total)


@router.get("/{application_id}")
def get_application(application_id: int):
    row = get_row("wbom_job_applications", "application_id", application_id)
    if not row:
        raise HTTPException(404, "Application not found")
    return api_single(row, entity="applications")


@router.put("/{application_id}")
def update_application(application_id: int, data: JobApplicationUpdate):
    updates = data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")
    row = update_row("wbom_job_applications", "application_id", application_id, updates)
    if not row:
        raise HTTPException(404, "Application not found")
    audit_log("job_application.updated", entity_type="job_application",
              entity_id=application_id, payload=updates)
    return api_single(row, entity="applications")


@router.delete("/{application_id}")
def delete_application(application_id: int):
    if not delete_row("wbom_job_applications", "application_id", application_id):
        raise HTTPException(404, "Application not found")
    audit_log("job_application.deleted", entity_type="job_application",
              entity_id=application_id)
    return {"deleted": True}
