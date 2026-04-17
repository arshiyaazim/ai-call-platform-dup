# ============================================================
# WBOM — Job Applications Routes
# Full CRUD for recruitment pipeline
# ============================================================
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from database import insert_row, get_row, update_row, delete_row, list_rows, search_rows, audit_log
from models import JobApplicationCreate, JobApplicationUpdate, JobApplicationResponse

router = APIRouter(prefix="/job-applications", tags=["job_applications"])


@router.post("", response_model=JobApplicationResponse, status_code=201)
def create_application(data: JobApplicationCreate):
    row = insert_row("wbom_job_applications", data.model_dump(exclude_none=True))
    audit_log("job_application.created", actor=data.source or "system",
              entity_type="job_application", entity_id=row.get("application_id"),
              payload={"applicant": data.applicant_name, "position": data.position})
    return row


@router.get("", response_model=list[JobApplicationResponse])
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
    return list_rows("wbom_job_applications", filters=filters, limit=limit, offset=offset)


@router.get("/{application_id}", response_model=JobApplicationResponse)
def get_application(application_id: int):
    row = get_row("wbom_job_applications", "application_id", application_id)
    if not row:
        raise HTTPException(404, "Application not found")
    return row


@router.put("/{application_id}", response_model=JobApplicationResponse)
def update_application(application_id: int, data: JobApplicationUpdate):
    updates = data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")
    row = update_row("wbom_job_applications", "application_id", application_id, updates)
    if not row:
        raise HTTPException(404, "Application not found")
    audit_log("job_application.updated", entity_type="job_application",
              entity_id=application_id, payload=updates)
    return row


@router.delete("/{application_id}")
def delete_application(application_id: int):
    if not delete_row("wbom_job_applications", "application_id", application_id):
        raise HTTPException(404, "Application not found")
    audit_log("job_application.deleted", entity_type="job_application",
              entity_id=application_id)
    return {"deleted": True}
