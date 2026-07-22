"""Repository for the process-level kv_store table.

Consolidates the raw Session(ENGINE)/KVRow CRUD previously inlined across
backend/api/routes/settings.py, backend/api/routes/webhooks.py, and
backend/scripts/reset_linkedin_scraper.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.core.database import ENGINE
from backend.models.kv import KVRow


@dataclass(frozen=True)
class KVEntry:
    key: str
    value: str
    updated_at: str


def get(key: str) -> Optional[KVEntry]:
    with Session(ENGINE) as db:
        row = db.get(KVRow, key)
        if row is None:
            return None
        return KVEntry(key=row.key, value=row.value, updated_at=row.updated_at)


def get_many(keys: list[str]) -> dict[str, KVEntry]:
    """Batch read — one session for all keys, missing keys simply absent from the result."""
    with Session(ENGINE) as db:
        result: dict[str, KVEntry] = {}
        for key in keys:
            row = db.get(KVRow, key)
            if row is not None:
                result[key] = KVEntry(key=row.key, value=row.value, updated_at=row.updated_at)
        return result


def upsert(key: str, value: str, updated_at: Optional[str] = None) -> None:
    ts = updated_at or datetime.now(timezone.utc).isoformat()
    with Session(ENGINE) as db:
        row = db.get(KVRow, key)
        if row:
            row.value = value
            row.updated_at = ts
        else:
            db.add(KVRow(key=key, value=value, updated_at=ts))
        db.commit()


def delete(key: str) -> bool:
    """Return True if a row was deleted, False if the key was already absent."""
    with Session(ENGINE) as db:
        row = db.get(KVRow, key)
        if row is None:
            return False
        db.delete(row)
        db.commit()
        return True
