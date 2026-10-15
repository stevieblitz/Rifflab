import unittest
from autocue import cue_window, cue_offset


class AutocueTests(unittest.TestCase):
    def test_sustain_across_viewport(self):
        result = cue_window([(0, "E"), (10, "B")], 8, seconds_ahead=5, seconds_behind=2)
        self.assertEqual(result, [(6, 10, "E", True), (10, 13, "B", False)])

    def test_no_artificial_repeated_note_at_window_boundary(self):
        result = cue_window([(0, "E"), (20, "A")], 15, seconds_ahead=8, seconds_behind=4)
        self.assertEqual(result, [(11, 20, "E", True), (20, 23, "A", False)])

    def test_fixed_playhead_offset(self):
        self.assertEqual(cue_offset(10, 100, .35, 1000), 650)
        self.assertEqual(cue_offset(1, 100, .35, 1000), 0)


if __name__ == "__main__":
    unittest.main()
