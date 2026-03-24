import httpx
import asyncio
import psycopg2
from datetime import datetime, timezone
from dotenv import load_dotenv
import os

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
DATABASE_URL = os.getenv("DATABASE_URL")
POLL_INTERVAL = 60

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

def save_failure(run: dict):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO failures (repo, workflow, branch, run_id, status)
            VALUES (%s, %s, %s, %s, 'pending')
            ON CONFLICT (run_id) DO NOTHING
        """, (
            GITHUB_REPO,
            run["name"],
            run["head_branch"],
            run["id"]
        ))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"DB error: {e}")
        return False

async def fetch_failed_runs():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/runs"
    params = {"status": "failure", "per_page": 10}
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=HEADERS, params=params)
        if resp.status_code != 200:
            print(f"GitHub API error: {resp.status_code} {resp.text}")
            return []
        data = resp.json()
        return data.get("workflow_runs", [])

async def poll_loop():
    print(f"Poller started — watching {GITHUB_REPO} every {POLL_INTERVAL}s")
    while True:
        try:
            runs = await fetch_failed_runs()
            new = 0
            for run in runs:
                if save_failure(run):
                    new += 1
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Polled — {len(runs)} failures found, {new} new")
        except Exception as e:
            print(f"Poll error: {e}")
        await asyncio.sleep(POLL_INTERVAL)
