from pathlib import Path

import cv2
import numpy as np
import pytest

from hpt_tracking.video_validation import (
    OpenCvVideoProbe,
    VideoValidationError,
    decode_fourcc,
    friendly_codec_name,
)


def _write_test_video(path: Path) -> None:
    """Create a tiny real video without keeping binary fixtures in Git."""

    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10.0,
        (64, 48),
    )
    if not writer.isOpened():
        pytest.skip("This OpenCV build cannot create the MJPG test fixture.")
    try:
        for index in range(12):
            frame = np.full((48, 64, 3), index * 10, dtype=np.uint8)
            writer.write(frame)
    finally:
        writer.release()


def test_probe_reports_metadata_from_a_decodable_video(tmp_path):
    video_path = tmp_path / "training.avi"
    _write_test_video(video_path)

    metadata = OpenCvVideoProbe().probe(video_path, "training.avi")

    assert metadata.original_filename == "training.avi"
    assert metadata.extension == ".avi"
    assert metadata.size_bytes > 0
    assert metadata.codec_tag == "mjpg"
    assert metadata.codec_name == "Motion JPEG"
    assert metadata.width_pixels == 64
    assert metadata.height_pixels == 48
    assert metadata.frames_per_second == pytest.approx(10.0)
    assert metadata.frame_count == 12
    assert metadata.duration_seconds == pytest.approx(1.2)
    assert metadata.decoded_sample_frames == 3
    assert metadata.requested_sample_frames == 3
    assert metadata.compatibility_status == "compatible"
    assert metadata.warnings == ()


def test_probe_rejects_text_renamed_as_mp4(tmp_path):
    fake_video = tmp_path / "renamed.mp4"
    fake_video.write_text("This is text, not encoded video.", encoding="utf-8")

    with pytest.raises(VideoValidationError, match="could not open"):
        OpenCvVideoProbe().probe(fake_video, "renamed.mp4")


@pytest.mark.parametrize(
    ("tag", "expected_name"),
    [
        ("avc1", "H.264 / AVC"),
        ("hvc1", "HEVC / H.265"),
        ("hev1", "HEVC / H.265"),
        ("mp4v", "MPEG-4 Part 2"),
        ("zzzz", "Unknown codec (zzzz)"),
    ],
)
def test_friendly_codec_name_explains_known_and_unknown_tags(tag, expected_name):
    assert friendly_codec_name(tag) == expected_name


def test_decode_fourcc_unpacks_opencv_integer_format():
    packed_hvc1 = cv2.VideoWriter_fourcc(*"hvc1")

    assert decode_fourcc(packed_hvc1) == "hvc1"
    assert decode_fourcc(0) == "unknown"
