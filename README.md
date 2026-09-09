# SeqChat

SeqChat is a local browser application that answers natural-language questions about the CDISC pilot ADSL dataset. Its current path is React → FastAPI → LangGraph → an OpenAI-compatible chat provider → SQLGlot → DuckDB → a result-grounded answer.

## Prerequisites

- Python 3.12 (managed by [uv](https://docs.astral.sh/uv/))
- uv
- Node.js 20.19 or newer
- npm
- Network access for the first dependency install, fixture download, and model calls

## Install

From the repository root:

```powershell
uv sync --directory backend --frozen
npm ci --prefix frontend
```

## Configure the model provider

The backend reads these process environment variables. Never prefix them with `VITE_` and never put real values in tracked files.

- `SEQCHAT_LLM_BASE_URL`
- `SEQCHAT_LLM_API_KEY`
- `SEQCHAT_LLM_MODEL` (depending on the user's provider)

To persist values for the current Windows user, set each value without writing it to this repository, then open a new terminal:

```powershell
[Environment]::SetEnvironmentVariable('SEQCHAT_LLM_BASE_URL', '<provider-base-url>', 'User')
[Environment]::SetEnvironmentVariable('SEQCHAT_LLM_API_KEY', '<provider-api-key>', 'User')
[Environment]::SetEnvironmentVariable('SEQCHAT_LLM_MODEL', '<provider-llm-model>', 'User')
```

`.env.example` lists names only. The application does not load `.env` files.

## Prepare DuckDB

This command downloads the fixture from its pinned upstream commit, verifies its SHA-256 checksum, maps Dataset-JSON columns to row values, and creates `data/seqchat.duckdb`. It is safe to run repeatedly.

```powershell
uv run --directory backend seqchat-init-data
```

Expected output reports 254 rows and 48 columns.

## Run locally

Open two terminals at the repository root.

Terminal 1:

```powershell
uv run --directory backend uvicorn seqchat.api:app --reload
```

Terminal 2:

```powershell
npm run dev --prefix frontend
```

Open <http://localhost:5173>. The Vite server proxies `/api` to FastAPI at `http://127.0.0.1:8000`; model configuration never enters frontend code.

Golden question:

> How many subjects are in each planned treatment group?

Expected evidence: Xanomeline High Dose 84, Xanomeline Low Dose 84, and Placebo 86.

## Verify

```powershell
uv run --directory backend ruff check .
uv run --directory backend mypy src
uv run --directory backend pytest
npm run lint --prefix frontend
npm run typecheck --prefix frontend
npm run test --prefix frontend
npm run build --prefix frontend
```

The backend tests use a class named `DeterministicFakeModel`. They verify deterministic workflow behavior, not the real provider path. Complete the real-provider and browser checks separately.

## Current limitations

- One dataset and one physical table (`adsl`) only.
- One synchronous question per request; no conversation memory or streaming.
- No automatic SQL repair or retries.
- Returned query evidence is limited to 100 rows.
- No authentication, deployment, charts, or production telemetry.
- Provider and unsupported-question quality depend on model behavior; SQL safety is enforced separately in deterministic code.
