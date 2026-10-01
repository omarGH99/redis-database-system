"""
dashboard.py -- chart-ready aggregates for the dashboard page.
"""

import os
import time
from typing import Any, Dict, List, Optional

import redis

from . import core
from .browse import TABLES


# ----------------------------------------------------------------------
# Dashboard data: small aggregations the front-end can chart
# ----------------------------------------------------------------------
def _tag_counts(r: redis.Redis, prefix: str, limit: Optional[int] = None,
                sort_by_label: bool = False) -> List[Dict[str, Any]]:
    """
    Cardinality of every reverse-index SET matching `<prefix>*`
    (e.g. "idx:student:by_major:"), computed with one SCAN + one pipeline.
    """
    keys = list(r.scan_iter(match=f"{prefix}*", count=2000))
    if not keys:
        return []
    pipe = r.pipeline()
    for k in keys:
        pipe.scard(k)
    rows = [{"label": k[len(prefix):], "value": n}
            for k, n in zip(keys, pipe.execute()) if k[len(prefix):]]
    rows.sort(key=(lambda x: x["label"]) if sort_by_label else (lambda x: -x["value"]))
    return rows[:limit] if limit else rows


_DASH_TTL = float(os.getenv("DASHBOARD_CACHE_SECONDS", 30))
_dash_cache: Dict[str, Any] = {"at": 0.0, "data": None}


def dashboard_data(force: bool = False) -> Dict[str, Any]:
    """
    Chart-ready aggregates across every domain.  Results are cached for
    DASHBOARD_CACHE_SECONDS so a busy public site doesn't re-aggregate on
    every page view.
    """
    now = time.monotonic()
    if not force and _dash_cache["data"] and now - _dash_cache["at"] < _DASH_TTL:
        return {**_dash_cache["data"], "cached": True}

    t0 = time.perf_counter()
    r = core.get_redis()
    out: Dict[str, Any] = {}

    # Row counts (all tables)
    pipe = r.pipeline()
    for meta in TABLES.values():
        pipe.scard(f"all:{meta['prefix']}")
    counts = pipe.execute()
    out["row_counts"] = [
        {"label": name.capitalize(), "value": c}
        for name, c in zip(TABLES, counts)
    ]

    # Education domain
    out["students_per_university"] = _tag_counts(r, "idx:student:by_university:", 10)
    out["students_per_major"] = _tag_counts(r, "idx:student:by_major:")

    buckets = [(0, 1, "0-1"), (1, 2, "1-2"), (2, 3, "2-3"),
               (3, 3.5, "3-3.5"), (3.5, 4.01, "3.5-4")]
    out["gpa_distribution"] = [
        {"label": label, "value": r.zcount("idx:student:by_gpa", lo, f"({hi}")}
        for lo, hi, label in buckets
    ]

    out["enrollments_per_semester"] = _tag_counts(
        r, "idx:enroll:by_semester:", sort_by_label=True)

    dept_name_counts: Dict[str, int] = {}
    for row in _tag_counts(r, "idx:course:by_department:"):
        name = r.hget(f"department:{row['label']}", "department_name") or row["label"]
        dept_name_counts[name] = dept_name_counts.get(name, 0) + row["value"]
    out["courses_per_department"] = [
        {"label": d, "value": v}
        for d, v in sorted(dept_name_counts.items(), key=lambda x: -x[1])[:10]
    ]

    # Events
    out["events_per_type"] = _tag_counts(r, "idx:event:by_type:")
    out["events_per_city"] = _tag_counts(r, "idx:event:by_city:", 6)

    # Other domains
    out["properties_per_city"] = _tag_counts(r, "idx:property:by_city:", 8)
    out["properties_per_status"] = _tag_counts(r, "idx:property:by_status:")
    out["hospitals_per_city"] = _tag_counts(r, "idx:hospital:by_city:", 8)
    out["patients_per_status"] = _tag_counts(r, "idx:patient:by_status:")
    out["companies_per_sector"] = _tag_counts(r, "idx:company:by_sector:", 10)

    # Headline stats
    gpas = [s for _, s in r.zrange("idx:student:by_gpa", 0, -1, withscores=True)]
    total_rows = sum(counts)
    out["stats"] = {
        "tables": len(TABLES),
        "total_rows": total_rows,
        "redis_keys": r.dbsize(),
        "avg_gpa": round(sum(gpas) / len(gpas), 2) if gpas else None,
    }
    out["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    out["cached"] = False

    _dash_cache.update(at=now, data=out)
    return out
