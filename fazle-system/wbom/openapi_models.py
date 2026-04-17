# ============================================================
# WBOM — OpenAPI Response Models
# Pydantic models used as response_model on endpoints so that
# FastAPI auto-generates typed OpenAPI docs (/docs, /openapi.json).
# ============================================================
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Optional


# ── Meta / Envelope ──────────────────────────────────────────

class Meta(BaseModel):
    total: int = Field(description="Total number of records")
    page: int = Field(1, description="Current page number")
    count: int = Field(description="Number of records in this response")


class ListEnvelope(BaseModel):
    success: bool = True
    data: list[dict[str, Any]] = Field(description="Array of normalized rows")
    meta: Meta
    schema_: dict[str, str] = Field({}, alias="schema", description="Field→type map")
    version: str = "v1"

    model_config = {"populate_by_name": True}


class SingleEnvelope(BaseModel):
    success: bool = True
    data: dict[str, Any] = Field(description="Single normalized row")
    schema_: dict[str, str] = Field({}, alias="schema")
    version: str = "v1"

    model_config = {"populate_by_name": True}


class ErrorEnvelope(BaseModel):
    success: bool = False
    error: str
    version: str = "v1"


# ── Typed Entity Models (normalized API-side names) ──────────

class Employee(BaseModel):
    id: int
    name: Optional[str] = None
    phone: Optional[str] = None
    designation: Optional[str] = None
    status: Optional[str] = None
    salary: Optional[float] = None
    bkash: Optional[str] = None
    nagad: Optional[str] = None
    nid: Optional[str] = None
    bank: Optional[str] = None
    emergency_phone: Optional[str] = None
    address: Optional[str] = None
    joined: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    model_config = {"extra": "allow"}


class Transaction(BaseModel):
    id: int
    employee_name: Optional[str] = None
    employee_id: Optional[int] = None
    employee_phone: Optional[str] = None
    type: Optional[str] = None
    amount: Optional[float] = None
    method: Optional[str] = None
    status: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    reference: Optional[str] = None
    remarks: Optional[str] = None
    model_config = {"extra": "allow"}


class Client(BaseModel):
    id: int
    name: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    type: Optional[str] = None
    balance: Optional[float] = None
    terms: Optional[str] = None
    is_active: Optional[bool] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    model_config = {"extra": "allow"}


class Application(BaseModel):
    id: int
    name: Optional[str] = None
    phone: Optional[str] = None
    position: Optional[str] = None
    experience: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    applied_at: Optional[str] = None
    updated_at: Optional[str] = None
    model_config = {"extra": "allow"}


class AuditEntry(BaseModel):
    id: int
    time: Optional[str] = None
    event: Optional[str] = None
    actor: Optional[str] = None
    entity: Optional[str] = None
    entity_id: Optional[int] = None
    payload: Optional[Any] = None
    model_config = {"extra": "allow"}


class Payment(BaseModel):
    id: int
    employee_name: Optional[str] = None
    employee_id: Optional[int] = None
    amount: Optional[float] = None
    method: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    model_config = {"extra": "allow"}


# ── Typed List Envelopes ─────────────────────────────────────

class EmployeeListResponse(BaseModel):
    success: bool = True
    data: list[Employee]
    meta: Meta
    schema_: dict[str, str] = Field({}, alias="schema")
    version: str = "v1"
    model_config = {"populate_by_name": True}


class TransactionListResponse(BaseModel):
    success: bool = True
    data: list[Transaction]
    meta: Meta
    schema_: dict[str, str] = Field({}, alias="schema")
    version: str = "v1"
    model_config = {"populate_by_name": True}


class ClientListResponse(BaseModel):
    success: bool = True
    data: list[Client]
    meta: Meta
    schema_: dict[str, str] = Field({}, alias="schema")
    version: str = "v1"
    model_config = {"populate_by_name": True}


class ApplicationListResponse(BaseModel):
    success: bool = True
    data: list[Application]
    meta: Meta
    schema_: dict[str, str] = Field({}, alias="schema")
    version: str = "v1"
    model_config = {"populate_by_name": True}


class AuditListResponse(BaseModel):
    success: bool = True
    data: list[AuditEntry]
    meta: Meta
    schema_: dict[str, str] = Field({}, alias="schema")
    version: str = "v1"
    model_config = {"populate_by_name": True}


class PaymentListResponse(BaseModel):
    success: bool = True
    data: list[Payment]
    meta: Meta
    schema_: dict[str, str] = Field({}, alias="schema")
    version: str = "v1"
    model_config = {"populate_by_name": True}
