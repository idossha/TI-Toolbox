#!/usr/bin/env python3
"""Fetch download and engagement stats from GitHub, store in SQLite.

Sources:
  - GitHub Releases: per-asset download counts (all-time cumulative)
  - GitHub Traffic Views: daily page views + uniques (14-day window)
  - GitHub Traffic Clones: daily git clones + uniques (14-day window)
  - GitHub Traffic Referrers: top referral sources (14-day window)

Requires GITHUB_TOKEN env var with repo scope for traffic endpoints.
Release download counts are public and don't need auth.
"""

import json
import os
import sqlite3
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("STATS_DB_PATH", Path(__file__).parent / "stats.db"))
GITHUB_REPO = "idossha/TI-toolbox"
GITHUB_API = "https://api.github.com"


def _headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    h = {"User-Agent": "ti-toolbox-stats/1.0", "Accept": "application/vnd.github+json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def fetch_json(url: str) -> object:
    req = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS github_releases (
            date         TEXT NOT NULL,
            tag          TEXT NOT NULL,
            asset        TEXT NOT NULL,
            downloads    INTEGER NOT NULL,
            PRIMARY KEY (date, tag, asset)
        );

        CREATE TABLE IF NOT EXISTS github_views (
            date         TEXT NOT NULL,
            views        INTEGER NOT NULL,
            uniques      INTEGER NOT NULL,
            PRIMARY KEY (date)
        );

        CREATE TABLE IF NOT EXISTS github_clones (
            date         TEXT NOT NULL,
            clones       INTEGER NOT NULL,
            uniques      INTEGER NOT NULL,
            PRIMARY KEY (date)
        );

        CREATE TABLE IF NOT EXISTS github_referrers (
            date         TEXT NOT NULL,
            referrer     TEXT NOT NULL,
            count        INTEGER NOT NULL,
            uniques      INTEGER NOT NULL,
            PRIMARY KEY (date, referrer)
        );
    """)


def fetch_releases(conn: sqlite3.Connection, today: str) -> None:
    """Cumulative per-asset download counts across all releases."""
    page, total = 1, 0
    while True:
        url = f"{GITHUB_API}/repos/{GITHUB_REPO}/releases?per_page=100&page={page}"
        releases = fetch_json(url)
        if not releases:
            break
        for release in releases:
            tag = release["tag_name"]
            for asset in release.get("assets", []):
                name = asset["name"]
                dl = asset["download_count"]
                total += dl
                conn.execute(
                    "INSERT OR REPLACE INTO github_releases (date, tag, asset, downloads) VALUES (?, ?, ?, ?)",
                    (today, tag, name, dl),
                )
        page += 1
    print(f"  releases: {total} total downloads")


def fetch_views(conn: sqlite3.Connection) -> None:
    """Daily page views — 14-day rolling window. INSERT OR IGNORE to avoid overwriting."""
    data = fetch_json(f"{GITHUB_API}/repos/{GITHUB_REPO}/traffic/views")
    for entry in data.get("views", []):
        date = entry["timestamp"][:10]
        conn.execute(
            "INSERT OR IGNORE INTO github_views (date, views, uniques) VALUES (?, ?, ?)",
            (date, entry["count"], entry["uniques"]),
        )
    print(f"  views: {data['count']} total, {data['uniques']} uniques (last 14d)")


def fetch_clones(conn: sqlite3.Connection) -> None:
    """Daily git clones — 14-day rolling window. INSERT OR IGNORE to avoid overwriting."""
    data = fetch_json(f"{GITHUB_API}/repos/{GITHUB_REPO}/traffic/clones")
    for entry in data.get("clones", []):
        date = entry["timestamp"][:10]
        conn.execute(
            "INSERT OR IGNORE INTO github_clones (date, clones, uniques) VALUES (?, ?, ?)",
            (date, entry["count"], entry["uniques"]),
        )
    print(f"  clones: {data['count']} total, {data['uniques']} uniques (last 14d)")


def fetch_referrers(conn: sqlite3.Connection, today: str) -> None:
    """Top referral sources — snapshot of last 14 days."""
    data = fetch_json(f"{GITHUB_API}/repos/{GITHUB_REPO}/traffic/popular/referrers")
    for entry in data:
        conn.execute(
            "INSERT OR REPLACE INTO github_referrers (date, referrer, count, uniques) VALUES (?, ?, ?, ?)",
            (today, entry["referrer"], entry["count"], entry["uniques"]),
        )
    print(f"  referrers: {len(data)} sources")


def main() -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"Fetching stats for {today}...")

    conn = sqlite3.connect(DB_PATH)
    try:
        init_db(conn)
        fetch_releases(conn, today)
        fetch_views(conn)
        fetch_clones(conn)
        fetch_referrers(conn, today)
        conn.commit()
        print("Done.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
