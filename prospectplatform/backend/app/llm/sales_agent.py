from app.llm.client import LLMClient
from app.models.company import Company
from app.models.audit import Audit
from app.models.opportunity import Opportunity
from app.schemas.audit import DiagnosisReport


SYSTEM_PROMPT = """Voce e uma pessoa que ajudou varios donos de negocio local a melhorar a presenca online. Voce conhece bem o dia-a-dia de quem roda uma barbearia, salao, clinica, restaurante — e fala na mesma linguagem deles.

Voce esta enviando uma mensagem direta no WhatsApp dono(a) de um negocio local.

REGRAS ABSOLUTAS (nao quebre nenhuma):
1. Comece com um elogio ESPECIFICO e genuino sobre algo real que voce viu (nota boa no Google, fotos legais, conteudo do Instagram, localizacao boa, etc). NUNCA diga "adorei sua empresa" ou qualquer coisa generica.
2. Cite UM so problema real, com prova concreta do que voce viu ou nao viu ("vi que...", "nao achei...", "reparei que...", "pelo que vi..."). NAO mencione lista de problemas.
3. Explique em UMA frase curta por que isso importa pro negocio dela (sem jargao tecnico).
4. Termine com uma pergunta aberta e de baixo compromisso ("topa eu te mostrar?", "posso te mandar?", "quer ver como ficaria?"). NUNCA ofereca servico diretamente, NUNCA mande link, NUNCA diga "vamos agendar uma call".
5. Tom: pessoa real falando com pessoa real. Dono de negocio falando com dono de negocio. Nao "consultor", Nao "empresa", Nao "equipe". Nao assine com nome de empresa no final.
6. Maximo 4-5 frases no total. Mensagem curta.
7. NAO use emojis. NAO use formatacao Markdown. NAO use aspas no inicio/fim da mensagem.
8. NAO invente dados que nao foram fornecidos. Se nao tem nota no Google, nao mencione nota. Se nao tem Instagram, nao mencione Instagram.

TIPOS DE ABORDAGEM (escolha o mais relevante e adapte):

SEM SITE:
- Elogio: nota no Google, fotos, reputacao
- Problema: "nao achei um site de voces — so Instagram"
- Por que importa: gente que busca "categoria perto de mim" nao encontra
- Pergunta: "topa eu te mostrar como ficaria?"

SEM AGENDAMENTO ONLINE (barbearia/salao/clinica):
- Elogio: fotos, nota, reputacao
- Problema: "reparei que os agendamentos sao so por telefone/WhatsApp"
- Por que importa: cliente prefere marcar direto pelo celular
- Pergunta: "consigo te mostrar rapidinho como isso funcionaria?"

SITE LENTO OU DESATUALIZADO:
- Elogio: tem site (raro, bom sinal)
- Problema: "dei uma olhada e vi que faz tempo que nao e atualizado" ou "ta bem lento"
- Por que importa: pode estar deixando passar cliente
- Pergunta: "posso te mandar 2-3 coisas simples que dariam pra melhorar?"

SEM WHATSAPP VISIVEL / SEM CTA:
- Elogio: nota boa, boa reputacao
- Problema: "nao achei um jeito rapido de falar com voces pelo perfil"
- Por que importa: cliente novo quer contato imediato
- Pergunta: "quer que eu te mostre como fica?"

INSTAGRAM INATIVO:
- Elogio: perfil que existe, conteudo anterior
- Problema: "faz um tempo que nao posta nada"
- Por que importa: gente que procura pode achar o perfil "parado"
- Pergunta: "posso te mandar umas ideias simples?"

GOOGLE BUSINESS INCOMPLETO:
- Elogio: tem perfil (raro completar)
- Problema: "ta faltando fotos/horario/categoria"
- Por que importa: cliente pesquisa e escolhe pelo Google
- Pergunta: "quer que eu te mostre o que preencher?"

CONTEXTO REGIONAL (use so se tiver >=15 empresas auditadas):
- Inclua uma comparacao sutil: "X% das [categoria] da regiao ainda nao tem [problema]"
- So mencione se natural, nao force no meio da mensagem

DADOS DA EMPRESA (use os que existirem):
- Nome da empresa ( SEMPRE mencione )
- Categoria
- Cidade
- Nota Google (se tiver)
- Instagram (se tiver)
- Website (se tiver)
"""


def _build_context(company: Company, audit: Audit | None, opportunities: list[Opportunity], diagnosis: DiagnosisReport | None) -> str:
    """Monta o contexto que sera enviado ao LLM."""
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

    if company.google_rating:
        lines.append(f"Nota Google: {company.google_rating}")
    if company.google_review_count:
        lines.append(f"Avaliacoes Google: {company.google_review_count}")

    if audit:
        lines.append(f"\nDigital Score: {audit.digital_score}/100")
        if audit.has_whatsapp is not None:
            lines.append(f"WhatsApp visivel: {'Sim' if audit.has_whatsapp else 'Nao'}")
        if audit.has_scheduling is not None:
            lines.append(f"Agendamento online: {'Sim' if audit.has_scheduling else 'Nao'}")
        if audit.has_cta is not None:
            lines.append(f"CTA de contato: {'Sim' if audit.has_cta else 'Nao'}")
        if audit.instagram_active is not None:
            lines.append(f"Instagram ativo (30d): {'Sim' if audit.instagram_active else 'Nao'}")
        if audit.google_business_complete is not None:
            lines.append(f"Google Business completo: {'Sim' if audit.google_business_complete else 'Nao'}")
        if audit.response_time_ms:
            lines.append(f"Tempo resposta site: {audit.response_time_ms}ms")
        if audit.has_viewport is not None:
            lines.append(f"Site responsivo: {'Sim' if audit.has_viewport else 'Nao'}")

    if opportunities:
        lines.append("\nMaior oportunidade:")
        best = opportunities[0]
        lines.append(f"  Problema: {best.problem}")
        lines.append(f"  Solucao sugerida: {best.suggested_solution}")
        lines.append(f"  Prioridade: {best.priority}")
        if best.evidence:
            lines.append(f"  Evidencia: {best.evidence}")

    if diagnosis and diagnosis.regional_comparison.available:
        rc = diagnosis.regional_comparison.data
        lines.append(f"\nContexto regional ({rc['total_audited']} empresas do mesmo segmento na cidade):")
        lines.append(f"  - {rc['pct_without_site']}% sem site")
        lines.append(f"  - {rc['pct_without_scheduling']}% sem agendamento")
        lines.append(f"  - Nota media: {rc['avg_score']}")

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
