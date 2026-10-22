"""Conservative YouTube music metadata suggestions; never treat uploader as artist."""
import re
import unicodedata

ALIASES = {
    'thee oh sees': 'Osees', 'oh sees': 'Osees', 'osees': 'Osees',
    'the oh sees': 'Osees', 'o sees': 'Osees'
}
NOISE = re.compile(r'(?i)\b(?:official\s+(?:music\s+)?video|official\s+audio|visualizer|lyric\s+video|full\s+album|4k|hd|hq|remaster(?:ed)?|audio\s+only)\b')
VERSION = re.compile(r'(?i)\b(?:live(?:\s+at\s+[^\])}]+)?|demo|session|acoustic|alternate\s+take|cover|radio\s+edit)(?:\s+\d{4})?\b')


def clean(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip(' -–—_|')


def canonical_artist(value):
    artist = clean(value)
    return ALIASES.get(artist.casefold(), artist)


def identify(info):
    original = clean(info.get('title'))
    explicit_track = clean(info.get('track'))
    explicit_artist = clean(info.get('artist'))
    album = clean(info.get('album'))
    title = explicit_track or original
    artist = canonical_artist(explicit_artist)
    confidence = 'high' if explicit_track and explicit_artist else 'low'
    # Recognise artist - song only when the source provides no reliable artist.
    if not artist:
        match = re.match(r'^(.+?)\s+[-–—]\s+(.+)$', title)
        if match:
            candidate = clean(match.group(1))
            # Reject channel promotions and unusually long artist candidates.
            if len(candidate) <= 65 and not NOISE.search(candidate):
                artist = canonical_artist(candidate)
                title = clean(match.group(2))
                confidence = 'medium'
    version_parts = []
    for piece in re.findall(r'[\[(]([^\])]+)[\])]', title):
        if VERSION.search(piece):
            version_parts.append(clean(piece))
    title = re.sub(r'[\[(][^\])]*[\])]', lambda m: '' if NOISE.search(m.group()) or VERSION.search(m.group()) else m.group(), title)
    title = NOISE.sub('', title)
    title = clean(title)
    if not title:
        title = original
    return {
        'title': title, 'artist': artist, 'album': album,
        'version': ', '.join(dict.fromkeys(version_parts)),
        'original_title': original,
        'source_id': clean(info.get('id')),
        'source_url': clean(info.get('webpage_url') or info.get('original_url')),
        'metadata_confidence': confidence,
        'tuning': 'Unknown', 'musical_key': ''
    }


def musicbrainz_suggestion(metadata, timeout=2.5):
    """Optional online verification; never silently replace source metadata."""
    if not metadata.get('artist') or not metadata.get('title'):
        return None
    try:
        import json
        from urllib.parse import urlencode
        from urllib.request import Request, urlopen
        artist = metadata['artist'].replace('"', '')
        title = metadata['title'].replace('"', '')
        query = f'recording:"{title}" AND artist:"{artist}"'
        url = 'https://musicbrainz.org/ws/2/recording/?' + urlencode(
            {'query': query, 'fmt': 'json', 'limit': 3})
        request = Request(url, headers={'User-Agent': 'RiffLab/0.2 (metadata matching; github.com/stevieblitz/Rifflab)'})
        with urlopen(request, timeout=timeout) as response:
            entries = json.load(response).get('recordings', [])
        for item in entries:
            candidate_artist = ', '.join(
                credit.get('name', '') for credit in item.get('artist-credit', [])
                if isinstance(credit, dict))
            candidate_title = clean(item.get('title'))
            if (candidate_title.casefold() == title.casefold()
                    and canonical_artist(candidate_artist).casefold() == canonical_artist(artist).casefold()):
                return {'artist': canonical_artist(candidate_artist),
                        'title': candidate_title,
                        'score': item.get('score', 0),
                        'musicbrainz_id': item.get('id')}
    except (OSError, ValueError, TypeError, KeyError, TimeoutError):
        return None
    return None
