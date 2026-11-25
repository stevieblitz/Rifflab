"""Accompaniment display: prioritize main notes over passing tones."""
import unittest
from accompaniment import simplify_for_accompaniment


class AccompanimentTests(unittest.TestCase):
    def test_static_god_style_passing_tones_suppressed(self):
        events = [(0, 'F'), (.13, 'A'), (.31, 'F'), (.43, 'G'),
                  (.64, 'F'), (1.0, 'F'), (1.2, 'D#'), (1.34, 'F'),
                  (1.66, 'F'), (1.75, 'G'), (1.92, 'F'),
                  (2.06, 'F'), (2.17, 'D#'), (2.28, 'F')]
        result = simplify_for_accompaniment(events, bpm=120, duration=3.0, complexity=35)
        self.assertEqual([label for _, label in result], ['F'])

    def test_real_sustained_changes_survive(self):
        events = [(0, 'F'), (2, 'A'), (4, 'C'), (6, 'F')]
        result = simplify_for_accompaniment(events, bpm=120, duration=8, complexity=35)
        self.assertEqual([label for _, label in result], ['F', 'A', 'C', 'F'])

    def test_short_but_strong_full_window_change_kept(self):
        events = [(0, 'F'), (2, 'A'), (3, 'F')]
        result = simplify_for_accompaniment(events, bpm=120, duration=5, complexity=35)
        self.assertEqual([label for _, label in result], ['F', 'A', 'F'])

    def test_max_detail_retains_raw_notes(self):
        events = [(0, 'F'), (.13, 'A'), (.31, 'F')]
        self.assertEqual(simplify_for_accompaniment(
            events, bpm=120, duration=2, complexity=100),
            [(0, 'F'), (.13, 'A'), (.31, 'F')])

    def test_returns_only_observed_pitch_classes(self):
        events = [(0, 'F'), (.2, 'F#'), (.3, 'F'),
                  (2, 'A'), (4, 'B')]
        result = simplify_for_accompaniment(events, bpm=120, duration=6)
        self.assertTrue(set(label for _, label in result) <= {'F','F#','A','B','—'})

    def test_concert_long_without_exploding_grid(self):
        events = [(0, 'F'), (900, 'A'), (4000, 'D')]
        result = simplify_for_accompaniment(
            events, bpm=120, duration=5400, complexity=35)
        self.assertEqual([label for _, label in result], ['F', 'A', 'D'])


if __name__ == '__main__':
    unittest.main()
