"""Compare timestamped RiffLab chord predictions against a user-provided reference.

Reference CSV: time,chord (seconds or mm:ss[.sss]). Rows mark the START of a chord.
The reference must be provided by the user: no scraping or implied Chordify API.
"""
import csv
import json
from bisect import bisect_right
from pathlib import Path

def seconds(value):
    value = str(value).strip()
    if ':' in value:
        parts = value.split(':')
        if len(parts) == 2:
            return 60 * float(parts[0]) + float(parts[1])
        if len(parts) == 3:
            return 3600 * float(parts[0]) + 60 * float(parts[1]) + float(parts[2])
        raise ValueError('Time must be seconds, mm:ss or hh:mm:ss')
    return float(value)

def normalize(chord):
    chord = str(chord).strip().replace('♯', '#').replace('♭', 'b')
    if not chord or chord.upper() in ('N', 'NC', 'N.C.', 'UNKNOWN', '-'):
        return None
    import re
    match = re.match(r'^([A-Ga-g])([#b]?)(.*)$', chord)
    if not match:
        return None
    root, accidental, suffix = match.groups()
    root = root.upper() + accidental
    equivalents = {'Db':'C#', 'Eb':'D#', 'Gb':'F#', 'Ab':'G#', 'Bb':'A#',
                   'Cb':'B', 'Fb':'E', 'E#':'F', 'B#':'C'}
    root = equivalents.get(root, root)
    suffix = suffix.lower().replace('minor', 'm').replace('major', '')
    if suffix.startswith('maj'):
        quality = 'maj'
    elif suffix.startswith('min') or suffix.startswith('m') and not suffix.startswith('maj'):
        quality = 'min'
    elif suffix.startswith('sus'):
        quality = 'sus'
    elif suffix.startswith('dim'):
        quality = 'dim'
    elif suffix.startswith('aug'):
        quality = 'aug'
    else:
        quality = 'maj'
    return root, quality

def parse_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError('Reference CSV is empty')
        cols = {c.strip().lower(): c for c in reader.fieldnames}
        timecol = cols.get('time') or cols.get('timestamp') or cols.get('start')
        chordcol = cols.get('chord') or cols.get('akkoord')
        if not timecol or not chordcol:
            raise ValueError('Reference CSV needs headers time,chord')
        events = [(seconds(row[timecol]), row[chordcol].strip()) for row in reader
                  if row.get(timecol) and row.get(chordcol)]
    return validate(events)

def validate(events):
    events = sorted((float(t), str(chord)) for t, chord in events)
    if not events or events[0][0] < 0:
        raise ValueError('Need timestamped chords starting at or after zero')
    return events

def compare(predicted, reference, end_seconds=None, step=0.25):
    predicted, reference = validate(predicted), validate(reference)
    if end_seconds is None:
        end_seconds = max(predicted[-1][0], reference[-1][0]) + 4
    end_seconds = float(end_seconds)
    start = max(predicted[0][0], reference[0][0])
    if end_seconds <= start:
        raise ValueError('No time overlap')
    import math
    pt, rt = [x[0] for x in predicted], [x[0] for x in reference]
    comparable = exact = root_equal = 0
    disagreements = []
    for index in range(int(math.ceil((end_seconds - start) / step))):
        t = start + (index + 0.5) * step
        if t >= end_seconds:
            break
        p = normalize(predicted[bisect_right(pt, t) - 1][1])
        r = normalize(reference[bisect_right(rt, t) - 1][1])
        if r is None:
            continue
        comparable += 1
        if p == r:
            exact += 1
        else:
            if p is not None and p[0] == r[0]:
                root_equal += 1
            disagreements.append((round(t, 3),
                                  predicted[bisect_right(pt, t) - 1][1],
                                  reference[bisect_right(rt, t) - 1][1]))
    if not comparable:
        raise ValueError('Reference contains no comparable chords')
    # Merge contiguous mismatches of identical chord pairs into useful intervals.
    groups = []
    for time, found, expected in disagreements:
        if groups and groups[-1]['riffLab'] == found and groups[-1]['reference'] == expected and time - groups[-1]['last'] < step * 1.6:
            groups[-1]['last'] = time
        else:
            groups.append({'start': time, 'last': time,
                           'riffLab': found, 'reference': expected})
    for g in groups:
        g['end'] = round(min(end_seconds, g.pop('last') + step / 2), 3)
    return {'exact_percent': round(exact / comparable * 100, 1),
            'root_percent': round((exact + root_equal) / comparable * 100, 1),
            'compared_seconds': round(comparable * step, 2),
            'intervals': groups}

def save_report(path, report):
    with open(path, 'w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['start_seconds','end_seconds','RiffLab','reference'])
        for row in report['intervals']:
            writer.writerow([row['start'], row['end'], row['riffLab'], row['reference']])
