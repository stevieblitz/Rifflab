"""Pure, bounded note-grid paging for long recordings."""


def visible_beat_window(total_beats, playhead_beat, page_size=800):
    if page_size <= 0:
        raise ValueError('page_size must be positive')
    total = max(1, int(total_beats))
    playhead = max(0, min(total - 1, int(playhead_beat)))
    start = (playhead // page_size) * page_size
    return start, min(page_size, total - start)
