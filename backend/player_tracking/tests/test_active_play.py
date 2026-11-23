from hpt_tracking.active_play import detect_active_play, samples_in_intervals


def test_idle_sections_are_excluded_from_active_play_denominator():
    fps = 10
    samples = []
    x = 0.0
    for frame in range(300):
        if 80 <= frame < 130 or 190 <= frame < 240:
            x += 0.12
        samples.append((frame, x, 5.0))

    summary = detect_active_play(samples, fps, 300)

    assert summary.status == "accepted"
    assert len(summary.intervals) == 2
    assert 100 < summary.active_frames < 220
    assert summary.active_frames < 300
    assert len(samples_in_intervals(samples, summary.intervals)) == summary.active_frames


def test_stationary_video_does_not_claim_active_play():
    samples = [(frame, 3.0, 5.0) for frame in range(180)]

    summary = detect_active_play(samples, 30, 180)

    assert summary.status == "unavailable"
    assert summary.active_frames == 0
    assert summary.intervals == ()


def test_short_noise_burst_is_not_reported_as_a_rally():
    samples = [(frame, (1.0 if frame == 50 else 0.0), 5.0) for frame in range(120)]

    summary = detect_active_play(samples, 30, 120)

    assert summary.status == "unavailable"
