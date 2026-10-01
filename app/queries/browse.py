"""
browse.py -- table metadata and the paginated table browser.
"""

import time
from typing import Any, Dict, List, Optional


from . import core
from .core import _hydrate


# Tables we expose for browsing.  Each entry: (key_prefix, all_set, default_sort_col)
TABLES: Dict[str, Dict[str, Any]] = {
    name: {"prefix": prefix, "id_col": id_col, "default_sort": id_col}
    for name, prefix, id_col in [
        ("universities",  "university",   "university_id"),
        ("departments",   "department",   "dept_id"),
        ("courses",       "course",       "course_id"),
        ("students",      "student",      "student_id"),
        ("enrollments",   "enrollment",   "enroll_id"),
        ("hospitals",     "hospital",     "hospital_id"),
        ("patients",      "patient",      "patient_id"),
        ("companies",     "company",      "company_id"),
        ("properties",    "property",     "property_id"),
        ("ministries",    "ministry",     "ministry_id"),
        ("projects",      "project",      "project_id"),
        ("events",        "event",        "event_id"),
        ("registrations", "registration", "registration_id"),
    ]
}


def list_tables() -> List[Dict[str, Any]]:
    """Return metadata for every browsable table (name + row count)."""
    r = core.get_redis()
    out = []
    for name, meta in TABLES.items():
        out.append({
            "name": name,
            "prefix": meta["prefix"],
            "id_col": meta["id_col"],
            "rows": r.scard(f"all:{meta['prefix']}"),
        })
    return out


MAX_PAGE_SIZE = 250


def browse_table(
    table: str,
    sort_col: Optional[str] = None,
    sort_dir: str = "asc",
    page: int = 1,
    page_size: int = 50,
    search: str = "",
) -> Dict[str, Any]:
    """
    Page through any of the 13 tables with optional sort + free-text
    filter.  Sorting is done client-side (Python) because Redis does not
    keep a full-row sort index for every column.  Numeric columns that
    do have a sorted-set index are detected automatically and used.
    """
    if table not in TABLES:
        return {"error": f"unknown table '{table}'", "rows": [], "total": 0}

    # Clamp untrusted paging / ordering input
    page = max(1, int(page))
    page_size = min(MAX_PAGE_SIZE, max(1, int(page_size)))
    sort_dir = "desc" if sort_dir == "desc" else "asc"
    search = (search or "").strip()[:100]

    t0 = time.perf_counter()
    r = core.get_redis()
    meta = TABLES[table]
    prefix = meta["prefix"]
    sort_col = sort_col or meta["default_sort"]

    # Fast path: if a sorted-set index exists for the requested column,
    # use it for the order.  Otherwise we sort client-side.
    zset_key = f"idx:{prefix}:by_{sort_col}"
    use_zset = bool(r.exists(zset_key)) and not search

    ids: List[str]
    total: int

    if use_zset:
        total = r.zcard(zset_key)
        # ZSET pagination
        start = (page - 1) * page_size
        stop = start + page_size - 1
        if sort_dir == "desc":
            ids = r.zrevrange(zset_key, start, stop)
        else:
            ids = r.zrange(zset_key, start, stop)
        rows = _hydrate(r, ids, prefix)
    else:
        # Slow path: load every row and sort/filter in Python
        all_ids = list(r.smembers(f"all:{prefix}"))
        rows = _hydrate(r, all_ids, prefix)

        # Free-text filter (case-insensitive across every field)
        if search:
            s_lower = search.lower()
            rows = [row for row in rows
                    if any(s_lower in str(v).lower() for v in row.values())]

        # Sort
        def keyfn(row):
            v = row.get(sort_col, "")
            try:
                return (0, float(v), "")
            except (TypeError, ValueError):
                return (1, 0.0, str(v).lower())

        rows.sort(key=keyfn, reverse=(sort_dir == "desc"))
        total = len(rows)
        start = (page - 1) * page_size
        rows = rows[start:start + page_size]

    # Determine column order from the first row (deterministic)
    columns: List[str] = []
    if rows:
        # Put id col first, then alphabetical
        first = rows[0]
        columns = [meta["id_col"]] + sorted(k for k in first.keys() if k != meta["id_col"])

    return {
        "table": table,
        "prefix": prefix,
        "id_col": meta["id_col"],
        "columns": columns,
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "sort_col": sort_col,
        "sort_dir": sort_dir,
        "search": search,
        "engine": "zset" if use_zset else "scan-and-sort",
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
    }
