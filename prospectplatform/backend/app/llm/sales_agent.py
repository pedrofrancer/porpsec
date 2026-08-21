from app.llm.client import LLMClient
from app.models.company import Company
from app.models.audit import Audit
from app.models.opportunity import Opportunity
from app.schemas.audit import DiagnosisReport


SYSTEM_PROMPT = """Voce e uma pessoa que ajuda donos de negocio local a melhorar a presenca online. Voce fala como quem ja trabajou com varios negocios parecidos — direto, sem papel, sem firula.

MENSAGEM: WhatsApp direto pro dono(a). Maximo 4 frases.

REGRAS (nao quebre nenhuma):

1. INCLUA O NOME DA EMPRESA NA MENSAGEM. SEMPRE. Se "Barbearia do Marco", escreva "Barbearia do Marco" na mensagem. Isso e obrigatorio pra validacao passar.

2. CITE UM DADO REAL da auditoria — algo que voce VISUOU no perfil/ site da empresa. Sem elogio generico. Exemplos de dados citaveis:
   - "seu Google mostra nota X com Y avaliacoes"
   - "vi que nao tem site, so o Instagram"
   - "o site nao abre no celular" / "demora pra carregar"
   - "nao achei horario de funcionamento no Google"
   - "vi que o Instagram ta sem postar faz tempo"
   - "nao tem como agendar pelo site"
   - "o perfil do Google ta incompleto"
   Se voce NAO tiver nenhum dado concreto pra citar, responda EXATAMENTE: INSUFFICIENT_DATA

2. LIGUE a dor a uma OPORTUNIDADE REAL que foi identificada. Nao invente problema novo. A mensagem tem que ser rastreavel ate o dado da auditoria.

3. VARE A ESTRUTURA. Nao abra sempre com "Oi, tudo bem?" ou "Vi o [nome] no Google". Varie:
   - Pode comecar com a constatacao direta ("Seu Google ta sem foto...")
   - Pode comecar com o dado positivo seguido do problema
   - Pode comecar com a pergunta
   - Nunca a mesma construcao duas vezes seguidas

4. TOM: 1 pessoa real conversando com outra. Nao "consultor". Nao "equipe". Nao "empresa". Nao assine com nome. Nao use emojis. Nao use Markdown. Nao use "Olá! Tudo bem?" de abertura.

5. SEJA ESPECIFICA mas sem jargao tecnico. Em vez de "SEO otimizado", diga "quem pesquisa [categoria] no Google nao te encontra". Em vez de "responsividade mobile", diga "o site nao abre direito no celular".

DADOS DA EMPRESA (use como base, nao invente nada que nao esteja aqui):
"""


def _build_context(company: Company, audit: Audit | None, opportunities: list[Opportunity], diagnosis: DiagnosisReport | None) -> str:
    """Monta o contexto rico de dados concretos para o LLM."""
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
    if company.facebook:
        lines.append(f"Facebook: {company.facebook}")

    if company.google_rating:
        lines.append(f"Nota Google: {company.google_rating} ({company.google_review_count or '?'} avaliacoes)")

    if audit:
        lines.append(f"\n--- DADOS DA AUDITORIA (fonte: verificacao automatica) ---")
        lines.append(f"Score digital: {audit.digital_score}/100")

        if company.website:
            if audit.has_https is not None:
                lines.append(f"HTTPS: {'Sim' if audit.has_https else 'NAO — site sem certificado SSL'}")
            if audit.response_time_ms:
                status = "OK" if audit.response_time_ms < 3000 else f"LENTOS ({audit.response_time_ms}ms)"
                lines.append(f"Tempo de carregamento: {status}")
            if audit.has_viewport is not None:
                lines.append(f"Responsivo (mobile): {'Sim' if audit.has_viewport else 'NAO — nao abre direito no celular'}")
            if audit.has_meta_title is not None:
                title_ok = audit.has_meta_title and (audit.meta_title_length or 0) > 10
                lines.append(f"Meta title: {'OK' if title_ok else 'Ausente ou muito curto'}")
            if audit.has_meta_description is not None:
                desc_ok = audit.has_meta_description and (audit.meta_desc_length or 0) > 50
                lines.append(f"Meta description: {'OK' if desc_ok else 'Ausente ou muito curta'}")
            if audit.has_blog_content is not None:
                if audit.has_blog_content and audit.blog_freshness_days:
                    lines.append(f"Blog: desatualizado ({audit.blog_freshness_days} dias sem post)")
                elif audit.has_blog_content:
                    lines.append(f"Blog: com conteudo")
                else:
                    lines.append(f"Blog: sem blog")
        else:
            lines.append(f"Empresa NAO tem website")

        if company.instagram:
            if audit.instagram_public is not None:
                lines.append(f"Instagram publico: {'Sim' if audit.instagram_public else 'NAO — perfil privado'}")
            if audit.instagram_active is not None:
                lines.append(f"Instagram ativo (30d): {'Sim' if audit.instagram_active else 'NAO — sem posts recentes'}")

        if company.facebook:
            if audit.facebook_active is not None:
                lines.append(f"Facebook ativo: {'Sim' if audit.facebook_active else 'NAO'}")

        lines.append(f"Google Business completo: {'Sim' if audit.google_business_complete else 'NAO — perfil incompleto'}")

        if audit.has_whatsapp is not None:
            lines.append(f"WhatsApp visivel no site/perfil: {'Sim' if audit.has_whatsapp else 'NAO'}")
        if audit.has_scheduling is not None:
            lines.append(f"Agendamento online: {'Sim' if audit.has_scheduling else 'NAO'}")
        if audit.has_cta is not None:
            lines.append(f"Call-to-action visivel: {'Sim' if audit.has_cta else 'NAO'}")
        if audit.has_form is not None:
            lines.append(f"Formulario de contato: {'Sim' if audit.has_form else 'NAO'}")
        if audit.whatsapp_catalog_link is not None:
            lines.append(f"Catalogo WhatsApp: {'Sim' if audit.whatsapp_catalog_link else 'NAO'}")

    if opportunities:
        lines.append(f"\n--- OPORTUNIDADES IDENTIFICADAS ---")
        for i, opp in enumerate(opportunities[:3], 1):
            lines.append(f"#{i} [{opp.priority}] {opp.problem}")
            if opp.evidence:
                lines.append(f"   Evidencia: {opp.evidence}")
            lines.append(f"   Solucao: {opp.suggested_solution}")

    if diagnosis and diagnosis.regional_comparison.available:
        rc = diagnosis.regional_comparison.data
        lines.append(f"\n--- CONTEXTO REGIONAL ---")
        lines.append(f"Amostra: {rc['total_audited']} empresas do mesmo segmento na cidade")
        lines.append(f"Sem site: {rc['pct_without_site']}%")
        lines.append(f"Sem agendamento: {rc['pct_without_scheduling']}%")
        lines.append(f"Nota media: {rc['avg_score']}")

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
    user_prompt = (
        "Gere UMA mensagem curta (maximo 5 frases) de abordagem no WhatsApp "
        "para o dono(a) desta empresa. Siga as regras do system prompt.\n\n"
        f"DADOS DA EMPRESA:\n{context}"
    )

    return await client.chat(SYSTEM_PROMPT, user_prompt, temperature=0.8)


def _fallback_message(company: Company, audit: Audit | None, opportunities: list[Opportunity]) -> str:
    """Mensagem fallback quando LLM nao esta configurado."""
    name = company.name
    cat = company.category.name if company.category else "seu negocio"

    if not company.website:
        return (
            f"Opa, tudo bem? Vi o {name} no Google, nota boa! "
            f"Só nao achei um site de voces — so Instagram. "
            f"Um site simples ajudaria bastante gente que busca '{cat} perto de mim' a te encontrar antes dos concorrentes. "
            f"Topa eu te mostrar como ficaria?"
        )

    if audit and not audit.has_scheduling:
        return (
            f"Oi! Passei aqui pelo Google e adorei as fotos do {name}! "
            f"Reparei que os agendamentos ainda sao so por telefone/WhatsApp — "
            f"muita cliente prefere marcar horario direto pelo celular, sem precisar esperar resposta. "
            f"Consigo te mostrar rapidinho como isso funcionaria pro negocio de voces?"
        )

    if audit and audit.instagram_active is False:
        return (
            f"Oi, tudo bem? Vi o {name} no Instagram, conteudo bom! "
            f"Mas faz um tempo que nao posta nada — gente que procura pode achar o perfil parado. "
            f"Posso te mandar umas ideias simples pra voltar a aparecer?"
        )

    if opportunities:
        opp = opportunities[0]
        return (
            f"Oi! Vi o {name} no Google — {cat} na região de {company.city.name if company.city else 'sua cidade'}. "
            f"Notei que {opp.problem.lower()}. "
            f"Quer que eu te mostre como resolver isso?"
        )

    return (
        f"Oi! Vi o {name} no Google e gostaria de conversar sobre a presenca online. "
        f"Topa uma troca rapida de ideias?"
    )
