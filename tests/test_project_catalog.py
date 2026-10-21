"""Regression tests for non-destructive multi-song projects and playlists."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from project_catalog import (initialize, create_collection, list_collections,
                             add_song, list_songs, remove_song, delete_collection)


class ProjectCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / 'library.sqlite3'
        initialize(self.database)
        self.one = self.root / 'one.riff'
        self.two = self.root / 'two.riff'
        self.one.write_text('{"format":"RiffLab Project","version":1}', encoding='utf-8')
        self.two.write_text('{"format":"RiffLab Project","version":1}', encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def test_multiple_songs_and_reuse_in_playlist(self):
        project = create_collection(self.database, 'Osees practice', 'project')
        playlist = create_collection(self.database, 'Bass riffs', 'playlist')
        add_song(self.database, project, self.one)
        add_song(self.database, project, self.two)
        add_song(self.database, playlist, self.one)
        add_song(self.database, project, self.one)  # idempotent
        self.assertEqual(len(list_songs(self.database, project)), 2)
        self.assertEqual(len(list_songs(self.database, playlist)), 1)
        self.assertEqual(len(list_collections(self.database)), 2)

    def test_deletion_keeps_original_song_files(self):
        project = create_collection(self.database, 'Test', 'project')
        add_song(self.database, project, self.one)
        remove_song(self.database, project, self.one)
        self.assertTrue(self.one.exists())
        add_song(self.database, project, self.one)
        delete_collection(self.database, project)
        self.assertEqual(list_songs(self.database, project), [])
        self.assertTrue(self.one.exists())

    def test_missing_or_unsaved_items_rejected(self):
        project = create_collection(self.database, 'Practice', 'project')
        with self.assertRaises(ValueError):
            add_song(self.database, project, self.root / 'missing.riff')
        with self.assertRaises(ValueError):
            create_collection(self.database, ' ', 'playlist')


if __name__ == '__main__':
    unittest.main()
