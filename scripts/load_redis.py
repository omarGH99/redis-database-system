"""
load_redis.py
--------------
Loads every CSV from ./data into Redis using the schema described in
docs/SCHEMA.md.  Run after `docker compose up -d`.

Expected files in ./data (each ~1,000 rows):
    universities.csv          1000 rows
    departments.csv           1000 rows
    courses.csv               1000 rows
    students.csv              1000 rows
    enrollments_1000.csv      1000 rows
    hospitals.csv             1000 rows
    patients_1000.csv         1000 rows
    companies.csv             1000 rows
    properties.csv            1000 rows
    ministries.csv            1000 rows
    government_projects.csv   1000 rows
    events.csv                1000 rows
    event_registrations_1000.csv  1000 rows

For every CSV we materialise:
  - a HASH per row at <prefix>:<id>
  - a SET   "all:<prefix>"                     -- global membership
  - SETs    "idx:<prefix>:by_<col>:<value>"    -- categorical lookup
  - ZSETs   "idx:<prefix>:by_<col>"            -- numeric/range lookup
  - relationship sets for the many-to-many tables
  - RediSearch full-text indexes for free-text Q&A
"""

import csv
import os
import sys
from pathlib import Path

import redis
from redis.commands.search.field import TagField, TextField, NumericField
try:
    from redis.commands.search.index_definition import IndexDefinition, IndexType
except ModuleNotFoundError:
    # Older redis-py (<5.0) used the camelCase filename
    from redis.commands.search.indexDefinition import IndexDefinition, IndexType

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None


def connect():
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD,
                    decode_responses=True)
    r.ping()
    print(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
    return r


# ----------------------------------------------------------------------
# Generic CSV -> Hash + indexes
# ----------------------------------------------------------------------
def load_csv(r, filename, key_prefix, id_col,
             tag_indexes=None, num_indexes=None, alias=None):
    """
    tag_indexes : list of column names that get SET reverse indexes
    num_indexes : list of column names that get SORTED-SET range indexes
    alias       : optional callable (row) -> list[(alias_index_name, value)]
                  for derived/multi-value indexes (e.g. comma-sep specialities)
    """
    path = DATA_DIR / filename
    if not path.exists():
        print(f"  skip {filename:30s} (not found)")
        return 0

    tag_indexes = tag_indexes or []
    num_indexes = num_indexes or []

    pipe = r.pipeline(transaction=False)
    count = 0

    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            row_id = (row.get(id_col) or "").strip()
            if not row_id:
                continue
            key = f"{key_prefix}:{row_id}"

            pipe.hset(key, mapping={k: (v or "") for k, v in row.items()})
            pipe.sadd(f"all:{key_prefix}", row_id)

            for col in tag_indexes:
                val = (row.get(col) or "").strip()
                if val:
                    pipe.sadd(f"idx:{key_prefix}:by_{col}:{val}", row_id)

            for col in num_indexes:
                val = (row.get(col) or "").strip()
                if val:
                    try:
                        pipe.zadd(f"idx:{key_prefix}:by_{col}", {row_id: float(val)})
                    except ValueError:
                        pass

            if alias is not None:
                for idx_name, val in alias(row):
                    if val:
                        pipe.sadd(f"idx:{key_prefix}:{idx_name}:{val}", row_id)

            count += 1
            if count % 500 == 0:
                pipe.execute()
                pipe = r.pipeline(transaction=False)

    pipe.execute()
    print(f"  loaded {count:>5} rows from {filename}")
    return count


# ----------------------------------------------------------------------
# Domain-specific loaders
# ----------------------------------------------------------------------
def load_universities(r):
    return load_csv(
        r, "universities.csv", "university", "university_id",
        tag_indexes=["city"],
        num_indexes=["founded", "students", "departments"],
    )


def load_departments(r):
    """Departments link to universities by the 'university' column (UKH/SPU/...)."""
    return load_csv(
        r, "departments.csv", "department", "dept_id",
        tag_indexes=["university", "department_name"],
        num_indexes=["students", "budget_usd"],
    )


def load_courses(r):
    """
    Courses link to a department via dept_id.  We resolve each course's
    university via departments.csv and store both a derived field on
    the hash AND an idx:course:by_university:<uni> reverse index.
    """
    path = DATA_DIR / "courses.csv"
    if not path.exists():
        print("  skip courses.csv (not found)")
        return 0

    dept_to_uni = {}
    dept_path = DATA_DIR / "departments.csv"
    if dept_path.exists():
        with open(dept_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                dept_to_uni[row["dept_id"]] = row["university"]

    pipe = r.pipeline(transaction=False)
    count = 0
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cid = row["course_id"]
            key = f"course:{cid}"
            uni = dept_to_uni.get((row.get("department") or "").strip(), "")
            payload = {**row, "university": uni}
            pipe.hset(key, mapping={k: (v or "") for k, v in payload.items()})
            pipe.sadd("all:course", cid)

            for col in ("department", "professor", "mode"):
                val = (row.get(col) or "").strip()
                if val:
                    pipe.sadd(f"idx:course:by_{col}:{val}", cid)
            if uni:
                pipe.sadd(f"idx:course:by_university:{uni}", cid)

            for col in ("credits", "max_cap"):
                try:
                    pipe.zadd(f"idx:course:by_{col}", {cid: float(row[col])})
                except (KeyError, ValueError):
                    pass

            count += 1
            if count % 500 == 0:
                pipe.execute()
                pipe = r.pipeline(transaction=False)
    pipe.execute()
    print(f"  loaded {count:>5} rows from courses.csv (with derived university index)")
    return count


def load_students(r):
    return load_csv(
        r, "students.csv", "student", "student_id",
        tag_indexes=["university", "major", "city"],
        num_indexes=["age", "gpa", "enroll_year"],
    )


def load_enrollments(r):
    """Many-to-many between students and courses, materialised both ways."""
    path = DATA_DIR / "enrollments_1000.csv"
    if not path.exists():
        print("  skip enrollments_1000.csv (not found)")
        return 0

    pipe = r.pipeline(transaction=False)
    count = 0
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            eid = row["enroll_id"]
            sid = row["student_id"]
            cid = row["course_id"]
            pipe.hset(f"enrollment:{eid}", mapping={k: (v or "") for k, v in row.items()})
            pipe.sadd("all:enrollment", eid)
            pipe.sadd(f"idx:enroll:students_in_course:{cid}", sid)
            pipe.sadd(f"idx:enroll:courses_of_student:{sid}", cid)
            pipe.sadd(f"idx:enroll:by_status:{(row.get('status') or '').strip()}", eid)
            pipe.sadd(f"idx:enroll:by_semester:{(row.get('semester') or '').strip()}", eid)
            if (row.get("grade") or "").strip():
                pipe.hset(f"grade:{sid}:{cid}", mapping={
                    "grade": row["grade"],
                    "semester": (row.get("semester") or ""),
                })
            count += 1
            if count % 500 == 0:
                pipe.execute()
                pipe = r.pipeline(transaction=False)
    pipe.execute()
    print(f"  loaded {count:>5} rows from enrollments_1000.csv")
    return count


def load_hospitals(r):
    """The 'specialities' column is comma-separated; split into one index per value."""
    def alias(row):
        return [
            ("by_speciality", s.strip())
            for s in (row.get("specialities") or "").split(",")
            if s.strip()
        ]
    return load_csv(
        r, "hospitals.csv", "hospital", "hospital_id",
        tag_indexes=["city", "type"],
        num_indexes=["beds"],
        alias=alias,
    )


def load_patients(r):
    return load_csv(
        r, "patients_1000.csv", "patient", "patient_id",
        tag_indexes=["city", "hospital", "diagnosis", "status", "doctor"],
        num_indexes=["age"],
    )


def load_companies(r):
    return load_csv(
        r, "companies.csv", "company", "company_id",
        tag_indexes=["city", "sector"],
        num_indexes=["founded", "employees", "annual_revenue_usd"],
    )


def load_properties(r):
    return load_csv(
        r, "properties.csv", "property", "property_id",
        tag_indexes=["type", "city", "district", "status"],
        num_indexes=["area_m2", "bedrooms", "listed_price_usd"],
    )


def load_ministries(r):
    return load_csv(
        r, "ministries.csv", "ministry", "ministry_id",
        tag_indexes=["city"],
        num_indexes=["employees", "annual_budget_usd"],
    )


def load_gov_projects(r):
    return load_csv(
        r, "government_projects.csv", "project", "project_id",
        tag_indexes=["ministry", "city", "status"],
        num_indexes=["budget_usd"],
    )


def load_events(r):
    return load_csv(
        r, "events.csv", "event", "event_id",
        tag_indexes=["type", "city", "venue", "organiser"],
        num_indexes=["tickets", "price_usd"],
    )


def load_event_registrations(r):
    path = DATA_DIR / "event_registrations_1000.csv"
    if not path.exists():
        print("  skip event_registrations_1000.csv (not found)")
        return 0

    pipe = r.pipeline(transaction=False)
    count = 0
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rid = row["registration_id"]
            eid = row["event_id"]
            pipe.hset(f"registration:{rid}", mapping={k: (v or "") for k, v in row.items()})
            pipe.sadd("all:registration", rid)
            pipe.sadd(f"idx:reg:by_event:{eid}", rid)
            pipe.sadd(f"idx:reg:by_city:{(row.get('city') or '').strip()}", rid)
            pipe.sadd(f"idx:reg:by_ticket_type:{(row.get('ticket_type') or '').strip()}", rid)
            try:
                pipe.zadd("idx:reg:by_paid_usd", {rid: float(row.get("paid_usd") or 0)})
            except ValueError:
                pass
            count += 1
            if count % 500 == 0:
                pipe.execute()
                pipe = r.pipeline(transaction=False)
    pipe.execute()
    print(f"  loaded {count:>5} rows from event_registrations_1000.csv")
    return count


# ----------------------------------------------------------------------
# RediSearch full-text indexes
# ----------------------------------------------------------------------
def _has_redisearch(r):
    """Detect whether RediSearch (FT.* commands) is loaded."""
    try:
        modules = r.execute_command("MODULE LIST")
    except redis.ResponseError:
        return False
    for mod in modules or []:
        # Module entries are alternating key/value lists in RESP2
        if "search" in [str(x).lower() for x in mod]:
            return True
    # Fallback: try FT._LIST
    try:
        r.execute_command("FT._LIST")
        return True
    except redis.ResponseError:
        return False


def build_search_indexes(r):
    if not _has_redisearch(r):
        print("Building RediSearch indexes ... SKIPPED (module not loaded; "
              "use redis/redis-stack via docker compose to enable)")
        return
    print("Building RediSearch indexes ...")

    for idx in ("idx_courses_ft", "idx_students_ft", "idx_events_ft"):
        try:
            r.ft(idx).dropindex(delete_documents=False)
        except redis.ResponseError:
            pass

    r.ft("idx_courses_ft").create_index(
        fields=[
            TextField("course_name", weight=5.0),
            TextField("professor"),
            TagField("department"),
            TagField("mode"),
            TagField("university"),
            NumericField("credits"),
            NumericField("max_cap"),
        ],
        definition=IndexDefinition(prefix=["course:"], index_type=IndexType.HASH),
    )

    r.ft("idx_students_ft").create_index(
        fields=[
            TextField("full_name", weight=5.0),
            TagField("university"),
            TagField("major"),
            TagField("city"),
            NumericField("gpa", sortable=True),
            NumericField("age", sortable=True),
            NumericField("enroll_year", sortable=True),
        ],
        definition=IndexDefinition(prefix=["student:"], index_type=IndexType.HASH),
    )

    r.ft("idx_events_ft").create_index(
        fields=[
            TextField("event_name", weight=5.0),
            TextField("venue"),
            TagField("type"),
            TagField("city"),
            TagField("organiser"),
            NumericField("price_usd", sortable=True),
            NumericField("tickets", sortable=True),
        ],
        definition=IndexDefinition(prefix=["event:"], index_type=IndexType.HASH),
    )
    print("  ready: idx_courses_ft, idx_students_ft, idx_events_ft")


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def load_all(r):
    """Load every CSV, build RediSearch indexes and print a summary."""
    print("Loading CSVs ...")
    load_universities(r)
    load_departments(r)
    load_courses(r)
    load_students(r)
    load_enrollments(r)
    load_hospitals(r)
    load_patients(r)
    load_companies(r)
    load_properties(r)
    load_ministries(r)
    load_gov_projects(r)
    load_events(r)
    load_event_registrations(r)

    build_search_indexes(r)

    print("\nSummary:")
    for prefix in ("university", "department", "course", "student", "enrollment",
                   "hospital", "patient", "company", "property", "ministry",
                   "project", "event", "registration"):
        n = r.scard(f"all:{prefix}")
        print(f"  {prefix:>14}: {n:>5}")


def main():
    r = connect()

    if "--reset" in sys.argv:
        print("Flushing DB (--reset) ...")
        r.flushdb()

    load_all(r)
    print("\nOpen RedisInsight at http://localhost:8001 to browse.")


if __name__ == "__main__":
    main()
