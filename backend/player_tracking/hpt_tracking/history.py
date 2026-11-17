"""Durable, user-scoped job history using Python's built-in SQLite driver.

The auth service still owns MySQL accounts. This file needs no extra service or
credentials and must be backed up together with the runtime job directories.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class HistoryStore:
    def __init__(self, runtime_dir: Path):
        self.path = runtime_dir / "history.sqlite3"
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS analysis_sessions (
                analysis_id TEXT PRIMARY KEY, owner TEXT NOT NULL,
                created_at TEXT NOT NULL, status TEXT NOT NULL,
                summary_json TEXT NOT NULL, record_json TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS history_owner_date ON "
                       "analysis_sessions(owner, created_at DESC, analysis_id DESC)")
        self.mark_interrupted()

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def save(self, record):
        result = record.get("result") or {}
        players = result.get("players") or []
        selected = str(result.get("selectedTrackId", ""))
        player = next((p for p in players if str(p.get("trackId")) == selected),
                      players[0] if players else {})
        summary = {key: record.get(key) for key in (
            "analysisId", "createdAt", "completedAt", "originalFilename",
            "targetPlayer", "athleteMassKg", "status", "progress", "error")}
        summary["totalDistance"] = {key: player.get("totalDistance", {}).get(key)
                                    for key in ("status", "value", "unit")}
        summary["speed"] = {key: player.get("speed", {}).get(key)
                            for key in ("status", "average", "unit")}
        with self.connect() as db:
            db.execute("""INSERT INTO analysis_sessions VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(analysis_id) DO UPDATE SET
                status=excluded.status, summary_json=excluded.summary_json,
                record_json=excluded.record_json""", (
                record["analysisId"], record["owner"], record["createdAt"],
                record["status"], json.dumps(summary, allow_nan=False),
                json.dumps(record, allow_nan=False)))

    def get(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT record_json FROM analysis_sessions WHERE analysis_id=?",
                             (job_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, owner, limit=20, offset=0):
        with self.connect() as db:
            total = db.execute("SELECT COUNT(*) FROM analysis_sessions WHERE owner=?",
                               (owner,)).fetchone()[0]
            rows = db.execute("""SELECT summary_json FROM analysis_sessions
                WHERE owner=? ORDER BY created_at DESC, analysis_id DESC LIMIT ? OFFSET ?""",
                              (owner, limit, offset)).fetchall()
        return {"items": [json.loads(row[0]) for row in rows], "total": total,
                "hasMore": offset + len(rows) < total}

    def delete(self, job_id):
        with self.connect() as db:
            db.execute("DELETE FROM analysis_sessions WHERE analysis_id=?", (job_id,))

    def mark_interrupted(self):
        with self.connect() as db:
            rows = db.execute("SELECT record_json FROM analysis_sessions WHERE "
                              "status IN ('queued', 'processing', 'cancelling')").fetchall()
        for row in rows:
            record = json.loads(row[0])
            record.update(status="failed", completedAt=utc_now(),
                          error="Analysis interrupted by a server restart. Please upload the video again.")
            self.save(record)
