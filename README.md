# porpsec

Plataforma de prospecção B2B para negócios locais. Encontra pequenas empresas com presença
digital fraca, mede o que falta com dado verificável, escreve para o dono no idioma dele e,
quando ele responde, entrega uma prévia do site novo já com a marca da empresa.

Comecei no Brasil, na Região dos Lagos, pelo WhatsApp. Hoje o foco é a Europa por e-mail:
Portugal, Bruxelas, França e Holanda.

## Por que existe

Prospecção é, no fundo, um problema de decisão sob incerteza com amostra minúscula. Não sei
quem vai responder, não sei por quê, e cada contato mal feito tem custo: para quem recebe e para
a reputação de quem envia. A resposta usual é aumentar o volume e deixar a lei dos grandes números
fazer o trabalho. Eu fui pelo caminho inverso: poucos contatos por dia, cada um citando um
problema real e verificável do site da empresa (não abre no telemóvel, demora seis segundos, não
tem reserva online), e a prova de valor chegando no único momento em que ela importa, quando a
pessoa responde.

Duas restrições guiam o projeto inteiro:

- **Nada inventado.** Mensagem sem dado concreto da auditoria não sai. A prévia usa nome, logo,
  cores e textos da própria empresa; foto de banco aparece marcada como ilustrativa; nenhum
  depoimento, prêmio ou "desde 1998" fabricado. Um sistema que fabrica evidência para convencer
  alguém é, tecnicamente, engenharia social, e eu passo tempo demais do outro lado disso para
  construir uma.
- **Conformidade antes de volume.** Só escrevo para a caixa genérica do domínio da empresa, com
  remetente identificado e saída por STOP. Na Holanda, só para B.V./N.V. A Espanha fica desligada,
  porque a LSSI exige consentimento prévio. A base legal de cada país é registrada em cada envio:
  não porque registrar a torne válida, mas porque torna o risco auditável.

## Modelo de ameaça, em resumo

O que me preocupa, em ordem:

1. **O sistema falar em meu nome sem que eu tenha decidido.** Por isso a prévia e a resposta ficam
   em rascunho até eu aprovar; o envio automático existe, mas é opt-in explícito.
2. **Dado pessoal onde deveria haver dado de empresa.** Webmail e e-mail com nome de pessoa são
   recusados na origem; opt-out é permanente e checado antes de qualquer envio, em qualquer canal.
3. **Exposição da operação.** Com `API_TOKEN` definido, API, prévias locais e docs exigem o
   token; sem ele, só entra quem vem do próprio PC. Túnel chega como 127.0.0.1, então quem expõe
   por túnel define o token. As prévias publicadas levam `noindex`, slug com sufixo aleatório e
   expiram em trinta dias.
4. **Entrada hostil.** Texto que chega de fora é não confiável por definição. Tudo que vem do
   Google Maps, de site auditado, de resposta recebida ou do LLM é escapado antes de ir para o
   painel, e a prévia escapa o que vem do site.

Nenhuma dessas camadas fecha o problema por completo. Elas só estreitam a janela.

## Como funciona

```
Google Maps (idioma local)
  -> auditoria do site (Playwright): velocidade, mobile, HTTPS, reserva, e-mail, forma jurídica, logo, cores
  -> regras de oportunidade (YAML)
  -> política de destinatário e escolha de canal
  -> e-mail curto no idioma da empresa (LLM + validação anti-genérico)
  -> leitura da caixa por IMAP: resposta, STOP, bounce
  -> primeira resposta: prévia do site (Jinja2) publicada no Cloudflare Pages
  -> aprovação no painel e resposta no mesmo thread
```

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy, Alembic, SQLite
- **Coleta e auditoria:** Playwright
- **Texto:** qualquer API compatível com OpenAI (uso o Groq no plano grátis)
- **E-mail:** SMTP e IMAP do Gmail com senha de app
- **Prévias:** Jinja2 e Cloudflare Pages via `wrangler`
- **WhatsApp (Brasil):** microserviço Node com Baileys

Custo de infraestrutura: zero. Roda no meu PC.

## Rodando

Instalação, variáveis do `.env` e o teste ponta a ponta estão em
[`prospectplatform/README.md`](prospectplatform/README.md). Resumo:

```powershell
cd prospectplatform
python -m venv .venv
.venv\Scripts\python -m pip install -r backend\requirements.txt
.venv\Scripts\python -m playwright install chromium
copy .env.example backend\.env
.venv\Scripts\python scripts\seed_geography.py
.venv\Scripts\python scripts\seed_categories.py
cd backend
..\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Testes: `.venv\Scripts\python -m pytest tests -q` na pasta `prospectplatform`.

## Estado

| Etapa | O quê | Estado |
|---|---|---|
| 1 a 13 | Coleta, auditoria, oportunidades, fila, envio por WhatsApp no Brasil | Fechadas |
| 14 | Pipeline europeu: e-mail, respostas, prévia de site (#1) | Fechada |
| 15 | Teste ponta a ponta contra os serviços reais (#2) | Aberta |
| 16 | Validação jurídica por país (#3) | Aberta |
| 17 | Suíte de testes no CI (#4) | Entregue (#13) |
| 18 | Autenticação no painel e na API (#5) | Entregue (#11) |
| 19 | Métricas do piloto (#6) | Aberta |
| 20 | Forma jurídica na Holanda pela KvK (#7) | Aberta |
| 21 | Resposta no WhatsApp (#8) | Aberta |
| 22 | Encerramento limpo dos loops de fundo (#9) | Entregue (#12) |
| 23 | E-mails na primeira pessoa, com voz de gente | Em revisão |

A Etapa 15 já tem a ferramenta (`scripts/verificar_config.py`), falta o teste contra os serviços
reais. Cento e noventa testes passam com dublês, e o CI roda todos em cada PR; nenhum deles ainda
falou com o Gmail de verdade. Até lá, o pipeline europeu é uma hipótese bem formalizada, não um
resultado.

Documentos de produto: [PRD](prospectplatform/prd.md) e [TechSpec](prospectplatform/techspec.md).
