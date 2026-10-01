"""
app.py
-------
Flask web UI for the Redis Database System project.

Pages:
  /            -- dashboard (stat cards + charts)
  /tasks       -- the 10 tasks, each runnable with live JSON output
  /browse      -- browse any of the 13 tables with sorting + search
  /ask         -- natural-language query interface

Configuration (environment variables):
  REDIS_HOST / REDIS_PORT / REDIS_PASSWORD   Redis connection
  READ_ONLY=1        block create/update/delete (use for public demos)
  AUTO_LOAD=1        load ./data into Redis on startup if it is empty
  FLASK_DEBUG=1      enable the debugger (local development only)
  HOST / PORT        bind address (default 127.0.0.1:5000)

By: Omar, Aya, Shelan
"""

import os
import sys
import time

import redis
from flask import Flask, jsonify, redirect, render_template, request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from queries import (  # noqa: E402
    REDIS_HOST,
    REDIS_PORT,
    TABLES,
    browse_table,
    dashboard_data,
    get_redis,
    list_tables,
    natural_language_query,
    task_01_load_summary,
    task_02_filter_students_by_major,
    task_03_top_n_students_by_gpa,
    task_04_crud_student,
    task_05_aggregation_avg_gpa_by_university,
    task_06_multi_condition_search,
    task_07_cross_domain_student_university_dept,
    task_08_redisearch_courses,
    task_09_validation_report,
    task_10_real_world_dashboard,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(
    __name__,
    template_folder=os.path.join(ROOT, "templates"),
    static_folder=os.path.join(ROOT, "static"),
)


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


READ_ONLY = _flag("READ_ONLY")


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _int_arg(name: str, default: int, lo: int, hi: int) -> int:
    """Read an int query param, falling back to `default` and clamping to [lo, hi]."""
    try:
        v = int(request.args.get(name, default))
    except (TypeError, ValueError):
        v = default
    return max(lo, min(hi, v))


def _float_arg(name: str, default: float) -> float:
    try:
        return float(request.args.get(name, default))
    except (TypeError, ValueError):
        return default


def _timed(fn, *args, **kwargs):
    """Run a query and return {"result": ..., "elapsed_ms": ...} for the UI."""
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    return {"result": result,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2)}


@app.context_processor
def inject_globals():
    return {
        "redis_endpoint": f"{REDIS_HOST}:{REDIS_PORT}",
        "read_only": READ_ONLY,
        "table_chips": [(n, m["id_col"]) for n, m in TABLES.items()],
        "repo_url": os.getenv("REPO_URL", "https://github.com/"),
    }


# ----------------------------------------------------------------------
# Pages
# ----------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("home.html")


@app.route("/dashboard")
def dashboard_page():
    return redirect("/", code=301)


@app.route("/ask")
def ask_page():
    return render_template("ask.html")


@app.route("/tasks")
def tasks_page():
    return render_template("tasks.html")


@app.route("/browse")
def browse_page():
    return render_template("browse.html")


# ----------------------------------------------------------------------
# Health + errors
# ----------------------------------------------------------------------
@app.route("/healthz")
def healthz():
    try:
        get_redis().ping()
        return jsonify({"status": "ok", "redis": "up"})
    except redis.RedisError as e:
        return jsonify({"status": "degraded", "redis": "down", "detail": str(e)}), 503


@app.errorhandler(redis.RedisError)
def redis_down(err):
    msg = "Cannot reach Redis. Is the database running and loaded?"
    if request.path.startswith("/api/"):
        return jsonify({"error": msg}), 503
    return render_template("error.html", message=msg), 503


@app.errorhandler(404)
def not_found(err):
    if request.path.startswith("/api/"):
        return jsonify({"error": "not found"}), 404
    return render_template("error.html", message="Page not found.", code=404), 404


@app.errorhandler(500)
def server_error(err):
    if request.path.startswith("/api/"):
        return jsonify({"error": "internal server error"}), 500
    return render_template("error.html", message="Something went wrong.", code=500), 500


# ----------------------------------------------------------------------
# JSON API
# ----------------------------------------------------------------------
@app.route("/api/task/1")
def api_task_1():
    return jsonify(task_01_load_summary())


@app.route("/api/task/2")
def api_task_2():
    major = request.args.get("major", "Computer Science")
    uni = request.args.get("university", "UKH")
    return jsonify(task_02_filter_students_by_major(major, uni))


@app.route("/api/task/3")
def api_task_3():
    n = _int_arg("n", 10, 1, 100)
    uni = request.args.get("university") or None
    return jsonify(task_03_top_n_students_by_gpa(n, uni))


@app.route("/api/task/4", methods=["POST"])
def api_task_4():
    data = request.get_json(force=True, silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "JSON object expected"}), 400
    action = data.pop("action", "read")
    if action not in ("create", "read", "update", "delete"):
        return jsonify({"error": f"unknown action '{action}'"}), 400
    if action != "read" and READ_ONLY:
        return jsonify({"error": "This demo is read-only: create/update/delete are disabled."}), 403
    return jsonify(task_04_crud_student(action, data))


@app.route("/api/task/5")
def api_task_5():
    return jsonify(task_05_aggregation_avg_gpa_by_university())


@app.route("/api/task/6")
def api_task_6():
    return jsonify(task_06_multi_condition_search(
        university=request.args.get("university", "UKH"),
        major=request.args.get("major", "Computer Science"),
        min_gpa=_float_arg("min_gpa", 3.0),
        max_gpa=_float_arg("max_gpa", 4.0),
    ))


@app.route("/api/task/7")
def api_task_7():
    return jsonify(task_07_cross_domain_student_university_dept())


@app.route("/api/task/8")
def api_task_8():
    return jsonify(task_08_redisearch_courses(
        query_text=request.args.get("q", "database"),
        university=request.args.get("university") or None,
    ))


@app.route("/api/task/9")
def api_task_9():
    return jsonify(task_09_validation_report())


@app.route("/api/task/10")
def api_task_10():
    return jsonify(task_10_real_world_dashboard())


@app.route("/api/ask")
def api_ask():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "empty question"}), 400
    if len(q) > 300:
        return jsonify({"error": "question too long (max 300 characters)"}), 400
    t0 = time.perf_counter()
    res = natural_language_query(q)
    if isinstance(res, dict):
        res["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return jsonify(res)


# Database browser
@app.route("/api/tables")
def api_tables():
    return jsonify(list_tables())


@app.route("/api/browse/<table>")
def api_browse(table):
    if table not in TABLES:
        return jsonify({"error": f"unknown table '{table}'", "rows": [], "total": 0}), 404
    return jsonify(browse_table(
        table,
        sort_col=request.args.get("sort_col") or None,
        sort_dir=request.args.get("sort_dir", "asc"),
        page=_int_arg("page", 1, 1, 1_000_000),
        page_size=_int_arg("page_size", 50, 1, 250),
        search=request.args.get("search", ""),
    ))


# Dashboard
@app.route("/api/dashboard")
def api_dashboard():
    return jsonify(dashboard_data())


@app.route("/api/config")
def api_config():
    return jsonify({"read_only": READ_ONLY, "redis": f"{REDIS_HOST}:{REDIS_PORT}"})


# ----------------------------------------------------------------------
# Startup
# ----------------------------------------------------------------------
def maybe_autoload() -> None:
    """Load ./data into Redis if the database is empty (AUTO_LOAD=1)."""
    if not _flag("AUTO_LOAD"):
        return
    try:
        r = get_redis()
        if r.scard("all:student") > 0:
            return
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from load_redis import load_all
        print("AUTO_LOAD: database is empty, loading CSVs ...")
        load_all(r)
    except redis.RedisError as e:
        print(f"AUTO_LOAD skipped: cannot reach Redis ({e})")


maybe_autoload()

if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", 5000)),
        debug=_flag("FLASK_DEBUG"),
    )
