"""Regression checks for pattern-aware chord analysis."""
import unittest
import numpy as np
from ai_worker import _reinforce_repeated_harmony


class PatternConsensusTests(unittest.TestCase):
    def test_repeated_phrase_reinforces_matching_musical_pattern(self):
        rng = np.random.default_rng(71)
        count = 180
        chroma = np.zeros((12, count), dtype=float)
        for start in (10, 100):
            for offset in range(36):
                chord = 0 if offset < 18 else 7
                chroma[chord, start + offset] = 1
                chroma[(chord + 4) % 12, start + offset] = 0.5
        chroma += rng.normal(0, 0.005, chroma.shape)
        chroma = np.maximum(chroma, 0)
        emission = np.full((count, 2), 0.2)
        emission[10:28, 0] = 0.9
        emission[28:46, 1] = 0.9
        emission[100:118, 0] = 0.9
        emission[118:136, 1] = 0.9
        # One noisy beat in second iteration: source likelihood must
        # become more consistent because the underlying riff repeats.
        emission[107:110, 0] = 0.3
        result = _reinforce_repeated_harmony(chroma, emission, 0.1)
        self.assertEqual(result.shape, emission.shape)
        self.assertGreaterEqual(result[108, 0], emission[108, 0])

    def test_short_track_is_left_unchanged(self):
        x = np.ones((12, 20))
        scores = np.arange(40, dtype=float).reshape(20, 2)
        np.testing.assert_array_equal(
            _reinforce_repeated_harmony(x, scores, 0.1), scores
        )


if __name__ == '__main__':
    unittest.main()
