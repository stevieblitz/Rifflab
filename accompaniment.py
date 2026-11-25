"""Beat-aware accompaniment overview built from existing note estimates.

Raw pitch events remain untouched. The overview chooses the prevailing note
over musical windows rather than rendering every momentary pitch hypothesis.
Pure Python so it can be regression-tested without Qt, NumPy or audio models.
"""
from bisect import bisect_right
from collections import defaultdict
import math


def _beat_boundaries(beat_times, duration, bpm):
    length = max(0.0, float(duration))
    if length == 0:
        return []
    try:
        observed = sorted({float(t) for t in (beat_times or [])
                           if math.isfinite(float(t)) and 0 <= float(t) < length})
    except (TypeError, ValueError):
        observed = []
    # A poor beat estimate must not make the accompaniment view unusable.
    if len(observed) > 2:
        intervals = [b-a for a, b in zip(observed, observed[1:]) if b-a > 0.08]
        if intervals:
            ordered = sorted(intervals)
            middle = ordered[len(ordered)//2]
            if 0.24 <= middle <= 1.50:
                edges = [0.0] if observed[0] > 0.08 else []
                edges.extend(observed)
                if edges[-1] < length:
                    edges.append(length)
                return edges
    period = 60.0 / max(40.0, min(240.0, float(bpm or 120.0)))
    count = int(math.ceil(length / period))
    return [min(length, i * period) for i in range(count + 1)]


def simplify_for_accompaniment(events, beat_times=None, bpm=120, duration=None,
                               complexity=35):
    """Choose prevailing pitch per musical window for a clear play-along basis.

    Complexity 0: four beats per block; 1..49: two beats; 50..84: one
    beat; >=85: original detailed events. No new pitch labels are invented.
    """
    events = sorted((max(0., float(t)), str(note)) for t, note in events)
    if not events:
        return []
    level = max(0, min(100, int(complexity)))
    if level >= 85:
        return events
    length = (max(events[-1][0] + 2.0, float(duration))
              if duration is not None and float(duration) > 0
              else events[-1][0] + 2.0)
    boundaries = _beat_boundaries(beat_times, length, bpm)
    if len(boundaries) < 2:
        return events
    block_beats = 4 if level <= 15 else 2 if level < 50 else 1
    times = [t for t, _ in events]
    blocks = []
    for start_index in range(0, len(boundaries)-1, block_beats):
        left = boundaries[start_index]
        right = boundaries[min(len(boundaries)-1, start_index + block_beats)]
        if right - left < 0.05:
            continue
        candidate_index = bisect_right(times, left) - 1
        current = events[candidate_index][1] if candidate_index >= 0 else None
        cursor = left
        k = candidate_index + 1
        totals = defaultdict(float)
        while k < len(events) and events[k][0] < right:
            change_time, label = events[k]
            if current is not None and change_time > cursor:
                totals[current] += change_time - cursor
            current = label
            cursor = max(cursor, change_time)
            k += 1
        if current is not None:
            totals[current] += max(0., right - cursor)
        totals.pop('—', None)
        totals.pop('', None)
        if not totals:
            chosen = blocks[-1][1] if blocks else '—'
        else:
            # A transitory alternative must own enough of the musical window
            # to displace an established root.
            chosen, weight = max(totals.items(), key=lambda kv: kv[1])
            previous = blocks[-1][1] if blocks else None
            if previous in totals and totals[previous] >= weight * 0.78:
                chosen = previous
            elif weight < (right-left) * 0.35 and previous:
                chosen = previous
        blocks.append((left, chosen))
    if not blocks:
        return events
    # Remove isolated one-window A-B-A excursions only in simplified modes.
    # This specifically collapses stray passing tones into a usable backing.
    if level < 50:
        names = [name for _, name in blocks]
        original = names[:]
        for i in range(1, len(names)-1):
            if original[i-1] == original[i+1] != original[i]:
                names[i] = original[i-1]
        blocks = [(t, name) for (t, _), name in zip(blocks, names)]
    result = []
    for t, name in blocks:
        if not result or name != result[-1][1]:
            result.append((round(t, 3), name))
    return result
