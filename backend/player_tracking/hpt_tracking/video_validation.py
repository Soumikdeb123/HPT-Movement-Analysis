"""Read video metadata and check that OpenCV can decode an upload.

The file extension is only an initial UI/API filter. A file named ``.mp4``
can still be corrupt, or it can contain a codec unavailable on this computer.
This module therefore opens the saved upload and decodes sample frames before
the expensive player-tracking job is allowed to start.
"""

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Dict, Protocol, Tuple

import cv2


CODEC_NAMES = {
    "avc1": "H.264 (AVC)",
    "h264": "H.264 (AVC)",
    "x264": "H.264 (AVC)",
    "hvc1": "HEVC (H.265)",
    "hev1": "HEVC (H.265)",
    "hevc": "HEVC (H.265)",
    "mp4v": "MPEG-4 Part 2",
    "mjpg": "Motion JPEG",
    "vp80": "VP8",
    "vp90": "VP9",
    "av01": "AV1",
}


class VideoValidationError(ValueError):
    """Raised when an uploaded file cannot safely enter the analysis queue."""


@dataclass(frozen=True)
class VideoMetadata:
    """Technical facts measured from the uploaded file, not user input."""

    original_filename: str
    extension: str
    size_bytes: int
    codec_tag: str
    codec_name: str
    width_pixels: int
    height_pixels: int
    frames_per_second: float
    frame_count: int
    duration_seconds: float
    decoded_sample_frames: int
    requested_sample_frames: int
    compatibility_status: str
    warnings: Tuple[str, ...]

    def to_dict(self) -> Dict:
        """Return the camelCase representation used by the Flutter API."""

        return {
            "originalFilename": self.original_filename,
            "extension": self.extension,
            "sizeBytes": self.size_bytes,
            "codecTag": self.codec_tag,
            "codecName": self.codec_name,
            "widthPixels": self.width_pixels,
            "heightPixels": self.height_pixels,
            "framesPerSecond": self.frames_per_second,
            "frameCount": self.frame_count,
            "durationSeconds": self.duration_seconds,
            "decodedSampleFrames": self.decoded_sample_frames,
            "requestedSampleFrames": self.requested_sample_frames,
            "compatibilityStatus": self.compatibility_status,
            "warnings": list(self.warnings),
        }


class VideoProbe(Protocol):
    """Interface used by the API so validation can be replaced in tests."""

    def probe(self, video_path: Path, original_filename: str) -> VideoMetadata:
        """Inspect one saved upload or raise ``VideoValidationError``."""


class OpenCvVideoProbe:
    """Inspect metadata and decode a few frames with the production decoder."""

    _SAMPLE_FRACTIONS = (0.0, 0.5, 0.9)

    def probe(self, video_path: Path, original_filename: str) -> VideoMetadata:
        capture = cv2.VideoCapture(str(video_path))
        try:
            if not capture.isOpened():
                raise VideoValidationError(
                    "The file has an allowed extension, but the local service "
                    "could not open it as a video."
                )

            width = _positive_integer(
                capture.get(cv2.CAP_PROP_FRAME_WIDTH), "frame width"
            )
            height = _positive_integer(
                capture.get(cv2.CAP_PROP_FRAME_HEIGHT), "frame height"
            )
            fps = _positive_number(capture.get(cv2.CAP_PROP_FPS), "frame rate")
            frame_count = _positive_integer(
                capture.get(cv2.CAP_PROP_FRAME_COUNT), "frame count"
            )

            sample_positions = _sample_positions(frame_count)
            decoded_samples = 0
            failed_positions = []
            for position in sample_positions:
                capture.set(cv2.CAP_PROP_POS_FRAMES, position)
                decoded, frame = capture.read()
                if decoded and frame is not None and frame.size > 0:
                    decoded_samples += 1
                else:
                    failed_positions.append(position)

            # The first frame is required because the tracking engine starts
            # reading at the beginning. Later seek failures are warnings: some
            # valid codecs support sequential decoding but imprecise seeking.
            if 0 in failed_positions:
                raise VideoValidationError(
                    "The video opened, but its first frame could not be decoded."
                )

            warnings = []
            if failed_positions:
                warnings.append(
                    f"{len(failed_positions)} of {len(sample_positions)} sampled "
                    "frames could not be decoded."
                )

            codec_tag = decode_fourcc(int(capture.get(cv2.CAP_PROP_FOURCC)))
            codec_name = friendly_codec_name(codec_tag)
            if codec_tag == "unknown":
                warnings.append("The video codec could not be identified.")

            return VideoMetadata(
                original_filename=original_filename,
                extension=video_path.suffix.lower(),
                size_bytes=video_path.stat().st_size,
                codec_tag=codec_tag,
                codec_name=codec_name,
                width_pixels=width,
                height_pixels=height,
                frames_per_second=round(fps, 3),
                frame_count=frame_count,
                duration_seconds=round(frame_count / fps, 3),
                decoded_sample_frames=decoded_samples,
                requested_sample_frames=len(sample_positions),
                compatibility_status=(
                    "compatible_with_warnings" if warnings else "compatible"
                ),
                warnings=tuple(warnings),
            )
        finally:
            # VideoCapture owns a native file handle. Releasing it also lets
            # the API delete rejected uploads immediately on Windows.
            capture.release()


def decode_fourcc(value: int) -> str:
    """Convert OpenCV's packed integer codec value into a readable tag."""

    characters = []
    for index in range(4):
        byte = (value >> (8 * index)) & 0xFF
        if 32 <= byte <= 126:
            characters.append(chr(byte))
    tag = "".join(characters).strip().lower()
    return tag or "unknown"


def friendly_codec_name(codec_tag: str) -> str:
    """Map common codec tags while preserving unknown values honestly."""

    normalised_tag = codec_tag.lower()
    if normalised_tag == "unknown":
        return "Unknown codec"
    return CODEC_NAMES.get(normalised_tag, f"Unknown codec ({codec_tag})")


def _positive_number(value: float, label: str) -> float:
    """Reject missing metadata required by distance-over-time calculations."""

    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise VideoValidationError(f"The video does not report a valid {label}.")
    return number


def _positive_integer(value: float, label: str) -> int:
    return int(round(_positive_number(value, label)))


def _sample_positions(frame_count: int) -> Tuple[int, ...]:
    """Return unique start/middle/late frame indexes for short or long videos."""

    last_index = max(0, frame_count - 1)
    positions = {
        min(last_index, int(last_index * fraction))
        for fraction in OpenCvVideoProbe._SAMPLE_FRACTIONS
    }
    return tuple(sorted(positions))
