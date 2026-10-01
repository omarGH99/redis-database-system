"""
tasks.py -- the 10 tasks: basic, intermediate and advanced.
"""

from collections import defaultdict
from typing import Any, Dict, List, Optional


from . import core
from .core import _ft_escape, _has_redisearch, _hydrate
from .browse import TABLES


# ======================================================================
# BASIC TASKS
# ======================================================================

def task_01_load_summary() -> Dict[str, int]:
    """
    BASIC #1 -- load + summary.
    Counts every table via SCARD on the all:* sets.
    """
    r = core.get_redis()
    pipe = r.pipeline()
    prefixes = [meta["prefix"] for meta in TABLES.values()]
    for prefix in prefixes:
        pipe.scard(f"all:{prefix}")
    return dict(zip(prefixes, pipe.execute()))


def task_02_filter_students_by_major(
    major: str = "Computer Science",
    university: str = "UKH",
) -> List[Dict[str, Any]]:
    """
    BASIC #2 -- filtering query.
    "Students at <university> majoring in <major>" -- one SINTER over two
    reverse-index sets.
    """
    r = core.get_redis()
    ids = sorted(r.sinter(
        f"idx:student:by_university:{university}",
        f"idx:student:by_major:{major}",
    ))
    return _hydrate(r, ids, "student")


def task_03_top_n_students_by_gpa(
    n: int = 10,
    university: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    BASIC #3 -- sorting + limiting.
    Top N students by GPA (optionally restricted to one university).
    Uses ZREVRANGE on idx:student:by_gpa for the global ranking,
    or ZSCORE fan-out filtered to a university's Set for the scoped version.
    """
    r = core.get_redis()
    if university:
        candidates = r.smembers(f"idx:student:by_university:{university}")
        if not candidates:
            return []
        pipe = r.pipeline()
        for sid in candidates:
            pipe.zscore("idx:student:by_gpa", sid)
        scores = pipe.execute()
        ranked = sorted(
            [(sid, s) for sid, s in zip(candidates, scores) if s is not None],
            key=lambda x: -x[1],
        )[:n]
        ids = [sid for sid, _ in ranked]
    else:
        ids = r.zrevrange("idx:student:by_gpa", 0, n - 1)
    return _hydrate(r, ids, "student")


# ======================================================================
# INTERMEDIATE TASKS
# ======================================================================

def task_04_crud_student(action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    INTERMEDIATE #1 -- full CRUD on a student record.
    Updates the hash AND keeps the reverse indexes consistent inside a
    pipeline so a partial failure leaves the indexes coherent.

    `action` is one of: create | read | update | delete.
    """
    r = core.get_redis()
    sid = payload.get("student_id", "").strip()
    if not sid:
        return {"error": "student_id is required"}
    key = f"student:{sid}"

    if action == "read":
        rec = r.hgetall(key)
        return rec or {"error": f"no such student {sid}"}

    if action == "delete":
        old = r.hgetall(key)
        if not old:
            return {"error": f"no such student {sid}"}
        pipe = r.pipeline()
        pipe.delete(key)
        pipe.srem("all:student", sid)
        for col in ("university", "major", "city"):
            if old.get(col):
                pipe.srem(f"idx:student:by_{col}:{old[col]}", sid)
        for col in ("age", "gpa", "enroll_year"):
            pipe.zrem(f"idx:student:by_{col}", sid)
        pipe.execute()
        return {"deleted": sid}

    # create | update
    old = r.hgetall(key) if action == "update" else {}
    pipe = r.pipeline()
    pipe.hset(key, mapping={k: str(v) for k, v in payload.items()})
    pipe.sadd("all:student", sid)
    for col in ("university", "major", "city"):
        if col in payload:
            new_val = str(payload[col])
            if old.get(col) and old[col] != new_val:
                pipe.srem(f"idx:student:by_{col}:{old[col]}", sid)
            pipe.sadd(f"idx:student:by_{col}:{new_val}", sid)
    for col in ("age", "gpa", "enroll_year"):
        if col in payload:
            try:
                pipe.zadd(f"idx:student:by_{col}", {sid: float(payload[col])})
            except (TypeError, ValueError):
                pass
    pipe.execute()
    return {"action": action, "student_id": sid, "record": r.hgetall(key)}


def task_05_aggregation_avg_gpa_by_university(min_students: int = 1) -> List[Dict[str, Any]]:
    """
    INTERMEDIATE #2 -- aggregation: average GPA per university.
    Redis has no GROUP BY, so we fan out one ZSCORE per student per
    university and aggregate client-side.  Demonstrates how to think
    about aggregations in a KV store.

    The dataset has many universities with only one student.  Pass
    min_students > 1 to focus on the universities with real cohorts.
    Results are returned in two groups: 'with_cohort' (>=min_students,
    sorted by avg GPA desc) and 'singletons' (everyone else, summarised).
    """
    r = core.get_redis()
    rows: List[Dict[str, Any]] = []

    for key in r.scan_iter(match="idx:student:by_university:*", count=2000):
        uni = key.split(":")[-1]
        sids = r.smembers(key)
        if not sids:
            continue
        pipe = r.pipeline()
        for sid in sids:
            pipe.zscore("idx:student:by_gpa", sid)
        gpas = [g for g in pipe.execute() if g is not None]
        if not gpas:
            continue
        uni_meta = r.hgetall(f"university:{uni}") if r.exists(f"university:{uni}") else {}
        rows.append({
            "university_id": uni,
            "name": uni_meta.get("name", uni),
            "city": uni_meta.get("city", ""),
            "students": len(sids),
            "avg_gpa": round(sum(gpas) / len(gpas), 3),
            "min_gpa": round(min(gpas), 2),
            "max_gpa": round(max(gpas), 2),
        })

    # Largest cohort first, then highest GPA
    rows.sort(key=lambda x: (-x["students"], -x["avg_gpa"]))
    return rows


def task_06_multi_condition_search(
    university: str = "UKH",
    major: str = "Computer Science",
    min_gpa: float = 3.0,
    max_gpa: float = 4.0,
) -> List[Dict[str, Any]]:
    """
    INTERMEDIATE #3 -- multi-condition (AND across categorical attributes
    + numeric range).  Combines two SETs (university, major) with one
    ZSCORE filter (gpa) using a single pipeline.
    """
    r = core.get_redis()
    cand = r.sinter(
        f"idx:student:by_university:{university}",
        f"idx:student:by_major:{major}",
    )
    if not cand:
        return []
    pipe = r.pipeline()
    for sid in cand:
        pipe.zscore("idx:student:by_gpa", sid)
    scores = pipe.execute()
    keep = [sid for sid, gpa in zip(cand, scores)
            if gpa is not None and min_gpa <= gpa <= max_gpa]
    return sorted(_hydrate(r, keep, "student"),
                  key=lambda s: -float(s.get("gpa", 0)))


def task_07_cross_domain_student_university_dept() -> List[Dict[str, Any]]:
    """
    INTERMEDIATE #4 -- cross-domain join: students × universities × departments.
    For each student, join their university name and the department name of
    their first enrolled course. Emulates a three-table SQL JOIN purely via
    hash lookups and set membership — no dedicated join index needed.
    """
    r = core.get_redis()
    out: List[Dict[str, Any]] = []

    # Build a quick dept_id → department_name lookup once
    dept_name_cache: Dict[str, str] = {}

    # Take a sample of 50 students for performance
    sids = list(r.smembers("all:student"))[:50]
    pipe = r.pipeline()
    for sid in sids:
        pipe.hgetall(f"student:{sid}")
    students = [s for s in pipe.execute() if s]

    for s in students:
        uni_id = s.get("university", "")
        uni_meta = r.hgetall(f"university:{uni_id}") if uni_id else {}

        # Find one enrolled course for this student and resolve its department
        course_ids = list(r.smembers(f"idx:enroll:courses_of_student:{s['student_id']}"))
        dept_name = ""
        if course_ids:
            dept_id = r.hget(f"course:{course_ids[0]}", "department") or ""
            if dept_id not in dept_name_cache:
                dept_name_cache[dept_id] = (
                    r.hget(f"department:{dept_id}", "department_name") or dept_id
                )
            dept_name = dept_name_cache[dept_id]

        out.append({
            "student_id":   s.get("student_id"),
            "full_name":    s.get("full_name"),
            "university":   uni_id,
            "uni_name":     uni_meta.get("name", uni_id),
            "uni_city":     uni_meta.get("city", ""),
            "major":        s.get("major"),
            "dept_name":    dept_name,
            "gpa":          s.get("gpa"),
        })

    return sorted(out, key=lambda x: x["student_id"] or "")


# ======================================================================
# ADVANCED TASKS
# ======================================================================

def task_08_redisearch_courses(
    query_text: str = "data science",
    university: Optional[str] = None,
) -> Dict[str, Any]:
    """
    ADVANCED #1 -- DB-specific feature: RediSearch full-text on courses.
    Falls back to a SCAN-based substring filter when RediSearch isn't
    loaded, so the demo keeps working on plain Redis as well.
    """
    r = core.get_redis()
    q = (query_text or "").strip()[:200] or "*"

    if _has_redisearch(r):
        from redis.commands.search.query import Query
        fq = q if q == "*" else " ".join(_ft_escape(w) for w in q.split())
        if university:
            q_str = f"({fq}) @university:{{{_ft_escape(university)}}}"
        else:
            q_str = fq
        res = r.ft("idx_courses_ft").search(Query(q_str).paging(0, 25))
        docs = []
        for doc in res.docs:
            d = {k: v for k, v in doc.__dict__.items() if k not in ("payload",)}
            docs.append(d)
        return {"engine": "RediSearch", "query": q_str, "total": res.total, "docs": docs}

    # Fallback: scan + substring match
    pattern = q.lower()
    docs = []
    for key in r.scan_iter(match="course:*", count=2000):
        row = r.hgetall(key)
        if university and row.get("university") != university:
            continue
        text = " ".join([row.get("course_name", ""), row.get("professor", ""),
                         row.get("department", "")]).lower()
        if pattern == "*" or pattern in text:
            docs.append({"id": key, **row})
            if len(docs) >= 25:
                break
    return {"engine": "scan-fallback", "query": q, "total": len(docs), "docs": docs}


def task_09_validation_report() -> Dict[str, Any]:
    """
    ADVANCED #2 -- referential integrity validation.
    Checks all foreign-key relations across the 6 student-focused tables:
      - enrollments  → student and course must exist
      - courses      → department must exist
      - students     → university must exist
      - departments  → university must exist
    Redis does not enforce these, so we audit them explicitly.
    """
    r = core.get_redis()
    issues = {
        "checked_enrollments":          0,
        "orphan_enrollments_student":   0,
        "orphan_enrollments_course":    0,
        "checked_courses":              0,
        "orphan_courses_department":    0,
        "checked_students":             0,
        "orphan_students_university":   0,
        "checked_departments":          0,
        "orphan_departments_university": 0,
    }
    examples: Dict[str, List[str]] = defaultdict(list)

    # Pre-load membership sets (fast EXISTS alternative)
    students     = r.smembers("all:student")
    courses      = r.smembers("all:course")
    departments  = r.smembers("all:department")
    universities = r.smembers("all:university")

    # enrollments → student + course
    pipe = r.pipeline()
    enroll_keys = list(r.scan_iter(match="enrollment:*", count=2000))
    for k in enroll_keys:
        pipe.hmget(k, "student_id", "course_id")
    for key, (sid, cid) in zip(enroll_keys, pipe.execute()):
        issues["checked_enrollments"] += 1
        if sid not in students:
            issues["orphan_enrollments_student"] += 1
            if len(examples["bad_enrollment_student"]) < 3:
                examples["bad_enrollment_student"].append(f"{key} → student:{sid}")
        if cid not in courses:
            issues["orphan_enrollments_course"] += 1
            if len(examples["bad_enrollment_course"]) < 3:
                examples["bad_enrollment_course"].append(f"{key} → course:{cid}")

    # courses → department
    pipe = r.pipeline()
    for cid in courses:
        pipe.hget(f"course:{cid}", "department")
    for cid, dept in zip(courses, pipe.execute()):
        issues["checked_courses"] += 1
        if dept and dept not in departments:
            issues["orphan_courses_department"] += 1
            if len(examples["bad_course_dept"]) < 3:
                examples["bad_course_dept"].append(f"course:{cid} → dept:{dept}")

    # students → university
    pipe = r.pipeline()
    for sid in students:
        pipe.hget(f"student:{sid}", "university")
    for sid, uni in zip(students, pipe.execute()):
        issues["checked_students"] += 1
        if uni and uni not in universities:
            issues["orphan_students_university"] += 1
            if len(examples["bad_student_uni"]) < 3:
                examples["bad_student_uni"].append(f"student:{sid} → uni:{uni}")

    # departments → university
    pipe = r.pipeline()
    for did in departments:
        pipe.hget(f"department:{did}", "university")
    for did, uni in zip(departments, pipe.execute()):
        issues["checked_departments"] += 1
        if uni and uni not in universities:
            issues["orphan_departments_university"] += 1

    issues["status"] = "OK" if all(
        v == 0 for k, v in issues.items() if k.startswith("orphan_")
    ) else "ISSUES"
    issues["examples"] = dict(examples)
    return issues


def task_10_real_world_dashboard() -> Dict[str, Any]:
    """
    ADVANCED #3 -- real-world composite query.
    Uses only the 6 student-focused tables:
      - top 5 most-enrolled courses
      - top universities by student count
      - students per major distribution
      - GPA stats per university (cohorts >= 3 students)
      - top events by tickets
      - departments by course count
    """
    r = core.get_redis()
    out: Dict[str, Any] = {}

    # Top 5 courses by enrollment
    course_ids = list(r.smembers("all:course"))
    pipe = r.pipeline()
    for cid in course_ids:
        pipe.scard(f"idx:enroll:students_in_course:{cid}")
    counts = pipe.execute()
    top = sorted(zip(course_ids, counts), key=lambda x: -x[1])[:5]
    out["top_courses_by_enrollment"] = [
        {**r.hgetall(f"course:{cid}"), "enrollment_count": cnt}
        for cid, cnt in top if cnt > 0
    ]

    # Top universities by student count
    uni_counts = []
    for key in r.scan_iter(match="idx:student:by_university:*", count=2000):
        uni = key.split(":")[-1]
        uni_counts.append((uni, r.scard(key)))
    uni_counts.sort(key=lambda x: -x[1])
    out["top_universities_by_students"] = [
        {**(r.hgetall(f"university:{uni}") or {"university_id": uni}),
         "student_count": c}
        for uni, c in uni_counts[:5]
    ]

    # Students per major
    major_counts = []
    for key in r.scan_iter(match="idx:student:by_major:*", count=2000):
        m = key.split(":", 3)[-1]
        major_counts.append({"major": m, "students": r.scard(key)})
    major_counts.sort(key=lambda x: -x["students"])
    out["students_per_major"] = major_counts

    # GPA stats (meaningful cohorts only)
    gpa_rows = task_05_aggregation_avg_gpa_by_university()
    out["gpa_by_university"] = [g for g in gpa_rows if g["students"] >= 3][:8]

    # Top events by tickets
    top_events = r.zrevrange("idx:event:by_tickets", 0, 4)
    if not top_events:
        top_events = list(r.smembers("all:event"))[:5]
    out["top_events"] = [r.hgetall(f"event:{eid}") for eid in top_events]

    # Departments by course count
    dept_counts = []
    for key in r.scan_iter(match="idx:course:by_department:*", count=2000):
        did = key.split(":", 3)[-1]
        cnt = r.scard(key)
        if cnt:
            dept_counts.append({
                "dept_id": did,
                "department_name": r.hget(f"department:{did}", "department_name") or did,
                "courses": cnt,
            })
    dept_counts.sort(key=lambda x: -x["courses"])
    out["departments_by_course_count"] = dept_counts[:8]

    return out
