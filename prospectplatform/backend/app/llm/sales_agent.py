from app.llm.client import LLMClient
from app.models.company import Company
from app.models.audit import Audit
from app.models.opportunity import Opportunity
from app.schemas.audit import DiagnosisReport


SYSTEM_PROMPT = """Você é um consultor de transformação digital que aborda donos de pequenos negócios locais de forma consultiva e respeitosa.

REGRAS:
- Mensagem curta (máximo 3 frases)
- Tom consultivo, nunca agressivo ou vendedor
- Citar 1 problema concreto que a empresa tem (com evidência)
- Sugerir 1 solução específica
- Se disponível, incluir comparativo regional (ex: "X% das barbearias da sua região não têm site")
- NUNCA inventar dados — use apenas o que foi fornecido
- Não usar emojis
- Assinar como "Equipe de Consultoria Digital"
- NÃO enviar link de agendamento — apenas sinalizar interesse em conversar

EXEMPLO:
"Sr. Marco, notei que a Barbearia do Marco não possui site, enquanto 60% das barbearias da região já investiram nisso. Podemos conversar sobre como mudar isso? Equipe de Consultoria Digital"
"""


def _build_context(company: Company, audit: Audit | None, opportunities: list[Opportunity], diagnosis: DiagnosisReport | None) -> str:
    """Monta o contexto que será enviado ao LLM."""
    lines = [
        f"Empresa: {company.name}",
        f"Categoria: {company.category.name if company.category else 'N/A'}",
        f"Cidade: {company.city.name if company.city else 'N/A'}",
    ]

    if company.phone:
        lines.append(f"Telefone: {company.phone}")
    if company.website:
        lines.append(f"Website: {company.website}")
    if company.instagram:
        lines.append(f"Instagram: {company.instagram}")

    if audit:
        lines.append(f"\nDigital Score: {audit.digital_score}/100")
        if audit.has_https is not None:
            lines.append(f"HTTPS: {'Sim' if audit.has_https else 'Não'}")
        if audit.response_time_ms:
            lines.append(f"Tempo resposta: {audit.response_time_ms}ms")
        if audit.has_whatsapp is not None:
            lines.append(f"WhatsApp visível: {'Sim' if audit.has_whatsapp else 'Não'}")
        if audit.has_scheduling is not None:
            lines.append(f"Agendamento online: {'Sim' if audit.has_scheduling else 'Não'}")
        if audit.instagram_active is not None:
            lines.append(f"Instagram ativo (30d): {'Sim' if audit.instagram_active else 'Não'}")
        if audit.google_business_complete is not None:
            lines.append(f"Google Business completo: {'Sim' if audit.google_business_complete else 'Não'}")

    if opportunities:
        lines.append("\nOportunidades identificadas:")
        for opp in opportunities[:3]:
            lines.append(f"  - [{opp.priority}] {opp.problem} -> {opp.suggested_solution}")

    if diagnosis and diagnosis.regional_comparison.available:
        rc = diagnosis.regional_comparison.data
        lines.append(f"\nContexto regional ({rc['total_audited']} empresas do mesmo segmento na cidade):")
        lines.append(f"  - {rc['pct_without_site']}% sem site")
        lines.append(f"  - {rc['pct_without_scheduling']}% sem agendamento")
        lines.append(f"  - Nota média: {rc['avg_score']}")

    return "\n".join(lines)


async def generate_outreach_message(
    company: Company,
    audit: Audit | None,
    opportunities: list[Opportunity],
    diagnosis: DiagnosisReport | None = None,
) -> str:
    """Gera mensagem curta de abordagem usando LLM."""
    client = LLMClient()

    if not client.is_configured:
        return _fallback_message(company, audit, opportunities)

    context = _build_context(company, audit, opportunities, diagnosis)
    user_prompt = f"Gere uma mensagem de abordagem consultiva para o dono desta empresa:\n\n{context}"

    return await client.chat(SYSTEM_PROMPT, user_prompt, temperature=0.7)


def _fallback_message(company: Company, audit: Audit | None, opportunities: list[Opportunity]) -> str:
    """Mensagem fallback quando LLM não está configurado."""
    problem = ""
    if not company.website:
        problem = "a ausência de website"
    elif audit and not audit.has_scheduling:
        problem = "a falta de agendamento online"
    elif audit and audit.instagram_active is False:
        problem = "o Instagram sem atividade recente"
    elif opportunities:
        problem = opportunities[0].problem.lower()

    if problem:
        return f"Olá, sou consultor digital e notei {problem} na sua empresa. Podemos conversar sobre como resolver isso? Equipe de Consultoria Digital"

    return "Olá, sou consultor digital e gostaria de conversar sobre a presença online da sua empresa. Podemos agendar uma conversa rápida? Equipe de Consultoria Digital"
