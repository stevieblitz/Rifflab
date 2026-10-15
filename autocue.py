"""Autocue timeline geometry. Pure Python: no audio or AI dependencies."""
from bisect import bisect_right


def cue_window(events, position, seconds_ahead=12.0, seconds_behind=5.0, duration=None):
    """Return note intervals overlapping the cue viewport, preserving sustained notes."""
    if not events:
        return []
    ordered = sorted((float(t), str(note)) for t, note in events)
    left = max(0.0, position - seconds_behind)
    right = position + seconds_ahead
    output = []
    for i, (start, note) in enumerate(ordered):
        end = ordered[i + 1][0] if i + 1 < len(ordered) else (duration if duration is not None else right)
        if end > left and start < right:
            output.append((max(start, left), min(end, right), note, start <= position < end))
    return output


def cue_offset(position, pixels_per_second, anchor_ratio, viewport_width):
    """Pixel offset to keep the playback cursor at a fixed viewport anchor."""
    return max(0.0, position * pixels_per_second - viewport_width * anchor_ratio)
