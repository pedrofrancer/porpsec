# STATUS — ProspectPlatform

> Atualizado: 2026-09-22 (expansao Europa, branch feat/eu-email-pipeline)

## Europa (PT, BE, FR, NL) — e-mail + previa de site

Implementado e coberto por testes (160 passando):
- [x] Configuracao por pais (idioma, fuso, janela, base legal); Espanha com envio desligado
- [x] Coleta no idioma local e extracao de e-mail, forma juridica, logo e cores na auditoria
- [x] Politica B2B: so caixa do dominio da empresa; NL so com B.V./N.V.
- [x] Outreach por Gmail (SMTP) com rodape legal e aquecimento proprio da caixa
- [x] Leitura de respostas por IMAP: resposta, STOP (opt-out) e bounce
- [x] Previa de site com a identidade da empresa, publicada no Cloudflare Pages, resposta no mesmo thread
- [x] Aprovacao no painel (aba Respostas) e envio automatico opcional
- [x] Migracao automatica do banco no startup

Depende de voce:
- [ ] Preencher `backend/.env` (Gmail + senha de app, remetente, Groq, Cloudflare, Pexels opcional)
- [ ] Rodar `scripts/teste_ponta_a_ponta.py` para um e-mail seu e responder
- [ ] Validacao juridica por pais antes de escalar o volume

Nao testado contra servico real (so com dublês nos testes): SMTP/IMAP do Gmail, deploy do wrangler,
API do Pexels e Groq. O primeiro teste ponta a ponta e o que prova esses quatro.

## Brasil (WhatsApp) — estado anterior

---

## Bloqueadores (nada envia sem isso)

- [ ] **WhatsApp sender offline** — `whatsapp-sender/node.js` precisa rodar (`node index.js`) e voce escanear o QR code via `GET /qr` ou terminal. Nenhuma mensagem sai sem isso.
- [ ] **Fila cheia de JA_ENVIADO sem envio real** — Existem 24 entradas com status `JA_ENVIADO` no banco de dados de producao que nunca foram enviadas. O bug de `_has_active_message` foi corrigido, mas essas entradas precisam ser resetadas pra `PENDENTE` para serem reprocessadas (ou apagadas e re-enfileiradas). Codigo do fix: `dispatcher.py:309-314`.
- [ ] **Limpar messages antigas com status `aprovado`** — Existem 25 msgs com status `aprovado` criadas pelo pipeline antigo. Como o `_has_active_message` agora so bloqueia `enviado`, essas msgs vao ser re-enfileiradas corretamente no proximo ciclo. Nao e bloqueador mas pode causar confusao no historico.

## Depende de acao manual (humano precisa fazer)

- [ ] **Escaneie o QR code do WhatsApp** — Rode `cd whatsapp-sender && node index.js`, espere o QR aparecer, escaneie com seu WhatsApp. Confirme com `curl http://localhost:3100/status` que retorna `"connected": true`.
- [ ] **Confirme SEND_WINDOW_START/END** — Estao configurados como 9-19 (horario de Brasilia). Se voce envia em outro horario, ajuste em `backend/.env` ou `config.py`.
- [ ] **Revise collection_targets.yaml** — Hoje so tem barbearia x 7 cidades da Regiao dos Lagos. Adicione outras categorias/cidades conforme necessario.
- [ ] **Defina o ton do LLM pra seu caso de uso** — O prompt foi reescrito em 2026-08-21. Gere 5-10 mensagens de teste com `backend/test_messages.py` e ajuste o prompt ate gostar do resultado.
- [ ] **Configure o git remote** — O push foi feito pra `https://github.com/pedrofrancer/porpsec.git`. Confirme que voce tem acesso pra push futuros.

## Testado e funcionando (com evidencia)

- [x] **44 testes passando** (pytest, 2026-08-21)
- [x] **Coleta Google Maps automatica** — Coletou 20 empresas de Cabo Frio quando base esgotou. Log: `Coleta finalizada: barbearia em Cabo Frio → 20 empresas novas` (2026-08-21)
- [x] **Auto-enqueue pipeline** — 13 empresas processadas em 3 ciclos (audita → oportunidades → LLM → valida → enfileira). Mensagens aprovadas pelo ContentValidator. (2026-08-21)
- [x] **Bug _has_active_message corrigido** — `aprovado` removido do filtro. Agora so `enviado` bloqueia reprocessamento. (2026-08-21, commit db981ab)
- [x] **Bug send window BRT corrigido** — Usa `America/Sao_Paulo` em vez de UTC. (2026-08-21, commit db981ab)
- [x] **ContentValidator com specificity check** — Rejeita msg que nao menciona dado especifico da empresa. 6 testes novos passando. (2026-08-21)
- [x] **Prompt LLM reescrito** — Mais focado em evidencia concreta, variacao de abertura, tom humano. 5 mensagens de teste geradas e aprovadas. (2026-08-21)
- [x] **Dispatcher status/pause/resume/run** — Endpoints funcionando, log do ciclo visivel. (2026-08-20)
- [x] **Historico de envios** — `GET /messages` e `GET /messages/stats` funcionando. Interface HTML com aba Envios. (2026-08-20)
- [x] **Opt-out permanente** — `POST /prospection/opt-out` registra e bloqueia envio futuro. (2026-08-20)
- [x] **Rate limit + warmup** — 5→10→15→20→25→30→40 dias, 20/dia, 5/hora. Implementado mas nunca exercitado com envios reais. (2026-08-20)
- [x] **Circuit breaker** — 5 erros consecutivos pausa o dispatcher. (2026-08-20)
- [x] **Dedup 30 dias** — Nao envia pra mesma empresa em 30 dias. (2026-08-20)

## Nao implementado ainda (feature que nunca foi pedida/fita)

- [ ] **Phone number normalization** — Telefones no banco variam: `(22)99801-1234`, `(22) 99221-2410`. O WhatsApp sender limpa com `replace(/\D/g, '')` mas padronizacao no banco evita problemas.
- [ ] **Follow-up / reengajamento** — Sem logica de segundo contato. Empresa que nao respondeu so recebe 1 msg.
- [ ] **Dashboard com dados reais de envio** — Interface existe mas nao ha dados reais de envio pra mostrar (WhatsApp sender nunca rodou).
- [ ] **Logs centralizados / monitoring** — S.logs no console do uvicorn. Em producao precisa de algo persistente.
- [ ] **Testes de integracao com WhatsApp sender** — Sem nenhum teste real contra o microservico Node.
- [ ] **Validacao de formato de telefone** — `ContentValidator` nao checa se o telefone e valido pro WhatsApp.
- [ ] **Retry com backoff no LLM** — Groq retorna 429 occasionalmente. O dispatcher nao tem retry (so falha e segue).
- [ ] **Graceful shutdown do dispatcher** — O `stop()` cancela o task mas nao espera ciclos em execucao terminarem.
- [ ] **Exportar dados / relatorios** — Sem funcionalidade de export.
