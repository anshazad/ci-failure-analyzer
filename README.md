# CI Failure Analyzer

An AI-powered GitHub Actions failure analyzer that automatically diagnoses CI/CD failures using LLM reasoning, semantic search over historical failures, and a human-in-the-loop approval gate.

## Architecture
```
GitHub API → Poller → PostgreSQL → AI Agent → Groq LLM
                                       ↓
                                 SSE Stream → Dashboard → Approval Gate
                                       ↓
                                 pgvector RAG (past failures)
```

## Features

- **Automatic polling** — watches a GitHub repo every 60s for failed workflow runs
- **AI diagnosis** — Groq LLM (Llama 3.3 70b) diagnoses root cause from real logs and commit diffs
- **Live streaming** — diagnosis streams to the dashboard in real time via SSE
- **Semantic search** — pgvector finds similar past resolved failures and feeds them as context to the LLM
- **Human-in-the-loop** — every suggested fix requires human approval before being marked resolved
- **Learning system** — approved fixes get embedded and stored, improving future diagnoses over time

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, Python |
| AI | Groq API (Llama 3.3 70b) |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Database | PostgreSQL + pgvector |
| Streaming | Server-Sent Events (SSE) |
| Data source | GitHub Actions API |
| Frontend | HTML, CSS, Vanilla JS |

## Setup

### Prerequisites
- Python 3.11+
- Docker

### 1. Clone the repo
```bash
git clone https://github.com/anshazad/ci-failure-analyzer.git
cd ci-failure-analyzer
```

### 2. Create virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment
```bash
cp .env.example .env
```
Fill in your values in `.env`:
- `GITHUB_TOKEN` — GitHub personal access token with `repo` and `workflow` read scope
- `GITHUB_REPO` — repo to watch e.g. `fastapi/fastapi`
- `GROQ_API_KEY` — free at console.groq.com
- `DATABASE_URL` — postgres connection string

### 4. Start PostgreSQL
```bash
docker compose -f docker/docker-compose.yml up -d
```

### 5. Run migrations
```bash
python -m db.migrations
```

### 6. Start the server
```bash
uvicorn backend.main:app --reload --port 8000
```

Open `http://localhost:8000` in your browser.

## How it works

1. The poller hits GitHub API every 60 seconds and saves new failed runs to PostgreSQL
2. Click any failure in the dashboard to trigger AI diagnosis
3. The agent fetches real logs (decompressed from GitHub's ZIP format), the commit diff, and searches pgvector for similar past failures
4. All of this gets sent to Groq as context — the LLM reasons through it and returns a structured JSON diagnosis
5. Each step streams to the browser in real time via SSE
6. The human approves or rejects the suggested fix
7. Approved fixes get embedded with sentence-transformers and stored in pgvector — making future diagnoses on similar failures more accurate

## Key concepts demonstrated

- **RAG (Retrieval Augmented Generation)** — past failures retrieved from pgvector are injected into the LLM prompt as context
- **Agentic tool use** — the AI calls tools (fetch_logs, get_commit_diff, search_past_failures) before reasoning
- **SSE streaming** — real-time event streaming from FastAPI to browser without WebSockets
- **Human-in-the-loop** — approval gate prevents unreviewed AI actions
- **Vector similarity search** — HNSW index on pgvector for fast cosine similarity search

## Project structure
```
ci-failure-analyzer/
├── backend/
│   ├── main.py          # FastAPI app, routes, SSE endpoint
│   ├── config.py        # environment variables
│   ├── poller.py        # GitHub API polling loop
│   └── models.py        # Pydantic models
├── ai/
│   ├── agent.py         # LLM orchestration, SSE streaming
│   ├── tools.py         # fetch_logs, get_commit_diff
│   └── prompts.py       # system prompt
├── db/
│   ├── migrations.py    # table + index creation
│   └── embeddings.py    # generate, store, search vectors
├── frontend/
│   ├── index.html
│   ├── dashboard.js
│   └── style.css
└── docker/
    └── docker-compose.yml
```
