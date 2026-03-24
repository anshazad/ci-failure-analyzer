import asyncio
import json
import psycopg2
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
from dotenv import load_dotenv
from backend.poller import poll_loop, fetch_failed_runs, save_failure
from backend.models import DiagnosisRequest, ApprovalRequest
from ai.agent import diagnose, store_resolved_embedding

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

app = FastAPI(title="CI Failure Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.on_event("startup")
async def startup():
    asyncio.create_task(poll_loop())

@app.get("/")
async def root():
    return FileResponse("frontend/index.html")

@app.get("/api/failures")
async def get_failures():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, repo, workflow, branch, run_id,
               error_category, diagnosis, fix_suggestion, status, created_at
        FROM failures
        ORDER BY created_at DESC
        LIMIT 50
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "id": r[0], "repo": r[1], "workflow": r[2],
            "branch": r[3], "run_id": r[4], "error_category": r[5],
            "diagnosis": r[6], "fix_suggestion": r[7],
            "status": r[8], "created_at": str(r[9])
        }
        for r in rows
    ]

@app.get("/api/stats")
async def get_stats():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM failures")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM failures WHERE status = 'diagnosed'")
    diagnosed = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM failures WHERE status = 'resolved'")
    resolved = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM failures WHERE status = 'pending'")
    pending = cur.fetchone()[0]
    cur.execute("""
        SELECT error_category, COUNT(*) as cnt
        FROM failures
        WHERE error_category IS NOT NULL
        GROUP BY error_category
        ORDER BY cnt DESC
    """)
    categories = [{"category": r[0], "count": r[1]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return {
        "total": total,
        "diagnosed": diagnosed,
        "resolved": resolved,
        "pending": pending,
        "automation_rate": round((diagnosed + resolved) / total * 100) if total > 0 else 0,
        "categories": categories
    }

@app.post("/api/diagnose")
async def trigger_diagnosis(req: DiagnosisRequest):
    async def stream():
        async for event in diagnose(req.run_id):
            yield {
                "event": event["type"],
                "data": json.dumps(event["data"])
            }
    return EventSourceResponse(stream())

@app.post("/api/approve")
async def approve_fix(req: ApprovalRequest):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    new_status = "resolved" if req.approved else "rejected"
    cur.execute("""
        UPDATE failures SET status = %s WHERE run_id = %s
    """, (new_status, req.run_id))
    conn.commit()
    cur.close()
    conn.close()

    # store embedding so future failures can find this as a similar past failure
    if req.approved:
        store_resolved_embedding(req.run_id)

    return {"status": new_status, "run_id": req.run_id}


@app.post("/api/poll")
async def manual_poll():
    runs = await fetch_failed_runs()
    saved = 0
    for run in runs:
        if save_failure(run):
            saved += 1
    return {"found": len(runs), "new": saved}
@app.get("/api/diagnose-get")
async def diagnose_get(run_id: int):
    async def stream():
        async for event in diagnose(run_id):
            evt_type = "error_event" if event["type"] == "error" else event["type"]
            yield {
                "event": evt_type,
                "data": json.dumps(event["data"])
            }
    return EventSourceResponse(stream())
