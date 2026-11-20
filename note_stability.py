"""Conservative, testable helpers for note-event display stability.

Only short A-B-A flickers are eliminated. Legitimate fast note changes
and runs with no matching neighbours survive; no beat quantisation.
"""


def stabilize_events(events, flicker_seconds=0.13):
    if not events:
        return []
    ordered = sorted((float(time), str(note)) for time, note in events)
    if len(ordered) < 3:
        return ordered
    output = [ordered[0]]
    for index in range(1, len(ordered) - 1):
        time, note = ordered[index]
        previous = output[-1][1]
        following = ordered[index + 1][1]
        duration = ordered[index + 1][0] - time
        if previous == following and note != previous and 0 <= duration < flicker_seconds:
            continue
        if note != previous:
            output.append((time, note))
    if ordered[-1][1] != output[-1][1]:
        output.append(ordered[-1])
    return output


def decode_chord_scores(scores, novelty=None, transition_penalty=0.22):
    """Viterbi for categorical chord states; scores is frames x states.

    A short unrelated frame must beat the persistence penalty in both
    directions; actual supported changes can still survive.
    """
    if not scores:
        return []
    states = len(scores[0])
    if not states or any(len(row) != states for row in scores):
        raise ValueError('Chord score matrix must be rectangular and non-empty.')
    if novelty is not None and len(novelty) != len(scores):
        raise ValueError('Novelty and score frame counts differ.')
    previous = [float(v) for v in scores[0]]
    back = [[i for i in range(states)]]
    for frame in range(1, len(scores)):
        row = [float(x) for x in scores[frame]]
        novelty_value = (max(0., min(1., float(novelty[frame])))
                         if novelty is not None else 0.)
        penalty = transition_penalty / (1. + 1.8 * novelty_value)
        best_origin = max(range(states), key=lambda k: previous[k])
        best_change = previous[best_origin] - penalty
        current = []
        parents = []
        for destination in range(states):
            if previous[destination] >= best_change:
                parents.append(destination)
                current.append(previous[destination] + row[destination])
            else:
                parents.append(best_origin)
                current.append(best_change + row[destination])
        previous = current
        back.append(parents)
    state = max(range(states), key=lambda k: previous[k])
    decoded = [state] * len(scores)
    for frame in range(len(scores) - 1, 0, -1):
        state = back[frame][state]
        decoded[frame - 1] = state
    return decoded
