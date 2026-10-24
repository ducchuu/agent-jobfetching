import sqlite3
import os
import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", "data/jobs.db")

STATUS_FILTERED_BOT = "FILTERED_BOT"
STATUS_FILTERED_LANG = "FILTERED_LANG"
STATUS_FILTERED_EXP = "FILTERED_EXP"
STATUS_EVALUATED = "EVALUATED"
STATUS_ERROR_TRANSIENT = "ERROR_TRANSIENT"

def compute_fingerprint(company: str, title: str) -> str:
    norm_company = "".join(ch.lower() for ch in (company or "") if ch.isalnum())
    norm_title = "".join(ch.lower() for ch in (title or "") if ch.isalnum())
    if not norm_company and not norm_title:
        return ""
    raw = f"{norm_company}:{norm_title}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def init_db():
    dirname = os.path.dirname(DB_PATH)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    cursor = conn.cursor()
    cursor.execute('PRAGMA journal_mode = WAL;')
    cursor.execute('PRAGMA busy_timeout = 5000;')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processed_jobs (
            id TEXT PRIMARY KEY,
            fingerprint TEXT,
            status TEXT,
            score INTEGER,
            reasoning TEXT,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Auto-migrate existing databases that might only have (id, processed_at)
    cursor.execute("PRAGMA table_info(processed_jobs)")
    existing_columns = {col[1] for col in cursor.fetchall()}
    for col_name, col_type in [
        ("fingerprint", "TEXT"),
        ("status", "TEXT"),
        ("score", "INTEGER"),
        ("reasoning", "TEXT"),
        ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    ]:
        if col_name not in existing_columns:
            cursor.execute(f"ALTER TABLE processed_jobs ADD COLUMN {col_name} {col_type};")

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_processed_jobs_fingerprint ON processed_jobs (fingerprint);')
    conn.commit()
    conn.close()
    logger.info(f"Database initialized at {DB_PATH}")

def is_job_processed(job_id: str, company: str = "", title: str = "") -> bool:
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    cursor = conn.cursor()
    
    # Check by raw ID first
    cursor.execute('SELECT status FROM processed_jobs WHERE id = ?', (job_id,))
    row = cursor.fetchone()
    if row:
        status = row[0]
        conn.close()
        # If it failed transiently, it is NOT treated as fully processed
        return status != STATUS_ERROR_TRANSIENT

    # Check by fingerprint (cross-platform deduplication)
    fp = compute_fingerprint(company, title)
    if fp:
        cursor.execute(
            'SELECT 1 FROM processed_jobs WHERE fingerprint = ? AND (status IS NULL OR status != ?)',
            (fp, STATUS_ERROR_TRANSIENT)
        )
        row = cursor.fetchone()
        conn.close()
        return row is not None

    conn.close()
    return False

def record_job_status(
    job_id: str, 
    company: str = "", 
    title: str = "", 
    status: str = STATUS_EVALUATED, 
    score: Optional[int] = None, 
    reasoning: str = ""
):
    fp = compute_fingerprint(company, title)
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO processed_jobs (id, fingerprint, status, score, reasoning, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                fingerprint = excluded.fingerprint,
                status = excluded.status,
                score = excluded.score,
                reasoning = excluded.reasoning,
                updated_at = CURRENT_TIMESTAMP
        ''', (job_id, fp, status, score, reasoning))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to record job status for {job_id}: {e}")
    finally:
        conn.close()

def mark_job_processed(job_id: str):
    record_job_status(job_id=job_id, status=STATUS_EVALUATED)
