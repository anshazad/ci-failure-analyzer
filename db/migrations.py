import psycopg2
from backend.config import DATABASE_URL

def run_migrations():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS failures (
            id SERIAL PRIMARY KEY,
            repo TEXT,
            workflow TEXT,
            branch TEXT,
            run_id BIGINT UNIQUE,
            error_category TEXT,
            log_tail TEXT,
            diagnosis TEXT,
            fix_suggestion TEXT,
            status TEXT DEFAULT 'pending',
            embedding vector(384),
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS failures_embedding_idx
        ON failures USING hnsw (embedding vector_cosine_ops);
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("Migrations done.")

if __name__ == "__main__":
    run_migrations()
