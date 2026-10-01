"""
queries package
----------------
The 10 tasks, the natural-language handler, the table browser and the
dashboard aggregates for the Redis Database System project.

  core.py       connection pool + shared helpers
  tasks.py      task_01 .. task_10
  nlq.py        natural_language_query
  browse.py     TABLES, list_tables, browse_table
  dashboard.py  dashboard_data

Everything the web app and CLI need is re-exported here.

By: Omar, Aya, Shelan
"""

from . import core
from .browse import TABLES, browse_table, list_tables
from .core import REDIS_HOST, REDIS_PORT, get_redis
from .dashboard import dashboard_data
from .nlq import natural_language_query
from .tasks import (
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

__all__ = [
    "REDIS_HOST", "REDIS_PORT", "TABLES", "browse_table", "core", "dashboard_data",
    "get_redis", "list_tables", "natural_language_query",
    "task_01_load_summary", "task_02_filter_students_by_major",
    "task_03_top_n_students_by_gpa", "task_04_crud_student",
    "task_05_aggregation_avg_gpa_by_university", "task_06_multi_condition_search",
    "task_07_cross_domain_student_university_dept", "task_08_redisearch_courses",
    "task_09_validation_report", "task_10_real_world_dashboard",
]
