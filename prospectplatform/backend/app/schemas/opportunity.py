from pydantic import BaseModel
from datetime import datetime


class OpportunityRuleRead(BaseModel):
    id: int
    name: str
    description: str
    condition_field: str
    condition_operator: str
    condition_value: str | None
    required_categories: str | None
    suggested_solution: str
    priority: str
    is_active: bool

    model_config = {"from_attributes": True}


class OpportunityRead(BaseModel):
    id: int
    company_id: int
    audit_id: int
    rule_id: int | None
    problem: str
    evidence: str
    suggested_solution: str
    priority: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class OpportunityUpdateStatus(BaseModel):
    status: str
