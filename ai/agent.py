import asyncio
import json
import psycopg2
import os
from groq import Groq
from dotenv import load_dotenv
from ai.tools import fetch_logs, get_commit_diff
from ai.prompts import SYSTEM_PROMPT
from db.embeddings import search_similar, store_embedding

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

client = Groq(api_key=GROQ_API_KEY)

async def diagnose(run_id: int):
    yield {"type": "thinking", "data": "Fetching failure logs from GitHub..."}
    logs = await fetch_logs(run_id)
    yield {"type": "tool_result", "data": f"Logs retrieved ({len(logs)} chars)"}

    yield {"type": "thinking", "data": "Fetching commit diff..."}
    diff = await get_commit_diff(run_id)
    yield {"type": "tool_result", "data": f"Diff: {diff[:200]}"}

    yield {"type": "thinking", "data": "Searching similar past failures..."}
    similar = search_similar(logs, limit=3)
    if similar:
        yield {"type": "tool_result", "data": f"Found {len(similar)} similar past failures (top similarity: {similar[0]['similarity']})"}
    else:
        yield {"type": "tool_result", "data": "No similar past failures found yet"}

    past_context = ""
    if similar:
        past_context = "\n\n--- SIMILAR PAST FAILURES ---\n"
        for i, s in enumerate(similar, 1):
            past_context += f"""
Past failure {i} (similarity: {s['similarity']}):
  Workflow: {s['workflow']}
  Diagnosis: {s['diagnosis']}
  Fix: {s['fix_suggestion']}
  Category: {s['error_category']}
"""

    yield {"type": "thinking", "data": "Building diagnosis prompt..."}

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"""
Diagnose this CI failure:

Run ID: {run_id}

--- FAILURE LOGS (last 3000 chars) ---
{logs}

--- COMMIT DIFF ---
{diff}
{past_context}
Provide:
1. Root cause (1-2 sentences)
2. Fix suggestion (specific and actionable)
3. Error category (one of: build_failure, test_failure, docker_failure, lint_error, oom, timeout, network, other)
4. Confidence (high/medium/low)

Format your response as JSON:
{{
  "root_cause": "...",
  "fix_suggestion": "...",
  "error_category": "...",
  "confidence": "..."
}}
"""}
    ]

    yield {"type": "tool_start", "data": "Sending to Groq LLM (llama-3.3-70b)..."}

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=0.1,
        max_tokens=500
    )

    raw = response.choices[0].message.content.strip()
    clean = raw.replace("```json", "").replace("```", "").strip()

    yield {"type": "stream", "data": clean}

    try:
        result = json.loads(clean)

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            UPDATE failures
            SET diagnosis = %s,
                fix_suggestion = %s,
                error_category = %s,
                log_tail = %s,
                status = 'diagnosed'
            WHERE run_id = %s
        """, (
            result.get("root_cause"),
            result.get("fix_suggestion"),
            result.get("error_category"),
            logs[-500:],
            run_id
        ))
        conn.commit()
        cur.close()
        conn.close()

        yield {"type": "done", "data": result}

    except Exception as e:
        yield {"type": "error", "data": f"Parse error: {e} | Raw: {raw}"}


def store_resolved_embedding(run_id: int):
    """
    Call this after a failure is approved/resolved.
    Embeds the log + diagnosis text so future failures can find it.
    """
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            SELECT log_tail, diagnosis, fix_suggestion, error_category
            FROM failures WHERE run_id = %s
        """, (run_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        if row and row[0]:
            text = f"{row[0]} diagnosis: {row[1]} fix: {row[2]} category: {row[3]}"
            store_embedding(run_id, text)
    except Exception as e:
        print(f"Error storing resolved embedding: {e}")
