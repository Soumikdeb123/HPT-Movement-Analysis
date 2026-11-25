"""Durable user-scoped players, analysis history and personal baselines."""
from datetime import datetime, timezone
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from statistics import mean
from uuid import uuid4

from .metric_motion import evaluate_force_velocity_profile


BASELINE_MIN_ANALYSES = 3
BASELINE_MAX_ANALYSES = 5
BASELINE_COMPARISON_RULE_VERSION = "2.0.0"
BASELINE_MOMENT_LABELS = {
    "above": "Above usual",
    "below": "Below usual",
    "close": "Close to usual",
}
LEGACY_BASELINE_MOMENT_LABEL = "Largest baseline difference"


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

    @staticmethod
    def _without_baseline_moment(events):
        """Remove the previously derived baseline-only label/window.

        Baselines are recalculated whenever history changes, so this keeps the
        derived review moment idempotent while preserving the three fixed
        movement categories and any coach exclusions.
        """
        cleaned = []
        for original in events or []:
            if original.get("baselineOnly"):
                continue
            event = dict(original)
            labels = [
                label.strip() for label in str(event.get("label", "")).split("·")
                if label.strip() and label.strip() not in {
                    *BASELINE_MOMENT_LABELS.values(),
                    LEGACY_BASELINE_MOMENT_LABEL,
                }
            ]
            event["label"] = " · ".join(labels) or "Key movement"
            event.pop("baselineComparison", None)
            cleaned.append(event)
        return cleaned

    @staticmethod
    def _attach_baseline_moment(profile, events, minimum, maximum, interpolate,
                                baseline_curve, comparison):
        """Tag a movement that genuinely demonstrates the session comparison.

        Above/below tags may add one representative review clip when none of
        the three fixed moments covers it.  ``Close to usual`` is contextual
        only: it can be attached to a fixed moment, but never creates a
        standalone clip.
        """
        label = BASELINE_MOMENT_LABELS.get(comparison)
        if label is None:
            return events
        samples = sorted(
            (dict(point) for point in profile.get("samples") or []),
            key=lambda point: (float(point.get("timeSeconds", 0)),
                               int(point.get("frame", 0))),
        )
        candidates = []
        for start, first in enumerate(samples):
            first_time = float(first.get("timeSeconds", 0))
            segment = first.get("segmentId")
            run = []
            for point in samples[start:]:
                if point.get("segmentId") != segment:
                    break
                time = float(point.get("timeSeconds", 0))
                if time-first_time > .70:
                    break
                if run and int(point.get("frame", 0)) != int(run[-1].get("frame", 0))+1:
                    break
                run.append(point)
            if len(run) < 5:
                continue
            propulsive = [
                point for point in run
                if float(point.get("tangentialAccelerationMps2", 0)) > 0
            ]
            if len(propulsive)/len(run) < .70:
                continue
            speed = mean(float(point.get("velocityMps", 0)) for point in propulsive)
            if not minimum <= speed <= maximum:
                continue
            actual = mean(
                float(point.get("tangentialAccelerationMps2", 0))
                for point in propulsive
            )
            expected = mean(
                interpolate(baseline_curve, float(point.get("velocityMps", 0)))
                for point in propulsive
            )
            difference = actual-expected
            percent = difference/max(.001, expected)*100
            direction_matches = (
                (comparison == "above" and percent > 0) or
                (comparison == "below" and percent < 0) or
                (comparison == "close" and abs(percent) <= 5)
            )
            if not direction_matches:
                continue
            candidates.append({
                "run": run,
                "actual": actual,
                "difference": difference,
                "percent": percent,
            })
        if not candidates:
            return events

        def matching_event(candidate):
            run = candidate["run"]
            start_time = float(run[0].get("timeSeconds", 0))
            end_time = float(run[-1].get("timeSeconds", start_time))
            centre = (start_time+end_time)/2
            return next((event for event in events if (
                not (end_time < float(event.get("startTimeSeconds", 0)) or
                     start_time > float(event.get("endTimeSeconds", 0))) or
                abs(centre-(
                    float(event.get("startTimeSeconds", 0))+
                    float(event.get("endTimeSeconds", event.get("startTimeSeconds", 0)))
                )/2) <= .75
            )), None)

        if comparison == "close":
            attached = [
                (abs(candidate["percent"]), candidate, matching_event(candidate))
                for candidate in candidates
            ]
            attached = [item for item in attached if item[2] is not None]
            if not attached:
                return events
            _, selected, existing = min(attached, key=lambda item: item[0])
        else:
            selected = max(candidates, key=lambda item: abs(item["percent"]))
            existing = matching_event(selected)

        run, actual = selected["run"], selected["actual"]
        start_time = float(run[0].get("timeSeconds", 0))
        end_time = float(run[-1].get("timeSeconds", start_time))
        if existing is not None:
            labels = [label.strip() for label in
                      str(existing.get("label", "")).split("·") if label.strip()]
            if label not in labels:
                labels.append(label)
            existing["label"] = " · ".join(labels)
            existing["baselineComparison"] = True
            return events

        if comparison == "close":
            return events

        peak = max(run, key=lambda point:
                   float(point.get("tangentialAccelerationMps2", 0)))
        speeds = [float(point.get("velocityMps", 0)) for point in run]
        start_frame = int(run[0].get("frame", 0))
        end_frame = int(run[-1].get("frame", start_frame))
        mass = profile.get("massKg")
        events.append({
            "eventId": f"baseline-{start_frame}-{end_frame}",
            "label": label,
            "startFrame": start_frame,
            "peakFrame": int(peak.get("frame", start_frame)),
            "endFrame": end_frame,
            "startTimeSeconds": round(start_time, 4),
            "peakTimeSeconds": round(float(peak.get("timeSeconds", start_time)), 4),
            "endTimeSeconds": round(end_time, 4),
            "videoSeekStartSeconds": round(max(0.0, start_time-.5), 4),
            "videoSeekEndSeconds": round(end_time+2.0, 4),
            "durationSeconds": round(max(0.0, end_time-start_time), 3),
            "startSpeedMps": round(speeds[0], 3),
            "peakSpeedMps": round(max(speeds), 3),
            "deltaSpeedMps": round(speeds[-1]-speeds[0], 3),
            "meanAccelerationMps2": round(actual, 3),
            "peakAccelerationMps2": round(
                float(peak.get("tangentialAccelerationMps2", 0)), 3),
            "meanForceNPerKg": round(actual, 3),
            "estimatedMeanForceN": (
                round(actual*float(mass), 2)
                if isinstance(mass, (int, float)) else None
            ),
            "startX": 0.0, "startY": 0.0, "endX": 0.0, "endY": 0.0,
            "excluded": False,
            "quality": "accepted",
            "baselineComparison": True,
            "baselineOnly": True,
        })
        events.sort(key=lambda event: float(event.get("startTimeSeconds", 0)))
        return events

    def attach_force_velocity_baseline(self, record):
        """Attach the player's recent comparable curves as a personal baseline."""
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
        profile["comparisonRuleVersion"] = BASELINE_COMPARISON_RULE_VERSION
        created_at = record.get("createdAt") or ""
        with self.connect() as db:
            rows = db.execute("""SELECT analysis_id, record_json FROM analysis_sessions
                WHERE owner=? AND player_id=? AND status='completed'
                AND algorithm_version=? AND analysis_id!=?
                AND (created_at < ? OR (created_at=? AND analysis_id < ?))
                ORDER BY created_at DESC LIMIT 20""",
                (record["owner"], player_id, version, record["analysisId"],
                 created_at, created_at, record["analysisId"])).fetchall()
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
                if len(previous) == BASELINE_MAX_ANALYSES:
                    break
        profile["baselineAnalysisCount"] = len(previous)
        profile["baselineAnalysisIds"] = previous_ids
        profile["events"] = self._without_baseline_moment(profile.get("events"))
        all_events = profile.get("events") or []
        events = [event for event in all_events
                  if not event.get("excluded", False)]
        profile["baselineCurve"] = []
        profile["comparisonOverallChangePercent"] = None
        profile["comparisonLargestDifferencePercent"] = None
        profile["comparisonLargestDifferenceVelocityMinMps"] = None
        profile["comparisonLargestDifferenceVelocityMaxMps"] = None
        profile["recommendedEventIds"] = [event.get("eventId") for event in events
                                           if event.get("eventId")]
        if not profile.get("fit") or not profile.get("currentCurve"):
            profile["comparisonSummary"] = None
            profile["comparisonDetail"] = None
            player["forceVelocity"] = profile
            return record
        profile["comparisonStatus"] = "no_baseline"
        profile["comparisonSummary"] = (
            "Personal baseline is being built "
            f"({BASELINE_MIN_ANALYSES} analyses required)"
        )
        profile["comparisonDetail"] = "Future sessions will be compared with this player’s usual movement."
        if len(previous) < BASELINE_MIN_ANALYSES:
            player["forceVelocity"] = profile
            return record

        curves = [item["currentCurve"] for item in previous]
        current_curve = profile["currentCurve"]
        observed_minimum = max(
            min(float(point["velocityMps"]) for point in current_curve),
            max(min(float(point["velocityMps"]) for point in curve) for curve in curves),
        )
        observed_maximum = min(
            max(float(point["velocityMps"]) for point in current_curve),
            min(max(float(point["velocityMps"]) for point in curve) for curve in curves),
        )
        if observed_maximum-observed_minimum < .10:
            player["forceVelocity"] = profile
            return record

        profile["baselineObservedVelocityMinMps"] = round(observed_minimum, 4)
        profile["baselineObservedVelocityMaxMps"] = round(observed_maximum, 4)
        comparison_velocities = [
            observed_minimum+(observed_maximum-observed_minimum)*index/23
            for index in range(24)
        ]
        def interpolate(curve, velocity):
            points = sorted((float(point["velocityMps"]), float(point["forceNPerKg"]))
                            for point in curve)
            for (x0, y0), (x1, y1) in zip(points, points[1:]):
                if x0 <= velocity <= x1:
                    if x1 == x0:
                        return y0
                    ratio = (velocity-x0)/(x1-x0)
                    return y0+(y1-y0)*ratio
            return points[0][1] if velocity <= points[0][0] else points[-1][1]

        # Display the recent-session baseline across exactly the same speed
        # range as this match. Every prior session contributes one fitted
        # prediction, so long clips or dense curves receive no extra weight.
        display_velocities = [float(point["velocityMps"])
                              for point in current_curve]
        session_predictions = [
            evaluate_force_velocity_profile(item, display_velocities)
            for item in previous
        ]
        session_predictions = [values for values in session_predictions
                               if values is not None]
        if len(session_predictions) < BASELINE_MIN_ANALYSES:
            player["forceVelocity"] = profile
            return record
        baseline_values = [
            mean(float(values[index]) for values in session_predictions)
            for index in range(len(display_velocities))
        ]
        profile["baselineCurve"] = [
            {"velocityMps": round(value, 4),
             "forceNPerKg": round(max(0.0, force), 4)}
            for value, force in zip(display_velocities, baseline_values)
        ]
        # Conclusions deliberately use only speeds genuinely observed in this
        # match and every contributing historical analysis. The extended
        # baseline beyond this range is presentation-only.
        comparison_session_values = [
            evaluate_force_velocity_profile(item, comparison_velocities)
            for item in previous
        ]
        comparison_baseline_values = [
            mean(float(values[index]) for values in comparison_session_values)
            for index in range(len(comparison_velocities))
        ]
        current_values = [interpolate(current_curve, value)
                          for value in comparison_velocities]
        differences = [
            (current-base)/max(.001, base)*100
            for current, base in zip(current_values, comparison_baseline_values)
        ]
        groups = [list(range(start, min(start+8, len(comparison_velocities))))
                  for start in range(0, len(comparison_velocities), 8)]
        selected_group = max(
            groups,
            key=lambda group: abs(sum(differences[index] for index in group)/len(group)),
        )
        selected_change = mean(differences[index] for index in selected_group)
        overall_change = mean(differences)
        # First classify the session as a whole.  The strongest local
        # difference is supporting context, never a replacement for the
        # overall result shown to the coach.
        change = overall_change
        comparison_minimum = observed_minimum
        comparison_maximum = observed_maximum
        if overall_change >= 5:
            comparison = "above"
        elif overall_change <= -5:
            comparison = "below"
        else:
            comparison = "close"
        profile["comparisonStatus"] = comparison
        profile["comparisonChangePercent"] = round(change, 1)
        profile["comparisonOverallChangePercent"] = round(overall_change, 1)
        profile["comparisonLargestDifferencePercent"] = round(selected_change, 1)
        profile["comparisonLargestDifferenceVelocityMinMps"] = round(
            comparison_velocities[selected_group[0]], 2,
        )
        profile["comparisonLargestDifferenceVelocityMaxMps"] = round(
            comparison_velocities[selected_group[-1]], 2,
        )
        profile["comparisonVelocityMinMps"] = round(comparison_minimum, 2)
        profile["comparisonVelocityMaxMps"] = round(comparison_maximum, 2)
        largest_range_label = (
            f"{comparison_velocities[selected_group[0]]:.1f}–"
            f"{comparison_velocities[selected_group[-1]]:.1f} m/s"
        )
        largest_direction = "above" if selected_change >= 0 else "below"
        largest_difference_detail = (
            f"Largest difference at {largest_range_label}: "
            f"{abs(selected_change):.1f}% {largest_direction} personal baseline."
        )
        if comparison == "above":
            profile["comparisonSummary"] = "Above usual overall"
            profile["comparisonDetail"] = largest_difference_detail
        elif comparison == "below":
            profile["comparisonSummary"] = "Below usual overall"
            profile["comparisonDetail"] = largest_difference_detail
        else:
            profile["comparisonSummary"] = (
                "Close to usual overall (difference under 5%)"
            )
            profile["comparisonDetail"] = None

        profile["events"] = self._attach_baseline_moment(
            profile, all_events, comparison_minimum, comparison_maximum,
            interpolate, profile["baselineCurve"], comparison,
        )
        events = [event for event in profile["events"]
                  if not event.get("excluded", False)]

        ranked = []
        baseline_curve = profile["baselineCurve"]
        for event in events:
            velocity = (
                float(event.get("startSpeedMps", 0))+
                float(event.get("peakSpeedMps", 0))
            )/2
            if observed_minimum <= velocity <= observed_maximum:
                expected = interpolate(baseline_curve, velocity)
                ranked.append((
                    abs(float(event.get("meanForceNPerKg", 0))-expected),
                    event.get("eventId"),
                ))
        ranked.sort(reverse=True)
        recommended = [event_id for _, event_id in ranked[:3] if event_id]
        profile["recommendedEventIds"] = recommended or [
            event.get("eventId") for event in events[:3] if event.get("eventId")
        ]
        player["forceVelocity"] = profile
        return record

    def refresh_force_velocity_comparisons(self, regenerate_reports=False):
        """Reapply current baseline rules to durable completed analyses.

        Stored tracking samples and movement metrics are reused.  Video
        inference, court mapping and player tracking are never rerun.
        """
        with self.connect() as db:
            rows = db.execute("""SELECT record_json FROM analysis_sessions
                WHERE status='completed' AND player_id IS NOT NULL
                ORDER BY owner, player_id, created_at, analysis_id""").fetchall()
        refreshed = 0
        for row in rows:
            record = json.loads(row["record_json"])
            result = record.get("result") or {}
            players = result.get("players") or []
            selected = str(result.get("selectedTrackId", ""))
            player = next((item for item in players
                           if str(item.get("trackId")) == selected),
                          players[0] if players else None)
            profile = player.get("forceVelocity") if player else None
            if not isinstance(profile, dict) or not profile.get("algorithmVersion"):
                continue
            self.attach_force_velocity_baseline(record)
            if regenerate_reports:
                # Analysis artifacts are served from each job's results folder.
                # Writing to the job root leaves the old exported PDF untouched.
                output_dir = self.path.parent / record["analysisId"] / "results"
                if output_dir.is_dir():
                    from .reports import save_reports
                    save_reports(result, output_dir)
            self.save(record)
            refreshed += 1
        return refreshed

    def set_movement_moment_excluded(self, owner, analysis_id, event_id, excluded):
        """Rebuild one stored F–V curve after a coach includes/excludes a moment."""
        record = self.get(analysis_id)
        if record is None or record.get("owner") != owner or record.get("status") != "completed":
            return None
        result = record.get("result") or {}
        players = result.get("players") or []
        selected = str(result.get("selectedTrackId", ""))
        player = next((item for item in players
                       if str(item.get("trackId")) == selected),
                      players[0] if players else None)
        profile = player.get("forceVelocity") if player else None
        events = profile.get("events") if profile else None
        if not isinstance(events, list):
            return None
        target = next((event for event in events
                       if event.get("eventId") == event_id), None)
        if target is None:
            return None
        target["excluded"] = bool(excluded)

        from .metric_motion import force_velocity_profile
        series = [
            {"timeSeconds": float(point.get("timeSeconds", 0)),
             "speed": float(point.get("velocityMps", 0)),
             "acceleration": float(point.get("tangentialAccelerationMps2", 0))}
            for point in profile.get("samples") or []
        ]
        excluded_ranges = [
            (float(event.get("startTimeSeconds", 0)),
             float(event.get("endTimeSeconds", 0)))
            for event in events if event.get("excluded", False)
        ]
        old_quality = profile.get("quality") or {}
        quality, fit, curve = force_velocity_profile(
            series,
            float(old_quality.get("trackingCoverage", 0)),
            float(old_quality.get("calibrationConfidence", 0)),
            excluded_ranges,
        )
        profile["quality"] = quality
        profile["fit"] = fit
        profile["currentCurve"] = curve
        profile["baselineCurve"] = []
        profile["comparisonSummary"] = None
        profile["comparisonDetail"] = None
        profile["recommendedEventIds"] = []
        player["forceVelocity"] = profile
        self.attach_force_velocity_baseline(record)
        self.save(record)
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
