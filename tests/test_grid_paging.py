import unittest
from grid_paging import visible_beat_window


class GridPagingTests(unittest.TestCase):
    def test_short_song(self):
        self.assertEqual(visible_beat_window(100, 50), (0, 100))

    def test_concert_second_page(self):
        self.assertEqual(visible_beat_window(12400, 812), (800, 800))

    def test_partial_last_page(self):
        self.assertEqual(visible_beat_window(1650, 1649), (1600, 50))

    def test_end_position_clamped(self):
        self.assertEqual(visible_beat_window(1600, 1600), (800, 800))

    def test_first_unanalyzed_page(self):
        self.assertEqual(visible_beat_window(16, 9000), (0, 16))


if __name__ == '__main__':
    unittest.main()
