"""Synthetic bass-root regression suite: known notes, independent of Chordify.

Run: python -m unittest discover -s tests -p 'test_bass_root_regression.py'
These are controlled bass recordings, NOT tests on commercial recordings.
"""
import tempfile
import unittest
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from ai_worker import bass_notes, NOTES


class BassRootRegression(unittest.TestCase):
    RATE = 11025

    @staticmethod
    def synth(notes, durations, harmonic_mode="normal"):
        parts = []
        for midi, duration in zip(notes, durations):
            count = int(duration * BassRootRegression.RATE)
            t = np.arange(count) / BassRootRegression.RATE
            fundamental = librosa.midi_to_hz(midi)
            audio = np.zeros(count, dtype=np.float64)
            for harmonic in range(1, 7):
                if harmonic_mode == "second_strong":
                    gain = 1.0 if harmonic == 2 else (.35 if harmonic == 1 else .10)
                else:
                    gain = 1.0 / harmonic
                audio += gain * np.sin(2 * np.pi * fundamental * harmonic * t)
            envelope = np.minimum(1, t / .03) * np.maximum(.3, 1 - t / duration * .3)
            parts.append((audio * envelope).astype(np.float32))
        audio = np.concatenate(parts)
        audio /= max(1.0, float(np.max(np.abs(audio))))
        return audio

    def assert_roots(self, notes, durations, mode="normal"):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "bass.wav"
            sf.write(file, self.synth(notes, durations, mode), self.RATE)
            detected = bass_notes(str(file), "balanced")
        roots = [note for _, note in detected]
        # Repeated plucks are deliberately expected to remain a single root.
        expected = []
        for midi in notes:
            name = NOTES[midi % 12]
            if not expected or expected[-1] != name:
                expected.append(name)
        self.assertEqual(roots, expected, f"Detected timeline: {detected}")
        return detected

    def test_spectral_support_keeps_original_notes_and_valid_intervals(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bass.wav"
            sf.write(path, self.synth([40, 41, 40], [.80, .22, .80]), self.RATE)
            plain = bass_notes(str(path), "balanced")
            annotated = bass_notes(str(path), "balanced", with_confidence=True)
        self.assertEqual(annotated["notes"], plain)
        self.assertEqual(len(annotated["confidence"]), len(plain))
        for (start, note), (begin, end, support) in zip(plain, annotated["confidence"]):
            self.assertAlmostEqual(start, begin, places=3)
            self.assertGreater(end, begin)
            self.assertGreaterEqual(support, 0.0)
            self.assertLessEqual(support, 1.0)

    def test_short_one_fret_step(self):
        self.assert_roots([40, 41, 40], [.80, .22, .80])

    def test_beat_length_one_fret_step(self):
        self.assert_roots([40, 41, 40], [.80, .36, .80])

    def test_repeated_same_note_plucks(self):
        self.assert_roots([40] * 8, [.20] * 8)

    def test_fast_chromatic_riff(self):
        self.assert_roots([40, 41, 42, 43], [.23] * 4)

    def test_strong_second_harmonic(self):
        self.assert_roots([40, 41, 40], [.70, .35, .70], "second_strong")

    def test_slow_four_root_progression(self):
        self.assert_roots([40, 45, 42, 47], [.75] * 4)

    def test_six_step_chromatic_walk(self):
        self.assert_roots([40, 41, 42, 43, 44, 45], [.27] * 6)


if __name__ == "__main__":
    unittest.main()
