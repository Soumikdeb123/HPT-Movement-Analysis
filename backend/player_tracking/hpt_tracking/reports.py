"""Persist metric-only presentation reports; never relabel image pixels as metres."""
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure

REPORT_FILES = {"movement_trajectories.png", "speed_deceleration.png", "analysis.json", "reports.zip"}


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
    (output_dir / "analysis.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    with ZipFile(output_dir / "reports.zip", "w", ZIP_DEFLATED) as archive:
        for filename in sorted(REPORT_FILES - {"reports.zip"}):
            archive.write(output_dir / filename, filename)
