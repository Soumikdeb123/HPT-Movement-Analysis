"""Persist metric-only presentation reports; never relabel image pixels as metres."""
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_pdf import PdfPages
import textwrap

REPORT_FILES = {"movement_trajectories.png", "speed_deceleration.png", "analysis.json",
                "coach_report.pdf", "reports.zip"}


def runs(samples):
    """Keep tracking discontinuities as separate lines, not interpolated motion."""
    current = []
    for p in samples:
        if current and p.get("segmentId") != current[-1].get("segmentId"):
            yield current
            current = []
        current.append(p)
    if current:
        yield current


def _selected_player(result):
    players = result.get("players") or []
    selected = str(result.get("selectedTrackId", ""))
    return next((p for p in players if str(p.get("trackId")) == selected),
                players[0] if players else {})


def _save_coach_report(result, output_path):
    """Generate a coach-readable PDF from exactly the same result JSON as the app."""
    player = _selected_player(result)
    force_velocity = player.get("forceVelocity") or {}
    quality = force_velocity.get("quality") or {}
    current_curve = force_velocity.get("currentCurve") or []
    baseline_curve = force_velocity.get("baselineCurve") or []
    events = force_velocity.get("events") or []
    with PdfPages(output_path) as pdf:
        cover = Figure(figsize=(8.27, 11.69), layout="constrained")
        ax = cover.add_subplot()
        ax.set_axis_off()
        ax.text(.02, .96, "HPT PLAYER ANALYSIS", fontsize=12, color="#267557",
                weight="bold", transform=ax.transAxes)
        ax.text(.02, .89, result.get("playerName") or "Player",
                fontsize=26, weight="bold", transform=ax.transAxes)
        ax.text(.02, .84, "Coach movement review", fontsize=16, transform=ax.transAxes)
        status = str(quality.get("status", "unavailable")).replace("_", " ").title()
        ax.text(.02, .77, f"Analysis quality: {status}", fontsize=13, weight="bold",
                transform=ax.transAxes)
        summary = force_velocity.get("comparisonSummary")
        if not summary:
            summary = ("The match sprint Force–Velocity profile was withheld because "
                       "there were not enough valid directionally stable sprint accelerations.")
        ax.text(.02, .68, "Coach summary", fontsize=17, weight="bold", transform=ax.transAxes)
        ax.text(.04, .63, textwrap.fill(summary, 92),
                fontsize=12, va="top", transform=ax.transAxes)
        ax.text(.02, .30, "What this report can support", fontsize=16, weight="bold",
                transform=ax.transAxes)
        ax.text(.04, .25, "\n".join([
            "• Review observed movement and acceleration events.",
            "• Compare the same player with recent comparable analyses.",
            "• Return to the annotated video at the listed timestamps.",
        ]), fontsize=11.5, va="top", transform=ax.transAxes)
        ax.text(.02, .07, "Video-derived estimates • not a laboratory force measurement, fatigue score, "
                "injury assessment or training prescription", fontsize=9, color="0.35",
                transform=ax.transAxes)
        pdf.savefig(cover)

        profile_page = Figure(figsize=(8.27, 11.69), layout="constrained")
        grid = profile_page.add_gridspec(3, 1, height_ratios=[.22, .48, .30])
        title = profile_page.add_subplot(grid[0]); title.set_axis_off()
        title.text(0, .85, "Match Sprint Force–Velocity", fontsize=22, weight="bold")
        title.text(0, .52, "This match compared with the player's personal baseline.", fontsize=11)
        title.text(0, .20, f"Valid acceleration events: {quality.get('validEventCount', 0)}  •  "
                   f"Tracking coverage: {100*quality.get('trackingCoverage', 0):.0f}%", fontsize=10)
        chart = profile_page.add_subplot(grid[1])
        if current_curve:
            chart.plot([point["velocityMps"] for point in current_curve],
                       [point["forceNPerKg"] for point in current_curve],
                       color="#267557", lw=3, label="This match")
            if baseline_curve:
                chart.plot([point["velocityMps"] for point in baseline_curve],
                           [point["forceNPerKg"] for point in baseline_curve],
                           color="0.35", lw=2.5, ls="--", label="Personal baseline")
            chart.legend(frameon=False)
        else:
            chart.text(.5, .5, "Force–Velocity profile unavailable\nNot enough valid sprint evidence",
                       ha="center", va="center", transform=chart.transAxes)
        chart.set(xlabel="Movement velocity (m/s)", ylabel="Estimated horizontal force (N/kg)")
        chart.grid(alpha=.25)
        detail = profile_page.add_subplot(grid[2]); detail.set_axis_off()
        detail.text(0, .95, textwrap.fill(summary, 105), va="top", fontsize=11)
        detail.text(0, .55, f"Valid sprint accelerations: {len(events)}", fontsize=10.5)
        detail.text(0, .15, "Only directionally stable sprint acceleration is included. Lateral small steps, "
                    "sharp turns and braking are excluded. The chart does not extrapolate beyond observed speeds.", fontsize=9.5,
                    color="0.35", wrap=True)
        pdf.savefig(profile_page)

        movement_page = Figure(figsize=(8.27, 11.69), layout="constrained")
        ax = movement_page.add_subplot()
        ax.set_title("Movement overview", fontsize=20, loc="left", pad=18)
        points = player.get("movementPath", {}).get("points") or []
        if points:
            ax.plot([p["x"] for p in points], [p["y"] for p in points], color="#267557", lw=1)
            ax.plot([0, 10.97, 10.97, 0, 0], [0, 0, 23.77, 23.77, 0], color="0.5")
            ax.plot([0, 10.97], [11.885, 11.885], color="0.5")
            ax.set(xlabel="Court X (m)", ylabel="Court Y (m)")
            ax.set_aspect("equal", adjustable="datalim"); ax.invert_yaxis(); ax.grid(alpha=.2)
        else:
            ax.set_axis_off(); ax.text(.5, .55, "Metre-based movement overview unavailable",
                                       ha="center", transform=ax.transAxes, fontsize=16)
        distance = player.get("totalDistance", {}).get("value")
        peak = player.get("speed", {}).get("peak")
        movement_page.text(.08, .08, f"Valid distance: {distance:.1f} m" if isinstance(distance, (int, float)) else "Valid distance: unavailable",
                           fontsize=11)
        movement_page.text(.08, .055, f"Reliable observed peak speed: {peak:.1f} m/s" if isinstance(peak, (int, float)) else "Peak speed: unavailable",
                           fontsize=11)
        pdf.savefig(movement_page)

        evidence_page = Figure(figsize=(8.27, 11.69), layout="constrained")
        ax = evidence_page.add_subplot(); ax.set_axis_off()
        ax.text(.02, .96, "Video evidence and method", fontsize=21, weight="bold", transform=ax.transAxes)
        ax.text(.02, .90, "Key acceleration moments", fontsize=14, weight="bold", transform=ax.transAxes)
        moment_lines = []
        for event in sorted(events, key=lambda item: item.get("meanForceNPerKg", 0), reverse=True)[:8]:
            seconds = float(event.get("startTimeSeconds", 0))
            moment_lines.append(f"• {int(seconds//60):02d}:{seconds%60:04.1f} — "
                                f"{event.get('meanForceNPerKg', 0):.2f} N/kg — "
                                f"speed {event.get('startSpeedMps', 0):.1f} to {event.get('peakSpeedMps', 0):.1f} m/s")
        if not moment_lines:
            moment_lines.append("• No valid acceleration moments were available.")
        ax.text(.04, .85, "\n\n".join(moment_lines), fontsize=10.5, va="top", transform=ax.transAxes)
        reasons = quality.get("reasons") or []
        ax.text(.02, .48, "Quality and limitations", fontsize=14, weight="bold", transform=ax.transAxes)
        method_lines = [
            f"Algorithm: {force_velocity.get('algorithmVersion', 'unavailable')}",
            f"Court calibration confidence: {100*quality.get('calibrationConfidence', 0):.0f}%",
            *(reasons or ["No additional quality limitation was raised by the automatic checks."]),
            "Position is estimated from fixed-camera court mapping and smoothed before derivatives are calculated.",
            "The profile uses sustained positive-acceleration events; braking is reported separately.",
            "N/kg is an estimated horizontal net-force-per-kilogram proxy, not measured ground-reaction force.",
        ]
        ax.text(.04, .43, "\n\n".join(textwrap.fill(str(line), 100) for line in method_lines),
                fontsize=10, va="top", transform=ax.transAxes)
        pdf.savefig(evidence_page)


def save_reports(result, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    players = [p for p in result.get("players", [])
               if p.get("speed", {}).get("unit") == "m/s"
               and p.get("movementPath", {}).get("points")]
    movement = Figure(figsize=(13, 6), layout="constrained")
    dynamics = Figure(figsize=(13, max(4, 4*len(players))), layout="constrained")
    if not players:
        for figure in (movement, dynamics):
            ax = figure.add_subplot()
            ax.set_axis_off()
            ax.text(.5, .5, "Metric report unavailable\n\nCourt calibration or metric trajectory validation failed.\n"
                    "Recheck court lines and reanalyse the video.\nPixel diagnostics are retained in analysis.json only.",
                    ha="center", va="center", transform=ax.transAxes, fontsize=15)
    else:
        path_ax, distance_ax = movement.subplots(1, 2, width_ratios=[1, 2])
        path_ax.set(title="Player movement trajectories", xlabel="Court X (m)", ylabel="Court Y (m)")
        # Do not clip valid positions outside court boundaries.
        path_ax.plot([0, 10.97, 10.97, 0, 0], [0, 0, 23.77, 23.77, 0], color="grey", lw=1)
        path_ax.plot([0, 10.97], [11.885, 11.885], color="grey", lw=1)
        path_ax.set_aspect("equal", adjustable="datalim")
        path_ax.invert_yaxis()
        distance_ax.set(title="Cumulative distance", xlabel="Time (s)", ylabel="Distance (m)")
        for index, player in enumerate(players):
            color = ["red", "blue", "green"][index % 3]
            label = f"Player {player.get('trackId', index)}"
            for n, run in enumerate(runs(player["movementPath"]["points"])):
                path_ax.plot([p["x"] for p in run], [p["y"] for p in run], color=color, label=label if n == 0 else None)
            for n, run in enumerate(runs(player["totalDistance"].get("samples", []))):
                distance_ax.plot([p["timeSeconds"] for p in run], [p["value"] for p in run], color=color, label=label if n == 0 else None)
            ax = dynamics.add_subplot(len(players), 1, index+1)
            right = ax.twinx()
            for n, run in enumerate(runs(player["speed"].get("samples", []))):
                right.plot([p["timeSeconds"] for p in run], [p["value"] for p in run], color="0.65", label="Speed (m/s)" if n == 0 else None)
            for n, run in enumerate(runs(player["acceleration"].get("samples", []))):
                ax.plot([p["timeSeconds"] for p in run], [p["value"] for p in run], color=color, label="Signed acceleration" if n == 0 else None)
            events = player.get("deceleration", {}).get("events", [])
            for event in events:
                ax.axvspan(event["startTimeSeconds"], event["endTimeSeconds"], color="red" if event.get("highIntensity") else "orange", alpha=.18)
            ax.axhline(-2, color="orange", ls="--", label="Braking threshold (-2 m/s²)")
            ax.axhline(-3, color="red", ls="--", label="High intensity (-3 m/s²)")
            ax.axhline(0, color="black", lw=.6)
            ax.set(title=f"{label}: speed and deceleration ({len(events)} events)", xlabel="Time (s)", ylabel="Acceleration (m/s²)")
            right.set_ylabel("Speed (m/s)")
            right.set_ylim(bottom=0)
            handles, labels = ax.get_legend_handles_labels()
            h2, l2 = right.get_legend_handles_labels()
            ax.legend(handles+h2, labels+l2, fontsize=8, loc="upper right")
            ax.grid(alpha=.3)
        for ax in (path_ax, distance_ax):
            ax.grid(alpha=.3)
            if ax.get_legend_handles_labels()[0]:
                ax.legend()
    for figure, filename in ((movement, "movement_trajectories.png"), (dynamics, "speed_deceleration.png")):
        figure.suptitle("Experimental court-mapped estimates • discontinuities shown • not a fatigue assessment", fontsize=10)
        figure.savefig(output_dir / filename, dpi=160)
        figure.clear()
    result["reportStatus"] = "metric" if players else "unavailable"
    result["reportImages"] = [
        {"title": "Trajectories and cumulative distance", "filename": "movement_trajectories.png"},
        {"title": "Speed and deceleration events", "filename": "speed_deceleration.png"},
    ]
    _save_coach_report(result, output_dir / "coach_report.pdf")
    result["coachReportFilename"] = "coach_report.pdf"
    (output_dir / "analysis.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    with ZipFile(output_dir / "reports.zip", "w", ZIP_DEFLATED) as archive:
        for filename in sorted(REPORT_FILES - {"reports.zip"}):
            archive.write(output_dir / filename, filename)
