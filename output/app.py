import logging
import os
import threading

from flask import Flask, redirect, render_template, request, url_for

from db.database import get_job_by_id, get_surfaced_jobs, init_db

logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="templates")

_db_path: str = ""
_run_cycle_fn = None
_cycle_lock = threading.Lock()


def configure(db_path: str, run_cycle_fn=None) -> None:
    global _db_path, _run_cycle_fn
    _db_path = db_path
    _run_cycle_fn = run_cycle_fn


def _get_conn():
    db_path = _db_path or os.environ.get("HEADHUNTER_DB", "db/headhunter.db")
    return init_db(db_path)


@app.route("/")
def index():
    sort_by = request.args.get("sort", "pass_rate")
    conn = _get_conn()
    try:
        jobs = get_surfaced_jobs(conn, sort_by=sort_by)
    finally:
        conn.close()
    return render_template("index.html", jobs=jobs, sort_by=sort_by)


@app.route("/job/<int:job_id>")
def job_detail(job_id: int):
    conn = _get_conn()
    try:
        job = get_job_by_id(conn, job_id)
    finally:
        conn.close()
    if not job:
        return "Job not found", 404
    return render_template("job_detail.html", job=job)


@app.route("/refresh", methods=["POST"])
def refresh():
    if _run_cycle_fn is not None:
        if _cycle_lock.acquire(blocking=False):
            try:
                thread = threading.Thread(target=_run_and_release, daemon=True)
                thread.start()
            except Exception:
                _cycle_lock.release()
                raise
        else:
            logger.info("Refresh already in progress — skipping")
    return redirect(url_for("index"))


def _run_and_release():
    try:
        if _run_cycle_fn:
            _run_cycle_fn()
    finally:
        _cycle_lock.release()
