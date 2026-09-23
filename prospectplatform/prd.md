# PRD — ProspectPlatform EU (Prospecção Multicanal B2B)

**Versão:** 0.2 (evolução do `porpsec-master/prospectplatform`)
**Data:** 2026-09-22
**Autor:** Eleandro Clarete da Matta (produto) — documento gerado a partir da análise do código-fonte enviado (`porpsec-master.zip`)
**Status:** Proposta para validação

---

## 1. Contexto e histórico

O `ProspectPlatform` já existe e está funcional em produção para o mercado brasileiro (Região dos Lagos/RJ), com o seguinte pipeline validado (ver `STATUS.md` do repositório):

1. **Coleta** de empresas via Google Maps (Playwright) ou importação de CSV.
2. **Auditoria digital automática** do site/redes sociais (`WebsiteAuditor`): HTTPS, tempo de carregamento, responsividade, meta tags, blog, Instagram/Facebook ativos, Google Business, sinais de WhatsApp.
3. **Motor de oportunidades** (`OpportunityEngine`) baseado em regras YAML (`config/opportunity_rules.yaml`) que cruza os dados da auditoria com a categoria do negócio (ex.: barbearia sem agendamento online).
4. **Geração de mensagem personalizada** via LLM (`sales_agent.py`), com validação anti-genérico (`ContentValidator`) que obriga citar o nome da empresa e um dado concreto da auditoria.
5. **Envio único via WhatsApp** (microserviço Node `whatsapp-sender` com Baileys), com fila (`ProspectingQueue`), rate limit diário/horário, curva de aquecimento de número, janela de horário (9h–19h, dias úteis), circuit breaker e opt-out.

**O que NÃO existe hoje** (confirmado na leitura do código, não é suposição):

- **Nenhum canal de e-mail.** Não há cliente SMTP/API de e-mail, nem template de e-mail, nem lógica de decisão "e-mail vs. WhatsApp".
- **Nenhuma detecção de resposta.** O microserviço WhatsApp (`whatsapp-sender/index.js`) tem um listener `messages.upsert` que **explicitamente ignora mensagens recebidas** (comentário no código: "Ignorar mensagens próprias"). Não existe webhook de e-mail (IMAP/Postmark/SendGrid inbound) tampouco.
- **Nenhuma geração de site/proposta visual.** O produto hoje só manda uma mensagem de texto oferecendo "posso te mostrar como ficaria?" — não existe motor que gere um site de fato, nem que extraia identidade visual (logo, cores, fontes) da empresa.
- **Escopo geográfico é só Brasil** (locale `pt-BR`, timezone `America/Sao_Paulo`, geografia semeada por `scripts/seed_geography.py` limitada a cidades da Região dos Lagos, mensagens em português coloquial brasileiro).

Este PRD define a evolução do produto para atender ao pedido do usuário:

> Varrer empresas pela Europa, mandar e-mails/WhatsApp personalizados oferecendo o que falta (site, Instagram, presença digital), e — assim que a empresa responder a primeira mensagem — encaminhar automaticamente um **template de site pronto**, com a identidade visual da própria empresa, **sem "cara de IA"**, via o mesmo canal que ela respondeu (e-mail ou WhatsApp).

---

## 2. Problema

Pequenas e médias empresas europeias frequentemente têm presença digital fraca ou inexistente (sem site, site desatualizado, sem Instagram ativo). Hoje, prospectar essas empresas manualmente para oferecer serviços de criação de site é lento e caro. O produto atual já resolve isso para o Brasil via WhatsApp, mas:

- Não cobre e-mail, que é o canal dominante de contato B2B na Europa (WhatsApp Business tem adoção desigual entre países).
- Para de agir depois de mandar a primeira mensagem — não fecha o loop de "engajou → aqui está uma prévia do que eu faria pelo seu negócio", que é o gancho comercial mais forte (mostrar valor concreto, não só prometer).
- O texto gerado, mesmo validado, ainda soa como outreach automatizado quando confrontado com "me mostra".

## 3. Objetivo do produto

Permitir que o usuário rode uma operação de prospecção fria multicanal (e-mail + WhatsApp) na Europa que:

1. Encontra empresas locais com lacunas digitais mensuráveis.
2. Manda uma mensagem curta, específica e verificável (sem alucinação) pelo canal que a empresa realmente usa.
3. Ao primeiro sinal de resposta, envia automaticamente **uma prévia de site pronta**, com a marca, cores, logo e conteúdo da própria empresa — funcionando como "prova social instantânea" que converte curiosidade em reunião comercial.

## 4. Público-alvo / ICP

- PMEs locais na Europa com presença digital fraca (sem site, site desatualizado, ou site não responsivo), em categorias de serviço com alto valor de agendamento/reserva (salões, barbearias, clínicas, academias, restaurantes, hotéis pequenos, oficinas, etc. — reaproveitando `opportunity_rules.yaml`).
- Inicialmente países onde o usuário decidir concentrar esforço comercial (a definir — ver seção 9, Questões em Aberto). O motor deve ser **country-agnostic por design**: idioma, moeda, formato de telefone e fuso variam por país.

## 5. Escopo — Funcionalidades novas

### 5.1 Coleta de empresas na Europa
- Estender o coletor (hoje só Google Maps + CSV, pt-BR) para operar em qualquer país/idioma europeu: busca localizada (`{categoria} em {cidade}` no idioma do país), extração de e-mail (hoje o coletor **não captura e-mail**, só telefone/site/Instagram) além dos campos já coletados.
- Fonte adicional de e-mail: quando a empresa tem site, o auditor deve tentar extrair e-mail de contato do próprio site (mailto:, página de contato) já que o Google Maps raramente expõe e-mail.
- Suporte a múltiplos idiomas/moedas/fusos por país (mapeado por país, não hardcoded como hoje).

### 5.2 Escolha de canal (e-mail vs. WhatsApp)
- Regra de decisão, por empresa, na hora de enfileirar para contato:
  - Se a empresa tem **WhatsApp verificável** (número de telefone com indícios de uso comercial, ex. catálogo do WhatsApp Business detectado na auditoria) → canal preferencial = WhatsApp.
  - Senão, se tem **e-mail válido** → canal = E-mail.
  - Se tiver os dois, priorizar o canal com maior taxa histórica de resposta por país/categoria (fallback inicial: preferir WhatsApp se existir, por ter taxa de abertura mais alta).
  - Se não tiver nenhum dos dois → empresa não é elegível para contato automático (fica só coletada/auditada).
- Essa decisão deve ficar registrada por empresa (não pode mudar de canal no meio da conversa).

### 5.3 Geração e envio de mensagem inicial personalizada (multicanal)
- Reaproveitar o motor de LLM + `ContentValidator` já existente, adaptando:
  - Prompt em inglês (ou idioma local, a definir) em vez de português coloquial brasileiro.
  - Formato de e-mail é diferente de WhatsApp: precisa de assunto (subject line) curto e corpo mais estruturado (mas ainda pessoal, não "corporativo"), enquanto WhatsApp mantém o formato atual de até 4–5 frases.
  - Regras de validação anti-genérico e anti-placeholder continuam obrigatórias nos dois canais.
- Envio de e-mail passa a ter um provedor real (hoje não existe nenhum) — ver Techspec para opções.

### 5.4 Detecção de resposta ("primeira resposta da empresa")
- **E-mail:** monitorar a caixa de envio via IMAP (ou webhook do provedor transacional, ex. inbound parsing) para detectar qualquer resposta ao thread da mensagem enviada. Primeira resposta dispara o próximo passo.
- **WhatsApp:** o microserviço `whatsapp-sender` precisa parar de ignorar `messages.upsert` e passar a notificar o backend (webhook interno) quando chega mensagem de um número para o qual mandamos outreach e ainda não recebemos resposta.
- Em ambos os casos, "resposta" é definida como: qualquer mensagem recebida do contato depois do envio da mensagem de outreach e antes de qualquer resposta anterior já registrada (ou seja, dispara só na primeira vez).

### 5.5 Envio automático do template de site na primeira resposta
Esta é a funcionalidade central pedida pelo usuário:

- Ao detectar a primeira resposta (qualquer conteúdo, mesmo "quem é vc?" ou "oi"), o sistema deve, **automaticamente e sem intervenção humana**:
  1. Gerar (ou selecionar de um catálogo pré-construído) um **template de site institucional** adequado à categoria do negócio (ex.: template para barbearia, template para clínica, template para restaurante).
  2. **Aplicar a identidade visual da empresa** no template: nome, logo (se detectável no site/Instagram/Google Business), paleta de cores extraída do site/logo/fotos existentes, fotos do Google/Instagram (quando disponíveis e permitido usar), endereço, telefone, horário de funcionamento (extraído do Google Business).
  3. Publicar essa prévia em uma URL única e hospedada (ex.: `preview.empresa.suaempresa.com` ou subpath), acessível sem login.
  4. Enviar essa URL de volta para o contato, pelo **mesmo canal em que ele respondeu** (e-mail → responde no thread do e-mail; WhatsApp → responde na mesma conversa).
  5. A mensagem de acompanhamento também precisa passar pelo `ContentValidator` (ou equivalente) e **não pode soar como resposta automática de robô** — deve ser curta, natural, contextual à resposta recebida.
- Requisito explícito do usuário: o resultado final **não pode ter "cara de IA"** — ou seja, o template não pode parecer genérico/produzido em massa; precisa refletir a marca real da empresa (cores, nome, fotos reais quando existirem) e o texto de acompanhamento precisa soar humano.

### 5.6 Painel/observabilidade
- Estender a interface existente (`interface/index.html`, que já tem abas de empresas/oportunidades/mensagens) para mostrar:
  - Canal usado por empresa (e-mail/WhatsApp).
  - Status da conversa: enviado → respondeu → template enviado → (opcional) reunião marcada.
  - Link para a prévia de site gerada por empresa.

## 6. Fora de escopo (nesta fase)

- Fechamento de venda, contrato ou cobrança — o produto para na entrega do template + agendamento manual de reunião.
- Publicação do site definitivo em domínio próprio da empresa (a prévia é hospedada pelo próprio ProspectPlatform, não é entrega final do produto de site).
- Suporte a canais adicionais (SMS, LinkedIn, Instagram DM) — mencionados como possível v2, não nesta fase.
- Tradução automática de conteúdo do site da empresa (o template usa os textos-padrão da categoria, só personalizados com dados objetivos da empresa).

## 7. Requisitos não-funcionais

- **Compliance de e-mail:** a operação de cold e-mail na Europa está sujeita ao GDPR e a regras nacionais de e-privacy (ex.: opt-out obrigatório, identificação clara do remetente, base legal para contato B2B — em vários países da UE, cold e-mail B2B é tolerado com opt-out fácil, mas isso **varia por país** e precisa de validação jurídica antes do lançamento; não é uma decisão técnica).
- **Compliance de WhatsApp:** a automação de envio em massa via número pessoal (Baileys, não oficial) já é uma prática de risco de banimento reconhecida no `STATUS.md` atual (por isso existe rate limit, warmup, circuit breaker). Para operar na Europa em escala, avaliar migração para a **WhatsApp Business Platform oficial (Cloud API)**, que exige aprovação de template de mensagem para o primeiro contato — isso muda a arquitetura de envio (ver Techspec).
- **Idempotência:** nunca disparar o template duas vezes para a mesma resposta, nem duas mensagens de outreach para a mesma empresa em menos de 30 dias (regra já existente, deve ser mantida).
- **Auditabilidade:** todo envio (outreach e template) deve ficar registrado com canal, conteúdo e timestamp (reaproveitar `ActionLog`/`Message`).
- **Idioma:** o LLM deve gerar conteúdo no idioma predominante do país da empresa (mínimo viável: inglês; idioma nativo é ideal e deve ser parametrizável por país).

## 8. Métricas de sucesso

| Métrica | Definição | Meta inicial (a validar) |
|---|---|---|
| Taxa de entrega | % de mensagens enviadas sem erro | > 95% |
| Taxa de resposta | % de empresas contatadas que respondem | benchmark a definir após piloto |
| Taxa de conversão resposta→template enviado | % de respostas que resultam em template entregue com sucesso | > 90% (falhas só por dados insuficientes p/ montar o template) |
| Tempo resposta→template | Tempo entre a empresa responder e receber o link do site | < 5 minutos |
| Taxa de "isso parece feito pra mim" | Qualitativo, via feedback do próprio usuário revisando amostras | Sem "cara de IA" na avaliação manual do usuário |

## 9. Questões em aberto (bloqueiam decisões de escopo/técnicas)

1. **Quais países europeus primeiro?** Isso define idioma do LLM, formato de telefone/WhatsApp, e viabilidade legal de cold e-mail/WhatsApp (regras variam por país-membro).
2. **Provedor de e-mail:** já existe alguma conta (Google Workspace, Microsoft 365, SendGrid, etc.) ou začí do zero?
3. **WhatsApp: manter Baileys (não oficial, mais barato, mais arriscado) ou migrar para WhatsApp Business Cloud API oficial (exige template pré-aprovado para primeira mensagem, o que **conflita** com a mensagem 100% personalizada gerada por LLM hoje)?** Esse é o ponto técnico/produto mais crítico do projeto — ver Techspec seção de riscos.
4. **Hospedagem da prévia do site:** domínio próprio do usuário com subdomínios por empresa, ou serviço externo (Vercel/Netlify/S3+CloudFront)?
5. **Fonte de identidade visual:** quando a empresa não tem nem site nem Instagram com boas fotos, o que o template usa (ilustração genérica de categoria? Placeholder claramente rotulado como "exemplo"?). Isso impacta diretamente o requisito de "não ter cara de IA".
6. **Volume-alvo:** quantas empresas/dia o usuário quer prospectar na Europa? Isso dimensiona custo de LLM, infraestrutura de geração de site e rate limits.
