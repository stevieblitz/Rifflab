"""Low-register fundamental evidence for bass notes in a full-band mix.

This model intentionally does not claim to transcribe arbitrary polyphony.
It reduces guitar/overtone leakage by evaluating individual bass fundamental
candidates, rather than summing every octave into one pitch class.
"""
import numpy as np


def bass_mix_pitch_scores(magnitude, first_midi=24):
    """Return (12, frames) scores from a semitone-resolution magnitude CQT.

    Candidate fundamentals span MIDI 28..55 (E1..G3), with low E or Drop D
    present. An octave/harmonic is a weak corroborator, not independent proof.
    """
    spectrum = np.maximum(np.asarray(magnitude, dtype=np.float32), 0)
    if spectrum.ndim != 2 or spectrum.shape[0] < 32:
        raise ValueError('Expected a CQT with at least 32 semitone bins')
    n_bins, n_frames = spectrum.shape
    # Compression reduces dominance of an isolated drum or distorted harmonic.
    spectrum = np.sqrt(spectrum)
    result = np.zeros((12, n_frames), dtype=np.float32)
    # At low frequencies a bass fundamental can be weaker than its octave.
    # Fundamental evidence remains necessary; pure upper harmonic energy
    # never creates an unrelated bass root on its own.
    for index in range(2, min(32, n_bins)):
        fundamental = spectrum[index]
        octave = spectrum[index + 12] if index + 12 < n_bins else 0
        third_harmonic = spectrum[index + 19] if index + 19 < n_bins else 0
        strength = fundamental * (1.0 + 0.18 * np.minimum(
            octave / np.maximum(fundamental, 1e-5), 2.0) +
            0.08 * np.minimum(third_harmonic / np.maximum(fundamental, 1e-5), 2.0))
        pitch = (first_midi + index) % 12
        np.maximum(result[pitch], strength, out=result[pitch])
    return result


def confident_pitch_segments(scores, frame_hop_seconds, min_stable_seconds=0.14,
                             separation_ratio=1.08):
    """Convert pitch evidence to conservative events, allowing silent gaps.

    Do not mark every uncertain frame as a new note. Confirm switches using
    a short run of consistent evidence; preserve sufficiently supported short
    transitions instead of applying a blanket minimum note duration.
    """
    signal = np.asarray(scores, dtype=np.float32)
    if signal.ndim != 2 or signal.shape[0] != 12:
        raise ValueError('Scores must have 12 pitch classes')
    if signal.shape[1] == 0:
        return []
    best = np.argmax(signal, axis=0)
    top = np.max(signal, axis=0)
    second = np.partition(signal, -2, axis=0)[-2]
    confidence = (top + 1e-8) / (second + 1e-8)
    active_floor = max(1e-5, float(np.percentile(top, 85)) * 0.16)
    viable = (top >= active_floor) & (confidence >= separation_ratio)
    minimum_frames = max(2, int(round(min_stable_seconds / frame_hop_seconds)))
    result = []
    current = None
    pending = None
    pending_start = 0
    for frame in range(signal.shape[1]):
        name = int(best[frame]) if viable[frame] else None
        if name == current:
            pending = None
            continue
        if name != pending:
            pending = name
            pending_start = frame
            continue
        if frame - pending_start + 1 < minimum_frames:
            continue
        current = name
        pending = None
        label = '—' if name is None else (
            'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')[name]
        result.append((round(float(pending_start * frame_hop_seconds), 3), label))
    return result
