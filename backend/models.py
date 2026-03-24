from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class Failure(BaseModel):
    id: Optional[int] = None
    repo: str
    workflow: str
    branch: str
    run_id: int
    error_category: Optional[str] = None
    log_tail: Optional[str] = None
    diagnosis: Optional[str] = None
    fix_suggestion: Optional[str] = None
    status: str = "pending"
    created_at: Optional[datetime] = None

class DiagnosisRequest(BaseModel):
    run_id: int

class ApprovalRequest(BaseModel):
    run_id: int
    approved: bool
    comment: Optional[str] = None
