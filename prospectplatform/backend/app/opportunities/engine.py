import yaml
from pathlib import Path
from dataclasses import dataclass
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.audit import Audit
from app.models.opportunity import Opportunity
from app.models.category import Category


RULES_PATH = Path(__file__).parent.parent.parent.parent / "config" / "opportunity_rules.yaml"


@dataclass
class OpportunityResult:
    """Resultado de uma oportunidade identificada."""
    problem: str
    evidence: str
    suggested_solution: str
    priority: str
    regional_context: dict | None = None


class OpportunityEngine:
    """Engine baseado em regras YAML + contexto regional."""

    MIN_SAMPLE = 15

    def __init__(self, db: Session):
        self.db = db
        self.rules = self._load_rules()

    def _load_rules(self) -> list[dict]:
        with open(RULES_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("rules", [])

    def _evaluate_condition(self, audit: Audit | None, rule: dict) -> bool:
        """Verifica se a regra se aplica à empresa auditada."""
        field_name = rule["condition_field"]
        operator = rule["condition_operator"]
        expected_value = rule.get("condition_value")

        # Se é um campo da empresa (não do audit)
        if field_name == "website":
            return True  # sempre avalia, o operador is_empty é tratado separado

        if audit is None:
            return operator == "is_false"

        actual_value = getattr(audit, field_name, None)

        if operator == "is_empty":
            return actual_value is None or actual_value == ""
        elif operator == "is_false":
            return actual_value is False or actual_value is None
        elif operator == "is_true":
            return actual_value is True
        elif operator == "gt":
            if actual_value is None:
                return False
            return actual_value > int(expected_value)
        elif operator == "lt":
            if actual_value is None:
                return False
            return actual_value < int(expected_value)

        return False

    def _get_regional_context(self, company: Company) -> dict | None:
        """Calcula média do mesmo segmento+cidade."""
        if not company.category_id or not company.city_id:
            return None

        count = self.db.query(Audit).join(Company).filter(
            Company.category_id == company.category_id,
            Company.city_id == company.city_id,
        ).count()

        if count < self.MIN_SAMPLE:
            return None

        audits = self.db.query(Audit).join(Company).filter(
            Company.category_id == company.category_id,
            Company.city_id == company.city_id,
        ).all()

        return {
            "total_audited": count,
            "pct_without_site": round(sum(1 for a in audits if not a.has_whatsapp) / count * 100, 1),
            "pct_without_scheduling": round(sum(1 for a in audits if not a.has_scheduling) / count * 100, 1),
            "avg_score": round(sum(a.digital_score for a in audits) / count, 1),
        }

    def _get_company_value(self, company: Company, field_name: str):
        """Busca valor do campo na empresa."""
        return getattr(company, field_name, None)

    def evaluate(self, company: Company) -> list[OpportunityResult]:
        """Avalia todas as regras para uma empresa e retorna oportunidades."""
        audit = self.db.query(Audit).filter(Audit.company_id == company.id).order_by(Audit.id.desc()).first()

        regional_ctx = self._get_regional_context(company)
        results = []

        category = self.db.get(Category, company.category_id) if company.category_id else None
        category_slug = category.slug if category else ""

        for rule in self.rules:
            # Filtro por categoria obrigatória
            required_cats = rule.get("required_categories", [])
            if required_cats and category_slug not in required_cats:
                continue

            # Campo pode ser do audit ou da empresa
            field_name = rule["condition_field"]

            if field_name == "website":
                applies = not bool(company.website)
            else:
                applies = self._evaluate_condition(audit, rule)

            if not applies:
                continue

            # Construir evidência
            evidence = self._build_evidence(rule, company, audit)

            results.append(OpportunityResult(
                problem=rule["description"],
                evidence=evidence,
                suggested_solution=rule["suggested_solution"],
                priority=rule["priority"],
                regional_context=regional_ctx,
            ))

        return results

    def _build_evidence(self, rule: dict, company: Company, audit: Audit | None) -> str:
        """Constrói string de evidência para a oportunidade."""
        field_name = rule["condition_field"]

        if field_name == "website":
            return f"Empresa {company.name} não possui website cadastrado"
        if field_name == "response_time_ms":
            ms = audit.response_time_ms if audit else None
            return f"Site com tempo de resposta de {ms}ms" if ms else "Tempo de resposta não medido"
        if field_name == "has_scheduling":
            return f"Empresa do segmento {company.category.name if company.category else ''} sem sistema de agendamento online"
        if field_name == "meta_title_length":
            length = audit.meta_title_length if audit else 0
            return f"Meta title com apenas {length} caracteres"
        if field_name == "has_viewport":
            return "Site sem meta viewport — não é responsivo para mobile"
        if field_name == "instagram_active":
            return "Instagram sem publicações nos últimos 30 dias"
        if field_name == "google_business_complete":
            return "Perfil do Google Business incompleto ou não verificado"
        if field_name == "blog_freshness_days":
            days = audit.blog_freshness_days if audit else None
            return f"Conteúdo do blog sem atualização há {days} dias" if days else "Blog sem conteúdo detectável"

        return rule.get("description", "Condição identificada")

    def save_opportunities(self, company: Company, results: list[OpportunityResult]) -> list[Opportunity]:
        """Salva oportunidades no banco e retorna."""
        saved = []
        for r in results:
            # Verificar se já existe esta oportunidade para a empresa
            existing = self.db.query(Opportunity).filter(
                Opportunity.company_id == company.id,
                Opportunity.suggested_solution == r.suggested_solution,
            ).first()

            if existing:
                continue

            opp = Opportunity(
                company_id=company.id,
                audit_id=None,  # será preenchido se audit existir
                problem=r.problem,
                evidence=r.evidence,
                suggested_solution=r.suggested_solution,
                priority=r.priority,
            )
            self.db.add(opp)
            self.db.flush()
            saved.append(opp)

        self.db.commit()
        return saved
