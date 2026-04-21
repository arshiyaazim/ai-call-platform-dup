# ============================================================
# WBOM — Recruitment Routes  (Sprint-3)
# WhatsApp candidate funnel: intake, scoring, assignment,
# stage advancement, metrics, reminders
# ============================================================
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import date

from database import execute_query, list_rows, count_rows
from models import (
    CandidateListResponse,
    CandidateDetailResponse,
    IntakeRequest,
    IntakeResponse,
    RecruiterAssignRequest,
    StageAdvanceRequest,
    RecruitmentMetricsResponse,
    ScoreResult,
)
import services.recruitment as svc

router = APIRouter(prefix="/recruitment", tags=["recruitment"])


# ── POST /recruitment/intake ─────────────────────────────────

@router.post("/intake", response_model=IntakeResponse, status_code=200)
def intake(body: IntakeRequest):
    """
    Process one inbound WhatsApp message.
    Returns the reply text to send back to the candidate.
    """
    result = svc.intake_message(phone=body.phone, message=body.message)
    return IntakeResponse(**result)


# ── GET /recruitment/candidates ──────────────────────────────

@router.get("/candidates", response_model=CandidateListResponse)
def list_candidates(
    funnel_stage: Optional[str] = None,
    score_bucket: Optional[str] = None,
    assigned_recruiter: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    filters: dict = {}
    if funnel_stage:
        filters["funnel_stage"] = funnel_stage
    if score_bucket:
        filters["score_bucket"] = score_bucket
    if assigned_recruiter:
        filters["assigned_recruiter"] = assigned_recruiter

    rows = list_rows("wbom_candidates", filters, limit=limit, offset=offset)
    total = count_rows("wbom_candidates", filters)
    return CandidateListResponse(items=[dict(r) for r in rows], total=total)


# ── GET /recruitment/candidates/{id} ────────────────────────

@router.get("/candidates/{candidate_id}", response_model=CandidateDetailResponse)
def get_candidate(candidate_id: int):
    rows = execute_query(
        "SELECT * FROM wbom_candidates WHERE candidate_id = %s LIMIT 1",
        (candidate_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Candidate not found")

    conv_rows = execute_query(
        """
        SELECT step, direction, message_text, collected_at
        FROM wbom_candidate_conversations
        WHERE candidate_id = %s
        ORDER BY collected_at
        """,
        (candidate_id,),
    )
    candidate = dict(rows[0])
    candidate["conversation"] = [dict(r) for r in conv_rows]
    return CandidateDetailResponse(**candidate)


# ── POST /recruitment/candidates/{id}/score ──────────────────

@router.post("/candidates/{candidate_id}/score", response_model=ScoreResult)
def rescore_candidate(candidate_id: int):
    try:
        result = svc.score_candidate(candidate_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ScoreResult(**result)


# ── POST /recruitment/candidates/{id}/assign ─────────────────

@router.post("/candidates/{candidate_id}/assign")
def assign(candidate_id: int, body: RecruiterAssignRequest):
    try:
        result = svc.assign_recruiter(candidate_id, body.recruiter_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return result


# ── POST /recruitment/candidates/{id}/advance ────────────────

@router.post("/candidates/{candidate_id}/advance")
def advance(candidate_id: int, body: StageAdvanceRequest):
    try:
        result = svc.advance_stage(candidate_id, body.to_stage)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return result


# ── GET /recruitment/metrics ─────────────────────────────────

@router.get("/metrics", response_model=RecruitmentMetricsResponse)
def metrics(ref_date: Optional[date] = None):
    data = svc.get_recruitment_metrics(ref_date=ref_date)
    return RecruitmentMetricsResponse(**data)


# ── GET /recruitment/reminders ───────────────────────────────

@router.get("/reminders")
def pending_reminders(limit: int = Query(50, le=200)):
    return svc.get_pending_reminders(limit=limit)
