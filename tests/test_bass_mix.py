import unittest
import numpy as np
from bass_mix import bass_mix_pitch_scores, confident_pitch_segments


class MixedBassTests(unittest.TestCase):
    def test_cqt_fundamental_not_overwhelmed_by_upper_harmonic(self):
        spec = np.zeros((48, 20), dtype=np.float32)
        spec[4] = 9.0   # E1 fundamental
        spec[16] = 3.0  # E2 harmonic
        spec[31] = 2.0  # G3 guitar
        scores = bass_mix_pitch_scores(spec)
        self.assertEqual(int(np.argmax(scores[:, 6])), 4)

    def test_stable_note_is_one_block(self):
        scores = np.zeros((12, 60), dtype=np.float32)
        scores[5] = 1.0
        self.assertEqual(confident_pitch_segments(scores, .025), [(0.0, 'F')])

    def test_very_short_wobble_does_not_invent_note(self):
        scores = np.zeros((12, 64), dtype=np.float32)
        scores[5] = 1.0
        scores[6, 20:23] = 1.3
        scores[5, 20:23] = 0.2
        result = confident_pitch_segments(scores, .025)
        self.assertEqual(result, [(0.0, 'F')])

    def test_held_real_change_is_preserved(self):
        scores = np.zeros((12, 64), dtype=np.float32)
        scores[5, :28] = 1.0
        scores[9, 28:] = 1.0
        result = confident_pitch_segments(scores, .025)
        self.assertEqual([name for _, name in result], ['F', 'A'])

    def test_uncertain_frames_do_not_create_new_pitch(self):
        scores = np.ones((12, 64), dtype=np.float32)
        self.assertEqual(confident_pitch_segments(scores, .025), [])


if __name__ == '__main__':
    unittest.main()
