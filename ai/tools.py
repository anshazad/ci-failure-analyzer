import httpx
import psycopg2
import os
import zipfile
import io
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
DATABASE_URL = os.getenv("DATABASE_URL")

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

async def fetch_logs(run_id: int) -> str:
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            r = await client.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/actions/runs/{run_id}/logs",
                headers=HEADERS,
                timeout=30
            )
            if r.status_code != 200:
                return f"Could not fetch logs: HTTP {r.status_code}"

            zip_bytes = io.BytesIO(r.content)
            all_text = []

            with zipfile.ZipFile(zip_bytes) as zf:
                for name in zf.namelist():
                    if name.endswith(".txt"):
                        with zf.open(name) as f:
                            content = f.read().decode("utf-8", errors="ignore")
                            all_text.append(f"=== {name} ===\n{content}")

            full_log = "\n".join(all_text)
            return full_log[-3000:] if len(full_log) > 3000 else full_log

    except zipfile.BadZipFile:
        return r.text[-3000:]
    except Exception as e:
        return f"Error fetching logs: {e}"

async def get_commit_diff(run_id: int) -> str:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/actions/runs/{run_id}",
                headers=HEADERS
            )
            if r.status_code != 200:
                return f"Could not fetch run details: HTTP {r.status_code}"

            run_data = r.json()
            sha = run_data.get("head_sha", "")
            if not sha:
                return "No commit SHA found"

            r2 = await client.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/commits/{sha}",
                headers=HEADERS
            )
            if r2.status_code != 200:
                return f"Could not fetch commit: HTTP {r2.status_code}"

            commit_data = r2.json()
            message = commit_data.get("commit", {}).get("message", "")
            files = commit_data.get("files", [])
            changed = [f["filename"] for f in files[:10]]
            return f"Commit: {message}\nChanged files: {', '.join(changed)}"
    except Exception as e:
        return f"Error fetching diff: {e}"

def search_past_failures(query_embedding: list, limit: int = 3) -> list:
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            SELECT workflow, branch, log_tail, diagnosis, fix_suggestion,
                   1 - (embedding <=> %s::vector) as similarity
            FROM failures
            WHERE embedding IS NOT NULL
              AND status = 'resolved'
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, (query_embedding, query_embedding, limit))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {
                "workflow": r[0],
                "branch": r[1],
                "log_tail": r[2][:300] if r[2] else "",
                "diagnosis": r[3],
                "fix_suggestion": r[4],
                "similarity": round(float(r[5]), 3)
            }
            for r in rows
        ]
    except Exception as e:
        print(f"Search error: {e}")
        return []
