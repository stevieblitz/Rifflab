import unittest
from smart_metadata import identify


class SmartMetadataTests(unittest.TestCase):
    def test_artist_title_and_version(self):
        result = identify({'title': 'THEE OH SEES - The Dream (LIVE 2017) [HD]', 'id': 'abc123'})
        self.assertEqual(result['artist'], 'Osees')
        self.assertEqual(result['title'], 'The Dream')
        self.assertIn('LIVE 2017', result['version'])
        self.assertEqual(result['original_title'], 'THEE OH SEES - The Dream (LIVE 2017) [HD]')

    def test_uploader_not_assumed_artist(self):
        result = identify({'title': 'Unknown improvisation', 'uploader': 'Random Archives'})
        self.assertEqual(result['artist'], '')
        self.assertEqual(result['metadata_confidence'], 'low')

    def test_explicit_artist_and_track_win(self):
        result = identify({'title': 'A noisy video', 'artist': 'Oh Sees', 'track': 'Tidal Wave'})
        self.assertEqual(result['artist'], 'Osees')
        self.assertEqual(result['title'], 'Tidal Wave')


if __name__ == '__main__':
    unittest.main()
