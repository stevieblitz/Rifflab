"""Short synthetic-audio regression checks (run after AI dependencies install).

These catch obvious regressions in detection speed/stability, not a guarantee
of accuracy on real mixes. No recording is downloaded or bundled.
"""
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from ai_worker import bass_notes, chords


RATE = 11025


def tone(frequencies, length):
    t = np.arange(int(length * RATE), dtype=np.float32) / RATE
    y = sum(np.sin(2 * np.pi * frequency * t) for frequency in frequencies)
    y = y / max(float(np.max(np.abs(y))), 1.0)
    fade = min(200, len(y) // 10)
    if fade:
        y[:fade] *= np.linspace(0, 1, fade)
        y[-fade:] *= np.linspace(1, 0, fade)
    return y.astype(np.float32)


class AudioRecognitionSmokeTests(unittest.TestCase):
    def write_audio(self, signal):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / 'test-audio.wav'
        sf.write(path, signal, RATE, subtype='PCM_16')
        return path

    def test_constant_chord_does_not_flicker_dozen_times(self):
        sound = tone([130.8128, 164.8138, 195.9977], 2.4)
        events = chords(str(self.write_audio(sound)), 'fast')
        self.assertGreaterEqual(len(events), 1)
        self.assertLessEqual(len(events), 5, events)

    def test_silence_is_not_mislabeled_as_a_chord(self):
        events = chords(str(self.write_audio(np.zeros(RATE * 2, dtype=np.float32))), 'fast')
        self.assertEqual([name for _, name in events], ['—'])

    def test_bass_pitch_stays_stable_then_changes(self):
        sound = np.concatenate([tone([82.4069], 0.7), tone([110.0], 0.7),
                                tone([98.0], 0.7)])
        events = bass_notes(str(self.write_audio(sound)), 'fast')
        labels = [note for _, note in events]
        self.assertGreaterEqual(len(set(labels)), 2, events)
        self.assertLessEqual(len(events), 12, events)


if __name__ == '__main__':
    unittest.main()
