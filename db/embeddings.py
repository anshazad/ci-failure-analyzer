import psycopg2
import os
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

model = SentenceTransformer('all-MiniLM-L6-v2')

def generate_embedding(text: str) -> list:
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()

def store_embedding(run_id: int, text: str):
    try:
        embedding = generate_embedding(text)
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            UPDATE failures
            SET embedding = %s::vector
            WHERE run_id = %s
        """, (embedding, run_id))
        conn.commit()
        cur.close()
        conn.close()
        print(f"Embedding stored for run_id {run_id}")
    except Exception as e:
        print(f"Error storing embedding: {e}")

def search_similar(text: str, limit: int = 3) -> list:
    try:
        embedding = generate_embedding(text)
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            SELECT workflow, branch, log_tail, diagnosis,
                   fix_suggestion, error_category,
                   1 - (embedding <=> %s::vector) as similarity
            FROM failures
            WHERE embedding IS NOT NULL
              AND status = 'resolved'
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, (embedding, embedding, limit))
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
                "error_category": r[5],
                "similarity": round(float(r[6]), 3)
            }
            for r in rows
        ]
    except Exception as e:
        print(f"Search error: {e}")
        return []
