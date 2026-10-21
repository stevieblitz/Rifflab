"""Non-destructive project and playlist collections for RiffLab.

Existing .riff manifests remain per-song and are never moved or deleted.
Collections store only references, avoiding duplicate downloads or stems.
"""
import sqlite3
from contextlib import closing
from pathlib import Path


def initialize(db_path):
    with closing(sqlite3.connect(db_path)) as db, db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS collections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('project', 'playlist')),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS collection_songs (
                collection_id INTEGER NOT NULL REFERENCES collections(id),
                song_path TEXT NOT NULL,
                position INTEGER NOT NULL,
                PRIMARY KEY (collection_id, song_path)
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS collection_song_order ON collection_songs(collection_id, position)")


def create_collection(db_path, name, kind):
    name = str(name).strip()
    if not name or kind not in ('project', 'playlist'):
        raise ValueError('Enter a collection name and a valid type.')
    with closing(sqlite3.connect(db_path)) as db, db:
        cursor = db.execute("INSERT INTO collections(name, kind) VALUES (?, ?)", (name, kind))
        return cursor.lastrowid


def list_collections(db_path, kind=None):
    sql = 'SELECT id, name, kind FROM collections'
    values = ()
    if kind:
        sql += ' WHERE kind=?'
        values = (kind,)
    sql += ' ORDER BY name COLLATE NOCASE, id'
    with closing(sqlite3.connect(db_path)) as db, db:
        return db.execute(sql, values).fetchall()


def add_song(db_path, collection_id, song_path):
    path = Path(song_path).resolve()
    if not path.is_file() or path.suffix.lower() != '.riff':
        raise ValueError('Save the song as a .riff file before adding it.')
    with closing(sqlite3.connect(db_path)) as db, db:
        exists = db.execute('SELECT 1 FROM collections WHERE id=?', (collection_id,)).fetchone()
        if not exists:
            raise ValueError('Collection no longer exists.')
        next_pos = db.execute(
            'SELECT COALESCE(MAX(position), -1) + 1 FROM collection_songs WHERE collection_id=?',
            (collection_id,)).fetchone()[0]
        db.execute(
            'INSERT OR IGNORE INTO collection_songs(collection_id, song_path, position) VALUES (?, ?, ?)',
            (collection_id, str(path), next_pos))


def list_songs(db_path, collection_id):
    with closing(sqlite3.connect(db_path)) as db, db:
        return db.execute(
            'SELECT song_path FROM collection_songs WHERE collection_id=? ORDER BY position, song_path',
            (collection_id,)).fetchall()


def remove_song(db_path, collection_id, song_path):
    with closing(sqlite3.connect(db_path)) as db, db:
        db.execute('DELETE FROM collection_songs WHERE collection_id=? AND song_path=?',
                   (collection_id, str(Path(song_path).resolve())))


def delete_collection(db_path, collection_id):
    """Delete only collection records. Never delete audio or .riff files."""
    with closing(sqlite3.connect(db_path)) as db, db:
        db.execute('DELETE FROM collection_songs WHERE collection_id=?', (collection_id,))
        db.execute('DELETE FROM collections WHERE id=?', (collection_id,))


def export_project(db_path, collection_id, destination):
    """Portable workspace manifest with references, not copied audio."""
    import json
    with closing(sqlite3.connect(db_path)) as db:
        row = db.execute("SELECT name, kind FROM collections WHERE id=?", (collection_id,)).fetchone()
        if not row or row[1] != 'project':
            raise ValueError('Select a project workspace.')
    data = {'format': 'RiffLab Workspace', 'version': 1, 'name': row[0],
            'songs': [p for (p,) in list_songs(db_path, collection_id)]}
    path = Path(destination)
    if path.suffix.lower() != '.riffproj':
        path = path.with_suffix('.riffproj')
    temp = path.with_suffix('.riffproj.tmp')
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)
    return path


def import_project(db_path, source):
    """Import a workspace; missing song paths remain references for recovery."""
    import json
    path = Path(source)
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('format') != 'RiffLab Workspace' or data.get('version') != 1:
        raise ValueError('Not a supported .riffproj workspace.')
    songs = data.get('songs')
    if not isinstance(songs, list) or any(not isinstance(p, str) for p in songs):
        raise ValueError('Invalid project song references.')
    ident = create_collection(db_path, data.get('name') or path.stem, 'project')
    with closing(sqlite3.connect(db_path)) as db, db:
        for position, song in enumerate(dict.fromkeys(songs)):
            db.execute('INSERT INTO collection_songs(collection_id, song_path, position) VALUES (?, ?, ?)',
                       (ident, song, position))
    return ident
