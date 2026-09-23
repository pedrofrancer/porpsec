# TechSpec — ProspectPlatform EU (Prospecção Multicanal + Template Automático)

**Versão:** 0.2
**Companheiro de:** `prd.md`
**Base de código analisada:** `porpsec-master/prospectplatform` (FastAPI + SQLAlchemy + SQLite/Postgres, Playwright, LLM via API OpenAI-compatible, microserviço Node/Baileys para WhatsApp)

---

## 1. Arquitetura atual (linha de base, confirmada no código)

```
┌─────────────────┐     ┌──────────────────┐     ┌───────────────────┐
│ Collectors        │────▶│ Auditors           │────▶│ OpportunityEngine   │
│ google_maps.py     │     │ website_auditor.py │     │ engine.py (YAML)    │
│ csv_collector.py   │     │ (Playwright async) │     │                     │
└─────────────────┘     └──────────────────┘     └──────────┬─────────┘
                                                                │
                                                                ▼
┌─────────────────┐     ┌──────────────────┐     ┌───────────────────┐
│ WhatsApp sender    │◀────│ Dispatcher          │◀────│ sales_agent.py      │
│ (Node/Baileys)     │     │ dispatcher.py       │     │ (LLM + Validator)   │
│ /send /status       │     │ fila + rate-limit   │     │                     │
└─────────────────┘     └──────────────────┘     └───────────────────┘
```

Pontos-chave do código existente que a evolução precisa **respeitar ou substituir explicitamente**:

- `Dispatcher.run_cycle()` (`backend/app/sending/dispatcher.py`) é o orquestrador único: auto-coleta → auto-enfileira → audita → gera oportunidade → gera mensagem → valida → envia. É síncrono por empresa, com delay aleatório entre envios (`SEND_DELAY_MIN_MS`/`MAX_MS`).
- `ContentValidator` (mesmo arquivo) é o guarda-corpo de qualidade de mensagem: bloqueia placeholders, exige nome da empresa, exige palavra-chave de "especificidade", exige referência a uma oportunidade real.
- `Company` (`backend/app/models/company.py`) **não tem campo de e-mail**. Tem `phone`, `website`, `instagram`, `facebook`.
- `Message` (`backend/app/models/message.py`) é genérico o suficiente (`message_text`, `status`, `sent_at`) mas **não tem campo de canal** nem de thread/conversa.
- `whatsapp-sender/index.js`: o listener `sock.ev.on('messages.upsert', ...)` está vazio — **não emite nada para o backend**. Esse é o ponto exato que precisa mudar para viabilizar detecção de resposta.
- Não existe nenhum módulo de e-mail (`app/sending/` só tem `dispatcher.py` e `whatsapp_client.py`).
- `GoogleMapsCollector` está fixado em `locale="pt-BR"` e monta a query como `"{categoria} em {cidade}"` (português). Não extrai e-mail.
- `Settings` (`backend/app/core/config.py`) tem `SEND_WINDOW_START/END` fixos em horário de Brasília (BRT hardcoded via `ZoneInfo("America/Sao_Paulo")` no dispatcher) — não é parametrizável por país/fuso.

## 2. Visão da arquitetura alvo

Novos componentes (em negrito = novo; os demais são reaproveitados/adaptados):

```
Collectors (multi-país) ──▶ Auditors (+ extração de e-mail e identidade visual)
        │
        ▼
OpportunityEngine (reaproveitado)
        │
        ▼
**ChannelRouter** (decide e-mail vs WhatsApp por empresa)
        │
        ├──▶ sales_agent (outreach) ──▶ **EmailSender** ──▶ Provedor SMTP/API
        │                                     │
        │                                     ▼
        │                          **InboundEmailListener** (IMAP/webhook)
        │
        └──▶ sales_agent (outreach) ──▶ WhatsAppClient (Baileys OU Cloud API)
                                              │
                                              ▼
                                   **InboundWhatsAppListener** (webhook do
                                    whatsapp-sender, hoje inexistente)

**ReplyEventHandler** (comum aos dois canais)
        │
        ▼
**BrandKitExtractor** (logo, cores, fotos, textos da empresa)
        │
        ▼
**SiteTemplateEngine** (seleciona template por categoria + injeta BrandKit)
        │
        ▼
**PreviewPublisher** (gera HTML estático, publica em hosting, retorna URL)
        │
        ▼
**FollowUpComposer** (mensagem curta de acompanhamento com o link) ──▶ envia
        pelo mesmo canal da resposta recebida
```

## 3. Mudanças no modelo de dados

### 3.1 `companies`
Adicionar:
- `email: str | None` — e-mail de contato extraído (site, Google Business, ou importação).
- `country_id` (novo FK, ou reaproveitar `states`/`regions` já existentes se a hierarquia `geography.py` for estendida com países europeus — a tabela `Country` **já existe** em `geography.py`, só nunca foi populada além do Brasil).
- `preferred_channel: str | None` (`"email"` | `"whatsapp"`) — resultado do `ChannelRouter`, congelado na primeira decisão.
- `whatsapp_business_signal: bool | None` — já existe parcialmente como `Audit.whatsapp_catalog_link`/`whatsapp_responds_badge`; promover a um campo de decisão explícito na company ou manter derivado do audit mais recente (recomendado: manter no audit, `ChannelRouter` só lê).

### 3.2 `messages`
Adicionar:
- `channel: str` (`"email"` | `"whatsapp"`) — hoje implícito (só existe WhatsApp).
- `message_type: str` (`"outreach"` | `"template_followup"`) — para diferenciar a primeira mensagem do envio do template.
- `thread_id: str | None` — id da thread de e-mail (`Message-ID`/`References`) ou id da conversa WhatsApp, necessário para responder no lugar certo e para o listener saber a qual outreach uma resposta pertence.
- `subject: str | None` — só relevante para e-mail.

### 3.3 Nova tabela `inbound_replies`
```
id, company_id (FK), message_id (FK messages.id, outreach original),
channel, raw_content, received_at, processed_at, resulted_in_template (bool)
```
Registra cada resposta recebida e o resultado do processamento — necessário para idempotência ("só dispara o template na primeira resposta") e para debug.

### 3.4 Nova tabela `site_previews`
```
id, company_id (FK), template_slug, brand_kit_json (Text),
preview_url, generated_at, sent_at, message_id (FK, o template_followup)
```
Registra o que foi gerado e enviado, permitindo reenvio manual se necessário e exibição no painel.

### 3.5 `Audit` (extensão)
Adicionar campos usados pelo `BrandKitExtractor` (evita reprocessar o site na hora do template):
- `logo_url: str | None`
- `dominant_colors: str | None` (JSON list de hex)
- `og_image_url: str | None` (imagem de destaque do site, útil como hero image do template)

## 4. Componentes novos — detalhamento

### 4.1 `ChannelRouter` (`app/prospecting/channel_router.py`, novo)
Regra determinística (não LLM), executada uma vez por empresa antes do primeiro enfileiramento:

```python
def decide_channel(company: Company, audit: Audit | None) -> str | None:
    has_whatsapp_signal = bool(audit and (audit.whatsapp_catalog_link or audit.whatsapp_responds_badge))
    has_phone = bool(company.phone)
    has_email = bool(company.email)

    if has_phone and has_whatsapp_signal:
        return "whatsapp"
    if has_email:
        return "email"
    if has_phone:
        return "whatsapp"  # fallback: tenta mesmo sem sinal confirmado
    return None  # não elegível
```
Persistido em `Company.preferred_channel` na primeira vez que a empresa entra na fila (nunca recalculado depois — evita mandar outreach por um canal e template por outro).

### 4.2 Coleta multi-país (`GoogleMapsCollector`, refatorado)
- Extrair `locale`, idioma da query, e domínio do Google Maps (`google.com/maps` já é global; mudar é sobretudo o parâmetro `hl=` e o texto da query) para uma tabela de configuração por país, ex. `config/collection_targets_eu.yaml`:
  ```yaml
  targets:
    - country_code: PT
      locale: pt-PT
      category_slug: barbearia
      city_name: Lisboa
      max_results: 20
    - country_code: ES
      locale: es-ES
      category_slug: peluqueria
      city_name: Madrid
      max_results: 20
  ```
- `Category`/`Subcategory` precisam de um mapeamento de slug→termo de busca por idioma (hoje o slug em si é usado como texto de busca — `barbearia` funciona em pt, mas não em `es`/`en`/`de`). Introduzir `CategoryTranslation(category_id, locale, search_term)`.
- Extração de e-mail: adicionar ao `_extract_detail()` do coletor uma tentativa de achar e-mail no próprio card do Google Maps (raramente presente) e, principalmente, delegar ao `WebsiteAuditor` (que já abre o site) a extração de `mailto:` links e texto de página de contato via regex de e-mail.
- Fuso horário e janela de envio (`SEND_WINDOW_START/END`) precisam ser por país, não fixos em BRT — mover para uma tabela `country_settings` ou config YAML com `timezone` e `send_window` por `country_code`.

### 4.3 `EmailSender` (`app/sending/email_client.py`, novo)
Duas opções técnicas (decisão de produto, não bloqueia o design da interface):

- **Opção A — SMTP simples** (Google Workspace/Microsoft 365/SMTP relay): mais barato, mas entregabilidade (SPF/DKIM/DMARC, reputação de IP) exige configuração cuidadosa de domínio e aquecimento — mesmo princípio do `WarmupManager` já existente para WhatsApp deve ser **replicado para e-mail** (limite diário crescente por caixa de envio).
- **Opção B — Provedor transacional com API** (SendGrid, Postmark, Resend, Amazon SES): melhor entregabilidade e, crucialmente, **suporte nativo a inbound parsing** (webhook quando alguém responde), o que simplifica MUITO o item 4.4 abaixo. **Recomendado** por isso.

Interface proposta (agnóstica de provedor, seguindo o padrão já usado em `LLMClient`/`WhatsAppClient`):
```python
class EmailSender:
    async def send(self, to: str, subject: str, body: str, in_reply_to: str | None = None) -> dict: ...
    async def is_configured(self) -> bool: ...
```

### 4.4 Detecção de resposta

**E-mail (via provedor com inbound parsing, ex. SendGrid Inbound Parse / Postmark Inbound Webhook):**
- Novo endpoint `POST /api/v1/webhooks/email-inbound` que recebe o payload do provedor, casa o `In-Reply-To`/`References` header com `Message.thread_id`, cria um registro em `inbound_replies`, e dispara o `ReplyEventHandler` de forma assíncrona.
- Alternativa sem provedor com webhook (Opção A/SMTP puro): job periódico via IMAP (`imaplib`) rodando a cada N minutos, procurando respostas na caixa de entrada que referenciem `Message-ID`s enviados — mais simples de montar, mas com latência maior (não bate a meta de "< 5 min" do PRD com folga).

**WhatsApp:**
- Mudar `whatsapp-sender/index.js`:
  ```js
  sock.ev.on('messages.upsert', ({ messages }) => {
      for (const m of messages) {
          if (m.key.fromMe) continue;
          const phone = m.key.remoteJid.replace('@s.whatsapp.net', '');
          const text = m.message?.conversation || m.message?.extendedTextMessage?.text || '';
          // Notifica o backend
          notifyBackend(phone, text, m.messageTimestamp);
      }
  });
  ```
- `notifyBackend` faz um `POST` para um novo endpoint `POST /api/v1/webhooks/whatsapp-inbound` no backend FastAPI, com `{ phone, text, timestamp }`.
- O backend casa `phone` com `Company.phone` (normalizado — ver débito técnico já registrado no `STATUS.md` sobre formato de telefone inconsistente; **esta é a hora de resolver isso**, pois agora o telefone vira chave de correlação de webhook, não só destino de envio) e verifica se existe uma `Message` de outreach `enviado` para essa empresa sem resposta registrada ainda.

**`ReplyEventHandler`** (comum, `app/prospecting/reply_handler.py`, novo):
```python
async def handle_reply(company_id: int, channel: str, raw_content: str, thread_id: str | None):
    # idempotência: já processamos uma resposta pra essa empresa?
    if already_has_processed_reply(company_id):
        return
    log_inbound_reply(...)
    brand_kit = await BrandKitExtractor(db).extract(company)
    preview = await SiteTemplateEngine(db).build(company, brand_kit)
    url = await PreviewPublisher(db).publish(preview)
    followup_text = await FollowUpComposer.compose(company, raw_content, url)
    await send_via_channel(channel, company, followup_text, thread_id)
```

### 4.5 `BrandKitExtractor` (`app/branding/extractor.py`, novo)
Reaproveita a sessão Playwright que o `WebsiteAuditor` já abre (evitar abrir o site duas vezes — idealmente essa extração roda **dentro** do `_audit_website` existente e só é usada depois, na hora da resposta):
- **Logo:** heurística comum — `<img>` dentro do `<header>`/`.logo`/`.navbar-brand`, ou `og:image`/`apple-touch-icon` como fallback.
- **Cores:** extrair `background-color`/`color` computados do header e botões primários via `page.evaluate`, ou (mais robusto) rodar um extrator de paleta sobre a imagem do logo/hero (ex. `colorthief` em Python) para pegar as 3–5 cores dominantes reais.
- **Fotos:** `og:image`, primeiras imagens do carrossel/hero, fotos do Google Business já coletadas (`google_url` permite outra rodada de scraping de fotos, se aceitável) e/ou fotos públicas do Instagram (`instagram` handle já salvo).
- **Texto institucional:** nome, categoria, cidade, telefone, horário — já estão no `Company`/`Audit`; se o site tiver uma seção "Sobre", extrair 1–2 frases para dar autenticidade ao template (evita o "cara de IA" citando algo que a própria empresa escreveu).
- **Sem site nem Instagram com imagens usáveis:** fallback documentado explicitamente como limitação de produto (ver PRD, questão em aberto #5) — não inventar fotos nem depoimentos falsos (isso violaria o próprio princípio de "sem cara de IA" e, mais grave, geraria conteúdo fabricado sobre a empresa).

Saída: um `BrandKit` (dataclass/JSON) com `{name, logo_url, colors: [hex], hero_image_url, phone, address, hours, about_snippet, category}`.

### 4.6 `SiteTemplateEngine` (`app/templates_site/engine.py`, novo)
- Biblioteca de templates HTML estáticos por categoria (barbearia, salão, clínica, restaurante, oficina, hotel pequeno, genérico), com placeholders de tema via CSS custom properties (`--color-primary`, `--color-secondary`) e blocos de conteúdo (hero, sobre, serviços, contato, mapa/Google, WhatsApp/e-mail de contato).
- Motor de template simples (Jinja2, já compatível com o stack Python existente) — não precisa de LLM para montar o HTML; o LLM já foi usado para o outreach, e usar LLM de novo para gerar HTML aumenta risco de "cara de IA" (layouts genéricos, textos clichê). **Templates artesanais + dados reais injetados é a abordagem que melhor atende ao requisito do usuário.**
- Um único parâmetro de personalização por LLM, opcional: gerar 1–2 frases de "sobre nós" quando a empresa não tem nenhum texto institucional aproveitável — nesse caso, o prompt deve ser extremamente ancorado nos dados reais (nome, categoria, cidade, avaliações do Google) para não soar genérico, reaproveitando a mesma filosofia do `ContentValidator` atual.

### 4.7 `PreviewPublisher` (`app/templates_site/publisher.py`, novo)
- Renderiza o HTML final (Jinja2 → string) e publica.
- Opções de hospedagem:
  - **S3 + CloudFront** (ou equivalente): `preview.<slug-da-empresa>.suaempresa.com` ou `suaempresa.com/preview/<slug>`. Simples, barato, sem servidor.
  - **Alternativa mais simples para MVP:** servir os previews pelo próprio FastAPI (`StaticFiles`, já usado em `main.py` para a interface) em `/preview/{slug}` — funciona para volume baixo/médio sem infraestrutura extra, mas não escala tão bem quanto um bucket+CDN.
- Slug único por empresa (`company.id` + hash, para não expor sequencial).
- TTL/expiração: opcional, mas recomendável (ex. 30 dias) para não acumular hosting de leads que nunca fecharam.

### 4.8 `FollowUpComposer`
Mesma filosofia do `sales_agent.py` atual, mas com prompt específico:
- Entrada: conteúdo da resposta recebida (para reagir contextualmente — ex. se a empresa respondeu "quem é você?", a resposta não pode ser idêntica a se tivesse respondido "quanto custa?").
- Regra dura: **sempre incluir a URL do preview**, nunca sem contexto ("aqui, já fiz uma prévia rapidinho baseada no que vi de vocês: <link>").
- Reaproveitar `ContentValidator` com uma variante que, em vez de exigir "opportunity keyword", exige a presença da URL do preview na mensagem.

## 5. Mudanças no `Dispatcher` existente

O `Dispatcher.run_cycle()` atual mistura coleta, auto-enfileiramento e envio em um loop monolítico. Propostas de mudança mínima (evitar reescrever tudo):

1. `_auto_enqueue()` passa a chamar `ChannelRouter.decide_channel()` antes de gerar a mensagem, e a persistir `preferred_channel` na `Company`.
2. `_process_company()` bifurca em `_send_message()` conforme o canal: hoje só chama `WhatsAppClient`; passa a checar `entry.company.preferred_channel` e chamar `EmailSender` ou `WhatsAppClient`.
3. O `run_cycle()` deve rodar **por país**, respeitando a janela de envio e o rate limit daquele país/canal específico (hoje é um único `SEND_WINDOW_START/END` e um único `WarmupManager` global — precisa virar `WarmupManager(channel, country)` ou, no mínimo, `WarmupManager(channel)`, já que e-mail e WhatsApp têm dinâmicas de aquecimento totalmente diferentes).
4. Novo: um segundo "loop" (ou o mesmo `run_cycle`, mais uma etapa) que processa a fila de `inbound_replies` pendentes de processamento — pode ser reativo via webhook (recomendado, menor latência, atende à meta do PRD) em vez de reaproveitar o polling de 60s do dispatcher.

## 6. Risco crítico de arquitetura — WhatsApp oficial vs. Baileys

Isto precisa ser decidido antes de escalar para a Europa (ver PRD, questão em aberto #3):

- **Baileys (atual):** simula um WhatsApp pessoal via engenharia reversa do protocolo. Não é uma API suportada pela Meta — risco real de banimento do número, sem SLA, sem suporte. Funciona bem em escala pequena/piloto.
- **WhatsApp Business Platform (Cloud API oficial):** exige que a **primeira mensagem** para um contato que nunca conversou com o número seja um **template pré-aprovado pela Meta** (não pode ser 100% gerado livremente por LLM a cada empresa) — isso conflita diretamente com o pipeline atual de `sales_agent.py`, que gera uma mensagem única por empresa citando dados específicos. É possível ter templates com variáveis (`{{1}}`, `{{2}}`) preenchidas dinamicamente (ex.: "Olá, vi o {{1}} no Google — {{2}}"), mas isso é mais restrito do que o texto livre atual.
- **Recomendação:** para o piloto europeu, manter Baileys apenas nos países/volumes onde o risco é aceitável, mas **desenhar o `WhatsAppClient` com uma interface neutra** (`send`, `is_connected`) para permitir trocar a implementação por Cloud API sem reescrever o `Dispatcher` — isso já é parcialmente verdade hoje (`whatsapp_client.py` é uma classe fininha), só precisa de uma segunda implementação (`WhatsAppCloudAPIClient`) atrás da mesma interface.

## 7. Compliance — implicações técnicas (GDPR / e-privacy)

- Toda empresa contatada precisa de um mecanismo de opt-out **funcional nos dois canais** — a tabela `OptOut` já existe e já é checada pelo dispatcher (`_check_opt_out`); precisa passar a registrar também `email` como `contact_identifier` (hoje só telefone/instagram são checados).
- Rodapé obrigatório de e-mail com identificação do remetente e link/instrução de opt-out (requisito legal, não só boa prática).
- Registro de base legal/justificativa de contato (ex. "interesse legítimo B2B") deve ficar documentado no processo, mesmo que não seja um campo de banco — é uma decisão de compliance que a equipe jurídica do usuário precisa validar por país antes do lançamento (fora do escopo técnico deste documento).
- Reter o mínimo de dados pessoais possível (o modelo atual já é majoritariamente B2B/empresa, mas e-mail e telefone de contato de uma pessoa física dentro da empresa contam como dado pessoal sob GDPR).

## 8. Plano de rollout sugerido

1. **Fase 1 — Fundação de dados:** adicionar `email` em `Company`, popular `Country`/geografia europeia, estender coletor para extrair e-mail, sem ainda enviar nada novo.
2. **Fase 2 — Canal de e-mail (outreach apenas):** `EmailSender` + `ChannelRouter` + adaptação do `sales_agent`/`ContentValidator` para e-mail. Sem detecção de resposta ainda — validar entregabilidade e qualidade de mensagem primeiro.
3. **Fase 3 — Detecção de resposta:** inbound parsing de e-mail + patch no `whatsapp-sender` para notificar respostas. Sem geração de template ainda — só logar `inbound_replies` e alertar o usuário manualmente.
4. **Fase 4 — Template automático:** `BrandKitExtractor` + `SiteTemplateEngine` + `PreviewPublisher` + `FollowUpComposer`, plugados no `ReplyEventHandler`. Rodar primeiro em modo "rascunho" (gera o preview e avisa o usuário, mas não envia sozinho) até o usuário validar qualidade/"cara de IA" numa amostra.
5. **Fase 5 — Envio automático fim-a-fim:** liga o envio automático do template na primeira resposta, com monitoramento e circuit breaker equivalente ao que já existe para envio de outreach.

## 9. Testes

- Reaproveitar a suíte existente (`tests/test_sending.py`, 44 testes citados no `STATUS.md`) como baseline de não-regressão.
- Novos testes unitários: `ChannelRouter` (matriz de decisão), `ContentValidator` para e-mail (assunto + corpo), casamento de thread de resposta (e-mail e WhatsApp), idempotência do `ReplyEventHandler` (resposta duplicada não gera dois previews).
- Teste de integração ponta-a-ponta em ambiente de staging: empresa fake → outreach por e-mail → resposta simulada via webhook de teste → verifica que o preview foi gerado, publicado e a URL enviada de volta no thread correto.
