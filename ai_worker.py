"""RiffLab AI worker. Heavy dependencies only load inside this process."""
import json
import sys
from pathlib import Path

STEMS = ('drums', 'bass', 'other', 'vocals')
NOTES = ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')


def split(source, output):
    from demucs.separate import main
    main(['-n', 'htdemucs', '--device', 'cpu', '-o', output, source])


def chords(path, accuracy="balanced"):
    import librosa
    import numpy as np
    y, sr = librosa.load(path, sr=11025, mono=True)
    hop = {'fast': 4096, 'balanced': 2048, 'detailed': 1024}.get(accuracy, 2048)
    chroma = librosa.feature.chroma_stft(y=y, sr=sr, hop_length=hop)
    templates = []
    for base in ([1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0],
                 [1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0]):
        for shift in range(12):
            v = np.roll(np.array(base, dtype=float), shift)
            templates.append(v / np.linalg.norm(v))
    c = chroma / np.maximum(np.linalg.norm(chroma, axis=0), 1e-9)
    ids = np.argmax(np.stack(templates) @ c, axis=0)
    return [(round(float(i * hop / sr), 3), NOTES[int(k) % 12] + ('m' if k >= 12 else ''))
            for i, k in enumerate(ids)]



def chords_instruments(other_path, bass_path, accuracy="balanced"):
    """Change-aware harmony tracking. No vocal or drum audio enters the chord model.

    Bass is a soft root hint; chord quality comes from harmonic instrument chroma.
    A transition penalty prevents frame-by-frame flicker and an onset novelty curve
    allows switches where the harmonic content actually changes.
    """
    import librosa
    import numpy as np
    from scipy.ndimage import median_filter, gaussian_filter1d

    sr, hop = 11025, 512
    other, _ = librosa.load(other_path, sr=sr, mono=True)
    bass, _ = librosa.load(bass_path, sr=sr, mono=True)
    if len(other) < sr // 2 or len(bass) < sr // 2:
        return []
    # CQT resolves pitch classes more cleanly than STFT at low guitar frequencies.
    other_h = librosa.effects.harmonic(other, margin=2.0)
    chroma = librosa.feature.chroma_cqt(y=other_h, sr=sr, hop_length=hop)
    # Bass pitch classes, limited to the fundamental range to avoid upper harmonics.
    bass_cqt = np.abs(librosa.cqt(bass, sr=sr, hop_length=hop,
                                  fmin=librosa.note_to_hz('E1'), n_bins=48))
    bass_pc = np.zeros((12, bass_cqt.shape[1]))
    midi_start = int(round(librosa.hz_to_midi(librosa.note_to_hz('E1'))))
    for i in range(bass_cqt.shape[0]):
        bass_pc[(midi_start+i) % 12] += bass_cqt[i]
    n = min(chroma.shape[1], bass_pc.shape[1])
    if not n: return []
    # Short-time averaging suppresses vibrato and individual picked notes.
    h = gaussian_filter1d(np.maximum(chroma[:, :n], 0), 2.5, axis=1)
    b = gaussian_filter1d(np.maximum(bass_pc[:, :n], 0), 2.5, axis=1)
    h /= np.maximum(np.linalg.norm(h, axis=0, keepdims=True), 1e-7)
    b /= np.maximum(np.linalg.norm(b, axis=0, keepdims=True), 1e-7)
    templates = []
    names = []
    for quality, intervals in [('maj', (0,4,7)), ('min',(0,3,7)),
                               ('7',(0,4,7,10)), ('m7',(0,3,7,10)),
                               ('sus4',(0,5,7))]:
        for root in range(12):
            t = np.zeros(12)
            for interval in intervals: t[(root + interval) % 12] = 1
            t /= np.linalg.norm(t)
            templates.append(t)
            names.append(NOTES[root] + ('' if quality == 'maj' else 'm' if quality == 'min' else quality))
    templates = np.asarray(templates)
    scores = templates @ h
    for i in range(len(names)):
        scores[i] += 0.13 * b[i % 12]
    # Novelty of harmonic content: switches are cheaper at genuine changes.
    diff = np.linalg.norm(h[:, 1:] - h[:, :-1], axis=0)
    novelty = np.r_[0, gaussian_filter1d(diff, 3)]
    scale = np.percentile(novelty, 85) + 1e-7
    novelty = np.clip(novelty / scale, 0, 2)
    # Decode on ~0.14-second frames, not on every raw CQT frame.
    stride = {'fast': 5, 'balanced': 3, 'detailed': 2}.get(accuracy, 3)
    frames = np.arange(0, n, stride)
    emission = scores[:, frames].T
    change = novelty[frames]
    states = emission.shape[1]
    back = np.zeros((len(frames), states), dtype=np.int16)
    dp = emission[0].copy()
    for t in range(1, len(frames)):
        penalty = 0.24 / (1 + 2.2 * change[t])
        # Every previous chord must be compared against every next chord.
        # Shape (states, states), not (states, 1).
        transition = np.broadcast_to(dp[:, None] - penalty, (states, states)).copy()
        np.fill_diagonal(transition, dp)
        back[t] = np.argmax(transition, axis=0)
        dp = transition[back[t], np.arange(states)] + emission[t]
    decoded = np.empty(len(frames), dtype=np.int16)
    decoded[-1] = np.argmax(dp)
    for t in range(len(frames)-1, 0, -1):
        decoded[t-1] = back[t, decoded[t]]
    # Suppress brief spurious labels; keep genuine changes at their timestamps.
    decoded = median_filter(decoded, size={'fast': 7, 'balanced': 5, 'detailed': 3}.get(accuracy, 5), mode='nearest')
    output = []
    last = None
    for frame, state in zip(frames, decoded):
        name = names[int(state)]
        if name != last:
            output.append((round(float(frame * hop / sr), 3), name))
            last = name
    return output



def bass_notes(path, accuracy="balanced"):
    """Pitch-first bass transcription with continuity-aware decoding.

    Root changes are inferred from time-local spectral evidence rather than
    predetermined minimum durations. A legitimate one-fret transition can
    survive even when it returns to the previous note within a beat.
    """
    import librosa
    import numpy as np
    from scipy.ndimage import gaussian_filter1d

    sr = 11025
    hop = {"fast": 512, "balanced": 256, "detailed": 256}.get(accuracy, 256)
    y, _ = librosa.load(path, sr=sr, mono=True)
    if len(y) < sr // 2:
        return []
    # Start BELOW the open E so edge-bin spectral leakage does not bias
    # E toward D#. Extend through B4 to preserve near-octave-boundary changes.
    mag = np.abs(librosa.cqt(
        y, sr=sr, hop_length=hop, fmin=librosa.note_to_hz("C1"),
        n_bins=48, bins_per_octave=12))
    n = mag.shape[1]
    if not n:
        return []
    evidence = np.zeros((12, n), dtype=np.float32)
    for k in range(48):
        weight = (.75 if k < 12 else 1.0 if k < 24
                  else .80 if k < 36 else .15)
        evidence[k % 12] += mag[k] * weight
    sigma = max(1.0, .045 * sr / hop)
    evidence = gaussian_filter1d(evidence, sigma=sigma, axis=1)
    power = np.max(mag[:36], axis=0)
    audible = power > max(float(np.percentile(power, 30)) * .24, 1e-6)
    score = evidence / np.maximum(np.max(evidence, axis=0, keepdims=True), 1e-7)

    # A twelve-state Viterbi path. Switching incurs a small fixed cost,
    # *not* a minimum-note-length requirement. Short semitone changes can win
    # if supported by their audio frames. No post-hoc A-B-A deletion.
    stride = 2 if accuracy == "fast" else 1
    frames = np.arange(0, n, stride)
    emission = score[:, frames].T
    active = audible[frames]
    penalty = .14 if accuracy == "fast" else .09
    back = np.zeros((len(frames), 12), dtype=np.int8)
    dp = emission[0].copy()
    for t in range(1, len(frames)):
        if not active[t]:
            back[t] = np.arange(12)
            continue
        transitions = np.broadcast_to(dp[:, None] - penalty, (12, 12)).copy()
        np.fill_diagonal(transitions, dp)
        back[t] = np.argmax(transitions, axis=0)
        dp = transitions[back[t], np.arange(12)] + emission[t]
    decoded = np.zeros(len(frames), dtype=np.int8)
    decoded[-1] = np.argmax(dp)
    for t in range(len(frames) - 1, 0, -1):
        decoded[t - 1] = back[t, decoded[t]]

    changes, previous = [], None
    for frame, root in zip(frames, decoded):
        if not audible[frame]:
            continue
        note = NOTES[int(root)]
        if note != previous:
            changes.append((round(float(frame * hop / sr), 3), note))
            previous = note
    return changes


def pattern_assisted_notes(events, audio_path, accuracy="balanced"):
    """Conservatively recover missed pitch changes using repeated audio phrases.

    Compare the actual bass-stem chroma over repeated time windows, not labels
    alone. A candidate must be present in two matching phrases and supported
    by local audio; never overwrite an existing event.
    """
    import bisect
    import librosa
    import numpy as np

    if len(events) < 6:
        return events
    sr, hop = 11025, 1024
    y, _ = librosa.load(audio_path, sr=sr, mono=True)
    if len(y) < sr * 12:
        return events
    cqt = np.abs(librosa.cqt(y, sr=sr, hop_length=hop,
                             fmin=librosa.note_to_hz('E1'), n_bins=36))
    pc = np.zeros((12, cqt.shape[1]), dtype=np.float32)
    for k in range(36):
        pc[(k + 4) % 12] += cqt[k]
    pc /= np.maximum(np.max(pc, axis=0, keepdims=True), 1e-7)
    step = hop / sr
    names = [e[1] for e in events]
    times = [float(e[0]) for e in events]
    duration = min(len(y) / sr, pc.shape[1] * step)
    # Compare 4-8 second phrases on a 1s lattice. No guessed bar lengths.
    # Chroma comparison is transposition-sensitive: only same-pitch riffs match.
    phrase = 6.0
    stride = 1.0
    starts = np.arange(0, max(0, duration - phrase), stride)
    if len(starts) > 900:
        starts = starts[:900]
    # Low-resolution phrase descriptors retain pitch and approximate timing.
    descriptors = []
    for t in starts:
        chunks = []
        for j in range(12):
            a = int((t + j * phrase / 12) / step)
            b = max(a+1, int((t + (j+1) * phrase / 12) / step))
            chunks.append(np.mean(pc[:, a:b], axis=1))
        vec = np.asarray(chunks).ravel()
        vec /= max(float(np.linalg.norm(vec)), 1e-8)
        descriptors.append(vec)
    if not descriptors:
        return events
    descriptors = np.asarray(descriptors)
    proposals = {}
    for i, start in enumerate(starts):
        # Compare only distant occurrences, excluding overlapping windows.
        similarity = descriptors @ descriptors[i]
        similarity[np.abs(starts - start) < phrase + 0.5] = -1
        best = np.argsort(similarity)[-3:]
        matches = [int(j) for j in best if similarity[j] >= 0.89]
        if len(matches) < 2:
            continue
        # Gather matching onset offsets from other repetitions.
        candidates = {}
        for j in matches:
            match_start = float(starts[j])
            for local_time, note in events:
                offset = float(local_time) - match_start
                if 0.6 <= offset <= phrase - 0.6 and note in NOTES:
                    key = (round(offset / 0.25), note)
                    candidates.setdefault(key, set()).add(j)
        for (offset_bin, note), supporters in candidates.items():
            if len(supporters) < 2:
                continue
            target = float(start + offset_bin * 0.25)
            if any(abs(target - existing) < 0.38 for existing in times):
                continue
            frame = int(target / step)
            if frame < 2 or frame + 2 >= pc.shape[1]:
                continue
            pitch = NOTES.index(note)
            local = np.mean(pc[:, frame-2:frame+3], axis=1)
            # Verify candidate is audible here; don't invent silent notes.
            if local[pitch] < 0.58 or local[pitch] < np.max(local) * 0.85:
                continue
            proposals[round(target, 3)] = note
    if not proposals:
        return events
    result = list(events)
    for t, note in sorted(proposals.items()):
        if not any(abs(t - old_t) < 0.38 for old_t, _ in result):
            result.append((t, note))
    return sorted(result, key=lambda x: x[0])

def bass_context(bass_path, other_path, accuracy="balanced", drums_path=None):
    """Bass transcription is the authority for detected pitch transitions.

    Other-stem harmonic chord roots may fall back only when the bass detector
    returns no notes at all; beats/harmony must never veto a detected semitone.
    """
    primary = bass_notes(bass_path, accuracy)
    if primary:
        return primary
    harmony = chords_instruments(other_path, bass_path, accuracy)
    result = []
    for t, chord in harmony:
        root = chord_root(chord)
        if not result or root != result[-1][1]:
            result.append((t, root))
    return result


def chord_root(name):
    import re
    match = re.match(r'^[A-G](?:#|b)?', name)
    return match.group(0) if match else name


def beats(path):
    """Estimate beats using librosa; timestamps in seconds, BPM as scalar."""
    import librosa
    import numpy as np
    y, sr = librosa.load(path, sr=11025, mono=True)
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=256)
    tempo, frames = librosa.beat.beat_track(onset_envelope=onset, sr=sr, hop_length=256, trim=False, start_bpm=120)
    bpm = float(np.asarray(tempo).reshape(-1)[0])
    times = librosa.frames_to_time(frames, sr=sr, hop_length=256)
    return {'bpm': round(bpm, 2), 'beats': [round(float(t), 3) for t in times]}


def mix(output, paths_json, levels_json, transpose_str="0"):
    import numpy as np
    import soundfile as sf
    paths = json.loads(paths_json)
    levels = json.loads(levels_json)
    semitones = int(transpose_str)
    arrays = []
    sr = None
    for name in STEMS:
        gain = float(levels.get(name, 0))
        if gain <= 0:
            continue
        audio, rate = sf.read(paths[name], always_2d=True, dtype='float32')
        if sr is not None and rate != sr:
            raise RuntimeError('Stem sample rates differ')
        sr = rate
        arrays.append(audio * gain)
    if not arrays:
        audio, sr = sf.read(paths['bass'], always_2d=True, dtype='float32')
        result = np.zeros_like(audio)
    else:
        n = min(len(a) for a in arrays)
        channels = min(a.shape[1] for a in arrays)
        result = np.zeros((n, channels), dtype='float32')
        for a in arrays:
            result += a[:n, :channels]
        peak = float(np.max(np.abs(result))) if result.size else 0
        if peak > 0.98:
            result *= 0.98 / peak
    if semitones:
        import librosa
        # Pitch shift preserves duration and tempo, unlike changing playback speed.
        result = np.stack([librosa.effects.pitch_shift(result[:, ch], sr=sr, n_steps=semitones)
                           for ch in range(result.shape[1])], axis=1)
        peak = float(np.max(np.abs(result))) if result.size else 0
        if peak > 0.98:
            result *= 0.98 / peak
    sf.write(output, result, sr, subtype='PCM_16')


if __name__ == '__main__':
    try:
        task = sys.argv[1]
        if task == 'split':
            split(*sys.argv[2:])
        elif task == 'chords':
            print(json.dumps(chords(*sys.argv[2:])))
        elif task == 'chords_instruments':
            print(json.dumps(chords_instruments(*sys.argv[2:])))
        elif task == 'bass_notes':
            print(json.dumps(bass_notes(*sys.argv[2:])))
        elif task == 'bass_context':
            print(json.dumps(bass_context(*sys.argv[2:])))
        elif task == 'beats':
            print(json.dumps(beats(*sys.argv[2:])))
        elif task == 'mix':
            mix(*sys.argv[2:])
        else:
            raise ValueError('Unknown worker task')
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)

