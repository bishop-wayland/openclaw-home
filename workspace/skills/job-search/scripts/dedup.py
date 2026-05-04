"""SQLite-backed dedup store for job postings.

Hash key = sha256(normalized_title + '|' + company + '|' + location). URL is intentionally
NOT part of the key — Greenhouse/Lever recycle job IDs and aggregators generate one-off URLs,
so URL-based dedup leaks duplicates.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "state" / "seen.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_postings (
  hash TEXT PRIMARY KEY,
  company TEXT NOT NULL,
  title TEXT NOT NULL,
  location TEXT,
  url TEXT,
  first_seen_iso TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_company ON seen_postings(company);
CREATE INDEX IF NOT EXISTS idx_first_seen ON seen_postings(first_seen_iso);
"""


def _normalize(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\s|]", "", s)
    return s


def posting_hash(company: str, title: str, location: str) -> str:
    key = f"{_normalize(title)}|{_normalize(company)}|{_normalize(location)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.executescript(SCHEMA)
    return c


def filter_new(postings: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (new, already_seen) split. `postings` items must have company/title/location."""
    if not postings:
        return [], []
    with _conn() as c:
        new, dup = [], []
        for p in postings:
            h = posting_hash(p["company"], p["title"], p.get("location", ""))
            row = c.execute("SELECT 1 FROM seen_postings WHERE hash = ?", (h,)).fetchone()
            if row:
                dup.append(p)
            else:
                p["_hash"] = h
                new.append(p)
        return new, dup


def mark_seen(postings: list[dict]) -> int:
    """Insert hashes for postings that have a `_hash` field. Returns rows inserted."""
    if not postings:
        return 0
    iso = _dt.datetime.now(_dt.timezone.utc).isoformat()
    inserted = 0
    with _conn() as c:
        for p in postings:
            h = p.get("_hash") or posting_hash(p["company"], p["title"], p.get("location", ""))
            try:
                c.execute(
                    "INSERT INTO seen_postings (hash, company, title, location, url, first_seen_iso) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (h, p["company"], p["title"], p.get("location", ""), p.get("url", ""), iso),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                pass  # race / pre-existing — ignore
        c.commit()
    return inserted


def stats() -> dict:
    """Quick stats for surfacing in logs / chat."""
    if not DB_PATH.exists():
        return {"total": 0}
    with _conn() as c:
        total = c.execute("SELECT COUNT(*) FROM seen_postings").fetchone()[0]
        last_30d = c.execute(
            "SELECT COUNT(*) FROM seen_postings WHERE first_seen_iso > ?",
            ((_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=30)).isoformat(),),
        ).fetchone()[0]
        return {"total": total, "added_last_30d": last_30d}
