"""Conservative active-play screening for fixed-camera court footage.

This module does not claim to recognise scores, serves or ball contacts.  It
finds sustained court movement and returns padded review intervals so idle
time, breaks and ball collection do not dominate coaching coverage figures.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Iterable, Sequence


TrajectorySample = tuple[int, float, float]


@dataclass(frozen=True)
class ActivePlayInterval:
    start_frame: int
    end_frame: int

    @property
    def frame_count(self) -> int:
        return max(0, self.end_frame - self.start_frame + 1)

    def as_dict(self, fps: float) -> dict:
        return {
            "startFrame": self.start_frame,
            "endFrame": self.end_frame,
            "startSeconds": round(self.start_frame / fps, 3),
            "endSeconds": round(self.end_frame / fps, 3),
        }


@dataclass(frozen=True)
class ActivePlaySummary:
    intervals: tuple[ActivePlayInterval, ...]
    active_frames: int
    confidence: float
    status: str

    def as_dict(self, fps: float, processed_frames: int) -> dict:
        return {
            "status": self.status,
            "confidence": round(self.confidence, 3),
            "activeFrames": self.active_frames,
            "processedFrames": processed_frames,
            "activeDurationSeconds": round(self.active_frames / fps, 3),
            "intervals": [interval.as_dict(fps) for interval in self.intervals],
        }


def detect_active_play(
    samples: Sequence[TrajectorySample] | Iterable[TrajectorySample],
    fps: float,
    processed_frames: int,
    *,
    movement_speed_mps: float = 0.55,
    acceleration_mps2: float = 0.65,
    bridge_seconds: float = 2.0,
    lead_seconds: float = 1.0,
    trail_seconds: float = 1.5,
    minimum_interval_seconds: float = 2.0,
) -> ActivePlaySummary:
    """Return padded intervals supported by sustained court movement.

    Walking between points can occasionally pass the speed threshold, so an
    interval also needs repeated motion evidence.  The result is deliberately
    conservative: unknown footage is reported as unavailable rather than
    silently treating the whole video as match play.
    """

    ordered = sorted(samples, key=lambda sample: sample[0])
    if fps <= 0 or processed_frames <= 0 or len(ordered) < 3:
        return ActivePlaySummary((), 0, 0.0, "unavailable")

    maximum_gap = max(1, round(fps * 0.5))
    evidence_frames: list[int] = []
    previous_speed = 0.0
    previous_speed_frame = ordered[0][0]
    for previous, current in zip(ordered, ordered[1:]):
        frame_gap = current[0] - previous[0]
        if frame_gap <= 0 or frame_gap > maximum_gap:
            previous_speed = 0.0
            previous_speed_frame = current[0]
            continue
        seconds = frame_gap / fps
        speed = hypot(current[1] - previous[1], current[2] - previous[2]) / seconds
        speed_seconds = max((current[0] - previous_speed_frame) / fps, 1.0 / fps)
        acceleration = abs(speed - previous_speed) / speed_seconds
        if speed >= movement_speed_mps or (
            speed >= movement_speed_mps * 0.45 and acceleration >= acceleration_mps2
        ):
            evidence_frames.append(current[0])
        previous_speed = speed
        previous_speed_frame = current[0]

    if not evidence_frames:
        return ActivePlaySummary((), 0, 0.0, "unavailable")

    bridge = max(1, round(bridge_seconds * fps))
    lead = max(0, round(lead_seconds * fps))
    trail = max(0, round(trail_seconds * fps))
    minimum = max(1, round(minimum_interval_seconds * fps))
    groups: list[list[int]] = [[evidence_frames[0]]]
    for frame in evidence_frames[1:]:
        if frame - groups[-1][-1] <= bridge:
            groups[-1].append(frame)
        else:
            groups.append([frame])

    intervals: list[ActivePlayInterval] = []
    minimum_evidence = max(3, round(fps * 0.25))
    for group in groups:
        start = max(0, group[0] - lead)
        end = min(processed_frames - 1, group[-1] + trail)
        if len(group) < minimum_evidence or end - start + 1 < minimum:
            continue
        interval = ActivePlayInterval(start, end)
        if intervals and interval.start_frame <= intervals[-1].end_frame + 1:
            previous = intervals.pop()
            intervals.append(
                ActivePlayInterval(previous.start_frame, max(previous.end_frame, interval.end_frame))
            )
        else:
            intervals.append(interval)

    if not intervals:
        return ActivePlaySummary((), 0, 0.0, "unavailable")

    active_frames = sum(interval.frame_count for interval in intervals)
    evidence_density = min(1.0, len(evidence_frames) / max(1, active_frames * 0.35))
    sample_coverage = min(1.0, len(ordered) / max(1, active_frames))
    confidence = 0.6 * evidence_density + 0.4 * sample_coverage
    status = "accepted" if confidence >= 0.55 else "limited"
    return ActivePlaySummary(tuple(intervals), active_frames, confidence, status)


def samples_in_intervals(
    samples: Sequence[TrajectorySample] | Iterable[TrajectorySample],
    intervals: Sequence[ActivePlayInterval],
) -> list[TrajectorySample]:
    """Keep trajectory samples inside the detected play intervals."""

    if not intervals:
        return []
    return [
        sample
        for sample in samples
        if any(interval.start_frame <= sample[0] <= interval.end_frame for interval in intervals)
    ]
