from pydantic import BaseModel
from datetime import datetime


class AuditRead(BaseModel):
    id: int
    company_id: int
    digital_score: int

    # Website
    has_https: bool | None
    response_time_ms: int | None
    has_whatsapp: bool | None
    has_cta: bool | None
    has_form: bool | None
    has_scheduling: bool | None
    has_meta_title: bool | None
    has_meta_description: bool | None
    meta_title_length: int | None
    meta_desc_length: int | None
    has_viewport: bool | None
    has_blog_content: bool | None
    blog_freshness_days: int | None

    # Redes sociais
    instagram_exists: bool | None
    instagram_public: bool | None
    instagram_active: bool | None
    facebook_exists: bool | None
    facebook_active: bool | None
    google_business_complete: bool | None

    # WhatsApp signals
    whatsapp_catalog_link: bool | None
    whatsapp_responds_badge: bool | None

    raw_data: str | None
    audited_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditCreate(BaseModel):
    company_id: int


# --- Diagnosis schemas ---

class DiagnosisItem(BaseModel):
    exists: bool = False
    details: dict = {}
    issues: list[str] = []


class DiagnosisDigitalPresence(BaseModel):
    website: DiagnosisItem
    instagram: DiagnosisItem
    facebook: DiagnosisItem
    google_business: DiagnosisItem
    digital_score: int
    score_breakdown: dict


class DiagnosisCommunication(BaseModel):
    whatsapp_signals: DiagnosisItem
    scheduling: DiagnosisItem
    cta_presence: DiagnosisItem


class DiagnosisRegional(BaseModel):
    available: bool
    sample_size: int
    min_required: int
    data: dict | None = None


class DiagnosisRecommendation(BaseModel):
    priority: str
    problem: str
    evidence: str
    solution: str
    impact: str


class DiagnosisReport(BaseModel):
    company_id: int
    company_name: str
    digital_presence: DiagnosisDigitalPresence
    communication_automation: DiagnosisCommunication
    management_crm: dict
    regional_comparison: DiagnosisRegional
    recommendations: list[DiagnosisRecommendation]
    generated_at: datetime
