# ProspectPlatform

Prospecção B2B de negócios locais. Coleta empresas no Google Maps, audita a presença digital,
manda um e-mail curto e específico no idioma da empresa e, quando ela responde, prepara uma
prévia de site com a identidade visual dela, publicada de graça no Cloudflare Pages.

Países ativos: Portugal, Bélgica (Bruxelas), França e Holanda. Espanha está configurada, mas com
envio desligado (a LSSI exige consentimento prévio). O Brasil continua no fluxo antigo por WhatsApp.

## Fluxo

1. **Coleta**: Google Maps no idioma do país (`config/collection_targets.yaml`, `config/category_terms.yaml`).
2. **Auditoria**: site, redes e Google Business, mais e-mail de contato, idioma do site, forma jurídica
   (B.V., SARL, Lda...), logo, cores e texto "sobre".
3. **Canal**: e-mail só para a caixa da própria empresa (domínio do site, sem webmail, sem e-mail
   pessoal). Na Holanda, só com B.V./N.V. no site. Quem não passa fica `NAO_ELEGIVEL` com o motivo.
4. **Outreach**: e-mail em PT-PT, FR ou NL citando um dado real da auditoria, com rodapé legal
   (remetente, endereço, como sair respondendo STOP). Limite diário com aquecimento da caixa.
5. **Respostas**: o IMAP lê o Gmail a cada 60s. STOP vira opt-out, bounce marca a mensagem e a
   primeira resposta real pede a prévia.
6. **Prévia**: site gerado com nome, logo, cores e fotos da empresa (ou fotos de banco rotuladas como
   ilustrativas) e resposta no mesmo thread com o link. Fica em rascunho até você aprovar na aba
   **Respostas**. `PREVIEW_AUTO_SEND=true` envia sozinho.

## Instalação (Windows)

```powershell
cd prospectplatform
python -m venv .venv
.venv\Scripts\python -m pip install -r backend\requirements.txt
.venv\Scripts\python -m playwright install chromium
copy .env.example backend\.env
.venv\Scripts\python scripts\seed_geography.py
.venv\Scripts\python scripts\seed_categories.py
```

O Node.js precisa estar instalado: a publicação usa `npx wrangler`.

## Configuração (`backend/.env`)

| O quê | Onde conseguir (tudo grátis) |
|---|---|
| `LLM_API_KEY` | https://console.groq.com/keys |
| `EMAIL_ADDRESS`, `EMAIL_APP_PASSWORD` | Gmail com verificação em 2 etapas → https://myaccount.google.com/apppasswords |
| `SENDER_BRAND`, `SENDER_POSTAL_ADDRESS` | Seu nome comercial e endereço: obrigatórios no rodapé na UE |
| `OFFER_PRICE_RANGE` | Ex.: `490 EUR`. Vazio = não fala de preço |
| `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_PAGES_PROJECT` | https://dash.cloudflare.com/profile/api-tokens, permissão *Cloudflare Pages: Edit* |
| `PEXELS_API_KEY` (opcional) | https://www.pexels.com/api/ |
| `API_TOKEN` (opcional) | Qualquer segredo longo. Vazio = só o próprio PC acessa o painel. Obrigatório se expuser na rede ou por túnel |

Sem e-mail configurado nada é enviado: as mensagens ficam aprovadas na fila, esperando.

Antes de ligar, confira cada serviço sem enviar nada:

```powershell
.venv\Scripts\python scriptserificar_config.py
```

Cada linha sai `OK`, `FALHA` ou `AVISO` com o que corrigir.

## Rodar

```powershell
cd prospectplatform\backend
..\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Painel: http://localhost:8000 · API: http://localhost:8000/docs

O banco é criado ou migrado sozinho no startup, inclusive o banco antigo sem `alembic_version`.
Com o PC desligado nada sai; respostas que chegarem nesse período são lidas ao religar.

## Testar sem contatar empresa real

Com o servidor rodando, envie o outreach para um e-mail seu (diferente da caixa do `.env`):

```powershell
.venv\Scripts\python scripts\teste_ponta_a_ponta.py --para voce@outro-email.com --pais FR
```

Responda esse e-mail. Em até 1 minuto a resposta aparece na aba **Respostas**. Em até 30 segundos
depois disso, a prévia aparece como rascunho: revise, edite a resposta e clique em **Publicar e enviar**.

Testes automatizados:

```powershell
.venv\Scripts\python -m pytest tests -q
```

## Antes de ligar o envio real

- A base legal por país está em `config/countries.yaml` e vai para o `ActionLog` de cada envio.
  Valide com um jurista antes de escalar.
- Gmail pessoal tem limite e reputação próprios: mantenha `EMAIL_DAILY_LIMIT` baixo (20).
- As prévias ficam com `noindex` e saem do ar após `PREVIEW_TTL_DAYS` (30).

## Estrutura

- `backend/app/collectors/`: Google Maps e CSV
- `backend/app/auditors/`: auditoria e extratores (e-mail, forma jurídica, cores)
- `backend/app/prospecting/`: política de e-mail e escolha de canal
- `backend/app/sending/`: dispatcher, envio SMTP e WhatsApp, validadores
- `backend/app/inbound/`: leitura IMAP e tratamento das respostas
- `backend/app/branding/`: identidade visual, template, publicação e ciclo da prévia
- `backend/app/llm/`: textos de outreach e de resposta
- `config/`: países, termos de busca, alvos de coleta, textos da prévia, regras de oportunidade
- `interface/`: painel
