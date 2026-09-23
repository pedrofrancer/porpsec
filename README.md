# porpsec

Plataforma de prospecção B2B para negócios locais. Encontra pequenas empresas com presença
digital fraca, mede o que falta com dados verificáveis, escreve para o dono no idioma dele e,
quando ele responde, entrega uma prévia do site novo já com a marca da empresa.

Comecei no Brasil, na Região dos Lagos, com WhatsApp. Hoje o foco é a Europa por e-mail:
Portugal, Bruxelas, França e Holanda.

## Por que existe

Prospectar à mão é lento, e mensagem genérica não converte. A ideia aqui é o contrário do spam:
poucos contatos por dia, cada um citando um problema real do site da empresa (não abre no
telemóvel, demora 6 segundos, não tem reserva online), e a prova de valor chegando na hora certa,
que é quando a pessoa responde.

Duas regras guiam o projeto:

- **Nada inventado.** Mensagem sem dado concreto da auditoria não sai. A prévia usa nome, logo,
  cores e textos da própria empresa; foto de banco aparece marcada como ilustrativa; nenhum
  depoimento, prêmio ou "desde 1998" fabricado.
- **Conformidade antes de volume.** Só escrevo para a caixa genérica do domínio da empresa, com
  remetente identificado e saída por "STOP". Na Holanda, só para B.V./N.V. Espanha fica desligada
  porque a LSSI exige consentimento prévio. A base legal de cada país fica registrada em cada envio.

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

O pipeline europeu está completo e coberto por testes com dublês. Falta o primeiro teste contra
os serviços reais e a validação jurídica por país antes de subir o volume. O que está em aberto
vive nas [issues](https://github.com/pedrofrancer/porpsec/issues).

Documentos de produto: [PRD](prospectplatform/prd.md) e [TechSpec](prospectplatform/techspec.md).

## Autor

Pedro Francisco, engenheiro de software com foco em segurança da informação.
Contato: pedroradical06@gmail.com
