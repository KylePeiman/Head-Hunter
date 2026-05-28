import json
import os
import sqlite3


def init_db(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            hash        TEXT    UNIQUE NOT NULL,
            title       TEXT    NOT NULL,
            company     TEXT    NOT NULL,
            location    TEXT,
            remote      INTEGER DEFAULT 0,
            description TEXT,
            url         TEXT,
            source      TEXT,
            posted_at   TEXT,
            embedding   TEXT,
            created_at  TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS simulations (
            id                         INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id                     INTEGER NOT NULL REFERENCES jobs(id),
            surfaced                   INTEGER DEFAULT 0,
            pass_rate                  REAL,
            ats_pass_rate              REAL,
            common_missing_keywords    TEXT,
            sample_recruiter_reasoning TEXT,
            simulated_at               TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    return conn


def job_exists(conn: sqlite3.Connection, job_hash: str) -> bool:
    row = conn.execute("SELECT 1 FROM jobs WHERE hash=? LIMIT 1", (job_hash,)).fetchone()
    return row is not None


def insert_job(conn: sqlite3.Connection, job: dict) -> int:
    cur = conn.execute(
        """INSERT OR IGNORE INTO jobs
           (hash, title, company, location, remote, description, url, source, posted_at, embedding)
           VALUES (:hash, :title, :company, :location, :remote, :description, :url, :source, :posted_at, :embedding)
        """,
        {
            "hash": job["hash"],
            "title": job["title"],
            "company": job["company"],
            "location": job.get("location", ""),
            "remote": 1 if job.get("remote") else 0,
            "description": job.get("description", ""),
            "url": job.get("url", ""),
            "source": job.get("source", ""),
            "posted_at": job.get("posted_at", ""),
            "embedding": json.dumps(job["embedding"]) if job.get("embedding") else None,
        },
    )
    conn.commit()
    if cur.lastrowid:
        return cur.lastrowid
    row = conn.execute("SELECT id FROM jobs WHERE hash=?", (job["hash"],)).fetchone()
    return row["id"]


def update_job_embedding(conn: sqlite3.Connection, job_id: int, embedding: list) -> None:
    conn.execute("UPDATE jobs SET embedding=? WHERE id=?", (json.dumps(embedding), job_id))
    conn.commit()


def upsert_simulation(conn: sqlite3.Connection, job_id: int, result: dict) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO simulations
           (job_id, surfaced, pass_rate, ats_pass_rate, common_missing_keywords, sample_recruiter_reasoning)
           VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            1 if result.get("surfaced") else 0,
            result.get("pass_rate", 0.0),
            result.get("ats_pass_rate", 0.0),
            json.dumps(result.get("common_missing_keywords", [])),
            result.get("sample_recruiter_reasoning", ""),
        ),
    )
    conn.commit()


def get_surfaced_jobs(conn: sqlite3.Connection, sort_by: str = "pass_rate") -> list[dict]:
    allowed = {"pass_rate", "ats_pass_rate"}
    col = sort_by if sort_by in allowed else "pass_rate"
    rows = conn.execute(
        f"""SELECT jobs.*, simulations.surfaced, simulations.pass_rate,
                   simulations.ats_pass_rate, simulations.common_missing_keywords,
                   simulations.sample_recruiter_reasoning, simulations.simulated_at
            FROM jobs
            JOIN simulations ON jobs.id = simulations.job_id
            WHERE simulations.surfaced = 1
            ORDER BY simulations.{col} DESC
        """
    ).fetchall()
    jobs = []
    for row in rows:
        job = dict(row)
        if job.get("common_missing_keywords"):
            try:
                job["common_missing_keywords"] = json.loads(job["common_missing_keywords"])
            except (json.JSONDecodeError, TypeError):
                job["common_missing_keywords"] = []
        else:
            job["common_missing_keywords"] = []
        if job.get("embedding"):
            job.pop("embedding")
        jobs.append(job)
    return jobs


def get_jobs_without_simulation(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT jobs.*
           FROM jobs
           LEFT JOIN simulations ON jobs.id = simulations.job_id
           WHERE simulations.job_id IS NULL
        """
    ).fetchall()
    jobs = []
    for row in rows:
        job = dict(row)
        if job.get("embedding"):
            try:
                job["embedding"] = json.loads(job["embedding"])
            except (json.JSONDecodeError, TypeError):
                job["embedding"] = None
        jobs.append(job)
    return jobs


def get_job_by_id(conn: sqlite3.Connection, job_id: int) -> dict | None:
    row = conn.execute(
        """SELECT jobs.*, simulations.surfaced, simulations.pass_rate,
                   simulations.ats_pass_rate, simulations.common_missing_keywords,
                   simulations.sample_recruiter_reasoning
            FROM jobs
            LEFT JOIN simulations ON jobs.id = simulations.job_id
            WHERE jobs.id = ?
        """,
        (job_id,),
    ).fetchone()
    if not row:
        return None
    job = dict(row)
    if job.get("common_missing_keywords"):
        try:
            job["common_missing_keywords"] = json.loads(job["common_missing_keywords"])
        except (json.JSONDecodeError, TypeError):
            job["common_missing_keywords"] = []
    else:
        job["common_missing_keywords"] = []
    if job.get("embedding"):
        job.pop("embedding")
    return job


def close_db(conn: sqlite3.Connection) -> None:
    conn.close()
