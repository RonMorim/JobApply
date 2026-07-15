"""
audit_cross_tenant_job_hijack.py — JOB-92 historical data-integrity audit.

Read-only check for `apply_url` values shared by more than one `user_id` in
the `jobs` table. Before the JOB-92 fix (save_with_source_priority no longer
reassigns row ownership across tenants, and scraped job_ids are salted per
user), a higher-priority save from a different user than the row's original
owner would silently overwrite that row's `user_id` in place. This script
surfaces any `apply_url` currently tied to more than one distinct `user_id`
so it can be manually reviewed before merging the fix.

Interpretation caveat
---------------------
A shared `apply_url` across users is NOT on its own conclusive proof of a
historical hijack — different scrapers can legitimately produce different
job_id prefixes for the same URL even under the old scheme. Treat each
flagged group as a candidate for manual review, not an automatic verdict.
After the JOB-92 fix ships, multiple rows (one per user) sharing an
apply_url becomes the expected, correct steady state — this script is only
useful for auditing data that predates the fix.

Read-only guarantee
--------------------
Opens jobs.db via a `file:...?mode=ro` URI connection — SQLite enforces this
at the OS/driver level, so any accidental write in this script would raise
`sqlite3.OperationalError: attempt to write a readonly database` rather than
silently succeeding.

Usage (from project root)
--------------------------
    python -m backend.scripts.audit_cross_tenant_job_hijack
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

_DB_PATH = Path(__file__).resolve().parents[1] / "jobs.db"


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def find_cross_tenant_apply_url_conflicts(conn: sqlite3.Connection) -> list[dict]:
    """
    Return one entry per apply_url that is associated with more than one
    distinct user_id, each entry listing every (job_id, user_id) row sharing
    that apply_url.
    """
    cur = conn.cursor()

    cur.execute(
        """
        SELECT apply_url
        FROM jobs
        WHERE apply_url IS NOT NULL AND apply_url != ''
        GROUP BY apply_url
        HAVING COUNT(DISTINCT user_id) > 1
        """
    )
    conflicting_urls = [row[0] for row in cur.fetchall()]

    results = []
    for apply_url in conflicting_urls:
        cur.execute(
            """
            SELECT job_id, user_id
            FROM jobs
            WHERE apply_url = ?
            ORDER BY user_id
            """,
            (apply_url,),
        )
        rows = cur.fetchall()
        results.append({
            "apply_url": apply_url,
            "rows": [{"job_id": job_id, "user_id": user_id} for job_id, user_id in rows],
            "conflicting_user_ids": sorted({user_id for _, user_id in rows}),
        })
    return results


def main() -> None:
    if not _DB_PATH.exists():
        print(f"ERROR: {_DB_PATH} not found.")
        sys.exit(1)

    conn = _connect_readonly(_DB_PATH)
    try:
        conflicts = find_cross_tenant_apply_url_conflicts(conn)
    finally:
        conn.close()

    if not conflicts:
        print(f"No apply_url shared across multiple user_ids found in {_DB_PATH}.")
        print("No evidence of historical cross-tenant job hijacking (JOB-92).")
        return

    print(f"Found {len(conflicts)} apply_url(s) shared across multiple user_ids in {_DB_PATH}:\n")
    for i, entry in enumerate(conflicts, start=1):
        print(f"[{i}] apply_url: {entry['apply_url']}")
        print(f"    conflicting user_ids: {entry['conflicting_user_ids']}")
        for row in entry["rows"]:
            print(f"      job_id={row['job_id']!r}  user_id={row['user_id']!r}")
        print()

    print(
        "NOTE: a shared apply_url is a candidate for manual review, not automatic "
        "proof of a hijack — see this script's docstring for the interpretation caveat."
    )


if __name__ == "__main__":
    main()
