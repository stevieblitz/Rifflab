import unittest

from note_stability import decode_chord_scores, stabilize_events


class StableNotesTests(unittest.TestCase):
    def test_one_frame_chord_flicker_keeps_surrounding_chord(self):
        # The alternate chord is only marginally favored for one frame.
        scores = [[1., 0.]] * 8 + [[0.49, 0.51]] + [[1., 0.]] * 8
        states = decode_chord_scores(scores)
        self.assertEqual(set(states), {0})

    def test_supported_brief_note_not_erased(self):
        # A powerful two-frame change should survive smoothing.
        scores = [[1., 0.]] * 8 + [[0., 1.2]] * 2 + [[1., 0.]] * 8
        states = decode_chord_scores(scores)
        self.assertIn(1, states[8:10])

    def test_sustained_change_is_detected(self):
        scores = [[1., 0.]] * 8 + [[0., 1.]] * 8
        states = decode_chord_scores(scores)
        self.assertEqual(states[0], 0)
        self.assertEqual(states[-1], 1)

    def test_quick_legitimate_run_not_deleted(self):
        events = [(0., 'A'), (.20, 'B'), (.36, 'C'), (.56, 'D')]
        self.assertEqual(stabilize_events(events), events)

    def test_short_aba_flicker_removed(self):
        events = [(0., 'A'), (.2, 'B'), (.28, 'A'), (.5, 'C')]
        self.assertEqual(stabilize_events(events), [(0., 'A'), (.5, 'C')])

    def test_empty_and_single(self):
        self.assertEqual(stabilize_events([]), [])
        self.assertEqual(decode_chord_scores([]), [])
        self.assertEqual(decode_chord_scores([[.2,.8]]), [1])


if __name__ == '__main__':
    unittest.main()
