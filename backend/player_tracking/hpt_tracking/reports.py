"""Persist metric-only presentation reports; never relabel image pixels as metres."""
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_pdf import PdfPages
import textwrap

from .metric_motion import evaluate_force_velocity_profile

REPORT_FILES = {"movement_trajectories.png", "speed_deceleration.png",
                "coach_report.pdf", "reports.zip"}
REPORT_ARCHIVE_FILES = {"movement_trajectories.png", "speed_deceleration.png",
                        "coach_report.pdf"}


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


def _number(value, digits=1, suffix=""):
    if not isinstance(value, (int, float)):
        return "Unavailable"
    return f"{value:.{digits}f}{suffix}"


def _baseline_for_display(force_velocity, current_curve):
    """Return a baseline evaluated over the full current-session range."""
    baseline = force_velocity.get("baselineCurve") or []
    if len(current_curve) < 2 or len(baseline) < 2:
        return baseline
    current_x = [float(point["velocityMps"]) for point in current_curve]
    same_range = (
        abs(float(baseline[0]["velocityMps"])-current_x[0]) < .0002 and
        abs(float(baseline[-1]["velocityMps"])-current_x[-1]) < .0002
    )
    if same_range:
        return baseline
    values = evaluate_force_velocity_profile(
        {"currentCurve": baseline}, current_x,
    )
    if values is None:
        return baseline
    return [
        {"velocityMps": round(velocity, 4),
         "forceNPerKg": round(max(0.0, float(force)), 4)}
        for velocity, force in zip(current_x, values)
    ]


def _save_coach_report(result, output_path):
    """Generate a coach-readable PDF from exactly the same result JSON as the app."""
    player = _selected_player(result)
    force_velocity = player.get("forceVelocity") or {}
    current_curve = force_velocity.get("currentCurve") or []
    baseline_curve = _baseline_for_display(force_velocity, current_curve)
    events = [event for event in force_velocity.get("events") or []
              if not event.get("excluded", False)]
    player_name = result.get("playerName") or "Player"
    summary = force_velocity.get("comparisonSummary") or "Personal baseline is being built"
    detail_text = force_velocity.get("comparisonDetail") or ""
    with PdfPages(output_path) as pdf:
        cover = Figure(figsize=(8.27, 11.69), layout="constrained")
        ax = cover.add_subplot()
        ax.set_axis_off()
        ax.text(.02, .96, "HPT PLAYER ANALYSIS", fontsize=12, color="#267557",
                weight="bold", transform=ax.transAxes)
        ax.text(.02, .89, player_name,
                fontsize=26, weight="bold", transform=ax.transAxes)
        ax.text(.02, .84, "Coach movement review", fontsize=16, transform=ax.transAxes)
        ax.text(.02, .68, "Match performance", fontsize=17, weight="bold", transform=ax.transAxes)
        ax.text(.04, .63, textwrap.fill(summary, 92),
                fontsize=12, va="top", transform=ax.transAxes)
        ax.text(.04, .57, textwrap.fill(detail_text, 92),
                fontsize=11.5, va="top", transform=ax.transAxes)
        ax.text(.02, .30, "Included in this report", fontsize=16, weight="bold",
                transform=ax.transAxes)
        ax.text(.04, .25, "\n".join([
            "• Movement direction, distance and speed",
            "• Tracking coverage and direction changes",
            "• Overall effort and Movement Force–Velocity",
            "• Key movement moments",
        ]), fontsize=11.5, va="top", transform=ax.transAxes)
        pdf.savefig(cover)

        summary_page = Figure(figsize=(8.27, 11.69), layout="constrained")
        summary_ax = summary_page.add_subplot(); summary_ax.set_axis_off()
        summary_ax.text(.02, .97, "Movement summary", fontsize=22, weight="bold",
                        transform=summary_ax.transAxes)
        lateral = (player.get("leftRightDistance") or {}).get("value")
        forward = (player.get("forwardBackDistance") or {}).get("value")
        distance = (player.get("totalDistance") or {}).get("value")
        speed = player.get("speed") or {}
        direction_changes = (player.get("directionChanges") or {}).get("count")
        coverage = player.get("coverage") or {}
        retained = coverage.get("retainedSamples")
        excluded = coverage.get("excludedSamples")
        coverage_percent = None
        if isinstance(retained, (int, float)) and isinstance(excluded, (int, float)) \
                and retained+excluded > 0:
            coverage_percent = retained/(retained+excluded)*100
        rows = [
            ("Lateral movement", _number(lateral, 1, " m")),
            ("Forward/back movement", _number(forward, 1, " m")),
            ("Total distance", _number(distance, 1, " m")),
            ("Average speed", _number(speed.get("average"), 1, " m/s")),
            ("Peak speed", _number(speed.get("peak"), 1, " m/s")),
            ("Direction changes", _number(direction_changes, 0)),
            ("Tracking coverage", _number(coverage_percent, 0, "%")),
            ("Analysed movement time",
             _number(coverage.get("validDurationSeconds"), 1, " s")),
        ]
        y = .88
        for label, value in rows:
            summary_ax.text(.05, y, label, fontsize=12,
                            transform=summary_ax.transAxes)
            summary_ax.text(.93, y, value, fontsize=12, weight="bold", ha="right",
                            transform=summary_ax.transAxes)
            summary_ax.plot([.05, .93], [y-.025, y-.025], color="#D6DDD8", lw=1,
                            transform=summary_ax.transAxes)
            y -= .09
        pdf.savefig(summary_page)

        effort_page = Figure(figsize=(8.27, 11.69), layout="constrained")
        effort_ax = effort_page.add_subplot(); effort_ax.set_axis_off()
        effort_ax.text(.02, .97, "Overall effort", fontsize=22, weight="bold",
                       transform=effort_ax.transAxes)
        effort = player.get("overallEffort") or {}
        effort_rows = [
            ("Speed contribution", _number(effort.get("speedAU"), 2, " AU")),
            ("Acceleration contribution", _number(effort.get("accelerationAU"), 2, " AU")),
            ("Braking contribution", _number(effort.get("brakingAU"), 2, " AU")),
            ("AU per valid minute", _number(effort.get("auPerValidMinute"), 2, " AU")),
            ("Total load", _number(effort.get("value"), 2, " AU")),
        ]
        y = .84
        for label, value in effort_rows:
            effort_ax.text(.08, y, label, fontsize=13,
                           transform=effort_ax.transAxes)
            effort_ax.text(.90, y, value, fontsize=13, weight="bold", ha="right",
                           transform=effort_ax.transAxes)
            effort_ax.plot([.08, .90], [y-.03, y-.03], color="#D6DDD8", lw=1,
                           transform=effort_ax.transAxes)
            y -= .11
        pdf.savefig(effort_page)

        profile_page = Figure(figsize=(8.27, 11.69), layout="constrained")
        grid = profile_page.add_gridspec(3, 1, height_ratios=[.22, .48, .30])
        title = profile_page.add_subplot(grid[0]); title.set_axis_off()
        title.text(0, .85, "Movement Force–Velocity", fontsize=22, weight="bold")
        chart = profile_page.add_subplot(grid[1])
        if current_curve:
            chart.plot([point["velocityMps"] for point in current_curve],
                       [point["forceNPerKg"] for point in current_curve],
                       color="#267557", lw=3, label="This match")
            if baseline_curve:
                chart.plot([point["velocityMps"] for point in baseline_curve],
                           [point["forceNPerKg"] for point in baseline_curve],
                           color="#C44F00", lw=2.5, ls="--", label="Personal baseline")
            chart.legend(frameon=False)
        else:
            chart.text(.5, .5, "Movement Force–Velocity unavailable",
                       ha="center", va="center", transform=chart.transAxes)
        chart.set(xlabel="Movement velocity (m/s)", ylabel="Estimated propulsion (N/kg)")
        chart.grid(alpha=.25)
        detail = profile_page.add_subplot(grid[2]); detail.set_axis_off()
        detail.text(0, .95, "Match performance", va="top", fontsize=13, weight="bold")
        detail.text(0, .78, textwrap.fill(summary, 105), va="top", fontsize=11.5, weight="bold")
        detail.text(0, .58, textwrap.fill(detail_text, 105), va="top", fontsize=11)
        peak_propulsion = force_velocity.get("peakEstimatedPropulsionN")
        mass_kg = force_velocity.get("massKg")
        if not isinstance(peak_propulsion, (int, float)) \
                and isinstance(mass_kg, (int, float)) and current_curve:
            peak_propulsion = max(point["forceNPerKg"] for point in current_curve) * mass_kg
        if isinstance(peak_propulsion, (int, float)):
            mass_label = f" ({mass_kg:.0f} kg)" if isinstance(mass_kg, (int, float)) else ""
            detail.text(0, .48, f"Peak estimated propulsion{mass_label}: {peak_propulsion:.0f} N",
                        va="top", fontsize=11.5, weight="bold")
        status = force_velocity.get("comparisonStatus")
        possibilities = {
            "below": [
                "Acceleration was not maintained after the initial movement.",
                "The player reached position more slowly than usual.",
                "Body position or footwork may have reduced propulsion.",
                "Movement performance may have dropped later in the session.",
                "The movement may have been tactical rather than full effort.",
            ],
            "above": [
                "The first movement was quicker.",
                "Acceleration was maintained after the initial movement.",
                "Chasing and recovery movement was more assertive.",
                "Body position and push-off may have been more effective.",
                "Key movements were performed at a higher intensity.",
            ],
            "close": [
                "Movement intensity was similar to recent sessions.",
                "Stronger and weaker movements balanced out across the session.",
                "Footwork and push-off were broadly consistent with usual.",
                "The session contained a familiar mix of attacking, recovery and tactical movement.",
                "The key movements reflected the player’s usual performance.",
            ],
        }.get(status, [])
        if possibilities:
            detail.text(0, .36, "Possible explanations", va="top",
                        fontsize=11, weight="bold")
            bullet_text = "\n".join(
                f"• {textwrap.fill(item, 98, subsequent_indent='  ')}"
                for item in possibilities
            )
            detail.text(0, .28, bullet_text, va="top", fontsize=10.5,
                        linespacing=1.35)
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
        ax.text(.02, .96, "Key movement moments", fontsize=21, weight="bold", transform=ax.transAxes)
        ax.text(.02, .90, "Use these timestamps to review the match context.", fontsize=11, transform=ax.transAxes)
        moment_lines = []
        for event in sorted(events, key=lambda item: item.get("meanForceNPerKg", 0), reverse=True)[:8]:
            seconds = float(event.get("startTimeSeconds", 0))
            moment_lines.append(f"• {int(seconds//60):02d}:{seconds%60:04.1f} — "
                                f"{event.get('label', 'Key movement')} — "
                                f"{event.get('startSpeedMps', 0):.1f} to {event.get('peakSpeedMps', 0):.1f} m/s")
        if not moment_lines:
            moment_lines.append("• No key movement moments were available.")
        ax.text(.04, .85, "\n\n".join(moment_lines), fontsize=10.5, va="top", transform=ax.transAxes)
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
            ax.text(.5, .5, "Metric report unavailable",
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
        figure.suptitle("Court-mapped movement", fontsize=10)
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
        for filename in sorted(REPORT_ARCHIVE_FILES):
            archive.write(output_dir / filename, filename)
