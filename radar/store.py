from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from radar.models import Job


class HistoryStore:
    """
    SQLite is the runtime store. A small JSON snapshot is committed to Git so
    history survives between GitHub Actions runs without an external database.
    """

    def __init__(self, db_path: Path, state_path: Path):
        self.db_path = db_path
        self.state_path = state_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_jobs (
                fingerprint TEXT PRIMARY KEY,
                job_key TEXT NOT NULL,
                source TEXT,
                external_id TEXT,
                title TEXT,
                company TEXT,
                location TEXT,
                url TEXT,
                posted_at TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                score INTEGER,
                label TEXT
            )
            """
        )
        self.conn.commit()
        self._seed_from_json()

    def _seed_from_json(self) -> None:
        if not self.state_path.exists():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return

        for row in payload.get("jobs", []):
            fingerprint = row.get("fingerprint")
            if not fingerprint:
                continue
            self.conn.execute(
                """
                INSERT OR IGNORE INTO seen_jobs
                (fingerprint, job_key, source, external_id, title, company, location,
                 url, posted_at, first_seen, last_seen, score, label)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fingerprint,
                    row.get("job_key", ""),
                    row.get("source"),
                    row.get("external_id"),
                    row.get("title"),
                    row.get("company"),
                    row.get("location"),
                    row.get("url"),
                    row.get("posted_at"),
                    row.get("first_seen"),
                    row.get("last_seen"),
                    row.get("score", 0),
                    row.get("label", ""),
                ),
            )
        self.conn.commit()

    def record(self, job: Job, score: int, label: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        existing = self.conn.execute(
            "SELECT fingerprint FROM seen_jobs WHERE fingerprint = ?",
            (job.fingerprint,),
        ).fetchone()
        is_new = existing is None

        if is_new:
            self.conn.execute(
                """
                INSERT INTO seen_jobs
                (fingerprint, job_key, source, external_id, title, company, location,
                 url, posted_at, first_seen, last_seen, score, label)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.fingerprint,
                    job.key,
                    job.source,
                    job.external_id,
                    job.title,
                    job.company,
                    job.location,
                    job.url,
                    job.posted_at,
                    now,
                    now,
                    score,
                    label,
                ),
            )
        else:
            self.conn.execute(
                """
                UPDATE seen_jobs
                SET last_seen = ?, url = ?, posted_at = COALESCE(?, posted_at),
                    score = ?, label = ?
                WHERE fingerprint = ?
                """,
                (now, job.url, job.posted_at, score, label, job.fingerprint),
            )
        self.conn.commit()
        return is_new

    def export_json(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        rows = self.conn.execute(
            """
            SELECT fingerprint, job_key, source, external_id, title, company,
                   location, url, posted_at, first_seen, last_seen, score, label
            FROM seen_jobs ORDER BY first_seen DESC
            """
        ).fetchall()
        keys = [
            "fingerprint", "job_key", "source", "external_id", "title", "company",
            "location", "url", "posted_at", "first_seen", "last_seen", "score", "label",
        ]
        payload = {"version": 1, "jobs": [dict(zip(keys, row)) for row in rows]}
        self.state_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def close(self) -> None:
        self.conn.close()
