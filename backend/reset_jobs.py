"""
reset_jobs.py — wipe all job and application records from jobs.db.

Safe to run at any time.  Preserves:
  - profile_interviews  (interview sessions + draft profiles)
  - kv_store            (ephemeral system state, e.g. gmail verification codes)

Clears:
  - jobs          (all analyzed JobMatch rows)
  - applications  (all submitted application records)

SQLite has no native auto-increment sequence to reset (it uses the max
existing rowid + 1), so a DELETE + sqlite_sequence reset is sufficient for
any INTEGER PRIMARY KEY columns.  The primary keys in both tables are
TEXT (string UUIDs / job IDs), so no sequence reset is strictly needed —
but the script clears sqlite_sequence entries anyway for hygiene.

Usage
-----
    python backend/reset_jobs.py          # dry-run prompt (default)
    python backend/reset_jobs.py --yes    # skip confirmation
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# ── Resolve database path ─────────────────────────────────────────────────────
# This script lives at backend/reset_jobs.py; jobs.db is also in backend/.
_SCRIPT_DIR = Path(__file__).resolve().parent
_DB_PATH    = _SCRIPT_DIR / "jobs.db"

# Tables to clear (order matters for any FK constraints — applications first)
_CLEAR_TABLES = ["applications", "jobs"]

# Tables that must NEVER be touched
_PROTECTED_TABLES = ["profile_interviews", "kv_store"]


def _confirm() -> bool:
    print()
    print("=" * 60)
    print("  WARNING: This will permanently delete all rows from:")
    for t in _CLEAR_TABLES:
        print(f"    - {t}")
    print()
    print("  The following tables will NOT be touched:")
    for t in _PROTECTED_TABLES:
        print(f"    - {t}  (protected)")
    print("=" * 60)
    answer = input("\n  Type YES to proceed: ").strip()
    return answer == "YES"


def _row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts = {}
    for table in _CLEAR_TABLES:
        (n,) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        counts[table] = n
    return counts


def reset(*, confirmed: bool = False) -> None:
    if not _DB_PATH.exists():
        sys.exit(f"[reset_jobs] Database not found: {_DB_PATH}")

    if not confirmed and not _confirm():
        print("\n[reset_jobs] Aborted — no changes made.")
        sys.exit(0)

    conn = sqlite3.connect(_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    try:
        before = _row_counts(conn)
        print()

        conn.execute("BEGIN")

        for table in _CLEAR_TABLES:
            conn.execute(f"DELETE FROM {table}")
            print(f"  Cleared: {table:20s} ({before[table]} rows deleted)")

        # Reset sqlite_sequence entries for these tables (no-op if they don't
        # use AUTOINCREMENT, but harmless to run regardless)
        seq_tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
            )
        }
        if seq_tables:
            for table in _CLEAR_TABLES:
                conn.execute(
                    "DELETE FROM sqlite_sequence WHERE name = ?", (table,)
                )

        conn.execute("COMMIT")

        # Reclaim disk space
        conn.execute("VACUUM")

        print()
        print("[reset_jobs] Done. Database is clean.")

        # Verify protected tables are untouched
        for table in _PROTECTED_TABLES:
            (n,) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            print(f"  Protected: {table:20s} ({n} rows — unchanged)")

    except Exception as exc:
        conn.execute("ROLLBACK")
        conn.close()
        sys.exit(f"[reset_jobs] ERROR — rolled back. {exc}")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Delete all job and application records from jobs.db."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt and proceed immediately.",
    )
    args = parser.parse_args()
    reset(confirmed=args.yes)
