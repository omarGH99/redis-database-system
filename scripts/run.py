"""
run.py
-------
Run every task from the command line and print the result.  Useful for
the presentation demo, in case the web UI is offline.

Usage:
  python scripts/run.py            # run all 10 tasks
  python scripts/run.py 8          # run only task 8
  python scripts/run.py ask "what courses does UKH offer?"

Redis Database System  --  By: Omar, Aya, Shelan
"""

import json
import sys
from pathlib import Path

# allow running from project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from queries import (
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
    natural_language_query,
)

TASKS = {
    1:  ("Basic 1: load summary",                       lambda: task_01_load_summary()),
    2:  ("Basic 2: CS students at UKH (top 5)",         lambda: task_02_filter_students_by_major("Computer Science", "UKH")[:5]),
    3:  ("Basic 3: top-5 students by GPA",    lambda: task_03_top_n_students_by_gpa(5)),
    4:  ("Intermediate 1: read S001",                   lambda: task_04_crud_student("read", {"student_id": "S001"})),
    5:  ("Intermediate 2: avg GPA by university (top10)", lambda: task_05_aggregation_avg_gpa_by_university()[:10]),
    6:  ("Intermediate 3: UKH CS, GPA 3.5-4.0",         lambda: task_06_multi_condition_search(university="UKH", major="Computer Science", min_gpa=3.5, max_gpa=4.0)[:5]),
    7:  ("Intermediate 4: students × universities × departments (5)",    lambda: task_07_cross_domain_student_university_dept()[:5]),
    8:  ("Advanced 1: search 'database' courses",       lambda: task_08_redisearch_courses("database")),
    9:  ("Advanced 2: validation report",               lambda: task_09_validation_report()),
    10: ("Advanced 3: real-world dashboard",            lambda: task_10_real_world_dashboard()),
}


def show(label, payload):
    bar = "─" * 70
    print(f"\n{bar}\n{label}\n{bar}")
    print(json.dumps(payload, indent=2, default=str)[:3500])


def main():
    args = sys.argv[1:]
    if args and args[0] == "ask":
        question = " ".join(args[1:]) or "what courses does AUK offer?"
        show(f"Ask: {question}", natural_language_query(question))
        return

    if args:
        ids = [int(a) for a in args]
    else:
        ids = list(TASKS.keys())

    for i in ids:
        label, fn = TASKS[i]
        try:
            show(f"[{i}] {label}", fn())
        except Exception as e:  # noqa: BLE001
            print(f"\n[{i}] {label}\n  ERROR: {e}")


if __name__ == "__main__":
    main()
