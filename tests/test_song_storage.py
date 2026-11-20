import json
import tempfile
import unittest
from pathlib import Path

from song_storage import manifest_for_song, song_basename


class SongIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.details = {'artist': 'Osees', 'title': 'The Dream', 'source_id': 'YouTubeAAA'}

    def test_reimport_same_id_uses_same_manifest(self):
        target = manifest_for_song(self.folder, self.details, 'music/YouTubeAAA.wav', None, 'YouTubeAAA')
        self.assertEqual(target.name, 'Osees - The Dream.riff')
        target.write_text(json.dumps({'metadata': self.details, 'source_audio': 'music/YouTubeAAA.wav'}))
        again = manifest_for_song(self.folder, self.details, None, 'stems/YouTubeAAA', 'YouTubeAAA')
        self.assertEqual(target, again)

    def test_identical_song_titles_different_videos_do_not_overwrite(self):
        first = manifest_for_song(self.folder, self.details, '/audio/a.wav', None, 'a')
        first.write_text(json.dumps({'metadata': self.details, 'source_audio': '/audio/a.wav'}))
        other = dict(self.details, source_id='YouTubeBBB')
        second = manifest_for_song(self.folder, other, '/audio/b.wav', None, 'b')
        self.assertNotEqual(first, second)
        self.assertTrue(second.name.startswith('Osees - The Dream-'))

    def test_cannot_reuse_unknown_source_with_null_paths(self):
        original = self.folder / 'A Song.riff'
        original.write_text(json.dumps({'metadata': {}, 'source_audio': None, 'stem_folder': '/old/stems'}))
        selected = manifest_for_song(self.folder, {'title': 'A Song'}, None, '/new/stems', 'new')
        self.assertNotEqual(original, selected)

    def test_title_does_not_use_youtube_id_when_metadata_exists(self):
        self.assertEqual(song_basename(self.details, 'YouTubeAAA'), 'Osees - The Dream')


if __name__ == '__main__':
    unittest.main()
