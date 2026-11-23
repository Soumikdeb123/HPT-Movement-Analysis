"""Durable user-scoped players, analysis history and personal baselines."""
from datetime import datetime, timezone
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from statistics import median
from uuid import uuid4


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
            columns = {row[1] for row in db.execute("PRAGMA table_info(analysis_sessions)")}
            if "player_id" not in columns:
                db.execute("ALTER TABLE analysis_sessions ADD COLUMN player_id TEXT")
            if "algorithm_version" not in columns:
                db.execute("ALTER TABLE analysis_sessions ADD COLUMN algorithm_version TEXT")
            db.execute("""CREATE TABLE IF NOT EXISTS players (
                player_id TEXT PRIMARY KEY, owner TEXT NOT NULL,
                display_name TEXT NOT NULL, default_mass_kg REAL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                archived_at TEXT
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS history_owner_date ON "
                       "analysis_sessions(owner, created_at DESC, analysis_id DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS history_player_date ON "
                       "analysis_sessions(owner, player_id, created_at DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS players_owner_name ON "
                       "players(owner, archived_at, display_name)")
        self.mark_interrupted()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create_player(self, owner, display_name, default_mass_kg=None):
        name = " ".join(str(display_name).strip().split())
        if not name or len(name) > 100:
            raise ValueError("Enter a player name of 1–100 characters.")
        if default_mass_kg is not None and not 20 <= float(default_mass_kg) <= 250:
            raise ValueError("Default mass must be between 20 and 250 kg.")
        now, player_id = utc_now(), uuid4().hex
        with self.connect() as db:
            db.execute("""INSERT INTO players
                (player_id, owner, display_name, default_mass_kg, created_at, updated_at, archived_at)
                VALUES (?, ?, ?, ?, ?, ?, NULL)""",
                (player_id, owner, name, default_mass_kg, now, now))
        return self.get_player(owner, player_id)

    def get_player(self, owner, player_id, include_archived=False):
        query = "SELECT * FROM players WHERE owner=? AND player_id=?"
        if not include_archived:
            query += " AND archived_at IS NULL"
        with self.connect() as db:
            row = db.execute(query, (owner, player_id)).fetchone()
        return self._player_dict(row) if row else None

    def list_players(self, owner, include_archived=False):
        query = """SELECT p.*,
            (SELECT COUNT(*) FROM analysis_sessions a
             WHERE a.owner=p.owner AND a.player_id=p.player_id) analysis_count,
            (SELECT MAX(created_at) FROM analysis_sessions a
             WHERE a.owner=p.owner AND a.player_id=p.player_id) last_analysis_at
            FROM players p WHERE p.owner=?"""
        if not include_archived:
            query += " AND p.archived_at IS NULL"
        query += " ORDER BY p.display_name COLLATE NOCASE, p.created_at"
        with self.connect() as db:
            rows = db.execute(query, (owner,)).fetchall()
        return {"items": [self._player_dict(row) for row in rows]}

    def update_player(self, owner, player_id, display_name=None,
                      default_mass_kg="unchanged", archive=False):
        current = self.get_player(owner, player_id, include_archived=True)
        if current is None:
            return None
        name = current["displayName"] if display_name is None else " ".join(str(display_name).strip().split())
        if not name or len(name) > 100:
            raise ValueError("Enter a player name of 1–100 characters.")
        mass = current["defaultMassKg"] if default_mass_kg == "unchanged" else default_mass_kg
        if mass is not None and not 20 <= float(mass) <= 250:
            raise ValueError("Default mass must be between 20 and 250 kg.")
        archived_at = utc_now() if archive else current.get("archivedAt")
        with self.connect() as db:
            db.execute("""UPDATE players SET display_name=?, default_mass_kg=?,
                updated_at=?, archived_at=? WHERE owner=? AND player_id=?""",
                (name, mass, utc_now(), archived_at, owner, player_id))
        return self.get_player(owner, player_id, include_archived=True)

    @staticmethod
    def _player_dict(row):
        data = dict(row)
        return {
            "playerId": data["player_id"], "displayName": data["display_name"],
            "defaultMassKg": data["default_mass_kg"], "createdAt": data["created_at"],
            "updatedAt": data["updated_at"], "archivedAt": data["archived_at"],
            "analysisCount": data.get("analysis_count", 0) or 0,
            "lastAnalysisAt": data.get("last_analysis_at"),
        }

    def save(self, record):
        result = record.get("result") or {}
        players = result.get("players") or []
        selected = str(result.get("selectedTrackId", ""))
        player = next((p for p in players if str(p.get("trackId")) == selected),
                      players[0] if players else {})
        fv = player.get("forceVelocity") or {}
        summary = {key: record.get(key) for key in (
            "analysisId", "createdAt", "completedAt", "originalFilename",
            "targetPlayer", "athleteMassKg", "status", "progress", "error",
            "playerId", "playerName")}
        summary["qualityStatus"] = player.get("qualityStatus", fv.get("quality", {}).get("status"))
        summary["forceVelocitySummary"] = self._force_velocity_summary(fv)
        summary["totalDistance"] = {key: player.get("totalDistance", {}).get(key)
                                    for key in ("status", "value", "unit")}
        summary["speed"] = {key: player.get("speed", {}).get(key)
                            for key in ("status", "average", "unit")}
        algorithm_version = fv.get("algorithmVersion")
        with self.connect() as db:
            db.execute("""INSERT INTO analysis_sessions
                (analysis_id, owner, created_at, status, summary_json, record_json,
                 player_id, algorithm_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(analysis_id) DO UPDATE SET
                status=excluded.status, summary_json=excluded.summary_json,
                record_json=excluded.record_json, player_id=excluded.player_id,
                algorithm_version=excluded.algorithm_version""", (
                record["analysisId"], record["owner"], record["createdAt"],
                record["status"], json.dumps(summary, allow_nan=False),
                json.dumps(record, allow_nan=False), record.get("playerId"),
                algorithm_version))

    @staticmethod
    def _force_velocity_summary(force_velocity):
        return force_velocity.get("comparisonSummary") or ""

    def attach_force_velocity_baseline(self, record):
        """Attach a last-three comparable baseline to a completed result."""
        player_id = record.get("playerId")
        result = record.get("result") or {}
        selected = str(result.get("selectedTrackId", ""))
        players = result.get("players") or []
        player = next((p for p in players if str(p.get("trackId")) == selected),
                      players[0] if players else None)
        if not player_id or player is None:
            return record
        profile = player.get("forceVelocity") or {}
        version = profile.get("algorithmVersion")
        if not version:
            return record
        with self.connect() as db:
            rows = db.execute("""SELECT analysis_id, record_json FROM analysis_sessions
                WHERE owner=? AND player_id=? AND status='completed'
                AND algorithm_version=? AND analysis_id!=?
                ORDER BY created_at DESC LIMIT 20""",
                (record["owner"], player_id, version, record["analysisId"])).fetchall()
        previous = []
        previous_ids = []
        for row in rows:
            old = json.loads(row["record_json"])
            old_result = old.get("result") or {}
            old_players = old_result.get("players") or []
            old_selected = str(old_result.get("selectedTrackId", ""))
            old_player = next((p for p in old_players if str(p.get("trackId")) == old_selected),
                              old_players[0] if old_players else None)
            old_profile = old_player.get("forceVelocity", {}) if old_player else {}
            if old_profile.get("fit") and old_profile.get("currentCurve"):
                previous.append(old_profile)
                previous_ids.append(row["analysis_id"])
                if len(previous) == 5:
                    break
        profile["baselineAnalysisCount"] = len(previous)
        profile["baselineAnalysisIds"] = previous_ids
        count = len(profile.get("events") or [])
        if not profile.get("fit") or not profile.get("currentCurve"):
            profile["comparisonSummary"] = None
            profile["baselineCurve"] = []
            player["forceVelocity"] = profile
            return record
        if len(previous) < 3:
            profile["comparisonSummary"] = (
                f"This match identified {count} valid sprint accelerations. "
                f"The personal baseline is forming ({len(previous)}/3 comparable analyses)."
            )
            profile["baselineCurve"] = []
            player["forceVelocity"] = profile
            return record

        fits = [item["fit"] for item in previous]
        intercept = median(float(item["interceptNPerKg"]) for item in fits)
        slope = median(float(item["slopeNPerKgPerMps"]) for item in fits)
        current_fit = profile["fit"]
        minimum = max(
            float(current_fit["minVelocityMps"]),
            max(float(item["minVelocityMps"]) for item in fits),
        )
        maximum = min(
            float(current_fit["maxVelocityMps"]),
            min(float(item["maxVelocityMps"]) for item in fits),
        )
        if maximum-minimum < .25:
            profile["baselineCurve"] = []
            profile["comparisonSummary"] = (
                f"This match identified {count} valid sprint accelerations. "
                "The current match and personal baseline did not share enough movement-speed range for comparison."
            )
            player["forceVelocity"] = profile
            return record

        velocities = [minimum+(maximum-minimum)*index/23 for index in range(24)]
        profile["baselineCurve"] = [
            {"velocityMps": round(value, 4),
             "forceNPerKg": round(max(0.0, intercept+slope*value), 4)}
            for value in velocities
        ]
        current_intercept = float(current_fit["interceptNPerKg"])
        current_slope = float(current_fit["slopeNPerKgPerMps"])
        baseline_values = [max(.001, intercept+slope*value) for value in velocities]
        differences = [
            (current_intercept+current_slope*value-base)/base*100
            for value, base in zip(velocities, baseline_values)
        ]
        change = sum(differences)/len(differences)
        if change > 5:
            comparison = "above"
        elif change < -5:
            comparison = "below"
        else:
            comparison = "close to"
        profile["comparisonStatus"] = comparison.replace(" ", "_")
        profile["comparisonChangePercent"] = round(change, 1)
        profile["comparisonVelocityMinMps"] = round(minimum, 2)
        profile["comparisonVelocityMaxMps"] = round(maximum, 2)

        ranked = []
        for event in profile.get("events") or []:
            velocity = (
                float(event.get("startSpeedMps", 0))+
                float(event.get("peakSpeedMps", 0))
            )/2
            if minimum <= velocity <= maximum:
                expected = intercept+slope*velocity
                ranked.append((
                    abs(float(event.get("meanForceNPerKg", 0))-expected),
                    event.get("eventId"),
                ))
        ranked.sort(reverse=True)
        recommended = [event_id for _, event_id in ranked[:3] if event_id]
        profile["recommendedEventIds"] = recommended
        event_numbers = []
        chronological = sorted(
            profile.get("events") or [], key=lambda item: item.get("startTimeSeconds", 0)
        )
        for event_id in recommended:
            for index, event in enumerate(chronological, 1):
                if event.get("eventId") == event_id:
                    event_numbers.append(str(index))
                    break
        suggestion = (
            f" Review sprint events {', '.join(event_numbers)} for match context."
            if event_numbers else ""
        )
        profile["comparisonSummary"] = (
            f"This match identified {count} valid sprint accelerations. "
            f"Force–Velocity performance was {comparison} the personal baseline "
            f"across the shared {minimum:.1f}–{maximum:.1f} m/s range.{suggestion}"
        )
        player["forceVelocity"] = profile
        return record

    def get(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT record_json FROM analysis_sessions WHERE analysis_id=?",
                             (job_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, owner, limit=20, offset=0, player_id=None):
        where, values = "owner=?", [owner]
        if player_id:
            where += " AND player_id=?"
            values.append(player_id)
        with self.connect() as db:
            total = db.execute(f"SELECT COUNT(*) FROM analysis_sessions WHERE {where}",
                               values).fetchone()[0]
            rows = db.execute(f"""SELECT summary_json FROM analysis_sessions
                WHERE {where} ORDER BY created_at DESC, analysis_id DESC LIMIT ? OFFSET ?""",
                              [*values, limit, offset]).fetchall()
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
