"""Second-pass video annotations from the same calculated samples as the report.

Centred filters need future frames. Values are aligned to video time, not claimed
to be live-stream computations. Missing/trimmed samples are explicitly N/A.
"""
from math import isfinite
import cv2
import numpy as np


def frame_values(player, fps):
    metric = player.get('speed', {}).get('unit') == 'm/s'
    def indexed(samples):
        return {round(p['timeSeconds']*fps): float(p['value']) for p in samples
                if p.get('value') is not None and isfinite(p['value'])}
    return {
        'speed': indexed(player.get('speed', {}).get('samples', [])) if metric else {},
        'acceleration': indexed(player.get('acceleration', {}).get('samples', [])) if metric else {},
        'distance': indexed(player.get('totalDistance', {}).get('samples', []))
                    if player.get('totalDistance', {}).get('unit') == 'm' else {},
    }


def label_lines(track_id, values, frame_number):
    def fmt(value, unit):
        return f'{value:.2f} {unit}' if value is not None else 'N/A'
    a = values['acceleration'].get(frame_number)
    acceleration = max(0., a) if a is not None else None
    deceleration = max(0., -a) if a is not None else None
    return [
        f'ID {track_id} | Distance: {fmt(values["distance"].get(frame_number), "m")}',
        f'Speed: {fmt(values["speed"].get(frame_number), "m/s")}',
        f'Accel: {fmt(acceleration, "m/s^2")} | Decel: {fmt(deceleration, "m/s^2")}',
    ]


def draw_label(frame, bbox, lines, colour):
    left, top, right, bottom = map(int, bbox)
    height, width = frame.shape[:2]
    cv2.rectangle(frame, (left, top), (right, bottom), colour, 2)
    scale = min(.65, max(.38, width/1600))
    font = cv2.FONT_HERSHEY_SIMPLEX
    sizes = [cv2.getTextSize(line, font, scale, 1)[0] for line in lines]
    largest = max(w for w, _ in sizes)
    if largest > width-16:
        scale *= (width-16)/largest
        sizes = [cv2.getTextSize(line, font, scale, 1)[0] for line in lines]
    line_height = max(h for _, h in sizes)+9
    box_width = max(w for w, _ in sizes)+12
    box_height = line_height*len(lines)+6
    x = max(0, min(left, width-box_width))
    y = max(0, min(top-box_height-5, height-box_height))
    cv2.rectangle(frame, (x, y), (x+box_width, y+box_height), (20,20,20), -1)
    for i, line in enumerate(lines):
        cv2.putText(frame, line, (x+6, y+(i+1)*line_height-3), font,
                    scale, (255,255,255), 1, cv2.LINE_AA)


def render_video(input_path, output_path, tracks, players, calibration, fps,
                 width, height, total_frames, cancelled, progress, cancelled_error):
    capture = cv2.VideoCapture(str(input_path))
    writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))
    if not capture.isOpened() or not writer.isOpened():
        capture.release()
        writer.release()
        raise RuntimeError('Could not open the annotated video output.')
    values = {p['trackId']: frame_values(p, fps) for p in players}
    index = 0
    try:
        while True:
            if cancelled():
                raise cancelled_error('Analysis cancelled during video rendering.')
            ok, frame = capture.read()
            if not ok:
                break
            if calibration is not None:
                cv2.polylines(frame, [calibration.corners.astype(np.int32)], True, (20,220,255), 2)
            for track in tracks:
                bbox = track.bbox_history.get(index)
                if bbox is None:
                    continue  # No stale box/values while the athlete is absent.
                lines = label_lines(track.track_id, values[str(track.track_id)], index)
                draw_label(frame, bbox, lines, track.colour)
            writer.write(frame)
            index += 1
            if total_frames:
                progress(min(index/total_frames, 1.))
    finally:
        capture.release()
        writer.release()
    if total_frames and index != total_frames:
        raise RuntimeError('Video decoding ended early during annotation; please retry.')
