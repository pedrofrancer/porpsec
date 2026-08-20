from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.audit import Audit
from app.models.opportunity import Opportunity
from app.schemas.audit import DiagnosisReport, DiagnosisItem, DiagnosisDigitalPresence, DiagnosisCommunication, DiagnosisRegional, DiagnosisRecommendation


def build_diagnosis(company: Company, audit: Audit | None, opportunities: list[Opportunity], db: Session) -> DiagnosisReport:
    """Monta o diagnóstico completo de uma empresa."""

    # Digital Presence
    website = DiagnosisItem(
        exists=bool(company.website),
        details={
            "url": company.website,
            "https": audit.has_https if audit else None,
            "response_time_ms": audit.response_time_ms if audit else None,
            "meta_title_length": audit.meta_title_length if audit else None,
            "meta_desc_length": audit.meta_desc_length if audit else None,
            "has_viewport": audit.has_viewport if audit else None,
            "has_blog_content": audit.has_blog_content if audit else None,
        } if audit else {},
        issues=_website_issues(audit, company),
    )

    instagram = DiagnosisItem(
        exists=bool(company.instagram),
        details={
            "public": audit.instagram_public if audit else None,
            "active_last_30d": audit.instagram_active if audit else None,
        } if audit and company.instagram else {},
        issues=_instagram_issues(audit, company),
    )

    facebook = DiagnosisItem(
        exists=bool(company.facebook),
        details={
            "active": audit.facebook_active if audit else None,
        } if audit and company.facebook else {},
        issues=_facebook_issues(audit, company),
    )

    google_business = DiagnosisItem(
        exists=audit.google_business_complete if audit else False,
        issues=_google_business_issues(audit, company),
    )

    digital_presence = DiagnosisDigitalPresence(
        website=website,
        instagram=instagram,
        facebook=facebook,
        google_business=google_business,
        digital_score=audit.digital_score if audit else 0,
        score_breakdown=_score_breakdown(audit),
    )

    # Communication / Automation
    whatsapp_signals = DiagnosisItem(
        exists=bool(audit and audit.whatsapp_catalog_link),
        details={
            "catalog_link": audit.whatsapp_catalog_link if audit else None,
            "responds_badge": audit.whatsapp_responds_badge if audit else None,
        } if audit else {},
        issues=_whatsapp_issues(audit, company),
    )

    scheduling = DiagnosisItem(
        exists=bool(audit and audit.has_scheduling),
        issues=[] if audit and audit.has_scheduling else ["Sem sistema de agendamento online detectado"],
    )

    cta_presence = DiagnosisItem(
        exists=bool(audit and audit.has_cta),
        issues=[] if audit and audit.has_cta else ["Nenhum call-to-action visível detectado"],
    )

    communication = DiagnosisCommunication(
        whatsapp_signals=whatsapp_signals,
        scheduling=scheduling,
        cta_presence=cta_presence,
    )

    # Management / CRM — não verificável
    management_crm = {
        "verifiable": False,
        "note": "Não verificável externamente nesta fase",
        "issues": [],
    }

    # Regional comparison
    regional = _get_regional_context(db, company.category_id, company.city_id) if company.category_id and company.city_id else None
    regional_comparison = DiagnosisRegional(
        available=regional is not None,
        sample_size=regional["total_audited"] if regional else 0,
        min_required=15,
        data=regional,
    )

    # Recommendations (from opportunities)
    recommendations = [
        DiagnosisRecommendation(
            priority=opp.priority,
            problem=opp.problem,
            evidence=opp.evidence,
            solution=opp.suggested_solution,
            impact=_impact_for_solution(opp.suggested_solution),
        )
        for opp in opportunities
    ]

    return DiagnosisReport(
        company_id=company.id,
        company_name=company.name,
        digital_presence=digital_presence,
        communication_automation=communication,
        management_crm=management_crm,
        regional_comparison=regional_comparison,
        recommendations=recommendations,
        generated_at=datetime.now(timezone.utc),
    )


def _website_issues(audit: Audit | None, company: Company) -> list[str]:
    issues = []
    if not company.website:
        issues.append("Empresa não possui website")
        return issues
    if audit:
        if not audit.has_https:
            issues.append("Site sem HTTPS válido")
        if audit.response_time_ms and audit.response_time_ms > 3000:
            issues.append(f"Site lento ({audit.response_time_ms}ms)")
        if not audit.has_meta_title or (audit.meta_title_length or 0) <= 10:
            issues.append("Meta title ausente ou muito curto")
        if not audit.has_meta_description or (audit.meta_desc_length or 0) <= 50:
            issues.append("Meta description ausente ou muito curta")
        if not audit.has_viewport:
            issues.append("Site sem meta viewport (não responsivo)")
        if audit.has_blog_content and audit.blog_freshness_days and audit.blog_freshness_days > 180:
            issues.append(f"Conteúdo desatualizado ({audit.blog_freshness_days} dias sem post)")
    return issues


def _instagram_issues(audit: Audit | None, company: Company) -> list[str]:
    issues = []
    if not company.instagram:
        issues.append("Instagram não informado")
        return issues
    if audit:
        if audit.instagram_public is False:
            issues.append("Perfil privado")
        if audit.instagram_active is False:
            issues.append("Sem publicações nos últimos 30 dias")
    return issues


def _facebook_issues(audit: Audit | None, company: Company) -> list[str]:
    issues = []
    if not company.facebook:
        return issues
    if audit and audit.facebook_active is False:
        issues.append("Perfil com pouco conteúdo ou inativo")
    return issues


def _google_business_issues(audit: Audit | None, company: Company) -> list[str]:
    issues = []
    if not audit or not audit.google_business_complete:
        issues.append("Perfil do Google Business incompleto ou não verificado")
    return issues


def _whatsapp_issues(audit: Audit | None, company: Company) -> list[str]:
    issues = []
    if not audit or not audit.whatsapp_catalog_link:
        issues.append("Nenhum link de catálogo WhatsApp Business detectado")
    if audit and not audit.whatsapp_responds_badge:
        issues.append("Sem selo de resposta rápida no Google Business")
    return issues


def _score_breakdown(audit: Audit | None) -> dict:
    if not audit:
        return {}
    return {
        "https": 15 if audit.has_https else 0,
        "response_time": 15 if audit.response_time_ms and audit.response_time_ms < 3000 else 0,
        "meta_title": 10 if audit.has_meta_title and (audit.meta_title_length or 0) > 10 else 0,
        "meta_description": 10 if audit.has_meta_description and (audit.meta_desc_length or 0) > 50 else 0,
        "viewport": 5 if audit.has_viewport else 0,
        "whatsapp": 10 if audit.has_whatsapp else 0,
        "cta": 5 if audit.has_cta else 0,
        "form": 5 if audit.has_form else 0,
        "scheduling": 10 if audit.has_scheduling else 0,
        "instagram": 5 if audit.instagram_active else 0,
        "google_business": 5 if audit.google_business_complete else 0,
        "blog_content": 5 if audit.has_blog_content and (audit.blog_freshness_days is None or audit.blog_freshness_days < 180) else 0,
    }


def _get_regional_context(db: Session, category_id: int | None, city_id: int | None) -> dict | None:
    """Média do mesmo segmento+cidade. Retorna None se < 15 empresas auditadas."""
    if not category_id or not city_id:
        return None

    MIN_SAMPLE = 15

    from app.models.company import Company as CompanyModel

    count = db.query(Audit).join(CompanyModel).filter(
        CompanyModel.category_id == category_id,
        CompanyModel.city_id == city_id,
    ).count()

    if count < MIN_SAMPLE:
        return None

    audits = db.query(Audit).join(CompanyModel).filter(
        CompanyModel.category_id == category_id,
        CompanyModel.city_id == city_id,
    ).all()

    return {
        "total_audited": count,
        "pct_without_site": round(sum(1 for a in audits if not a.has_whatsapp) / count * 100, 1),
        "pct_without_scheduling": round(sum(1 for a in audits if not a.has_scheduling) / count * 100, 1),
        "avg_score": round(sum(a.digital_score for a in audits) / count, 1),
    }


def _impact_for_solution(solution: str) -> str:
    impacts = {
        "Website Institucional": "Perda de credibilidade e ausência em buscas online",
        "Integração WhatsApp": "Dificuldade de contato pelos clientes",
        "Sistema de Agendamento": "Perda de clientes que preferem agendar online",
        "Gestão de Redes Sociais": "Engajamento baixo e ausência em redes sociais",
        "Otimização Google Business": "Perda de visibilidade em buscas locais",
        "Otimização SEO Básica": "Site difícil de encontrar nos mecanismos de busca",
        "Design Responsivo": "Experiência ruim em dispositivos móveis",
        "Marketing de Conteúdo": "Site sem tráfego orgânico",
        "Otimização de Performance": "Taxa de rejeição alta por lentidão",
    }
    return impacts.get(solution, "Impacto na presença digital")
