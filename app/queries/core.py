"""
core.py -- Redis connection and helpers shared by every query module.
"""

import os
import re
from typing import Any, Dict, List, Optional

import redis



REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None

# One shared connection pool for the whole process
_pool = redis.ConnectionPool(
    host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD,
    decode_responses=True, socket_connect_timeout=3,
)


def get_redis() -> redis.Redis:
    return redis.Redis(connection_pool=_pool)


# ======================================================================
# Helpers
# ======================================================================
def _hydrate(r: redis.Redis, ids: List[str], prefix: str) -> List[Dict[str, Any]]:
    """Bulk-fetch hashes for a list of ids using a pipeline."""
    if not ids:
        return []
    pipe = r.pipeline()
    for i in ids:
        pipe.hgetall(f"{prefix}:{i}")
    return [row for row in pipe.execute() if row]


def _has_redisearch(r: redis.Redis) -> bool:
    try:
        r.execute_command("FT._LIST")
        return True
    except redis.ResponseError:
        return False


_FT_SPECIAL = re.compile(r"""([,.<>{}\[\]"':;!@#$%^&*()\-+=~|/\\])""")


def _ft_escape(text: str) -> str:
    """Escape RediSearch query punctuation so user text is treated literally."""
    return _FT_SPECIAL.sub(lambda m: "\\" + m.group(1), text or "")


def _resolve_university(r: redis.Redis, fragment: str) -> Optional[str]:
    """Map a free-form name fragment to a university_id (UKH / SPU / U006 / ...)."""
    fragment = (fragment or "").strip()
    if not fragment:
        return None

    # Direct hit on a known short code
    if r.exists(f"university:{fragment}"):
        return fragment

    # Common aliases
    aliases = {
        "auk": "AUK",                                         # not in unis table; events only
        "ukh": "UKH",
        "university of kurdistan hewler": "UKH",
        "spu": "SPU",
        "sulaimani polytechnic university": "SPU",
        "uos": "UoS",
        "university of sulaimani": "UoS",
        "uzakho": "UZakho",
        "university of zakho": "UZakho",
        "ebu": "EBU",
        "erbil business university": "EBU",
    }
    f_lower = fragment.lower()
    if f_lower in aliases and r.exists(f"university:{aliases[f_lower]}"):
        return aliases[f_lower]

    # Substring match against names (slow path, but only ~1000 rows)
    for uid in r.smembers("all:university"):
        name = (r.hget(f"university:{uid}", "name") or "").lower()
        if f_lower in name:
            return uid
    return None
