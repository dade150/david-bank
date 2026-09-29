# LipariBank AI

API di una filiale bancaria con assistente AI: ricerca documentale (RAG), chat e un
**agente dotato di tool che non esegue un'azione rilevante senza il permesso di un
responsabile**.

## Cosa c'è dentro

- **RAG** su documenti interni (regolamenti, commissioni, condizioni), con visibilità
  per ruolo e filiale
- **Chat, consigli, glossario** e **categorizzazione** dei movimenti
- **Agente con tool**: saldo, movimenti, carte, bonifici, ricerca policy,
  apertura segnalazioni di compliance
- **Approvazione umana**: sopra soglia il run si ferma *prima* dell'azione, una persona
  decide, e lo stato è nel database — sopravvive ai riavvii del server
- **Supervisor**: la stessa domanda, divisa fra due specialisti (dati / policy)
- **Server MCP**: gli stessi tool esposti ad altri client, con identità firmata da JWT
- **Auth JWT** con ruoli e portafoglio clienti per operatore

## Stack

FastAPI · PostgreSQL 16 + pgvector · SQLAlchemy async + Alembic · uv ·
LLM compatibile OpenAI (server opencode) · sentence-transformers · fastmcp

## Struttura

```
src/
  api/        router (auth, conti, chat, agent, ingest)
  agents/     loop, tool, approvazione, supervisor, deps
  auth/       JWT, ruoli, hash delle password
  db/         modelli, repository, migrazioni
  llm/        provider opencode, embedding, tipi
  services/   retrieval, alert
  scripts/    seed utenti, seed dati, ingest documenti
liparibank_mcp/   server MCP
alembic/          migrazioni
data/docs/        documenti da indicizzare
```

## Quickstart

```bash
docker compose up -d          # PostgreSQL 16 + pgvector su :5432
uv sync                        # dipendenze

cp .env.example .env           # e compila OPENCODE_SERVER_PASSWORD

uv run alembic upgrade head
uv run python -m src.scripts.seed_users    # utenti e ruoli
uv run python -m src.scripts.seed          # conti, movimenti, carte, bonifici
uv run python -m src.scripts.ingest        # indicizza data/docs/

uv run uvicorn src.my_dvd_bank.main:app --port 8000
curl localhost:8000/health                  # {"status":"UP"}
```

Documentazione interattiva: <http://localhost:8000/docs>

## Utenti di sviluppo

Stessa password per tutti (`bootcamp`), solo su ambiente locale:

| Username | Ruolo | Può |
|---|---|---|
| `mbianchi` | operator | chiedere, non decidere |
| `ferri` | operator | chiedere, non decidere |
| `grossi` | compliance_lead | **approvare / respingere** |
| `lverdi` | risk_lead | **approvare / respingere** |

Ogni operatore vede solo il proprio portafoglio di conti.

## API

| | |
|---|---|
| `GET /health` | stato del servizio |
| `POST /api/auth/login` | token JWT |
| `GET /api/accounts/{iban}/movements` | movimenti di un conto |
| `GET /api/accounts/{iban}/total-spent` | spese totali |
| `POST /api/ai/chat` | chat con RAG |
| `POST /api/ai/advice` | consiglio bancario con fonti |
| `POST /api/ai/categorize` | categoria di un movimento |
| `POST /api/ai/glossary` | spiega un termine interno |
| `POST /api/ai/agent` | **l'agente con tool** |
| `POST /api/ai/supervisor` | stessa domanda, due specialisti |
| `GET /api/ai/agent/{run_id}` | cosa sta aspettando approvazione |
| `POST /api/ai/agent/{run_id}/approve` | approva e riprende |
| `POST /api/ai/agent/{run_id}/reject` | respinge, con motivo |
| `POST /api/ai/documents/ingest` | indicizza un documento |

## L'agente

**I tool.** Sei, costruiti per chi fa la richiesta: il muro d'accesso («è un conto del tuo
portafoglio?») sta dentro il tool, così vale anche se la chiamata arriva da fuici.

**L'approvazione.** Solo `apri_segnalazione_compliance` scrive. Sopra
`SOGLIA_APPROVAZIONE_EUR` (5.000 €) — o senza importo — il run si ferma **prima** di
eseguire qualunque tool di quel passo:

1. il run viene salvato in `agent_runs` (`status = awaiting_approval`);
2. `GET /api/ai/agent/{run_id}` mostra a chi deve decidere cosa sta per succedere;
3. `approve` fa ripartire il ciclo da dove si era fermato (stesso run, stessi passi);
4. `reject` passa il motivo al modello, che riferisce il rifiuto senza aver scritto niente.

Chi ha chiesto non può approvare (403), le decisioni simultanee vincono una sola
(409), e nessuno a cui chiedere non è un via libera: il tool non parte.

**Il supervisor.** Un triage classifica la domanda, poi uno o due specialisti rispondono
ciascuno col proprio prompt e i propri tool (solo lettura) e una sintesi ricompone.
Le azioni restano su `/api/ai/agent`, dove c'è l'approvazione.

## MCP

```bash
uv run python -m liparibank_mcp.server        # transport stdio
```

Espone tre tool in sola lettura (`search_policy`, `get_account_balance`,
`list_recent_movements`). L'identità non è un parametro: arriva nel token `LIPARI_TOKEN`
nell'ambiente del processo, viene verificata a ogni chiamata, e con un token non valido
il server risponde *Identità non verificata* invece di un saldo.

Per provarlo a mano con l'Inspector:

```bash
npx @modelcontextprotocol/inspector -e LIPARI_TOKEN=$TOKEN \
  uv run python -m liparibank_mcp.server
```

## Qualità

```bash
uv run ruff check src liparibank_mcp
uv run mypy src liparibank_mcp
```

## Note

- Il modello in `.env` di default è gratuito: `cost_eur` resta a `0`. Mettendo un modello
  a pagamento e i prezzi si abilita il budget per run.
- `find_customer_accounts` non esiste: i conti si chiedono per IBAN.
- Il log `agent_step` riporta `tool_args = <omessi>` per i tool che scrivono: gli
  argomenti stanno nella tabella, non nei log.
